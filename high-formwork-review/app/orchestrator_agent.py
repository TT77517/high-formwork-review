"""后端总控审查 Agent。

该模块只负责编排与汇总：把既有确定性审查、语义审查、计算校核、
参数一致性和图文一致性结果包装成统一的 dispatch_plan / tool_observations，
供前端展示“计划 -> 调度 -> 追证 -> 人工确认 -> 重跑”闭环。
"""

from __future__ import annotations

import re
from typing import Any

from .models import MinerUDocument

TOOL_ORDER = [
    "completeness_review",
    "semantic_review",
    "calculation_review",
    "drawing_review",
]


def build_orchestrator_state(
    document: MinerUDocument,
    *,
    project_facts: dict[str, Any],
    project_qualification: dict[str, Any],
    completeness_summary: dict[str, Any],
    completeness_results: list[dict[str, Any]],
    rule_engine: dict[str, Any],
    semantic: dict[str, Any],
    calculation: dict[str, Any],
    substantive_review: list[dict[str, Any]],
    consistency_review: list[dict[str, Any]],
    drawing_review: list[dict[str, Any]],
    review_plan: dict[str, Any] | None = None,
    decisions: list[dict[str, Any]] | None = None,
    human_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """生成总控 Agent 的统一落盘对象。"""
    facts = (project_facts or {}).get("facts", {})
    parameter_pool = _parameter_candidate_pool(facts)
    conflicts = _parameter_conflicts(parameter_pool)
    doc_corrections = _document_parse_corrections(decisions or [])
    formula_rechecks = _formula_rechecks(calculation)

    dispatch_plan = _dispatch_plan(
        document=document,
        project_qualification=project_qualification,
        review_plan=review_plan,
        conflicts=conflicts,
        doc_corrections=doc_corrections,
    )
    observations = [
        _tool_observation(
            "completeness_review",
            "完整性审查工具",
            completeness_summary,
            completeness_results,
        ),
        _semantic_observation(rule_engine, semantic),
        _calculation_observation(calculation, consistency_review, formula_rechecks),
        _drawing_observation(drawing_review, semantic),
    ]

    return {
        "version": "1.0",
        "agent": "orchestrator_agent",
        "flow": ["plan", "dispatch", "evidence_chase", "human_confirmation", "rerun"],
        "dispatch_plan": dispatch_plan,
        "tool_observations": observations,
        "parameter_candidate_pool": parameter_pool,
        "parameter_conflicts": conflicts,
        "human_confirmation": {
            "required": bool(conflicts or doc_corrections or project_qualification.get("requires_human_review")),
            "items": [
                *_conflict_confirmation_items(conflicts),
                *_document_confirmation_items(doc_corrections),
            ],
        },
        "rerun_context": {
            "human_overrides": (human_overrides or {}).get("overrides", {}),
            "document_parse_corrections": doc_corrections,
            "document_corrections_participate": bool(doc_corrections),
        },
        "formula_recalculations": formula_rechecks,
        "notice": "总控 Agent 只做审查调度与证据组织，不输出最终合格/不合格结论。",
    }


def _dispatch_plan(
    *,
    document: MinerUDocument,
    project_qualification: dict[str, Any],
    review_plan: dict[str, Any] | None,
    conflicts: list[dict[str, Any]],
    doc_corrections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    focus = (review_plan or {}).get("focus_areas") or []
    agent_targets = (review_plan or {}).get("agent_targets") or []
    return [
        {
            "step": 1,
            "stage": "plan",
            "name": "制定审查计划",
            "status": "completed" if review_plan else "local_fallback",
            "summary": f"识别 {document.physical_page_count} 页文档，审查范围：{project_qualification.get('support_system_label') or '待确认'}",
            "focus_areas": focus,
        },
        {
            "step": 2,
            "stage": "dispatch",
            "name": "调度四类审查工具",
            "status": "completed",
            "tools": list(TOOL_ORDER),
        },
        {
            "step": 3,
            "stage": "evidence_chase",
            "name": "证据追证",
            "status": "completed" if agent_targets else "not_required",
            "agent_targets": agent_targets,
        },
        {
            "step": 4,
            "stage": "human_confirmation",
            "name": "人工确认",
            "status": "pending" if conflicts or doc_corrections else "not_required",
            "pending_count": len(conflicts) + len(doc_corrections),
        },
        {
            "step": 5,
            "stage": "rerun",
            "name": "确认后重跑",
            "status": "available" if conflicts or doc_corrections else "not_required",
            "inputs": ["support_system", "numeric_parameters", "document_parse_corrections"],
        },
    ]


def _tool_observation(
    tool_id: str,
    tool_name: str,
    summary: dict[str, Any],
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "tool_id": tool_id,
        "tool_name": tool_name,
        "status": "completed",
        "input": {"rule_count": summary.get("total_rules", len(results))},
        "output": {
            "pass": summary.get("pass_count", 0),
            "missing": summary.get("missing_count", 0),
            "uncertain": summary.get("uncertain_count", 0),
        },
        "requires_human_review": sum(1 for item in results if item.get("requires_human_review")),
    }


def _semantic_observation(rule_engine: dict[str, Any], semantic: dict[str, Any]) -> dict[str, Any]:
    return {
        "tool_id": "semantic_review",
        "tool_name": "规范审查 Agent",
        "status": "completed",
        "input": {
            "deterministic_rules": rule_engine.get("total_rules", 0),
            "semantic_rules": semantic.get("total_rules", 0),
        },
        "output": {
            "compliant": rule_engine.get("compliant", 0) + semantic.get("compliant", 0),
            "violated": rule_engine.get("violated", 0) + semantic.get("violated", 0),
            "uncertain": rule_engine.get("uncertain", 0) + semantic.get("uncertain", 0),
            "pending_confirmation": rule_engine.get("pending_confirmation", 0)
            + semantic.get("pending_confirmation", 0),
        },
        "dispatch": {
            "mode": semantic.get("mode"),
            "route_stats": semantic.get("route_stats", {}),
            "route_decisions": semantic.get("route_decisions", []),
        },
        "evidence_chase": {
            "agent_trace_count": sum(
                1 for item in semantic.get("results", []) if isinstance(item.get("agent"), dict)
            ),
            "warnings": semantic.get("warnings", []),
        },
    }


def _calculation_observation(
    calculation: dict[str, Any],
    consistency_review: list[dict[str, Any]],
    formula_rechecks: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "tool_id": "calculation_review",
        "tool_name": "计算校核工具",
        "status": "completed",
        "input": {
            "formula_rules": calculation.get("total_rules", 0),
            "parameter_pairs": len(consistency_review),
        },
        "output": {
            "compliant": calculation.get("compliant", 0),
            "violated": calculation.get("violated", 0)
            + sum(1 for item in consistency_review if item.get("status") == "ISSUE"),
            "uncertain": calculation.get("uncertain", 0)
            + sum(1 for item in consistency_review if item.get("status") == "REVIEW"),
            "formula_recalculated": len(formula_rechecks),
        },
        "formula_recalculations": formula_rechecks,
    }


def _drawing_observation(
    drawing_review: list[dict[str, Any]],
    semantic: dict[str, Any],
) -> dict[str, Any]:
    trace_count = sum(1 for item in semantic.get("results", []) if item.get("route") == "AGENT_REQUIRED")
    return {
        "tool_id": "drawing_review",
        "tool_name": "图文一致性工具",
        "status": "completed",
        "input": {"comparison_items": len(drawing_review)},
        "output": {
            "pass": sum(1 for item in drawing_review if item.get("status") == "PASS"),
            "issue": sum(1 for item in drawing_review if item.get("status") == "ISSUE"),
            "review": sum(1 for item in drawing_review if item.get("requires_human_review")),
        },
        "evidence_chase": {
            "semantic_agent_trace_available": trace_count > 0,
            "linked_agent_trace_count": trace_count,
        },
    }


def _parameter_candidate_pool(facts: dict[str, Any]) -> list[dict[str, Any]]:
    pool = []
    for key, fact in (facts or {}).items():
        if not isinstance(fact, dict):
            continue
        candidates = []
        for index, item in enumerate(fact.get("candidates") or [], start=1):
            if not isinstance(item, dict):
                continue
            ev = item.get("evidence") or {}
            candidates.append({
                "candidate_id": f"{key}#{index}",
                "value": item.get("value"),
                "unit": item.get("unit"),
                "raw_value": item.get("raw_value"),
                "confidence": item.get("confidence"),
                "source_role": item.get("source_role"),
                "page": ev.get("physical_page"),
                "block_id": ev.get("block_id"),
                "quote": ev.get("text"),
            })
        pool.append({
            "parameter": key,
            "status": fact.get("status"),
            "selected_value": fact.get("value"),
            "unit": fact.get("unit"),
            "has_conflict": bool(fact.get("has_conflict")),
            "requires_human_review": bool(fact.get("requires_human_review")),
            "candidates": candidates,
        })
    return pool


def _parameter_conflicts(pool: list[dict[str, Any]]) -> list[dict[str, Any]]:
    conflicts = []
    for item in pool:
        values = {
            str(c.get("value"))
            for c in item.get("candidates", [])
            if c.get("value") is not None
        }
        if item.get("has_conflict") or item.get("status") == "conflict" or len(values) >= 2:
            conflicts.append({
                "parameter": item["parameter"],
                "reason": "参数候选值冲突，需人工确认后重跑",
                "candidate_count": len(item.get("candidates", [])),
                "values": sorted(values),
            })
    return conflicts


def _document_parse_corrections(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    corrections = []
    for decision in decisions:
        if decision.get("source") != "document_parse":
            continue
        if decision.get("human_decision") not in {"need_supplement", "confirmed", "unable_to_verify"}:
            continue
        note = str(decision.get("note") or "").strip()
        if not note:
            continue
        corrections.append({
            "item_key": decision.get("item_key"),
            "decision": decision.get("human_decision"),
            "note": note,
            "decided_at": decision.get("decided_at"),
        })
    return corrections


def _conflict_confirmation_items(conflicts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "parameter_conflict",
            "parameter": conflict["parameter"],
            "reason": conflict["reason"],
            "values": conflict["values"],
        }
        for conflict in conflicts
    ]


def _document_confirmation_items(corrections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "document_parse_correction",
            "item_key": item["item_key"],
            "reason": "文档解析详情页已有人工修正记录，将作为重跑上下文",
        }
        for item in corrections
    ]


def _formula_rechecks(calculation: dict[str, Any]) -> list[dict[str, Any]]:
    checks = []
    for result in calculation.get("results", []):
        if result.get("status") not in {"COMPLIANT", "VIOLATED", "UNCERTAIN"}:
            continue
        for evidence in result.get("evidence", []):
            quote = str(evidence.get("quote") or "")
            parsed = _parse_numeric_comparison(quote)
            if not parsed:
                continue
            left, operator, right = parsed
            passed = left <= right if operator in {"<=", "≤"} else left >= right
            checks.append({
                "rule_id": result.get("rule_id"),
                "rule_name": result.get("rule_name"),
                "page": evidence.get("page"),
                "quote": quote[:240],
                "left_value": left,
                "operator": operator,
                "right_value": right,
                "recalculated_status": "PASS" if passed else "ISSUE",
            })
            if len(checks) >= 5:
                return checks
    return checks


def _parse_numeric_comparison(text: str) -> tuple[float, str, float] | None:
    match = re.search(
        r"(-?\d+(?:\.\d+)?)\s*(≤|<=|≥|>=)\s*(-?\d+(?:\.\d+)?)",
        text.replace(" ", ""),
    )
    if not match:
        return None
    return float(match.group(1)), match.group(2), float(match.group(3))
