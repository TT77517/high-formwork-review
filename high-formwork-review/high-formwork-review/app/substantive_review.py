"""少量内容符合性预审。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CANDIDATE_RULES = PROJECT_ROOT / "config" / "candidate_compliance_rules_v1.2.json"


def build_substantive_review(
    project_qualification: dict[str, Any],
    project_facts: dict[str, Any],
    rules_path: str | Path = DEFAULT_CANDIDATE_RULES,
) -> list[dict[str, Any]]:
    facts = project_facts.get("facts", {})
    candidate_rules = _load_candidate_rules(rules_path)
    return [
        _support_system_item(project_qualification),
        _numeric_item(
            "SR-02",
            "支架构造",
            "水平杆标准步距",
            facts.get("standard_step_height", {}),
            _rule(candidate_rules, "HF-JGJT231-6.1.3-01"),
            fallback_requirement="按候选规则中 6.1.3 相关要求执行；当前未找到候选规则时需人工核验。",
        ),
        _numeric_item(
            "SR-03",
            "支架构造",
            "可调托撑悬臂长度",
            facts.get("head_jack_cantilever_length", {}),
            _rule(candidate_rules, "HF-JGJT231-6.2.4-01"),
            fallback_requirement="按候选规则中 6.2.4 相关要求执行；当前未找到候选规则时需人工核验。",
        ),
        _horizontal_scissor_brace_interval_item(
            facts.get("horizontal_scissor_brace_interval", {}),
            _rule(candidate_rules, "HF-JGJT231-6.2.7-01"),
        ),
        _load_items_item(
            "SR-04",
            "荷载设计",
            "永久荷载项目",
            facts.get("permanent_load_items", {}),
            _rule(candidate_rules, "HF-JGJT231-4.1.2-01"),
            {
                "formwork_support_self_weight",
                "fresh_concrete_self_weight",
                "reinforcement_self_weight",
            },
        ),
        _load_items_item(
            "SR-05",
            "荷载设计",
            "可变荷载项目",
            facts.get("variable_load_items", {}),
            _rule(candidate_rules, "HF-JGJT231-4.1.4-01"),
            {
                "personnel_equipment_load",
                "concrete_vibration_load",
                "wind_load",
            },
        ),
    ]


def _support_system_item(project_qualification: dict[str, Any]) -> dict[str, Any]:
    value = project_qualification.get("support_system", "unknown")
    status = "PASS" if value == "disk_lock" else "REVIEW"
    return {
        "review_item_id": "SR-01",
        "category": "工程识别",
        "title": "支撑体系识别",
        "review_method": "classification",
        "status": status,
        "conclusion": (
            "已识别为承插型盘扣式支撑体系，适用盘扣式专业规则包。"
            if status == "PASS"
            else "支撑体系未可靠识别，需人工确认适用专业规则包。"
        ),
        "actual": {
            "value": value,
            "label": project_qualification.get("support_system_label", "未识别"),
        },
        "requirement": {
            "description": "识别支撑体系，用于选择后续专业规则包；本项不输出符合性结论。",
            "rule_id": None,
        },
        "evidence": _first_fact_evidence(project_qualification),
        "basis": [],
        "requires_human_review": status != "PASS",
    }


def _numeric_item(
    review_item_id: str,
    category: str,
    title: str,
    fact: dict[str, Any],
    rule: dict[str, Any] | None,
    *,
    fallback_requirement: str,
) -> dict[str, Any]:
    status = "REVIEW"
    actual_value = fact.get("value")
    requirement = _requirement(rule, fallback_requirement)
    limit = _numeric_requirement(rule)
    if fact.get("status") == "confirmed" and isinstance(actual_value, (int, float)) and limit:
        status = "PASS" if _compare(actual_value, limit["operator"], limit["value"]) else "ISSUE"
    conclusion = _numeric_conclusion(status, title, actual_value, fact.get("unit"), limit)
    return {
        "review_item_id": review_item_id,
        "category": category,
        "title": title,
        "review_method": "numeric",
        "status": status,
        "conclusion": conclusion,
        "actual": {
            "value": actual_value,
            "unit": fact.get("unit"),
            "raw_value": fact.get("raw_value"),
            "status": fact.get("status", "missing"),
        },
        "requirement": requirement,
        "evidence": [_evidence_dict(item) for item in fact.get("evidence", [])],
        "basis": _basis(rule),
        "requires_human_review": status in {"ISSUE", "REVIEW"},
    }


def _horizontal_scissor_brace_interval_item(
    fact: dict[str, Any],
    rule: dict[str, Any] | None,
) -> dict[str, Any]:
    review_item_id = "SR-06"
    category = "支架构造"
    title = "水平剪刀撑设置间隔"
    value = fact.get("value") if isinstance(fact.get("value"), dict) else {}
    interval = _interval_requirement(rule)
    status = "REVIEW"
    if fact.get("status") == "confirmed" and value and interval:
        actual_min = value.get("minimum")
        actual_max = value.get("maximum")
        if isinstance(actual_min, (int, float)) and isinstance(actual_max, (int, float)):
            status = (
                "PASS"
                if actual_min >= interval["minimum"] and actual_max <= interval["maximum"]
                else "ISSUE"
            )
    conclusion = _horizontal_scissor_brace_conclusion(status, value, interval, rule)
    return {
        "review_item_id": review_item_id,
        "category": category,
        "title": title,
        "review_method": "standard_step_interval_partial_scope",
        "status": status,
        "conclusion": conclusion,
        "actual": {
            "value": value or None,
            "raw_value": fact.get("raw_value"),
            "status": fact.get("status", "missing"),
        },
        "requirement": _requirement(rule, "按候选规则中 6.2.7 水平剪刀撑设置间隔要求核验。"),
        "evidence": [_evidence_dict(item) for item in fact.get("evidence", [])],
        "basis": _basis(rule),
        "requires_human_review": status in {"ISSUE", "REVIEW"},
        "compliance_scope": rule.get("compliance_scope") if isinstance(rule, dict) else None,
        "execution_scope": rule.get("execution_scope") if isinstance(rule, dict) else None,
        "external_dependency_status": rule.get("external_dependency_status") if isinstance(rule, dict) else None,
        "scope_notice": (
            "当前仅核验 JGJ/T 231-2021 第6.2.7条中明确的水平剪刀撑设置间隔要求；"
            "该条引用的 JGJ 130 具体构造要求尚未纳入本次自动核验，需人工复核或待对应规范规则接入。"
        ),
    }


def _load_items_item(
    review_item_id: str,
    category: str,
    title: str,
    fact: dict[str, Any],
    rule: dict[str, Any] | None,
    required_items: set[str],
) -> dict[str, Any]:
    actual_items = set(fact.get("value") or []) if isinstance(fact.get("value"), list) else set()
    missing = sorted(required_items - actual_items)
    if fact.get("status") != "confirmed":
        status = "REVIEW"
        conclusion = "未可靠识别方案纳入的荷载项目，需人工核验。"
    elif missing:
        status = "ISSUE"
        conclusion = "当前证据显示荷载项目可能不完整，需重点核验：" + "、".join(missing)
    else:
        status = "PASS"
        conclusion = "当前证据支持方案已纳入该项要求的主要荷载项目。"
    return {
        "review_item_id": review_item_id,
        "category": category,
        "title": title,
        "review_method": "set_completeness",
        "status": status,
        "conclusion": conclusion,
        "actual": {
            "items": sorted(actual_items),
            "missing_items": missing,
            "status": fact.get("status", "missing"),
        },
        "requirement": _requirement(rule, "按候选规则要求核验荷载项目是否纳入。"),
        "evidence": [_evidence_dict(item) for item in fact.get("evidence", [])],
        "basis": _basis(rule),
        "requires_human_review": status in {"ISSUE", "REVIEW"},
    }


def _load_candidate_rules(path: str | Path) -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    rules = data.get("rules", []) if isinstance(data, dict) else []
    return {str(rule.get("rule_id")): rule for rule in rules if isinstance(rule, dict)}


def _rule(rules: dict[str, dict[str, Any]], rule_id: str) -> dict[str, Any] | None:
    return rules.get(rule_id)


def _numeric_requirement(rule: dict[str, Any] | None) -> dict[str, Any] | None:
    if not rule:
        return None
    req = rule.get("requirement", {})
    if not isinstance(req, dict):
        return None
    if req.get("operator") and isinstance(req.get("value"), (int, float)):
        return {"operator": str(req["operator"]), "value": float(req["value"]), "unit": req.get("unit")}
    return None


def _interval_requirement(rule: dict[str, Any] | None) -> dict[str, float] | None:
    if not rule:
        return None
    req = rule.get("requirement", {})
    interval = req.get("interval") if isinstance(req, dict) else None
    if not isinstance(interval, dict):
        return None
    minimum = interval.get("minimum")
    maximum = interval.get("maximum")
    if isinstance(minimum, (int, float)) and isinstance(maximum, (int, float)):
        return {"minimum": float(minimum), "maximum": float(maximum)}
    return None


def _compare(actual: float, operator: str, expected: float) -> bool:
    return {
        "<=": actual <= expected,
        "<": actual < expected,
        ">=": actual >= expected,
        ">": actual > expected,
        "==": actual == expected,
    }.get(operator, False)


def _numeric_conclusion(status: str, title: str, value: Any, unit: Any, limit: dict[str, Any] | None) -> str:
    if status == "REVIEW":
        return f"未取得可直接判定的{title}完整规则输入，需人工核验。"
    rule_text = f"{limit['operator']} {limit['value']}{limit.get('unit') or unit or ''}" if limit else "候选规则要求"
    if status == "PASS":
        return f"当前方案证据显示实际值为 {value}{unit or ''}，支持满足要求（{rule_text}）。"
    return f"当前方案证据显示实际值为 {value}{unit or ''}，可能不满足要求（{rule_text}）。"


def _horizontal_scissor_brace_conclusion(
    status: str,
    value: dict[str, Any],
    interval: dict[str, float] | None,
    rule: dict[str, Any] | None,
) -> str:
    if status == "REVIEW":
        return "未取得可直接判定的水平剪刀撑设置间隔证据，需人工核验。"
    actual = f"{value.get('minimum'):g}~{value.get('maximum'):g}个标准步距"
    expected = (
        f"{interval['minimum']:g}~{interval['maximum']:g}个标准步距"
        if interval
        else "候选规则要求"
    )
    scope_note = "仅限JGJ/T 231-2021第6.2.7条设置间隔要求"
    if status == "PASS":
        return f"当前方案证据显示水平剪刀撑沿高度每间隔{actual}设置，{scope_note}未发现明显问题（要求：{expected}）。"
    return f"当前方案证据显示水平剪刀撑设置间隔为 {actual}，可能不满足{scope_note}（要求：{expected}）。"


def _requirement(rule: dict[str, Any] | None, fallback: str) -> dict[str, Any]:
    if not rule:
        return {"description": fallback, "rule_id": None}
    source = rule.get("source", {}) if isinstance(rule.get("source"), dict) else {}
    req = rule.get("requirement", {})
    description = source.get("original_text") or rule.get("name") or fallback
    return {
        "description": description,
        "rule_id": rule.get("rule_id"),
        "requirement": req,
    }


def _basis(rule: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not rule:
        return []
    source = rule.get("source", {}) if isinstance(rule.get("source"), dict) else {}
    return [
        {
            "standard": source.get("standard_code", "JGJ/T 231-2021"),
            "clause": source.get("article"),
            "rule_id": rule.get("rule_id"),
        }
    ]


def _first_fact_evidence(project_qualification: dict[str, Any]) -> list[dict[str, Any]]:
    for value in project_qualification.get("identified_parameters", {}).values():
        evidence = value.get("evidence") if isinstance(value, dict) else None
        if evidence:
            return evidence
    return []


def _evidence_dict(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return {
            "page": item.get("physical_page") or item.get("page"),
            "section": " / ".join(item.get("section_path", []))
            if isinstance(item.get("section_path"), list)
            else item.get("section"),
            "block_id": item.get("block_id"),
            "quote": item.get("quote") or item.get("text"),
        }
    return {
        "page": getattr(item, "physical_page", None),
        "section": " / ".join(getattr(item, "section_path", []) or []),
        "block_id": getattr(item, "block_id", None),
        "quote": getattr(item, "quote", None),
    }
