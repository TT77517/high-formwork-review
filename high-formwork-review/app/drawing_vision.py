"""Task 5C：真实 Vision Provider Adapter（图文 Agent 视觉 Tool 实现）。

职责单一：
- 从 ``MinerUPage`` 解析出真实图纸图片路径
- 读取图片 → base64 data URL
- 拼结构化抽取 prompt
- 复用项目已有 ``LLMChatClient``（OpenAI 兼容）调一次真实视觉模型
- 将模型返回归一为 Task 5B vision contract（6 字段 dict）

边界：
- 不实现 Agent Policy / 状态机 / Evidence 构造（由 ``drawing_agent`` 负责）
- 不做规范判断 / 整改建议 / CoT
- 不接 Pipeline / web / main
- 默认不修改 ``drawing_agent.py``

依赖方向：``drawing_agent`` → 通过 ``vision_tool`` callable 注入本模块 → 复用
``drawing_review.resolve_drawing_image_path`` 与 ``services.llm_chat_client``。
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

from .dify_config import _load_project_env
from .drawing_review import resolve_drawing_image_path


DEFAULT_VLM_MODEL = "qwen-vl-plus"
DEFAULT_VLM_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_VLM_TIMEOUT_SECONDS = 90.0

# 最小 MIME 映射（按文件后缀，避免引入 MIME 检测依赖）
_MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}

# Vision Contract 6 字段（Task 5B 锁定）
_CONTRACT_KEYS = ("found", "value", "unit", "evidence_text", "confidence", "scope")


# ---------------------------------------------------------------------------
# 公共入口：注入 Agent
# ---------------------------------------------------------------------------


def inspect_drawing_page(page, task, *, client=None, job_dir=None) -> dict:
    """vision_tool 注入实现：识别当前候选页的图纸目标参数。

    返回 6 字段 vision contract：
        {found, value, unit, evidence_text, confidence, scope}
    Agent 在 Task 5B 已定义好的下游逻辑据此构造 ``Evidence(source_type="vlm")``。

    行为：
    - 图片不存在或不可读 → found=False，其他字段全 None/空
    - Provider 抛出非 LLMChatError → 允许向上抛（Task 5B 第三十三节）
    - Provider 返回非 dict / 解析失败 → 安全降级 found=False
    - 任何 Provider 额外字段 → 严格丢弃，只保留 6 字段
    """
    image_path = resolve_drawing_image_path(page, job_dir=job_dir)
    if image_path is None or not image_path.is_file():
        return _empty_contract()

    image_data_url = _encode_image_as_data_url(image_path)
    if image_data_url is None:
        return _empty_contract()

    client = client or _build_default_client()
    raw_content = _call_vision(client, task, image_data_url)
    return _parse_vision_response(raw_content)


# ---------------------------------------------------------------------------
# 内部 helper
# ---------------------------------------------------------------------------


def _build_default_client() -> Any:
    """按项目现有 LLM Agent 凭据 + 视觉模型名构造 LLMChatClient（单模型，不轮转）。"""
    from .services.llm_chat_client import LLMChatClient

    _load_project_env()
    api_key = os.getenv("LLM_AGENT_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("LLM_AGENT_API_KEY 未配置，无法调用真实视觉模型")
    base_url = (
        os.getenv("LLM_AGENT_BASE_URL", "").strip() or DEFAULT_VLM_BASE_URL
    ).rstrip("/")
    model = os.getenv("VLM_MODEL", "").strip() or DEFAULT_VLM_MODEL
    return LLMChatClient(
        base_url=base_url,
        api_key=api_key,
        models=[model],
        timeout_seconds=DEFAULT_VLM_TIMEOUT_SECONDS,
    )


def _encode_image_as_data_url(path: Path) -> str | None:
    """读取图片 → data URL。返回 None 表示编码失败（格式不支持/文件不可读）。"""
    mime = _MIME_BY_EXT.get(path.suffix.lower())
    if mime is None:
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return None
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _call_vision(client: Any, task: Any, image_data_url: str) -> str:
    """构造结构化 prompt + 调 client.chat_sync，返回模型原始 content。"""
    messages = [
        {"role": "system", "content": _build_system_prompt(task)},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": _build_user_prompt(task)},
                {"type": "image_url", "image_url": {"url": image_data_url}},
            ],
        },
    ]
    response = client.chat_sync(messages, temperature=0.1)
    return response.content or ""


def _build_system_prompt(task: Any) -> str:
    """系统提示：严格约束只识别图中可见参数，禁止推断/合规判断/CoT。"""
    display_name = getattr(task, "display_name", "")
    aliases = getattr(task, "aliases", []) or []
    unit = getattr(task, "unit", "") or ""
    return (
        "你只负责识别图中明确可见的工程参数。\n"
        f"目标参数：{display_name}\n"
        f"可能表达：{' / '.join(aliases) if aliases else display_name}\n"
        f"默认单位：{unit or '（由图面决定）'}\n\n"
        "规则：\n"
        "1. 图中未明确标注该参数 → found=false，不得编造数值。\n"
        "2. 不得根据工程经验、规范条文、常见做法或上下文猜测缺失数值。\n"
        "3. 不得做规范符合性判断（不属于本任务）。\n"
        "4. 不得输出推理过程，只返回结构化 JSON。\n"
    )


def _build_user_prompt(task: Any) -> str:
    """用户提示：明确的 JSON 输出 schema。"""
    return (
        "请按以下 JSON schema 输出，不要包含其他字段或解释：\n"
        "{\n"
        '  "found": true|false,\n'
        '  "value": number | null,\n'
        '  "unit": "mm" | "m" | "kN/m" | null,\n'
        '  "evidence_text": "图中直接支撑结果的短标注原文",\n'
        '  "confidence": 0.0-1.0,\n'
        '  "scope": {}\n'
        "}"
    )


def _parse_vision_response(raw_content: str) -> dict:
    """把模型返回（自由文本）解析成 6 字段 contract。失败一律 found=False。"""
    if not raw_content:
        return _empty_contract()
    # 尝试 1：直接 JSON
    parsed = _try_parse_json(raw_content)
    if parsed is None:
        # 尝试 2：从文本中抽取首个 {...} 段
        parsed = _try_extract_first_json_object(raw_content)
    if not isinstance(parsed, dict):
        return _empty_contract()
    return _filter_to_contract(parsed)


def _try_parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


def _try_extract_first_json_object(text: str) -> Any:
    """粗略抽取首个 {...} 子串并解析（不允许 eval）。"""
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    return _try_parse_json(text[start : end + 1])


def _filter_to_contract(raw: dict) -> dict:
    """强制只保留 6 字段，其他 Provider 多余字段一律丢弃。"""
    found = bool(raw.get("found"))
    if not found:
        return _empty_contract()
    unit = raw.get("unit")
    evidence_text = raw.get("evidence_text")
    if isinstance(evidence_text, str) and len(evidence_text) > 300:
        evidence_text = evidence_text[:300]
    scope = raw.get("scope") if isinstance(raw.get("scope"), dict) else {}
    return {
        "found": True,
        "value": raw.get("value"),
        "unit": unit if isinstance(unit, str) else None,
        "evidence_text": evidence_text if isinstance(evidence_text, str) else None,
        "confidence": raw.get("confidence") if isinstance(raw.get("confidence"), (int, float)) else None,
        "scope": dict(scope),
    }


def _empty_contract() -> dict:
    return {key: None if key != "found" and key != "scope" else (False if key == "found" else {}) for key in _CONTRACT_KEYS}
