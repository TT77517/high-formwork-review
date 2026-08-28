"""后端总控审查 Agent。

该模块只负责编排与汇总：把既有确定性审查、语义审查、计算校核、
参数一致性和图文一致性结果包装成统一的 dispatch_plan / tool_observations，
供前端展示“计划 -> 调度 -> 追证 -> 人工确认 -> 重跑”闭环。
"""

from __future__ import annotations

import re
from dataclasses import asdict, is_dataclass
from typing import Any, Mapping

from .calculation_dependencies import parameters_for_calculation_rule, parameters_for_formula_id
from .models import MinerUDocument
from .uncertainty_analysis import build_uncertainty_analysis

TOOL_ORDER = [
    "completeness_review",
    "semantic_review",
    "calculation_review",
    "drawing_review",
]

RERUN_PARAMETER_KEYS = {
    "support_height",
    "standard_step_height",
    "head_jack_cantilever_length",
    "head_jack_screw_exposed_length",
    "sweeper_centerline_height_above_base_plate",
    "vertical_spacing",
    "horizontal_spacing",
    "framework_height",
    "height_to_width_ratio",
    "support_span",
    "concentrated_line_load",
    "total_load",
    "panel_thickness",
    "steel_plate_thickness",
}

AGENT_DRAWING_STATUSES = (
    "CONSISTENT",
    "CONFLICT",
    "TEXT_ONLY",
    "DRAWING_ONLY",
    "UNCERTAIN",
    "NOT_FOUND",
)


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
    agent_drawing_review: Any | None = None,
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
    parameter_to_rules = _parameter_to_rules(
        parameter_pool=parameter_pool,
        rule_engine=rule_engine,
        semantic=semantic,
        calculation=calculation,
    )
    drawing_quality = _drawing_evidence_quality_summary(drawing_review)
    agent_drawing_domain = _agent_drawing_review_domain(agent_drawing_review)
    uncertainty_analysis = build_uncertainty_analysis(
        project_facts=project_facts,
        completeness_results=completeness_results,
        rule_engine=rule_engine,
        semantic=semantic,
        calculation=calculation,
    )
    semantic_confirmations = _semantic_confirmation_items(semantic)

    dispatch_plan = _dispatch_plan(
        document=document,
        project_qualification=project_qualification,
        review_plan=review_plan,
        conflicts=conflicts,
        doc_corrections=doc_corrections,
        semantic_confirmations=semantic_confirmations,
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
        _drawing_observation(drawing_review, semantic, drawing_quality, agent_drawing_domain),
    ]

    return {
        "version": "1.0",
        "agent": "orchestrator_agent",
        "flow": ["plan", "dispatch", "evidence_chase", "human_confirmation", "rerun"],
        "dispatch_plan": dispatch_plan,
        "plan_explanation": _plan_explanation(
            document=document,
            project_qualification=project_qualification,
            review_plan=review_plan,
            conflicts=conflicts,
            semantic_confirmations=semantic_confirmations,
            consistency_review=consistency_review,
            drawing_review=drawing_review,
        ),
        "tool_observations": observations,
        "parameter_candidate_pool": parameter_pool,
        "parameter_to_rules": parameter_to_rules,
        "parameter_conflicts": conflicts,
        "uncertainty_analysis": uncertainty_analysis,
        "human_confirmation": {
            "required": bool(
                conflicts
                or doc_corrections
                or semantic_confirmations
                or project_qualification.get("requires_human_review")
            ),
            "items": [
                *_conflict_confirmation_items(conflicts),
                *semantic_confirmations,
                *_document_confirmation_items(doc_corrections),
            ],
        },
        "rerun_context": {
            "human_overrides": (human_overrides or {}).get("overrides", {}),
            "document_parse_corrections": doc_corrections,
            "document_corrections_participate": bool(doc_corrections),
        },
        "formula_recalculations": formula_rechecks,
        "drawing_evidence_quality": drawing_quality,
        "agent_drawing_review": agent_drawing_domain,
        "notice": "总控 Agent 只做审查调度与证据组织，不输出最终合格/不合格结论。",
    }


