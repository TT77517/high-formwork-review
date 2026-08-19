"""ProjectFacts 参数冲突检测。"""

from __future__ import annotations

from typing import Any


def resolve_fact(parameter_definition: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    parameter = str(parameter_definition["parameter"])
    canonical_unit = parameter_definition.get("canonical_unit")
    if parameter_definition.get("aggregation_mode") == "set_union":
        return _resolve_set_union_fact(parameter, canonical_unit, candidates)
    if not candidates:
        return _empty_fact(parameter, "missing", unit=canonical_unit)
    explicit = [item for item in candidates if item.get("value") is not None and "normalization_error" not in item]
    explicit = _filter_plausible(parameter_definition, explicit)
    if not explicit:
        fact = _empty_fact(parameter, "uncertain", unit=canonical_unit, candidates=candidates, requires_human_review=True)
        fact["evidence"] = [item["evidence"] for item in candidates[:8] if item.get("evidence")]
        return fact

    scoped = [str(item.get("scope_hint") or "") for item in explicit if item.get("scope_hint")]
    evidence_text = "\n".join(
        str((item.get("evidence") or {}).get("text") or "") for item in explicit
    )
    values = {_value_key(item.get("value"), item.get("unit")) for item in explicit}
    if parameter == "support_height" and len(values) >= 2:
        return _uncertain(parameter, explicit, "检测到多个区域/部位的不同支撑高度")
    if parameter_definition.get("resolution_mode") == "max_numeric":
        return _resolve_max_numeric_fact(parameter, canonical_unit, explicit)
    if len(values) > 1:
        return _conflict(parameter, explicit)

    best = sorted(explicit, key=lambda item: float(item.get("confidence") or 0), reverse=True)[0]
    if best.get("evidence_quality") == "low" or float(best.get("confidence") or 0) < 0.7:
        return _empty_fact(parameter, "uncertain", unit=canonical_unit, candidates=explicit, requires_human_review=True)
    return {
        "value": best.get("value"),
        "unit": best.get("unit"),
        "raw_value": best.get("raw_value"),
        "status": "confirmed",
        "confidence": best.get("confidence"),
        "candidates": explicit,
        "evidence": [item["evidence"] for item in explicit[:5] if item.get("evidence")],
        "source_role": best.get("source_role"),
        "has_conflict": False,
        "requires_human_review": False,
    }


def _conflict(parameter: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "value": None,
        "unit": candidates[0].get("unit"),
        "raw_value": None,
        "status": "conflict",
        "confidence": None,
        "candidates": candidates,
        "evidence": [item["evidence"] for item in candidates[:8] if item.get("evidence")],
        "source_role": None,
        "has_conflict": True,
        "requires_human_review": True,
    }


def _resolve_max_numeric_fact(
    parameter: str,
    canonical_unit: Any,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    numeric = [item for item in candidates if isinstance(item.get("value"), (int, float))]
    if not numeric:
        return _empty_fact(parameter, "uncertain", unit=canonical_unit, candidates=candidates, requires_human_review=True)
    max_value = max(float(item["value"]) for item in numeric)
    top = [item for item in numeric if round(float(item["value"]), 4) == round(max_value, 4)]
    best = sorted(top, key=lambda item: float(item.get("confidence") or 0), reverse=True)[0]
    if best.get("evidence_quality") == "low" or float(best.get("confidence") or 0) < 0.7:
        return _empty_fact(parameter, "uncertain", unit=canonical_unit, candidates=candidates, requires_human_review=True)
    evidence_items = top + [item for item in numeric if item not in top]
    return {
        "value": best.get("value"),
        "unit": best.get("unit"),
        "raw_value": best.get("raw_value"),
        "status": "confirmed",
        "confidence": best.get("confidence"),
        "candidates": candidates,
        "evidence": [item["evidence"] for item in evidence_items[:5] if item.get("evidence")],
        "source_role": best.get("source_role"),
        "has_conflict": False,
        "requires_human_review": False,
        "resolution_mode": "max_numeric",
    }


def _resolve_set_union_fact(
    parameter: str,
    canonical_unit: Any,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    explicit = [
        item for item in candidates
        if isinstance(item.get("value"), str) and "normalization_error" not in item
    ]
    if not explicit:
        return _empty_fact(parameter, "missing", unit=canonical_unit)
    values = sorted({str(item["value"]) for item in explicit})
    confidence = round(min(0.98, max(float(item.get("confidence") or 0) for item in explicit)), 2)
    return {
        "value": values,
        "unit": canonical_unit,
        "raw_value": None,
        "status": "confirmed",
        "confidence": confidence,
        "candidates": explicit,
        "evidence": [item["evidence"] for item in explicit[:8] if item.get("evidence")],
        "source_role": explicit[0].get("source_role"),
        "has_conflict": False,
        "requires_human_review": False,
        "aggregation_mode": "set_union",
    }


def _filter_plausible(
    parameter_definition: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    minimum = parameter_definition.get("plausible_min")
    maximum = parameter_definition.get("plausible_max")
    if not isinstance(minimum, (int, float)) and not isinstance(maximum, (int, float)):
        return candidates
    result = []
    for item in candidates:
        value = item.get("value")
        if isinstance(value, (int, float)):
            if isinstance(minimum, (int, float)) and float(value) < float(minimum):
                continue
            if isinstance(maximum, (int, float)) and float(value) > float(maximum):
                continue
        result.append(item)
    return result


def _uncertain(parameter: str, candidates: list[dict[str, Any]], reason: str) -> dict[str, Any]:
    fact = _empty_fact(parameter, "uncertain", unit=candidates[0].get("unit"), candidates=candidates, requires_human_review=True)
    fact["reason"] = reason
    fact["evidence"] = [item["evidence"] for item in candidates[:8] if item.get("evidence")]
    return fact


def _empty_fact(
    parameter: str,
    status: str,
    *,
    unit: Any = None,
    candidates: list[dict[str, Any]] | None = None,
    requires_human_review: bool = False,
) -> dict[str, Any]:
    return {
        "value": None,
        "unit": unit,
        "raw_value": None,
        "status": status,
        "confidence": None,
        "candidates": candidates or [],
        "evidence": [],
        "source_role": None,
        "has_conflict": status == "conflict",
        "requires_human_review": requires_human_review,
    }


def _value_key(value: Any, unit: Any) -> tuple[float | str, str]:
    if isinstance(value, (int, float)):
        return (round(float(value), 4), str(unit or ""))
    return (str(value), str(unit or ""))


def _looks_like_multi_region(text: str) -> bool:
    markers = ("A区", "B区", "C区", "梁区", "板区", "地下室", "地上部分")
    return sum(1 for marker in markers if marker in text) >= 2
