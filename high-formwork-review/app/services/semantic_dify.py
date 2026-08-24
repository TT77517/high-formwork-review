"""规范语义审查 —— Dify Workflow 集成。

架构（详见 docs/semantic_agent_design.md）：
- 适用性门禁（本地）：PENDING_CONFIRMATION / NOT_APPLICABLE 由本地判定，不消耗 LLM
- 证据提取器（本地）：复用 build_semantic_evidence 召回相关方案文本
- LLM 判定（Dify）：分批调用语义审查 Workflow，输出结构化 JSON
- 结果校验（本地）：rule_id 集合、状态枚举、证据引用一致性校验
- 降级：单批失败时该批回退本地关键词模式，任务不中断
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from ..dify_cache import CACHE_ROOT
from ..dify_config import resolve_semantic_api_key
from ..models import MinerUDocument
from ..rule_engine import system_applicability_status
from ..semantic_engine import (
    SEMANTIC_EVIDENCE_LIMIT,
    _build_sem_result,
    _evaluate_semantic_local,
    _find_relevant_sections,
    _normalize_text,
    build_semantic_evidence,
    load_semantic_rules,
)
from .dify_client import (
    DifyClient,
    DifyError,
    extract_review_result,
)

SEMANTIC_BATCH_SIZE = 8
SEMANTIC_DIFY_USER = "semantic-review-agent"
ALLOWED_LLM_STATUSES = {"COMPLIANT", "VIOLATED", "UNCERTAIN"}
SEMANTIC_PROMPT_VERSION = "sem-v1"
SEMANTIC_CACHE_NAMESPACE = "semantic"


def build_semantic_batches(
    rules: list[dict[str, Any]],
    document: MinerUDocument,
    *,
    batch_size: int = SEMANTIC_BATCH_SIZE,
) -> list[dict[str, Any]]:
    """本地证据提取 + 分批。每批携带规则定义与该规则的证据文本。"""
    units: list[dict[str, Any]] = []
    for rule in rules:
        code_ref = rule.get("code_ref") or {}
        units.append(
            {
                "rule_id": str(rule.get("rule_id", "")),
                "rule_name": rule.get("rule_name", ""),
                "check_content": rule.get("check_content", ""),
                "semantic_judgment": rule.get("check_logic", {}).get(
                    "semantic_judgment", ""
                ),
                "standard": code_ref.get("standard", ""),
                "original_text": code_ref.get("original_text", ""),
                "severity": rule.get("severity", ""),
                "evidence_text": build_semantic_evidence(document, rule)[
                    :SEMANTIC_EVIDENCE_LIMIT
                ],
                "evidence_blocks": _collect_rule_evidence_blocks(document, rule),
            }
        )
    batch_count = math.ceil(len(units) / batch_size) if units else 0
    batches: list[dict[str, Any]] = []
    for start in range(0, len(units), batch_size):
        group = units[start : start + batch_size]
        batches.append(
            {
                "batch_index": len(batches) + 1,
                "batch_count": batch_count,
                "rule_ids": [unit["rule_id"] for unit in group],
                "evidence_blocks": {
                    unit["rule_id"]: unit["evidence_blocks"] for unit in group
                },
                "inputs": {
                    "rules_json": json.dumps(
                        [
                            {k: v for k, v in unit.items() if k != "evidence_text"}
                            for unit in group
                        ],
                        ensure_ascii=False,
                    ),
                    "evidence_json": json.dumps(
                        [
                            {
                                "rule_id": unit["rule_id"],
                                "evidence_text": unit["evidence_text"],
                            }
                            for unit in group
                        ],
                        ensure_ascii=False,
                    ),
                    "expected_rule_count": len(group),
                },
            }
        )
    return batches


def run_semantic_review_dify(
    document: MinerUDocument,
    project_facts: dict[str, Any] | None = None,
    *,
    client: DifyClient | None = None,
    batch_size: int = SEMANTIC_BATCH_SIZE,
    cache_enabled: bool = True,
) -> dict[str, Any]:
    """执行语义审查：适用性门禁本地判定，其余规则分批送 Dify Workflow。"""
    rules = load_semantic_rules()
    facts = (project_facts or {}).get("facts", {})
    system_value = facts.get("support_system", {}).get("value", "unknown")

    results: list[dict[str, Any]] = []
    pending_rules: list[dict[str, Any]] = []
    for rule in rules:
        applicability = system_applicability_status(
            rule.get("applicable_types", ["universal"]), system_value
        )
        if applicability == "PENDING_CONFIRMATION":
            results.append(
                _build_sem_result(
                    rule,
                    "PENDING_CONFIRMATION",
                    "支撑体系未识别，该规则仅适用于特定支撑体系，待人工确认后重跑",
                    [],
                    "",
                )
            )
        elif applicability == "NOT_APPLICABLE":
            results.append(
                _build_sem_result(rule, "NOT_APPLICABLE", "支架类型不适用", [], "")
            )
        else:
            pending_rules.append(rule)

    warnings: list[dict[str, Any]] = []
    if pending_rules:
        batches = build_semantic_batches(
            pending_rules, document, batch_size=batch_size
        )
        rules_by_id = {str(r.get("rule_id", "")): r for r in pending_rules}
        dify_client = client or _build_client()
        for batch in batches:
            batch_rules = [rules_by_id[rid] for rid in batch["rule_ids"]]
            try:
                llm_items = _run_batch(
                    batch, dify_client, cache_enabled=cache_enabled
                )
                results.extend(
                    _map_llm_item(
                        item, rules_by_id, batch.get("evidence_blocks")
                    )
                    for item in llm_items
                )
            except DifyError as exc:
                warnings.append(
                    {
                        "code": "SEMANTIC_DIFY_BATCH_FALLBACK",
                        "batch_index": batch["batch_index"],
                        "rule_ids": batch["rule_ids"],
                        "message": f"Dify 语义审查批次失败，已降级为本地关键词模式：{exc}",
                    }
                )
                results.extend(
                    _local_fallback_result(rule, document, system_value)
                    for rule in batch_rules
                )

    order = {str(rule.get("rule_id", "")): i for i, rule in enumerate(rules)}
    results.sort(key=lambda r: order.get(str(r.get("rule_id", "")), len(rules)))

    return {
        "version": "4.0.0",
        "engine_type": "semantic",
        "mode": "dify_llm_semantic",
        "total_rules": len(rules),
        "compliant": sum(1 for r in results if r["status"] == "COMPLIANT"),
        "violated": sum(1 for r in results if r["status"] == "VIOLATED"),
        "uncertain": sum(1 for r in results if r["status"] == "UNCERTAIN"),
        "not_applicable": sum(
            1 for r in results if r["status"] == "NOT_APPLICABLE"
        ),
        "pending_confirmation": sum(
            1 for r in results if r["status"] == "PENDING_CONFIRMATION"
        ),
        "results": results,
        "warnings": warnings,
    }


def run_semantic_review_dify_safe(
    document: MinerUDocument,
    project_facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """安全执行：Dify 路径整体不可用时（缺配置等）回退本地引擎。"""
    from ..semantic_engine import run_semantic_engine_local

    try:
        return run_semantic_review_dify(document, project_facts)
    except DifyError:
        local = run_semantic_engine_local(document, project_facts)
        local.setdefault("warnings", []).append(
            {
                "code": "SEMANTIC_DIFY_UNAVAILABLE",
                "message": "Dify 语义审查不可用（配置缺失或连接失败），已整体降级为本地关键词模式",
            }
        )
        return local


def run_semantic_stage(
    document: MinerUDocument,
    project_facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """语义审查统一入口：按 SEMANTIC_REVIEW_MODE 选择 agent / Dify LLM / 本地模式。"""
    from ..dify_config import resolve_semantic_review_mode
    from ..semantic_engine import run_semantic_engine_safe

    try:
        mode = resolve_semantic_review_mode()
    except ValueError:
        mode = "local"
    if mode == "agent":
        # 降级链：agent -> Dify 批式 -> 本地关键词（V3.1 §1）
        try:
            from .semantic_agent import run_semantic_review_agent

            return run_semantic_review_agent(document, project_facts)
        except Exception as exc:  # noqa: BLE001 - agent 通道任何失败都降级
            result = run_semantic_review_dify_safe(document, project_facts)
            result.setdefault("warnings", []).append(
                {
                    "code": "AGENT_MODE_FALLBACK",
                    "message": f"Agent 语义审查不可用（{exc}），已降级为 Dify 批式/本地模式",
                }
            )
            return result
    if mode == "dify":
        return run_semantic_review_dify_safe(document, project_facts)
    return run_semantic_engine_safe(document, project_facts)


def _build_client() -> DifyClient:
    api_key = resolve_semantic_api_key()
    if not api_key:
        raise DifyError("缺少 DIFY_SEMANTIC_API_KEY / DIFY_API_KEY")
    base = DifyClient.from_env()
    return DifyClient(
        base_url=base.base_url,
        api_key=api_key,
        timeout_seconds=base.timeout_seconds,
        max_retries=base.max_retries,
        retry_backoff_seconds=base.retry_backoff_seconds,
    )


def _run_batch(
    batch: dict[str, Any],
    client: DifyClient,
    *,
    cache_enabled: bool,
) -> list[dict[str, Any]]:
    """单批调用：先查缓存，未命中则调用 Workflow 并校验、回写缓存。"""
    cache_path = _batch_cache_path(batch)
    if cache_enabled and cache_path.is_file():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(cached, list):
                return cached
        except (OSError, json.JSONDecodeError):
            pass

    import asyncio

    inputs = dict(batch["inputs"])
    inputs["task_id"] = f"semantic-batch-{batch['batch_index']}-{_batch_digest(batch)[:8]}"
    raw_response = asyncio.run(
        client.run_workflow(inputs, user=SEMANTIC_DIFY_USER)
    )
    parsed = extract_review_result(raw_response)
    items = _validate_semantic_items(parsed, batch["rule_ids"])
    if cache_enabled:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(
                json.dumps(items, ensure_ascii=False), encoding="utf-8"
            )
        except OSError:
            pass
    return items


def _validate_semantic_items(
    parsed: Any, expected_rule_ids: list[str]
) -> list[dict[str, Any]]:
    """校验 LLM 返回：结构与 rule_id 集合一致、状态枚举合法。"""
    if isinstance(parsed, dict) and isinstance(parsed.get("results"), list):
        items = parsed["results"]
    elif isinstance(parsed, list):
        items = parsed
    elif isinstance(parsed, dict) and parsed.get("rule_id"):
        items = [parsed]
    else:
        raise DifyError("Dify 语义审查结果缺少规则结果列表")
    if not all(isinstance(item, dict) for item in items):
        raise DifyError("Dify 语义审查结果列表包含非对象元素")
    actual_ids = [str(item.get("rule_id", "")).strip() for item in items]
    if len(actual_ids) != len(set(actual_ids)):
        raise DifyError("Dify 语义审查结果包含重复 rule_id")
    expected = {str(rid).strip() for rid in expected_rule_ids}
    if set(actual_ids) != expected:
        raise DifyError("Dify 语义审查返回的 rule_id 集合与请求批次不一致")
    for item in items:
        status = str(item.get("status", "")).upper()
        if status not in ALLOWED_LLM_STATUSES:
            raise DifyError(
                f"Dify 语义审查规则 {item.get('rule_id')} 返回了无效状态：{status}"
            )
    return items


def _batch_digest(batch: dict[str, Any]) -> str:
    payload = json.dumps(
        [
            batch["inputs"]["rules_json"],
            batch["inputs"]["evidence_json"],
            SEMANTIC_PROMPT_VERSION,
        ],
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _batch_cache_path(batch: dict[str, Any]) -> Path:
    return (
        Path(CACHE_ROOT)
        / SEMANTIC_CACHE_NAMESPACE
        / f"{_batch_digest(batch)}.json"
    )


def _collect_rule_evidence_blocks(
    document: MinerUDocument, rule: dict[str, Any]
) -> list[dict[str, Any]]:
    """收集该规则证据召回命中的 block 定位（block_id/页码/文本），供 LLM 引用回填。"""
    keywords = rule.get("check_logic", {}).get("extraction_keywords", [])
    try:
        sections = _find_relevant_sections(document, keywords or None)
    except Exception:
        return []
    blocks: list[dict[str, Any]] = []
    for sec in sections:
        if not sec.get("matched"):
            continue
        for block in sec.get("blocks", [])[:5]:
            blocks.append(
                {
                    "block_id": block.get("block_id"),
                    "block_type": block.get("block_type"),
                    "physical_page": block.get("physical_page"),
                    "text": (block.get("text") or "")[:300],
                }
            )
        if not sec.get("blocks"):
            blocks.append(
                {
                    "block_id": None,
                    "block_type": "section",
                    "physical_page": sec.get("page"),
                    "text": (sec.get("text") or "")[:300],
                }
            )
    return blocks[:10]


def _locate_llm_quote(
    quote: str, blocks: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """把 LLM 返回的证据引用定位到具体 block（页码/block_id）。

    LLM 引用可能不逐字（省略/改写），按最长公共片段匹配：
    取引用中的 6~12 字滑窗，在 block 文本中找命中，取命中窗口最长者。
    """
    if not quote:
        return None
    norm_quote = _normalize_text(quote)
    if not norm_quote:
        return None
    best = None
    best_len = 0
    for block in blocks:
        text = block.get("text") or ""
        norm_text = _normalize_text(text)
        if not norm_text:
            continue
        # 整段引用直接命中
        if norm_quote in norm_text:
            return dict(block)
        # 滑窗找最长命中片段
        for size in range(min(len(norm_quote), 24), 5, -1):
            for start in range(0, len(norm_quote) - size + 1):
                if norm_quote[start : start + size] in norm_text:
                    if size > best_len:
                        best = dict(block)
                        best_len = size
                    break
            if best is not None and best_len == size:
                break
    return best if best_len >= 6 else None


def _map_llm_item(
    item: dict[str, Any],
    rules_by_id: dict[str, dict[str, Any]],
    evidence_blocks: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    rule = rules_by_id.get(str(item.get("rule_id", "")), {})
    status = str(item.get("status", "")).upper()
    quote = str(item.get("evidence_quote") or "").strip()
    evidence: list[dict[str, Any]] = []
    if quote:
        entry: dict[str, Any] = {"quote": quote[:500], "source": "llm"}
        blocks = (evidence_blocks or {}).get(str(item.get("rule_id", "")), [])
        located = _locate_llm_quote(quote, blocks)
        if located:
            entry["page"] = located.get("physical_page")
            entry["block_id"] = located.get("block_id")
            entry["block_type"] = located.get("block_type")
        evidence.append(entry)
    code_ref = rule.get("code_ref") or {}
    from ..rule_engine import MODULE_NAMES

    return {
        "rule_id": str(item.get("rule_id", "")),
        "rule_name": rule.get("rule_name", ""),
        "module": rule.get("module", ""),
        "module_name": MODULE_NAMES.get(rule.get("module", ""), ""),
        "check_type": "semantic",
        "severity": rule.get("severity", ""),
        "risk_level": rule.get("risk_level", ""),
        "status": status,
        "reason": str(item.get("reason") or ""),
        "code_ref": {
            "standard": code_ref.get("standard", ""),
            "original_text": code_ref.get("original_text", ""),
        },
        "remedy_suggestion": rule.get("remedy_suggestion", ""),
        "typical_violation": rule.get("typical_violation", ""),
        "manual_review": status != "COMPLIANT",
        "evidence": evidence,
        "semantic_judgment": rule.get("check_logic", {}).get(
            "semantic_judgment", ""
        ),
        "raw_evidence_snippet": "",
        "confidence": item.get("confidence"),
        "review_engine": "dify_llm",
    }


def _local_fallback_result(
    rule: dict[str, Any],
    document: MinerUDocument,
    system_value: str,
) -> dict[str, Any]:
    result = _evaluate_semantic_local(rule, document, system_value)
    result["review_engine"] = "local_fallback"
    result["manual_review"] = True
    return result