def _dispatch_plan(
    *,
    document: MinerUDocument,
    project_qualification: dict[str, Any],
    review_plan: dict[str, Any] | None,
    conflicts: list[dict[str, Any]],
    doc_corrections: list[dict[str, Any]],
    semantic_confirmations: list[dict[str, Any]],
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
            "status": "pending" if conflicts or doc_corrections or semantic_confirmations else "not_required",
            "pending_count": len(conflicts) + len(doc_corrections) + len(semantic_confirmations),
        },
        {
            "step": 5,
            "stage": "rerun",
            "name": "确认后重跑",
            "status": "available" if conflicts or doc_corrections or semantic_confirmations else "not_required",
            "inputs": ["support_system", "numeric_parameters", "document_parse_corrections"],
        },
    ]


def _plan_explanation(
    *,
    document: MinerUDocument,
    project_qualification: dict[str, Any],
    review_plan: dict[str, Any] | None,
    conflicts: list[dict[str, Any]],
    semantic_confirmations: list[dict[str, Any]],
    consistency_review: list[dict[str, Any]],
    drawing_review: list[dict[str, Any]],
) -> dict[str, Any]:
    """生成面向审查员的计划解释，不暴露内部函数名。"""
    support_system = project_qualification.get("support_system_label") or "支撑体系待确认"
    risk_class = (
        project_qualification.get("risk_classification_label")
        or _risk_label(project_qualification.get("risk_classification"))
        or "风险属性待确认"
    )
    focus = (review_plan or {}).get("focus_areas") or []
    agent_targets = (review_plan or {}).get("agent_targets") or []
    consistency_review_count = sum(1 for item in consistency_review if item.get("status") == "REVIEW")
    consistency_issue_count = sum(1 for item in consistency_review if item.get("status") == "ISSUE")
    drawing_review_count = sum(1 for item in drawing_review if item.get("status") == "REVIEW")
    drawing_issue_count = sum(1 for item in drawing_review if item.get("status") == "ISSUE")
    bullets = [
        f"先按 {document.physical_page_count} 页方案识别工程特征，当前审查范围为：{support_system}，风险属性为：{risk_class}。",
        "再把规则分配给完整性、规范语义、计算校核和图文一致性四类工具，分别完成章节、条文、公式和图纸证据检查。",
    ]
    if focus:
        names = "、".join(_human_text(item.get("area"), "关键风险") for item in focus[:3])
        bullets.append(f"本轮优先审查 {names}，因为这些内容直接影响规则适用范围和后续复核顺序。")
    if agent_targets:
        bullets.append(f"对 {len(agent_targets)} 项证据不足或需要深度比对的内容安排 Agent 追证，补齐条文、方案原文和页码证据。")
    if conflicts or semantic_confirmations or consistency_issue_count or drawing_issue_count:
        bullets.append(
            "发现参数冲突、证据不足或审查结论分歧时，不直接给最终结论，转入人工确认后再重跑相关规则。"
        )
    return {
        "recognized_scope": {
            "support_system": support_system,
            "risk_classification": risk_class,
            "page_count": document.physical_page_count,
        },
        "selected_tools": [
            "完整性审查工具",
            "规范审查 Agent",
            "计算校核工具",
            "图文一致性工具",
        ],
        "focus_count": len(focus),
        "agent_target_count": len(agent_targets),
        "human_gate_count": len(conflicts) + len(semantic_confirmations) + consistency_review_count + drawing_review_count,
        "issue_count": consistency_issue_count + drawing_issue_count,
        "bullets": bullets,
    }


