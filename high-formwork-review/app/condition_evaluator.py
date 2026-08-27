"""规则适用条件轻量判定。

第一版只覆盖已经结构化且可从计算书/ProjectFacts 稳定判断的条件。
未覆盖或证据不足时返回 UNKNOWN，不把缺失证据误判为条件不触发。
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any


def evaluate_applicability_conditions(
    rule: dict[str, Any],
    *,
    facts: dict[str, Any] | None = None,
    text: str = "",
) -> dict[str, Any] | None:
    conditions = rule.get("applicability_conditions") or []
    if not conditions:
        return None

    rule_id = str(rule.get("rule_id") or "")
    facts = facts or {}
    norm_text = _norm(text)

    if rule_id in {"2.4", "2.18"}:
        return _evaluate_construction_load_conditions(rule, norm_text)
    if rule_id == "2.19":
        return _evaluate_gb50666_side_pressure(rule, norm_text)
    if rule_id == "2.24":
        return _evaluate_q3_conditions(rule, facts, norm_text)
    if rule_id == "3.20":
        return _evaluate_overturning_working_conditions(rule, norm_text)
    if rule_id == "3.22":
        return _evaluate_top_step_reduction(rule, norm_text)

    return _generic_unknown(rule)


def _evaluate_construction_load_conditions(rule: dict[str, Any], text: str) -> dict[str, Any]:
    has_horizontal_pipe = _has_any(text, ("水平泵管", "泵管设置", "设置泵管"))
    has_mobile_equipment = _has_any(text, ("移动设备", "布料机", "泵车"))
    items = []
    for condition in rule.get("applicability_conditions") or []:
        name = str(condition.get("condition") or "")
        if "水平泵管" in name:
            status = "TRIGGERED" if has_horizontal_pipe else "UNKNOWN"
            basis = "计算书/荷载说明出现水平泵管相关表述" if has_horizontal_pipe else "未识别到水平泵管是否设置"
        elif "移动设备" in name:
            status = "TRIGGERED" if has_mobile_equipment else "UNKNOWN"
            basis = "识别到移动设备/布料机等关键词" if has_mobile_equipment else "未识别到移动设备信息"
        else:
            status = "TRIGGERED"
            basis = "一般工况默认作为基础施工荷载条件"
        items.append(_item(condition, status, basis))
    return _summary(rule, items)


def _evaluate_gb50666_side_pressure(rule: dict[str, Any], text: str) -> dict[str, Any]:
    velocity = _find_value(text, (r"\bV\b", "浇筑速度"))
    slump = _find_value(text, ("坍落度",))
    use_hydrostatic = (velocity is not None and velocity > 10) or (slump is not None and slump > 180)
    has_complete_condition_inputs = velocity is not None and slump is not None
    has_t0 = _has_any(text, ("t0", "初凝时间", "200/(T+15)", "200/(t+15)"))
    items = []
    for condition in rule.get("applicability_conditions") or []:
        name = str(condition.get("condition") or "")
        if "V≤10" in name or "浇筑速度" in name and "坍落度≤180" in name:
            if not has_complete_condition_inputs:
                status = "UNKNOWN"
                basis = "未提取到浇筑速度V或坍落度"
            elif use_hydrostatic:
                status = "NOT_TRIGGERED"
                basis = _side_pressure_basis(velocity, slump)
            else:
                status = "TRIGGERED"
                basis = _side_pressure_basis(velocity, slump)
        elif "V>10" in name or "坍落度>180" in name:
            if not has_complete_condition_inputs:
                status = "UNKNOWN"
                basis = "未提取到浇筑速度V或坍落度"
            else:
                status = "TRIGGERED" if use_hydrostatic else "NOT_TRIGGERED"
                basis = _side_pressure_basis(velocity, slump)
        elif "初凝时间" in name:
            status = "TRIGGERED" if has_t0 else "UNKNOWN"
            basis = "识别到t0或200/(T+15)初凝时间表达式" if has_t0 else "未识别到初凝时间取值或默认公式"
        else:
            status = "UNKNOWN"
            basis = "当前版本未内置该条件判定"
        items.append(_item(condition, status, basis))
    branch = (
        "unknown"
        if not has_complete_condition_inputs
        else "hydrostatic_gamma_h" if use_hydrostatic else "gb50666_028_beta_formula"
    )
    result = _summary(rule, items)
    result["selected_branch"] = branch
    return result


def _evaluate_q3_conditions(rule: dict[str, Any], facts: dict[str, Any], text: str) -> dict[str, Any]:
    variable_items = _fact_value(facts, "variable_load_items")
    facts_has_q3 = isinstance(variable_items, list) and "concrete_pumping_load" in variable_items
    text_has_pumping = _has_any(text, ("泵送", "泵管", "附加水平荷载", "Q3"))
    text_has_unbalanced = _has_any(text, ("不均匀堆载", "不均匀"))
    text_has_two_percent = _has_any(text, ("2%", "0.02", "百分之二"))
    items = []
    for condition in rule.get("applicability_conditions") or []:
        name = str(condition.get("condition") or "")
        if "泵送" in name:
            status = "TRIGGERED" if facts_has_q3 or text_has_pumping else "UNKNOWN"
            basis = "ProjectFacts或文本识别到泵送/Q3/附加水平荷载" if status == "TRIGGERED" else "未识别到是否存在泵送工况"
        elif "不均匀堆载" in name:
            status = "TRIGGERED" if text_has_unbalanced else "UNKNOWN"
            basis = "文本识别到不均匀堆载" if text_has_unbalanced else "未识别到是否存在不均匀堆载"
        elif "Q3" in name:
            status = "TRIGGERED" if text_has_two_percent else "UNKNOWN"
            basis = "识别到2%或0.02取值表达" if text_has_two_percent else "未识别到Q3按2%取值证据"
        else:
            status = "UNKNOWN"
            basis = "当前版本未内置该条件判定"
        items.append(_item(condition, status, basis))
    return _summary(rule, items)


def _evaluate_overturning_working_conditions(rule: dict[str, Any], text: str) -> dict[str, Any]:
    has_before = _has_any(text, ("浇筑前", "混凝土浇筑前"))
    has_during = _has_any(text, ("浇筑时", "混凝土浇筑时"))
    has_q3 = _has_any(text, ("Q3", "泵送", "附加水平荷载", "不均匀堆载"))
    has_gb50666 = _has_any(text, ("GB50666", "Mo", "Mr", "γ0Mo"))
    items = []
    for condition in rule.get("applicability_conditions") or []:
        name = str(condition.get("condition") or "")
        if "浇筑前" in name:
            status = "TRIGGERED" if has_before else "UNKNOWN"
            basis = "识别到浇筑前抗倾覆工况" if has_before else "未识别到浇筑前工况"
        elif "浇筑时" in name:
            status = "TRIGGERED" if has_during or has_q3 else "UNKNOWN"
            basis = "识别到浇筑时/Q3/泵送附加水平荷载" if status == "TRIGGERED" else "未识别到浇筑时工况"
        elif "GB50666" in name:
            status = "TRIGGERED" if has_gb50666 else "UNKNOWN"
            basis = "识别到GB50666或Mo/Mr表达式" if has_gb50666 else "未识别到GB50666抗倾覆表达式"
        else:
            status = "UNKNOWN"
            basis = "当前版本未内置该条件判定"
        items.append(_item(condition, status, basis))
    return _summary(rule, items)


def _evaluate_top_step_reduction(rule: dict[str, Any], text: str) -> dict[str, Any]:
    frame_type = "Z" if _has_any(text, ("重型", "Z型", "Z 型")) else "B" if _has_any(text, ("标准型", "B型", "B 型")) else None
    load = _find_value(text, ("单肢立杆荷载设计值", "立杆荷载设计值", "Nd", r"\bN\b"))
    threshold = 65.0 if frame_type == "Z" else 40.0 if frame_type == "B" else None
    triggered = load is not None and threshold is not None and load > threshold
    reduced = _has_any(text, ("顶层步距", "缩小0.5", "缩小 0.5"))
    items = []
    for condition in rule.get("applicability_conditions") or []:
        name = str(condition.get("condition") or "")
        if "B型" in name:
            status, basis = _threshold_condition_status(frame_type, load, "B", 40.0)
        elif "Z型" in name:
            status, basis = _threshold_condition_status(frame_type, load, "Z", 65.0)
        elif "未超过" in name:
            if load is None or threshold is None:
                status = "UNKNOWN"
                basis = "未识别到盘扣架型号或单肢立杆荷载"
            else:
                status = "TRIGGERED" if not triggered else "NOT_TRIGGERED"
                basis = f"{frame_type}型单肢立杆荷载{load:g}kN，阈值{threshold:g}kN"
        else:
            status = "UNKNOWN"
            basis = "当前版本未内置该条件判定"
        items.append(_item(condition, status, basis))
    result = _summary(rule, items)
    result["selected_branch"] = "top_step_must_reduce" if triggered else "top_step_not_triggered" if load is not None and threshold is not None else "unknown"
    result["followup"] = "已识别顶层步距缩小措施" if triggered and reduced else "触发后需查证顶层步距是否缩小0.5m" if triggered else ""
    return result


def _threshold_condition_status(frame_type: str | None, load: float | None, target_type: str, threshold: float) -> tuple[str, str]:
    if frame_type != target_type:
        return "NOT_TRIGGERED" if frame_type else "UNKNOWN", "支撑架型号不匹配" if frame_type else "未识别到盘扣架型号"
    if load is None:
        return "UNKNOWN", f"识别为{target_type}型，但缺少单肢立杆荷载"
    return (
        ("TRIGGERED", f"{target_type}型单肢立杆荷载{load:g}kN > {threshold:g}kN")
        if load > threshold
        else ("NOT_TRIGGERED", f"{target_type}型单肢立杆荷载{load:g}kN <= {threshold:g}kN")
    )


def _generic_unknown(rule: dict[str, Any]) -> dict[str, Any]:
    return _summary(
        rule,
        [_item(condition, "UNKNOWN", "当前版本未内置该条件判定") for condition in rule.get("applicability_conditions") or []],
    )


def _summary(rule: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = {item["status"] for item in items}
    if "TRIGGERED" in statuses and "UNKNOWN" not in statuses:
        overall = "TRIGGERED"
    elif statuses == {"NOT_TRIGGERED"}:
        overall = "NOT_TRIGGERED"
    elif "TRIGGERED" in statuses:
        overall = "PARTIAL"
    else:
        overall = "UNKNOWN"
    return {
        "rule_id": rule.get("rule_id"),
        "overall_status": overall,
        "items": items,
    }


def _item(condition: dict[str, Any], status: str, basis: str) -> dict[str, Any]:
    return {
        "condition": condition.get("condition", ""),
        "expected": condition.get("expected", ""),
        "status": status,
        "basis": basis,
    }


def _fact_value(facts: dict[str, Any], key: str) -> Any:
    fact = facts.get(key)
    return fact.get("value") if isinstance(fact, dict) else None


def _find_value(text: str, labels: tuple[str, ...]) -> float | None:
    for label in labels:
        clean = label.replace(r"\b", "")
        for pattern in (
            rf"(?:^|[^a-zA-Z]){clean}\s*(?:=|:|：|＝)\s*(-?\d+(?:\.\d+)?)",
            rf"{clean}[^\d\-]{{0,16}}(-?\d+(?:\.\d+)?)\s*(?:kN|m/h|mm|m|h)?",
        ):
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return float(match.group(1))
    return None


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(_norm(needle) in text for needle in needles)


def _side_pressure_basis(velocity: float | None, slump: float | None) -> str:
    parts = []
    if velocity is not None:
        parts.append(f"V={velocity:g}m/h")
    if slump is not None:
        parts.append(f"坍落度={slump:g}mm")
    return "，".join(parts) if parts else "未提取到V/坍落度"


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text or ""))
    text = text.replace("（", "(").replace("）", ")").replace("＝", "=")
    text = text.replace("\\leq", "≤").replace("\\geq", "≥")
    return re.sub(r"\s+", "", text)
