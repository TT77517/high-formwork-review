"""工程识别与审查范围确定。"""

from __future__ import annotations

from typing import Any

from .models import ReviewEvidence
from .project_facts import build_project_facts
from .rule_engine import load_rule_library
from .standards import derive_applicable_standards


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
        "support_span": _parameter_from_facts(facts, "support_span", "当前未识别跨度参数"),
        "total_load_design": _parameter_from_facts(facts, "total_load", "当前未识别总荷载设计值"),
        "concentrated_line_load_design": _parameter_from_facts(
            facts, "concentrated_line_load", "当前未识别集中线荷载设计值"
        ),
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
        "key_parameters": _key_parameters(facts),
        "triggered_conditions": _triggered_conditions(support_height),
        "applicable_rule_packs": rule_packs,
        "applicable_standards": derive_applicable_standards(
            load_rule_library(), system_value
        ),
        "pending_confirmation": _pending_confirmation(system_value),
        "requires_human_review": requires_review,
        "human_review_reason": (
            "关键工程识别参数未完全识别，需人工确认"
            if requires_review
            else "工程识别信息可用于后续预审范围选择"
        ),
    }


# 关键参数 → （中文名，该参数驱动的下游审查环节）
_KEY_PARAMETER_DEFS = [
    ("support_height", "支撑高度", ["危大范围判定（≥5m）", "超规模危大判定（≥8m）", "风险属性分级"]),
    ("support_span", "搭设跨度", ["危大范围判定（跨度≥10m）", "超规模危大判定（跨度≥18m）"]),
    ("total_load", "施工总荷载", ["危大范围判定（≥10kN/m²）", "超规模危大判定（≥15kN/m²）"]),
    ("concentrated_line_load", "集中线荷载", ["危大范围判定（≥15kN/m）", "超规模危大判定（≥20kN/m）"]),
    ("standard_step_height", "架体标准步距", ["计算书参数一致性校核"]),
    ("head_jack_cantilever_length", "可调托撑悬臂长度", ["计算书参数一致性校核"]),
    ("vertical_spacing", "立杆纵距", ["计算书参数一致性校核"]),
    ("horizontal_spacing", "立杆横距", ["计算书参数一致性校核"]),
    ("framework_height", "架体高度", ["构造参数校核"]),
    ("permanent_load_items", "恒载项", ["荷载组合完整性"]),
    ("variable_load_items", "可变荷载项", ["荷载组合完整性"]),
]


def _key_parameters(facts: dict[str, Any]) -> list[dict[str, Any]]:
    """关键参数速览：识别结果 + 来源页 + 驱动的下游审查环节。"""
    from .parameter_definitions import get_parameter_definitions

    definitions = {str(d["parameter"]): d for d in get_parameter_definitions()}
    result = []
    for fact_id, label, drives in _KEY_PARAMETER_DEFS:
        fact = facts.get(fact_id) or {}
        status = str(fact.get("status", "missing"))
        value = fact.get("value")
        unit = fact.get("unit")
        if isinstance(value, list):
            names = _load_item_names(definitions.get(fact_id, {}), value)
            value_text = "、".join(names)
        elif value is not None:
            value_text = f"{value} {unit}".strip() if unit else str(value)
        else:
            value_text = ""
        page = None
        for ev in fact.get("evidence") or []:
            page = ev.get("physical_page") or ev.get("page")
            if page:
                break
        result.append(
            {
                "id": fact_id,
                "label": label,
                "status": status,
                "value_text": value_text,
                "evidence_page": page,
                "drives": list(drives),
            }
        )
    return result


def _load_item_names(definition: dict[str, Any], item_ids: list[Any]) -> list[str]:
    items = {str(item.get("id")): item for item in definition.get("load_items", [])}
    names = []
    for item_id in item_ids:
        entry = items.get(str(item_id))
        aliases = (entry or {}).get("aliases") or []
        names.append(str(aliases[0]) if aliases else str(item_id))
    return names


def _fact(facts: dict[str, Any], fact_id: str) -> dict[str, Any]:
    value = facts.get(fact_id)
    return value if isinstance(value, dict) else {}


def _parameter_from_facts(facts: dict[str, Any], fact_id: str, reason: str) -> dict[str, Any]:
    """接通 facts 中已提取的参数；无值时保持原 unknown 形状。"""
    fact = _fact(facts, fact_id)
    if fact.get("value") is None:
        return _unknown_parameter(reason)
    return _parameter(fact)


# 支撑体系选项 → 规则库 applicable_types 体系码
_SYSTEM_OPTIONS = [
    ("disk_lock", "承插型盘扣式", "pankou"),
    ("coupler", "扣件式", "koujian"),
    ("other", "其他", "wankou"),
]


def _pending_confirmation(system_value: Any) -> dict[str, Any] | None:
    """支撑体系未识别时输出待确认摘要（含各体系待执行专属规则数）。"""
    if system_value not in (None, "", "unknown"):
        return None
    options = []
    for value, label, code in _SYSTEM_OPTIONS:
        count = sum(
            1
            for rule in load_rule_library()
            if "universal" not in rule.get("applicable_types", ["universal"])
            and code in rule.get("applicable_types", [])
        )
        options.append({"value": value, "label": label, "pending_rule_count": count})
    return {
        "field": "support_system",
        "note": "支撑体系未识别，体系专属规则暂未执行，人工确认后重跑",
        "options": options,
    }


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
