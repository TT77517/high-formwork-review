"""正文-计算书参数一致性检查。

本模块做关键输入参数的一致性预审，不做完整力学复算。
"""

from __future__ import annotations

from typing import Any

from .calculation_dependencies import calculation_impacts_for_parameter
from .models import MinerUDocument


PARAMETER_LABELS = {
    "standard_step_height": "水平杆标准步距",
    "head_jack_cantilever_length": "可调托撑悬臂长度",
    "horizontal_scissor_brace_interval": "水平剪刀撑设置间隔",
    "personnel_equipment_load_standard": "施工人员及设备荷载标准值",
}


def build_consistency_review(
    project_facts: dict[str, Any],
    parsed_document: MinerUDocument | None = None,
) -> list[dict[str, Any]]:
    facts = project_facts.get("facts", {})
    page_count = parsed_document.physical_page_count if parsed_document else None
    return [
        _parameter_consistency_item(parameter_id, fact, page_count)
        for parameter_id, fact in facts.items()
        if parameter_id in PARAMETER_LABELS
    ]


def _parameter_consistency_item(
    parameter_id: str,
    fact: dict[str, Any],
    page_count: int | None,
) -> dict[str, Any]:
    candidates = [
        item for item in fact.get("candidates", []) if isinstance(item, dict)
    ]
    design_candidates = [
        item for item in candidates if not _looks_like_calculation_candidate(item, page_count)
    ]
    calculation_candidates = [
        item for item in candidates if _looks_like_calculation_candidate(item, page_count)
    ]
    design_value = _representative_value(design_candidates)
    calculation_value = _representative_value(calculation_candidates)
    status = _consistency_status(design_value, calculation_value)
    return {
        "review_item_id": f"CR-{_parameter_index(parameter_id):02d}",
        "category": "参数一致性",
        "title": PARAMETER_LABELS[parameter_id],
        "parameter": parameter_id,
        "review_method": "text_calculation_parameter_consistency",
        "status": status,
        "conclusion": _conclusion(status, PARAMETER_LABELS[parameter_id]),
        "design_side": {
            "value": design_value,
            "evidence": [_candidate_evidence(item) for item in design_candidates[:3]],
        },
        "calculation_side": {
            "value": calculation_value,
            "evidence": [_candidate_evidence(item) for item in calculation_candidates[:3]],
        },
        "resolved_fact": {
            "value": fact.get("value"),
            "unit": fact.get("unit"),
            "status": fact.get("status"),
        },
        "calculation_impacts": calculation_impacts_for_parameter(parameter_id),
        "automation_level": "parameter_consistency_only",
        "requires_human_review": status != "PASS",
        "boundary": "本项只核对正文/构造参数与计算书输入参数是否一致，并提示受影响的公式验算；最终承载力、稳定性等仍由计算校核模块复算或追证。",
    }


def _looks_like_calculation_candidate(
    candidate: dict[str, Any],
    page_count: int | None,
) -> bool:
    if candidate.get("source_role") == "calculation":
        return True
    evidence = candidate.get("evidence") if isinstance(candidate.get("evidence"), dict) else {}
    text = str(evidence.get("text") or "")
    page = evidence.get("physical_page")
    if any(token in text for token in ("G_{", "Q_{", "\\gamma", "γ", "Mmax", "N/mm", "kN/m")):
        return True
    if isinstance(page, int) and page_count and page >= max(1, int(page_count * 0.38)):
        return True
    return False


def _representative_value(candidates: list[dict[str, Any]]) -> Any:
    values: list[Any] = []
    for candidate in candidates:
        value = candidate.get("value")
        if value is None:
            continue
        if not any(_same_value(value, existing) for existing in values):
            values.append(value)
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return values


def _consistency_status(design_value: Any, calculation_value: Any) -> str:
    if design_value is None or calculation_value is None:
        return "REVIEW"
    design_values = design_value if isinstance(design_value, list) else [design_value]
    calculation_values = calculation_value if isinstance(calculation_value, list) else [calculation_value]
    for left in design_values:
        for right in calculation_values:
            if _same_value(left, right):
                return "PASS"
    return "ISSUE"


def _same_value(left: Any, right: Any) -> bool:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= max(0.001, abs(float(right)) * 0.01)
    if isinstance(left, dict) and isinstance(right, dict):
        return all(_same_value(left.get(key), right.get(key)) for key in sorted(set(left) | set(right)))
    return left == right


def _conclusion(status: str, title: str) -> str:
    if status == "PASS":
        return f"正文/构造参数与计算书输入中识别到的{title}一致。"
    if status == "ISSUE":
        return f"正文/构造参数与计算书输入中识别到的{title}不一致，需重点复核。"
    return f"未同时取得正文/构造参数和计算书输入中的{title}，需人工复核一致性。"


def _candidate_evidence(candidate: dict[str, Any]) -> dict[str, Any]:
    evidence = candidate.get("evidence") if isinstance(candidate.get("evidence"), dict) else {}
    return {
        "value": candidate.get("value"),
        "unit": candidate.get("unit"),
        "raw_value": candidate.get("raw_value"),
        "source_role": candidate.get("source_role"),
        "page": evidence.get("physical_page"),
        "printed_page": evidence.get("printed_page"),
        "section": " / ".join(evidence.get("section_path", []))
        if isinstance(evidence.get("section_path"), list)
        else None,
        "block_id": evidence.get("block_id"),
        "quote": evidence.get("text"),
    }


def _parameter_index(parameter_id: str) -> int:
    return list(PARAMETER_LABELS).index(parameter_id) + 1