def _human_text(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    if not text or re.search(r"[a-zA-Z_]{3,}", text):
        return fallback
    return text[:20]


def _risk_label(value: Any) -> str:
    mapping = {
        "over_scale_dangerous": "超规模危大工程",
        "dangerous": "危大工程",
        "general": "一般工程",
        "unknown": "待确认",
    }
    return mapping.get(str(value or ""), str(value or ""))


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
    drawing_quality: dict[str, Any],
    agent_drawing_domain: dict[str, Any],
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
        "agent_domain": agent_drawing_domain,
        "evidence_chase": {
            "semantic_agent_trace_available": trace_count > 0,
            "linked_agent_trace_count": trace_count,
            "evidence_quality": drawing_quality,
        },
    }


def _agent_drawing_review_domain(payload: Any | None) -> dict[str, Any]:
    """Normalize stable Drawing Agent results without rejudging domain statuses."""
    data = _mapping_payload(payload)
    if data is None:
        return _empty_agent_drawing_domain()
    items = [_agent_drawing_item(item) for item in data.get("items", []) or []]
    source_counts = data.get("status_counts") or {}
    counts = {
        status: int(source_counts.get(status, 0) or 0)
        for status in AGENT_DRAWING_STATUSES
    }
    if not any(counts.values()) and items:
        for item in items:
            status = item.get("status")
            if status in counts:
                counts[status] += 1
    return {
        "source": "drawing_consistency_agent",
        "total_tasks": int(data.get("total_tasks") or len(items)),
        "reviewed_tasks": int(data.get("reviewed_tasks") or len(items)),
        "status_counts": counts,
        "items": items,
        "authoritative": True,
        "policy": "domain_status_authoritative_no_orchestrator_rejudge",
    }


def _empty_agent_drawing_domain() -> dict[str, Any]:
    return {
        "source": None,
        "total_tasks": 0,
        "reviewed_tasks": 0,
        "status_counts": {status: 0 for status in AGENT_DRAWING_STATUSES},
        "items": [],
        "authoritative": False,
        "policy": "legacy_drawing_review_authoritative",
    }


def _mapping_payload(payload: Any) -> Mapping[str, Any] | None:
    if payload is None:
        return None
    if is_dataclass(payload):
        payload = asdict(payload)
    return payload if isinstance(payload, Mapping) else None


