"""参数数值和单位归一化。"""

from __future__ import annotations

import re
from typing import Any


_NUMBER_UNIT_PATTERN = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>kn/m2|kn/m²|kn/㎡|kn/m3|kn/m³|kn/立方米|kn/m|kn/米|kpa|mm|cm|m|毫米|厘米|米)?",
    re.IGNORECASE,
)

_UNIT_TO_MM = {
    "mm": 1.0,
    "毫米": 1.0,
    "cm": 10.0,
    "厘米": 10.0,
    "m": 1000.0,
    "米": 1000.0,
}

_LOAD_UNITS = {
    "kn/m2": "kN/m2",
    "kn/m²": "kN/m2",
    "kn/㎡": "kN/m2",
    "kpa": "kN/m2",
    "kn/m3": "kN/m3",
    "kn/m³": "kN/m3",
    "kn/立方米": "kN/m3",
    "kn/m": "kN/m",
    "kn/米": "kN/m",
}


def parse_numeric_value(raw_value: str) -> dict[str, Any] | None:
    match = _NUMBER_UNIT_PATTERN.search(str(raw_value))
    if not match:
        return None
    unit = match.group("unit") or ""
    return {
        "value": float(match.group("value")),
        "unit": unit,
        "raw_value": match.group(0),
        "raw_unit": unit,
    }


def normalize_numeric(value: float, raw_unit: str, canonical_unit: str) -> dict[str, Any] | None:
    from_unit = _normalize_unit(raw_unit)
    to_unit = _normalize_unit(canonical_unit)
    if not to_unit:
        return None
    if not from_unit:
        from_unit = to_unit
    if to_unit in {"kN/m2", "kN/m3", "kN/m"}:
        return {"value": round(float(value), 4), "unit": to_unit} if from_unit == to_unit else None
    if to_unit == "m" and from_unit == "m" and float(value) >= 100:
        from_unit = "mm"
    if from_unit not in _UNIT_TO_MM or to_unit not in _UNIT_TO_MM:
        return None
    mm_value = float(value) * _UNIT_TO_MM[from_unit]
    normalized = mm_value / _UNIT_TO_MM[to_unit]
    return {"value": round(normalized, 4), "unit": to_unit}


def normalize_candidate(candidate: dict[str, Any], canonical_unit: str | None) -> dict[str, Any]:
    result = dict(candidate)
    if canonical_unit is None:
        return result
    parsed_value = candidate.get("value")
    raw_unit = str(candidate.get("raw_unit") or candidate.get("unit") or "")
    if parsed_value is None:
        parsed = parse_numeric_value(str(candidate.get("raw_value") or ""))
        if parsed:
            parsed_value = parsed["value"]
            raw_unit = parsed["raw_unit"]
            result.setdefault("raw_value", parsed["raw_value"])
            result["raw_unit"] = raw_unit
    if parsed_value is None:
        result["normalization_error"] = "未找到可归一化的数值"
        return result
    normalized = normalize_numeric(float(parsed_value), raw_unit, canonical_unit)
    if normalized is None:
        result["normalization_error"] = f"不支持的单位换算：{raw_unit} -> {canonical_unit}"
        return result
    result["value"] = normalized["value"]
    result["unit"] = normalized["unit"]
    result["raw_unit"] = raw_unit
    return result


def _normalize_unit(unit: str) -> str:
    unit = str(unit).strip().lower()
    return {"毫米": "mm", "厘米": "cm", "米": "m", **_LOAD_UNITS}.get(unit, unit)
