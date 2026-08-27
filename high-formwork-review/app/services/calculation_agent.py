"""计算校核证据追踪 Agent。

第一版不调用 LLM，不直接做公式判定；它把高价值计算规则的证据追踪标准化：
定位计算书片段、登记 Evidence ID、输出可展示的 trace，并把缺失项留给复算器或人工复核。
"""

from __future__ import annotations

import time
from typing import Any

from ..condition_evaluator import evaluate_applicability_conditions
from ..models import MinerUDocument
from .agent_guardrails import EvidenceRegistry, display_normalize, normalize_for_match
from .agent_tools import TOOL_HANDLERS

CALC_AGENT_RULE_IDS = {"2.8", "2.12", "2.19", "3.19", "3.20", "3.22", "3.25"}
CALC_AGENT_VERSION = "calculation-agent-v1"
SEARCH_WINDOW_BEFORE = 90
SEARCH_WINDOW_AFTER = 180
MAX_AGENT_EVIDENCE = 5


CALC_RULE_PROFILES: dict[str, dict[str, Any]] = {
    "2.8": {
        "keywords": ["侧压力", "F", "浇筑速度", "β1", "β2", "t0"],
        "preferred_sections": ["计算书", "荷载计算", "侧压力"],
        "missing_checks": [
            ("侧压力公式", ["0.22", "γ", "t0", "β1", "β2", "V"]),
            ("取两式较小值", ["min", "较小", "γH"]),
        ],
    },
    "2.19": {
        "keywords": ["侧压力", "F", "0.28", "γc", "t0", "β", "坍落度"],
        "preferred_sections": ["计算书", "荷载计算", "侧压力", "GB50666"],
        "missing_checks": [
            ("GB50666侧压力公式", ["0.28", "γ", "t0", "β", "V"]),
            ("适用条件", ["浇筑速度", "坍落度"]),
            ("取两式较小值或γH分支", ["较小", "γH"]),
        ],
    },
    "2.12": {
        "keywords": ["荷载组合", "1.3", "1.5", "承载力", "极限状态"],
        "preferred_sections": ["计算书", "荷载组合", "荷载计算"],
        "missing_checks": [
            ("承载能力极限状态分项系数", ["1.3", "1.5"]),
            ("永久荷载/可变荷载组合", ["G", "Q"]),
        ],
    },
    "3.19": {
        "keywords": ["地基", "承载力", "N/A", "fa", "基础"],
        "preferred_sections": ["计算书", "地基", "承载力"],
        "missing_checks": [
            ("地基承载力公式", ["N/A", "fa", "承载力"]),
            ("底面积或垫板面积", ["A", "面积"]),
        ],
    },
    "3.20": {
        "keywords": ["抗倾覆", "MR", "MT", "γ0", "倾覆力矩"],
        "preferred_sections": ["计算书", "抗倾覆", "整体稳定"],
        "missing_checks": [
            ("抗倾覆公式", ["MR", "MT", "γ0"]),
            ("倾覆/抗倾覆力矩", ["倾覆力矩", "抗倾覆力矩"]),
        ],
    },
    "3.22": {
        "keywords": ["单肢立杆荷载", "立杆荷载", "顶层步距", "标准型", "重型", "40", "65"],
        "preferred_sections": ["计算书", "构造", "盘扣", "步距"],
        "missing_checks": [
            ("盘扣架型号", ["标准型", "重型", "B型", "Z型"]),
            ("单肢立杆荷载", ["单肢立杆荷载", "立杆荷载", "Nd"]),
            ("顶层步距缩小措施", ["顶层步距缩小", "缩小0.5", "比标准步距缩小"]),
        ],
    },
    "3.25": {
        "keywords": ["抗倾覆", "Mo", "Mr", "γ0", "GB50666"],
        "preferred_sections": ["计算书", "抗倾覆", "整体稳定"],
        "missing_checks": [
            ("GB50666抗倾覆公式", ["Mo", "Mr", "γ0"]),
            ("分项系数说明", ["1.35", "1.4", "0.9"]),
        ],
    },
}


def should_run_calculation_agent(rule_id: str) -> bool:
    return str(rule_id) in CALC_AGENT_RULE_IDS


def calculation_agent_route(rule_id: str, recheck: dict[str, Any] | None) -> str:
    if recheck and recheck.get("status") in {"PASS", "ISSUE"}:
        return "deterministic_recheck"
    if should_run_calculation_agent(rule_id):
        return "agent_evidence"
    if recheck and recheck.get("status") == "UNCERTAIN":
        return "human_review"
    return "presence_check"


