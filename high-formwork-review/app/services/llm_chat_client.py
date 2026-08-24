"""LLM Chat 客户端：Agent 通道直连 LLM API（V3.1 Phase 2）。

与 DifyClient 并列、职责互补：
- DifyClient：批式语义审查 / 完整性复核（Dify Workflow）
- LLMChatClient：Evidence Agent 的 tool-calling 循环（OpenAI 兼容协议直连）

模型链自动轮转（Phase 0 验证的设计）：
- LLM_AGENT_MODEL 支持逗号分隔优先级链（前面的额度耗尽自动切后面的）
- 触发轮转：欠费(Arrearage)/限流(429/Throttling)/额度耗尽/模型不存在
- 切换粘性（换到能用的模型后后续调用继续用它），切换事件记录审计
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from typing import Any

import httpx

from ..dify_config import _load_project_env

DEFAULT_LLM_AGENT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_LLM_AGENT_MODEL = "qwen-plus"
DEFAULT_LLM_AGENT_TIMEOUT_SECONDS = 90.0
DEFAULT_LLM_AGENT_MAX_RETRIES = 2
DEFAULT_LLM_AGENT_RETRY_BACKOFF_SECONDS = 1.0

# 触发模型轮转的错误关键词（其余错误直接抛出）
_ROTATABLE_KEYWORDS = (
    "arrear", "quota", "throttl", "rate limit", "balance",
    "免费额度", "欠费", "限流", "not exist", "invalid model",
)


class LLMChatError(Exception):
    """LLM 聊天调用失败（含模型链全部不可用）。"""

    def __init__(self, message: str, technical_details: dict | None = None):
        super().__init__(message)
        self.technical_details = technical_details or {}


@dataclass
class ChatResponse:
    content: str
    tool_calls: list[dict[str, Any]]  # [{id, name, arguments(dict)}]
    model: str
    finish_reason: str = ""


@dataclass
class LLMChatClient:
    """OpenAI 兼容 chat/completions 客户端，带模型链自动轮转。"""

    base_url: str
    api_key: str
    models: list[str]
    timeout_seconds: float = DEFAULT_LLM_AGENT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_LLM_AGENT_MAX_RETRIES
    retry_backoff_seconds: float = DEFAULT_LLM_AGENT_RETRY_BACKOFF_SECONDS
    rotation_events: list[dict[str, Any]] = field(default_factory=list)
    _current_model: str = ""
    _http_client: httpx.AsyncClient | None = None

    def __post_init__(self) -> None:
        if not self.api_key:
            raise LLMChatError("缺少 LLM Agent API Key")
        if not self.models:
            raise LLMChatError("LLM Agent 模型链为空")
        if not self._current_model:
            self._current_model = self.models[0]

    # ------------------------------------------------------------------
    # 构造
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls, *, load_environment: bool = True) -> "LLMChatClient":
        if load_environment:
            _load_project_env()
        api_key = os.getenv("LLM_AGENT_API_KEY", "").strip()
        base_url = (
            os.getenv("LLM_AGENT_BASE_URL", "").strip()
            or DEFAULT_LLM_AGENT_BASE_URL
        )
        models = [
            m.strip()
            for m in os.getenv("LLM_AGENT_MODEL", "").split(",")
            if m.strip()
        ] or [DEFAULT_LLM_AGENT_MODEL]
        timeout = _env_float("LLM_AGENT_TIMEOUT_SECONDS", DEFAULT_LLM_AGENT_TIMEOUT_SECONDS)
        return cls(
            base_url=base_url.rstrip("/"),
            api_key=api_key,
            models=models,
            timeout_seconds=timeout,
        )

    @property
    def model_identifier(self) -> str:
        """缓存键用的模型标识（整条链）。"""
        return ",".join(self.models)

    @property
    def current_model(self) -> str:
        return self._current_model

    # ------------------------------------------------------------------
    # 调用
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.1,
    ) -> ChatResponse:
        """调用 chat/completions；当前模型额度耗尽时沿链轮转。

        网络瞬时错误在同模型上重试（指数退避）；可轮转错误（欠费/限流/
        额度/模型不存在）直接换下一个模型；其余错误抛 LLMChatError。
        """
        owns_client = self._http_client is None
        client = self._http_client or httpx.AsyncClient(timeout=self.timeout_seconds)
        try:
            order = [self._current_model] + [
                m for m in self.models if m != self._current_model
            ]
            last_error = "未知错误"
            for model in order:
                payload: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                }
                if tools:
                    payload["tools"] = tools
                response = None
                for attempt in range(self.max_retries + 1):
                    try:
                        response = await client.post(
                            f"{self.base_url}/chat/completions",
                            headers={
                                "Authorization": f"Bearer {self.api_key}",
                                "Content-Type": "application/json",
                            },
                            json=payload,
                        )
                        break
                    except httpx.HTTPError as exc:
                        last_error = f"{model}: {exc}"
                        if attempt >= self.max_retries:
                            break
                        await asyncio.sleep(
                            self.retry_backoff_seconds * (2 ** attempt)
                        )
                if response is None:
                    continue  # 网络错误重试耗尽 -> 换下一个模型（可能是网关问题）
                if response.is_error:
                    err_body = _safe_error_body(response)
                    last_error = (
                        f"{model}: HTTP {response.status_code} "
                        f"{err_body.get('code', '')} {(err_body.get('message') or '')[:120]}"
                    )
                    if _is_rotatable(response.status_code, err_body):
                        continue
                    raise LLMChatError(
                        f"LLM 调用失败（不可轮转错误）：{last_error}",
                        technical_details=err_body,
                    )
                try:
                    data = response.json()
                except ValueError as exc:
                    raise LLMChatError(
                        f"LLM 返回了非 JSON 响应（HTTP {response.status_code}）",
                        technical_details={"body_preview": response.text[:300]},
                    ) from exc
                if model != self._current_model:
                    self.rotation_events.append(
                        {"from": self._current_model, "to": model,
                         "reason": last_error[:200]}
                    )
                    self._current_model = model
                return _parse_chat_response(data, model)
            raise LLMChatError(f"模型链全部不可用：{last_error}")
        finally:
            if owns_client:
                await client.aclose()

    def chat_sync(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.1,
    ) -> ChatResponse:
        """同步封装（语义 Agent 循环是同步代码）。"""
        return asyncio.run(self.chat(messages, tools=tools, temperature=temperature))


def _parse_chat_response(data: dict[str, Any], model: str) -> ChatResponse:
    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMChatError(
            "LLM 响应缺少 choices[0].message",
            technical_details={"body_preview": json.dumps(data, ensure_ascii=False)[:300]},
        ) from exc
    tool_calls = []
    for tc in message.get("tool_calls") or []:
        try:
            arguments = json.loads(tc["function"].get("arguments") or "{}")
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            raise LLMChatError(
                f"LLM tool_call arguments 不是合法 JSON：{tc}",
            ) from exc
        tool_calls.append(
            {"id": tc.get("id", ""), "name": tc["function"]["name"],
             "arguments": arguments}
        )
    return ChatResponse(
        content=message.get("content") or "",
        tool_calls=tool_calls,
        model=model,
        finish_reason=data.get("choices", [{}])[0].get("finish_reason", ""),
    )


def _safe_error_body(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {"message": response.text[:300]}
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        return body["error"]
    return body if isinstance(body, dict) else {"message": str(body)[:300]}


def _is_rotatable(status_code: int, err_body: dict[str, Any]) -> bool:
    if status_code == 429:
        return True
    text = f"{err_body.get('code', '')} {err_body.get('message', '')}".lower()
    return any(k in text for k in _ROTATABLE_KEYWORDS)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "").strip() or default)
    except ValueError:
        return default
