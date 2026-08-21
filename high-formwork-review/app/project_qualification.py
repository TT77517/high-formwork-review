"""工程识别与审查范围确定。"""

from __future__ import annotations

from typing import Any

from .models import ReviewEvidence
from .project_facts import build_project_facts
from .standards import applicable_standards_for


def build_project_qualification(document: Any, project_facts: dict[str, Any] | None = None) -> dict[str, Any]:
    facts_doc = project_facts or build_project_facts(document)
    facts = facts_doc.get("facts", {})
    support_system = _fact(facts, "support_system")
    support_height = _fact(facts, "support_height")

    system_value = support_system.get("value")
    rule_packs = ["general_high_formwork"]
    if system_value == "disk_lock":
        rule_packs.append("disk_lock")

    identified = {
        "support_height": _parameter(support_height),
        "support_span": _unknown_parameter("当前未识别跨度参数"),
        "total_load_design": _unknown_parameter("当前未识别总荷载设计值"),
        "concentrated_line_load_design": _unknown_parameter("当前未识别集中线荷载设计值"),
    }
    missing_core = [
        key for key, value in identified.items()
        if key == "support_height" and value["status"] != "confirmed"
    ]
    requires_review = bool(missing_core) or system_value in {None, "unknown"}

    return {
        "project_type": "concrete_formwork_support",
        "risk_classification": _risk_classification(support_height),
        "support_system": system_value or "unknown",
        "support_system_label": _support_system_label(system_value),
        "identified_parameters": identified,
        "triggered_conditions": _triggered_conditions(support_height),
        "applicable_rule_packs": rule_packs,
        "applicable_standards": applicable_standards_for(system_value),
        "requires_human_review": requires_review,
        "human_review_reason": (
            "关键工程识别参数未完全识别，需人工确认"
            if requires_review
            else "工程识别信息可用于后续预审范围选择"
        ),
    }


def _fact(facts: dict[str, Any], fact_id: str) -> dict[str, Any]:
    value = facts.get(fact_id)
    return value if isinstance(value, dict) else {}


def _parameter(fact: dict[str, Any]) -> dict[str, Any]:
    return {
        "value": fact.get("value"),
        "unit": fact.get("unit"),
        "status": fact.get("status", "missing"),
        "evidence": [_evidence_dict(item) for item in fact.get("evidence", [])],
    }


def _unknown_parameter(reason: str) -> dict[str, Any]:
    return {
        "value": None,
        "unit": None,
        "status": "unknown",
        "reason": reason,
        "evidence": [],
    }


def _risk_classification(support_height: dict[str, Any]) -> str:
    if support_height.get("status") != "confirmed":
        return "unknown"
    value = support_height.get("value")
    if isinstance(value, (int, float)) and value >= 8:
        return "over_scale_dangerous"
    return "dangerous"


def _triggered_conditions(support_height: dict[str, Any]) -> list[dict[str, Any]]:
    if support_height.get("status") != "confirmed":
        return []
    value = support_height.get("value")
    if isinstance(value, (int, float)) and value >= 8:
        return [
            {
                "rule_id": "PQ-HIGH-FORMWORK-HEIGHT-01",
                "name": "支撑高度达到超过一定规模危大工程识别条件",
                "condition": "support_height >= 8m",
                "source": "项目预审配置",
                "source_clause": "需由人工结合现行法规确认",
                "status": "source_pending_manual_confirmation",
            }
        ]
    return []


def _support_system_label(value: Any) -> str:
    return {
        "disk_lock": "承插型盘扣式",
        "coupler": "扣件式",
        "other": "其他",
        "unknown": "未识别",
        None: "未识别",
    }.get(value, str(value))


def _evidence_dict(item: Any) -> dict[str, Any]:
    if isinstance(item, ReviewEvidence):
        return {
            "page": item.physical_page,
            "section": " / ".join(item.section_path),
            "block_id": item.block_id,
            "quote": item.quote,
        }
    if isinstance(item, dict):
        return {
            "page": item.get("physical_page") or item.get("page"),
            "section": " / ".join(item.get("section_path", []))
            if isinstance(item.get("section_path"), list)
            else item.get("section"),
            "block_id": item.get("block_id"),
            "quote": item.get("quote") or item.get("text"),
        }
    return {}