def trace_calculation_evidence(
    rule: dict[str, Any],
    document: MinerUDocument,
    segments: list[dict[str, Any]],
    *,
    facts: dict[str, Any] | None = None,
    condition_evaluation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """为单条计算规则追踪计算书证据，返回可并入 calculation_results 的 agent 对象。"""
    started = time.perf_counter()
    rule_id = str(rule.get("rule_id") or "")
    profile = CALC_RULE_PROFILES.get(rule_id) or _profile_from_rule(rule)
    registry = EvidenceRegistry(document_id=document.document_id)
    steps: list[dict[str, Any]] = []
    if condition_evaluation is None:
        condition_evaluation = evaluate_applicability_conditions(
            rule,
            facts=facts,
            text="\n".join(str(seg.get("text") or "") for seg in segments),
        )
    if condition_evaluation is not None:
        steps.append({
            "step": 1,
            "action": "evaluate_applicability_conditions",
            "args": {
                "condition_count": len(condition_evaluation.get("items") or []),
            },
            "status": condition_evaluation.get("overall_status"),
            "summary": _condition_summary(condition_evaluation),
        })

    evidence = _search_segments(
        segments,
        keywords=list(profile.get("keywords") or []),
        preferred_sections=list(profile.get("preferred_sections") or []),
        registry=registry,
    )
    steps.append({
        "step": len(steps) + 1,
        "action": "search_calculation_evidence",
        "args": {
            "keywords": profile.get("keywords") or [],
            "preferred_sections": profile.get("preferred_sections") or [],
        },
        "evidence_ids": [item["evidence_id"] for item in evidence],
    })
    if not evidence:
        fallback_text, fallback_ids = TOOL_HANDLERS["search_document"](
            document,
            registry,
            keywords=list(profile.get("keywords") or [])[:4],
            preferred_sections=["计算书", *(profile.get("preferred_sections") or [])],
        )
        evidence = _registry_evidence(registry, fallback_ids)
        steps.append({
            "step": len(steps) + 1,
            "action": "search_document",
            "args": {
                "keywords": list(profile.get("keywords") or [])[:4],
                "preferred_sections": ["计算书", *(profile.get("preferred_sections") or [])],
            },
            "evidence_ids": fallback_ids,
            "summary": fallback_text[:240],
        })

    missing = _missing_items(evidence, profile.get("missing_checks") or [])
    status_hint = "UNCERTAIN" if missing else "EVIDENCE_FOUND"
    reason = (
        f"计算书证据追踪找到 {len(evidence)} 条候选证据。"
        if evidence else "计算书证据追踪未找到可用候选证据。"
    )
    if missing:
        reason += " 缺少：" + "、".join(missing)
    return {
        "version": CALC_AGENT_VERSION,
        "type": "calculation_evidence_agent",
        "status_hint": status_hint,
        "reason": reason,
        "steps": steps,
        "evidence_ids": [item["evidence_id"] for item in evidence],
        "evidence": evidence,
        "found": _found_items(evidence),
        "missing": missing,
        "condition_evaluation": condition_evaluation,
        "llm_calls": 0,
        "tool_calls": 1,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "registry": registry.to_dict(),
    }


def _condition_summary(condition_evaluation: dict[str, Any]) -> str:
    parts = []
    for item in condition_evaluation.get("items") or []:
        parts.append(f"{item.get('condition')}={item.get('status')}")
    return "；".join(parts)


def _profile_from_rule(rule: dict[str, Any]) -> dict[str, Any]:
    cl = rule.get("check_logic") or {}
    keywords = cl.get("extraction_keywords") or []
    formula = cl.get("formula") or cl.get("expected_value") or ""
    return {
        "keywords": [str(item) for item in keywords[:6]],
        "preferred_sections": ["计算书", str(rule.get("rule_name") or "")],
        "missing_checks": [(str(rule.get("rule_name") or "计算公式"), [str(formula)])] if formula else [],
    }


def _search_segments(
    segments: list[dict[str, Any]],
    *,
    keywords: list[str],
    preferred_sections: list[str],
    registry: EvidenceRegistry,
) -> list[dict[str, Any]]:
    norm_keywords = [normalize_for_match(k) for k in keywords if normalize_for_match(k)]
    norm_sections = [normalize_for_match(s) for s in preferred_sections if normalize_for_match(s)]
    hits: list[tuple[float, dict[str, Any], list[str]]] = []
    for seg in segments:
        text = str(seg.get("text") or "")
        norm_text = normalize_for_match(text)
        matched = [kw for kw in norm_keywords if kw and kw in norm_text]
        if not matched:
            continue
        section_text = normalize_for_match(str(seg.get("section") or ""))
        section_bonus = 3.0 if any(term in section_text for term in norm_sections) else 0.0
        score = (
            float(seg.get("calculation_score") or 0)
            + len(set(matched)) * 4.0
            + section_bonus
            + (1.5 if seg.get("block_type") in {"table", "formula", "equation"} else 0.0)
        )
        hits.append((score, seg, sorted(set(matched))))
    hits.sort(key=lambda item: item[0], reverse=True)

    evidence: list[dict[str, Any]] = []
    seen_blocks: set[str] = set()
    for score, seg, matched in hits:
        block_id = seg.get("block_id")
        key = str(block_id or f"page-{seg.get('physical_page')}")
        if key in seen_blocks:
            continue
        seen_blocks.add(key)
        quote = _best_window(str(seg.get("text") or ""), matched)
        evidence_id = registry.register(
            page=int(seg.get("physical_page") or 0),
            text=quote,
            source_tool="calculation_agent",
            block_id=str(block_id) if block_id else None,
            block_type=str(seg.get("block_type") or "text"),
        )
        evidence.append({
            "evidence_id": evidence_id,
            "page": seg.get("physical_page"),
            "block_id": block_id,
            "block_type": seg.get("block_type"),
            "quote": quote,
            "score": round(score, 2),
            "matched_keywords": matched,
            "in_calculation_section": bool(seg.get("in_calculation_section")),
        })
        if len(evidence) >= MAX_AGENT_EVIDENCE:
            break
    return evidence


def _registry_evidence(
    registry: EvidenceRegistry,
    evidence_ids: list[str],
) -> list[dict[str, Any]]:
    evidence = []
    for obj in registry.resolve(evidence_ids)[0][:MAX_AGENT_EVIDENCE]:
        evidence.append({
            "evidence_id": obj.evidence_id,
            "page": obj.page,
            "block_id": obj.block_id,
            "block_type": obj.block_type,
            "quote": obj.text,
            "score": 0.0,
            "matched_keywords": [],
            "in_calculation_section": False,
        })
    return evidence


def _best_window(text: str, matched_keywords: list[str]) -> str:
    norm_text = normalize_for_match(text)
    idx = -1
    for keyword in matched_keywords:
        idx = norm_text.find(keyword)
        if idx >= 0:
            break
    if idx < 0:
        return display_normalize(text[: SEARCH_WINDOW_BEFORE + SEARCH_WINDOW_AFTER])
    raw_idx = _approximate_raw_index(text, idx)
    start = max(0, raw_idx - SEARCH_WINDOW_BEFORE)
    end = min(len(text), raw_idx + SEARCH_WINDOW_AFTER)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{display_normalize(text[start:end])}{suffix}"


def _approximate_raw_index(text: str, normalized_index: int) -> int:
    count = 0
    for idx, char in enumerate(text):
        if char.isspace() or char == "$":
            continue
        count += len(normalize_for_match(char))
        if count >= normalized_index:
            return idx
    return 0


def _missing_items(evidence: list[dict[str, Any]], checks: list[tuple[str, list[str]]]) -> list[str]:
    joined = normalize_for_match("\n".join(str(item.get("quote") or "") for item in evidence))
    missing: list[str] = []
    for label, tokens in checks:
        normalized = [normalize_for_match(token) for token in tokens if normalize_for_match(token)]
        if normalized and not any(token in joined for token in normalized):
            missing.append(label)
    if not evidence:
        missing.append("计算书证据")
    return missing


def _found_items(evidence: list[dict[str, Any]]) -> list[str]:
    found = []
    pages = sorted({item.get("page") for item in evidence if item.get("page")})
    if pages:
        found.append("候选证据页：" + "、".join(str(page) for page in pages[:5]))
    if evidence:
        keywords = sorted({kw for item in evidence for kw in item.get("matched_keywords", [])})
        if keywords:
            found.append("命中关键词：" + "、".join(keywords[:8]))
    return found