def _agent_drawing_item(item: Any) -> dict[str, Any]:
    data = _mapping_payload(item) or {}
    return {
        "fact_id": data.get("fact_id"),
        "display_name": data.get("display_name"),
        "status": data.get("status"),
        "reason": data.get("reason"),
        "scope_alignment": data.get("scope_alignment"),
        "text_value": data.get("text_value"),
        "drawing_value": data.get("drawing_value"),
        "text_unit": data.get("text_unit"),
        "drawing_unit": data.get("drawing_unit"),
        "text_evidence_count": int(data.get("text_evidence_count") or 0),
        "drawing_evidence_count": int(data.get("drawing_evidence_count") or 0),
        "comparable_pair_count": int(data.get("comparable_pair_count") or 0),
        "finish_reason": data.get("finish_reason"),
        "iterations": int(data.get("iterations") or 0),
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


def _semantic_confirmation_items(semantic: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for result in semantic.get("results", []):
        if result.get("route") != "HUMAN_REQUIRED" or not result.get("manual_review"):
            continue
        items.append({
            "type": "semantic_human_required",
            "rule_id": result.get("rule_id"),
            "rule_name": result.get("rule_name"),
            "reason": result.get("reason"),
            "route": result.get("route"),
        })
    return items


def _formula_rechecks(calculation: dict[str, Any]) -> list[dict[str, Any]]:
    checks = []
    for result in calculation.get("results", []):
        if result.get("status") not in {"COMPLIANT", "VIOLATED", "UNCERTAIN"}:
            continue
        recheck = result.get("calculation_recheck")
        if isinstance(recheck, dict):
            checks.append({
                "rule_id": result.get("rule_id"),
                "rule_name": result.get("rule_name"),
                "formula_id": recheck.get("formula_id"),
                "formula_name": recheck.get("formula_name"),
                "pages": recheck.get("pages", []),
                "expression": recheck.get("expression"),
                "substituted_expression": recheck.get("substituted_expression"),
                "computed_value": recheck.get("computed_value"),
                "operator": recheck.get("operator"),
                "allowed_value": recheck.get("allowed_value"),
                "recalculated_status": recheck.get("status"),
                "warnings": recheck.get("warnings", []),
            })
            if len(checks) >= 5:
                return checks
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


def _parameter_to_rules(
    *,
    parameter_pool: list[dict[str, Any]],
    rule_engine: dict[str, Any],
    semantic: dict[str, Any],
    calculation: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    known = {item.get("parameter") for item in parameter_pool} | RERUN_PARAMETER_KEYS
    mapping: dict[str, list[dict[str, Any]]] = {str(param): [] for param in known if param}
    for source, payload in (
        ("rule_engine", rule_engine),
        ("semantic_engine", semantic),
        ("calculation_engine", calculation),
    ):
        for result in payload.get("results", []):
            params = set()
            if result.get("param_name"):
                params.add(str(result["param_name"]))
            params.update(_params_from_text(str(result.get("reason") or "")))
            recheck = result.get("calculation_recheck") or {}
            if isinstance(recheck, dict) and recheck.get("status") == "UNCERTAIN":
                params.update(_params_from_formula_id(str(recheck.get("formula_id") or "")))
            if source == "calculation_engine":
                formula_id = str(recheck.get("formula_id") or "") if isinstance(recheck, dict) else ""
                params.update(parameters_for_calculation_rule(str(result.get("rule_id") or ""), formula_id or None))
            for param in params:
                if param in mapping:
                    mapping[param].append({
                        "source": source,
                        "rule_id": result.get("rule_id"),
                        "rule_name": result.get("rule_name") or result.get("name") or result.get("title"),
                        "status": result.get("status"),
                    })
    return {
        param: _dedupe_rule_refs(items)
        for param, items in mapping.items()
        if items
    }


def _params_from_text(text: str) -> set[str]:
    params = set(re.findall(r"\b[a-zA-Z][a-zA-Z0-9_]{2,}\b", text))
    return {
        param
        for param in params
        if param in RERUN_PARAMETER_KEYS
    }


def _params_from_formula_id(formula_id: str) -> set[str]:
    explicit = parameters_for_formula_id(formula_id)
    if explicit:
        return explicit
    if formula_id == "slenderness":
        return {"standard_step_height", "support_height"}
    if formula_id == "vertical_stability":
        return {"support_height", "standard_step_height"}
    if formula_id == "jack_capacity":
        return {"head_jack_cantilever_length"}
    return set()


def _dedupe_rule_refs(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    seen = set()
    for item in items:
        key = (item.get("source"), item.get("rule_id"), item.get("rule_name"))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _drawing_evidence_quality_summary(drawing_review: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    items = []
    for item in drawing_review:
        quality = item.get("evidence_quality") or {}
        label = quality.get("label") or "未标注"
        counts[label] = counts.get(label, 0) + 1
        items.append({
            "review_item_id": item.get("review_item_id"),
            "title": item.get("title"),
            "status": item.get("status"),
            "level": quality.get("level"),
            "label": label,
            "reasons": quality.get("reasons", []),
        })
    return {"counts": counts, "items": items}


def _parse_numeric_comparison(text: str) -> tuple[float, str, float] | None:
    match = re.search(
        r"(-?\d+(?:\.\d+)?)\s*(≤|<=|≥|>=)\s*(-?\d+(?:\.\d+)?)",
        text.replace(" ", ""),
    )
    if not match:
        return None
    return float(match.group(1)), match.group(2), float(match.group(3))
