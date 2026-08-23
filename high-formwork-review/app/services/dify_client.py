"""Dify Workflow API 异步客户端与结果解析。"""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv


def _load_project_env() -> None:
    """加载项目根 .env，与启动目录无关（override=False 不覆盖已显式导出的变量）。"""
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env", override=False)


RETRYABLE_GATEWAY_STATUSES = {502, 503, 504}


class DifyError(RuntimeError):
    """Dify 配置、请求或响应错误。"""

    def __init__(
        self,
        message: str,
        *,
        raw_response: dict[str, Any] | None = None,
        technical_details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.raw_response = raw_response
        self.technical_details = technical_details or {}


class DifyClient:
    """以 blocking 模式调用 Dify Workflow。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout_seconds: float = 180.0,
        max_retries: int = 2,
        retry_backoff_seconds: float = 1.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not base_url.strip():
            raise DifyError("缺少环境变量 DIFY_BASE_URL")
        if not api_key.strip():
            raise DifyError("缺少环境变量 DIFY_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        if max_retries < 0:
            raise DifyError("DIFY_MAX_RETRIES 不能小于 0")
        if retry_backoff_seconds < 0:
            raise DifyError("DIFY_RETRY_BACKOFF_SECONDS 不能小于 0")
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self._http_client = http_client

    @classmethod
    def from_env(cls) -> "DifyClient":
        _load_project_env()
        timeout_text = os.getenv("DIFY_TIMEOUT_SECONDS", "180").strip()
        try:
            timeout_seconds = float(timeout_text)
        except ValueError as exc:
            raise DifyError("DIFY_TIMEOUT_SECONDS 必须是有效数字") from exc
        if timeout_seconds <= 0:
            raise DifyError("DIFY_TIMEOUT_SECONDS 必须大于 0")
        max_retries = _env_nonnegative_int("DIFY_MAX_RETRIES", 2)
        retry_backoff_seconds = _env_nonnegative_float(
            "DIFY_RETRY_BACKOFF_SECONDS", 1.0
        )
        return cls(
            base_url=os.getenv("DIFY_BASE_URL", ""),
            api_key=os.getenv("DIFY_API_KEY", ""),
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            retry_backoff_seconds=retry_backoff_seconds,
        )

    async def run_workflow(
        self,
        inputs: dict[str, Any],
        *,
        user: str,
    ) -> dict[str, Any]:
        request_body = {
            "inputs": inputs,
            "response_mode": "blocking",
            "user": user,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        owns_client = self._http_client is None
        client = self._http_client or httpx.AsyncClient(timeout=self.timeout_seconds)
        try:
            response = None
            for attempt in range(self.max_retries + 1):
                response = await client.post(
                    f"{self.base_url}/workflows/run",
                    headers=headers,
                    json=request_body,
                )
                if (
                    response.status_code not in RETRYABLE_GATEWAY_STATUSES
                    or attempt >= self.max_retries
                ):
                    break
                await asyncio.sleep(
                    self.retry_backoff_seconds * (2 ** attempt)
                )
            assert response is not None
            try:
                raw_response = response.json()
            except ValueError as exc:
                response_details = {
                    "http_status": response.status_code,
                    "content_type": response.headers.get("content-type"),
                    "body_preview": response.text[:500],
                }
                raise DifyError(
                    f"Dify 返回了非 JSON 响应（HTTP {response.status_code}）",
                    technical_details=response_details,
                ) from exc
            if not isinstance(raw_response, dict):
                raise DifyError(
                    "Dify 返回的 JSON 顶层不是对象",
                    raw_response={"response": raw_response},
                    technical_details={
                        "http_status": response.status_code,
                        "content_type": response.headers.get("content-type"),
                    },
                )
            if response.is_error:
                raise DifyError(
                    f"Dify Workflow 调用失败（HTTP {response.status_code}）",
                    raw_response=raw_response,
                    technical_details={
                        "http_status": response.status_code,
                        "content_type": response.headers.get("content-type"),
                    },
                )
            data = raw_response.get("data")
            if isinstance(data, dict) and data.get("status") == "failed":
                detail = str(data.get("error") or "").strip()
                message = (
                    f"Dify Workflow 执行失败：{detail}" if detail else "Dify Workflow 执行失败"
                )
                raise DifyError(
                    message,
                    raw_response=raw_response,
                )
            return raw_response
        except httpx.TimeoutException as exc:
            raise DifyError("Dify Workflow 调用超时") from exc
        except httpx.RequestError as exc:
            raise DifyError("无法连接 Dify Workflow API") from exc
        finally:
            if owns_client:
                await client.aclose()


def extract_review_result(raw_response: dict[str, Any]) -> Any:
    """提取并解析 Dify ``result_json`` 输出。"""
    data = raw_response.get("data")
    outputs = data.get("outputs") if isinstance(data, dict) else None
    if not isinstance(outputs, dict):
        raise DifyError("Dify 响应缺少 data.outputs", raw_response=raw_response)
    value = outputs.get("result_json")
    if value is None:
        value = outputs.get("result")
    if value is None:
        raise DifyError(
            "Dify 响应缺少 result_json 输出",
            raw_response=raw_response,
        )
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        raise DifyError(
            "Dify result_json 类型无效",
            raw_response=raw_response,
        )
    cleaned = _strip_json_fence(value)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise DifyError(
            "Dify result_json 不是有效 JSON",
            raw_response=raw_response,
        ) from exc


def validate_review_result(
    result: Any,
    expected_rule_ids: list[str],
    *,
    allow_unrequested: bool = False,
) -> Any:
    """校验单批返回的规则集合和三态值与请求一致。"""
    validated, _ = validate_review_result_with_warnings(
        result,
        expected_rule_ids,
        allow_unrequested=allow_unrequested,
    )
    return validated


def validate_review_result_with_warnings(
    result: Any,
    expected_rule_ids: list[str],
    *,
    allow_unrequested: bool = False,
) -> tuple[Any, list[dict[str, Any]]]:
    """Validate requested rules and ignore any extra unrequested rules when allowed."""
    items = _result_items(result)
    expected_ids = [str(value).strip() for value in expected_rule_ids]
    actual_ids = [str(item.get("rule_id", "")).strip() for item in items]
    if len(actual_ids) != len(set(actual_ids)):
        raise DifyError("Dify 返回的规则结果包含重复 rule_id")
    expected_set = set(expected_ids)
    actual_set = set(actual_ids)
    missing_ids = [rule_id for rule_id in expected_ids if rule_id not in actual_set]
    unexpected_ids = [rule_id for rule_id in actual_ids if rule_id not in expected_set]
    if missing_ids or (unexpected_ids and not allow_unrequested):
        raise DifyError(
            "Dify 返回的规则集合或 rule_id 与当前批次请求不一致"
        )
    warnings: list[dict[str, Any]] = []
    if unexpected_ids:
        warnings.append(
            {
                "code": "UNREQUESTED_RULE_IGNORED",
                "rule_ids": list(dict.fromkeys(unexpected_ids)),
                "message": "Dify 返回了未请求规则，已忽略",
            }
        )
        items = [
            item
            for item in items
            if str(item.get("rule_id", "")).strip() in expected_set
        ]
    allowed_statuses = {"PASS", "MISSING", "UNCERTAIN"}
    for item in items:
        if str(item.get("status", "")).upper() not in allowed_statuses:
            raise DifyError(
                f"Dify 规则 {item.get('rule_id')} 返回了无效状态"
            )
    if isinstance(result, list):
        return items, warnings
    if isinstance(result, dict) and isinstance(result.get("results"), list):
        filtered = dict(result)
        filtered["results"] = items
        return filtered, warnings
    return items[0] if items else result, warnings


def merge_batch_review_results(
    parsed_batches: list[dict[str, Any]],
    *,
    expected_rule_ids: list[str],
    fallback_results: list[dict[str, Any]] | None = None,
    oversized_rule_ids: set[str] | None = None,
) -> dict[str, Any]:
    """按 rule_id 汇总批次；重复只允许来自超大单规则分片。"""
    oversized = oversized_rule_ids or set()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for batch in parsed_batches:
        for result in _result_items(batch["result"]):
            rule_id = str(result.get("rule_id", "")).strip()
            if not rule_id:
                raise DifyError("Dify 审查结果缺少 rule_id")
            grouped.setdefault(rule_id, []).append(result)
    for result in fallback_results or []:
        grouped.setdefault(str(result.get("rule_id")), []).append(result)

    merged: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for rule_id in expected_rule_ids:
        items = grouped.get(rule_id, [])
        if not items:
            raise DifyError(f"Dify 审查结果缺少规则 {rule_id}")
        if len(items) == 1:
            merged.append(items[0])
            continue
        if rule_id not in oversized:
            raise DifyError(f"规则 {rule_id} 在多个正常批次中重复返回")
        merged_result = _merge_oversized_rule(rule_id, items)
        merged.append(merged_result)
        warnings.append(
            {
                "code": "OVERSIZED_RULE_MERGED",
                "rule_id": rule_id,
                "message": f"超大规则由 {len(items)} 个证据分片保守汇总",
            }
        )
    return {
        "total_rules": len(merged),
        "results": merged,
        "warnings": warnings,
    }


def _result_items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        items = value
    elif isinstance(value, dict) and isinstance(value.get("results"), list):
        items = value["results"]
    elif isinstance(value, dict) and value.get("rule_id"):
        items = [value]
    else:
        raise DifyError("Dify result_json 缺少规则结果列表")
    if not all(isinstance(item, dict) for item in items):
        raise DifyError("Dify 规则结果列表包含非对象元素")
    return items


def _merge_oversized_rule(
    rule_id: str,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    statuses = [str(item.get("status", "")).upper() for item in items]
    all_pass = bool(statuses) and all(status == "PASS" for status in statuses)
    evidence = _unique_evidence(
        evidence_item
        for item in items
        for evidence_item in item.get("evidence", [])
        if isinstance(evidence_item, dict)
    )
    first = dict(items[0])
    first["status"] = "PASS" if all_pass else "UNCERTAIN"
    first["reason"] = (
        f"超大规则 {rule_id} 的全部 {len(items)} 个证据分片均为 PASS，"
        "本地汇总为 PASS；分片结果不单独代表整条规则。"
        if all_pass
        else f"超大规则 {rule_id} 的分片结果无法一致确认完整满足，"
        "本地保守汇总为 UNCERTAIN，需人工复核。"
    )
    first["evidence"] = evidence
    first["manual_review"] = True
    first["requires_human_review"] = True
    first["part_results"] = [
        {
            "part_index": index,
            "status": item.get("status"),
        }
        for index, item in enumerate(items, start=1)
    ]
    return first


def _unique_evidence(items: Any) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in items:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True)
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _strip_json_fence(value: str) -> str:
    cleaned = value.strip()
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else cleaned


def _env_nonnegative_int(name: str, default: int) -> int:
    value = os.getenv(name, str(default)).strip()
    try:
        parsed = int(value)
    except ValueError as exc:
        raise DifyError(f"{name} 必须是非负整数") from exc
    if parsed < 0:
        raise DifyError(f"{name} 不能小于 0")
    return parsed


def _env_nonnegative_float(name: str, default: float) -> float:
    value = os.getenv(name, str(default)).strip()
    try:
        parsed = float(value)
    except ValueError as exc:
        raise DifyError(f"{name} 必须是非负数字") from exc
    if parsed < 0:
        raise DifyError(f"{name} 不能小于 0")
    return parsed
