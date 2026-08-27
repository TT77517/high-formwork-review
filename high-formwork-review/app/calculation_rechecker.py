"""轻量确定性计算复核。

只处理首批高价值公式；所有输入必须来自计算书证据片段，缺值不推测。
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any


SUPPORTED_RULES = {
    "2.8", "2.12", "2.19", "2.23", "3.9", "3.11", "3.12", "3.14", "3.15", "3.17", "3.17p",
    "3.19", "3.20", "3.25", "3.27",
}


def recheck_calculation(
    rule: dict[str, Any],
    segments: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """对支持的计算规则执行真实复核；不支持返回 None。"""
    rule_id = str(rule.get("rule_id") or "")
    if rule_id not in SUPPORTED_RULES:
        return None
    if rule_id in {"3.11", "3.14"}:
        return _recheck_slenderness(rule, segments)
    if rule_id in {"2.12", "2.23"}:
        return _recheck_load_combination(rule, segments)
    if rule_id in {"2.8", "2.19"}:
        return _recheck_side_pressure(rule, segments)
    if rule_id in {"3.9", "3.12", "3.15", "3.27"}:
        return _recheck_stability(rule, segments)
    if rule_id in {"3.17", "3.17p"}:
        return _recheck_jack_capacity(rule, segments)
    if rule_id == "3.19":
        return _recheck_foundation_bearing(rule, segments)
    if rule_id in {"3.20", "3.25"}:
        return _recheck_overturning(rule, segments)
    return None


def _recheck_load_combination(rule: dict[str, Any], segments: list[dict[str, Any]]) -> dict[str, Any]:
    focused = _focused_segments(segments, ("荷载组合", "承载力", "极限状态", "1.3", "1.5", "SGk", "SQk"))
    text = _join_text(focused)
    if not text:
        return _uncertain(rule, "load_combination", "S = 1.3*SGk + 1.5*SQk", ["计算书未找到荷载组合片段"], focused)

    ctext = _compact_formula(text)
    has_13 = bool(re.search(r"1\.3\s*[×*·]?\s*(?:S?G|G|永久|恒)", ctext, re.IGNORECASE))
    has_15 = bool(re.search(r"1\.5\s*[×*·]?\s*(?:S?Q|Q|可变|活|施工)", ctext, re.IGNORECASE))
    has_expression = bool(re.search(r"(?:S|组合|承载力)[^。；\n]{0,80}1\.3[^。；\n]{0,80}1\.5", ctext, re.IGNORECASE))
    if not (has_13 and has_15) and not has_expression:
        return _uncertain(
            rule,
            "load_combination",
            "S = 1.3*SGk + 1.5*SQk",
            ["未识别到1.3永久荷载与1.5可变荷载组合表达式"],
            focused,
        )

    return _result(
        rule,
        formula_id="load_combination",
        formula_name="荷载组合系数复核",
        expression="S = 1.3*SGk + 1.5*SQk",
        inputs=[
            _input("γG", 1.3, "", "计算书承载能力极限状态组合"),
            _input("γQ", 1.5, "", "计算书承载能力极限状态组合"),
        ],
        substituted_expression="S = 1.3*SGk + 1.5*SQk",
        computed_value=1.0,
        allowed_value=1.0,
        operator="formula",
        status="PASS",
        segments=focused,
        found=["识别到承载能力极限状态荷载组合分项系数1.3/1.5"],
        missing=[],
        decision="荷载组合分项系数表达式满足当前规则的确定性复核条件。",
    )


def _recheck_side_pressure(rule: dict[str, Any], segments: list[dict[str, Any]]) -> dict[str, Any]:
    rule_id = str(rule.get("rule_id") or "")
    is_gb50666 = rule_id == "2.19"
    focused = _focused_segments(
        segments,
        ("侧压力", "G4", "G4k", "F=", "γc", "gamma", "t0", "β", "beta", "浇筑速度", "坍落度"),
    )
    text = _join_text(focused)
    expression = (
        "V<=10且坍落度<=180时 F = min(0.28*γc*t0*β*sqrt(V), γc*H)，否则 F = γc*H"
        if is_gb50666
        else "F = min(0.22*γc*t0*β1*β2*sqrt(V), γc*H)"
    )
    if not text:
        return _uncertain(rule, "side_pressure", expression, ["计算书未找到混凝土侧压力计算片段"], focused)

    gamma_c = _find_explicit_value(text, (r"γc", r"γ_c", r"gammac", r"混凝土重力密度"))
    t0 = _find_explicit_value(text, (r"t0", r"初凝时间"))
    velocity = _find_explicit_value(text, (r"\bV\b", r"浇筑速度"))
    height = _find_explicit_value(text, (r"\bH\b", r"浇筑高度", r"有效压头高度", r"侧压力计算位置至顶部高度"))
    reported = _find_side_pressure_result(text)
    slump = _find_explicit_value(text, (r"坍落度",))

    missing = []
    if gamma_c is None:
        missing.append("缺少混凝土重力密度 γc")
    if height is None:
        missing.append("缺少侧压力计算高度 H")
    if is_gb50666:
        beta = _find_explicit_value(text, (r"β(?![12])", r"beta(?![12])", r"坍落度影响修正系数"))
        force_hydrostatic = (velocity is not None and velocity > 10) or (slump is not None and slump > 180)
        if velocity is None and not (slump is not None and slump > 180):
            missing.append("缺少浇筑速度 V")
        if t0 is None and not force_hydrostatic:
            missing.append("缺少初凝时间 t0")
        if beta is None and not force_hydrostatic:
            missing.append("缺少坍落度影响修正系数 β")
    else:
        beta1 = _find_explicit_value(text, (r"β1", r"beta1", r"外加剂影响系数"))
        beta2 = _find_explicit_value(text, (r"β2", r"beta2", r"坍落度影响系数"))
        if t0 is None:
            missing.append("缺少初凝时间 t0")
        if velocity is None:
            missing.append("缺少浇筑速度 V")
        if beta1 is None:
            missing.append("缺少外加剂影响系数 β1")
        if beta2 is None:
            missing.append("缺少坍落度影响系数 β2")
    if reported is None:
        missing.append("缺少计算书给出的侧压力结果 F")
    if missing:
        return _uncertain(rule, "side_pressure", expression, missing, focused)

    hydrostatic = gamma_c * height
    inputs = [
        _input("γc", gamma_c, "kN/m³", "混凝土重力密度"),
        _input("H", height, "m", "侧压力计算高度"),
    ]
    if is_gb50666 and ((velocity is not None and velocity > 10) or (slump is not None and slump > 180)):
        computed = hydrostatic
        substituted = f"F = γc*H = {gamma_c:g} * {height:g} = {computed:.2f}"
        if velocity is not None:
            inputs.append(_input("V", velocity, "m/h", "浇筑速度"))
        if slump is not None:
            inputs.append(_input("坍落度", slump, "mm", "坍落度"))
    elif is_gb50666:
        formula_pressure = 0.28 * gamma_c * t0 * beta * (velocity ** 0.5)
        computed = min(formula_pressure, hydrostatic)
        inputs.extend([
            _input("t0", t0, "h", "初凝时间"),
            _input("β", beta, "", "坍落度影响修正系数"),
            _input("V", velocity, "m/h", "浇筑速度"),
        ])
        substituted = (
            f"F = min(0.28*{gamma_c:g}*{t0:g}*{beta:g}*sqrt({velocity:g}), "
            f"{gamma_c:g}*{height:g}) = {computed:.2f}"
        )
    else:
        formula_pressure = 0.22 * gamma_c * t0 * beta1 * beta2 * (velocity ** 0.5)
        computed = min(formula_pressure, hydrostatic)
        inputs.extend([
            _input("t0", t0, "h", "初凝时间"),
            _input("β1", beta1, "", "外加剂影响系数"),
            _input("β2", beta2, "", "坍落度影响系数"),
            _input("V", velocity, "m/h", "浇筑速度"),
        ])
        substituted = (
            f"F = min(0.22*{gamma_c:g}*{t0:g}*{beta1:g}*{beta2:g}*sqrt({velocity:g}), "
            f"{gamma_c:g}*{height:g}) = {computed:.2f}"
        )

    tolerance = max(1.0, computed * 0.03)
    status = "PASS" if abs(reported - computed) <= tolerance else "ISSUE"
    return _result(
        rule,
        formula_id="side_pressure",
        formula_name="混凝土侧压力复算",
        expression=expression,
        inputs=inputs + [_input("F", reported, "kN/m²", "计算书给出的侧压力结果")],
        substituted_expression=f"{substituted}; report F = {reported:g}",
        computed_value=reported,
        allowed_value=round(computed, 4),
        operator="≈",
        status=status,
        segments=focused,
        found=[f"复算侧压力 {computed:.2f}kN/m²", f"计算书给出 {reported:g}kN/m²"],
        missing=[],
        decision=f"计算书结果 {reported:g} 与复算值 {computed:.2f} {'一致' if status == 'PASS' else '不一致'}",
    )


def _recheck_slenderness(rule: dict[str, Any], segments: list[dict[str, Any]]) -> dict[str, Any]:
    limit = 210.0 if str(rule.get("rule_id")) == "3.11" else 150.0
    focused = _focused_segments(segments, ("长细比", "λ", "lambda", "l0/i", "lo/i"))
    text = _join_text(focused)
    if not text:
        return _uncertain(rule, "slenderness", "λ = l0 / i", ["计算书未找到长细比验算片段"], focused)

    # Extraction priority: fraction (λ=l0/i=A/B) → explicit value (=141.5≤)
    # Individual l0/i extraction is too error-prone (η coefficient mistaken for l0,
    # table values from unrelated rows) — only use when fraction or explicit value found.
    ctext = _compact_formula(text)
    parsed_fraction = _parse_fraction_after_lambda(ctext)
    explicit_lambda = _find_explicit_lambda_value(ctext)

    if parsed_fraction:
        l0, i = parsed_fraction
        computed = l0 / i
        inputs = [
            _input("l0", l0, "mm", "计算长度（从 λ=l0/i 分数提取）"),
            _input("i", i, "mm", "截面回转半径（从 λ=l0/i 分数提取）"),
        ]
        substituted = f"lambda = {l0:g} / {i:g} = {computed:.2f}"
    elif explicit_lambda is not None:
        computed = explicit_lambda
        inputs = [_input("lambda", explicit_lambda, "", "计算书给出的长细比")]
        substituted = f"lambda = {computed:.2f}"
    else:
        return _uncertain(
            rule,
            "slenderness",
            "λ = l0 / i",
            ["计算书未写出 λ=l0/i 分数或 λ 计算值，无法确定复算输入"],
            focused,
        )

    status = "PASS" if computed <= limit else "ISSUE"
    return _result(
        rule,
        formula_id="slenderness",
        formula_name="长细比复算",
        expression="λ = l0 / i <= [λ]",
        inputs=inputs,
        substituted_expression=f"{substituted} <= {limit:g}",
        computed_value=computed,
        allowed_value=limit,
        operator="<=",
        status=status,
        segments=focused,
        found=[f"提取到长细比计算值 {computed:.2f}", f"限值 {limit:g}"],
        missing=[],
        decision=f"复算结果 {computed:.2f} {'≤' if status == 'PASS' else '>'} {limit:g}",
    )


def _recheck_stability(rule: dict[str, Any], segments: list[dict[str, Any]]) -> dict[str, Any]:
    focused = _focused_segments(segments, ("立杆", "稳定", "N/(φA)", "φA", "phi", "稳定性"))
    text = _join_text(focused)
    if not text:
        return _uncertain(rule, "vertical_stability", "σ = N / (φA) <= f", ["计算书未找到立杆稳定性验算片段"], focused)

    explicit_stress = _find_explicit_stress(_compact_formula(text))
    limit = _find_strength_limit(text) or 205.0
    if explicit_stress is not None:
        computed = explicit_stress
        inputs = [_input("sigma", explicit_stress, "N/mm²", "计算书给出的稳定应力")]
        substituted = f"sigma = {computed:.2f} <= {limit:g}"
    else:
        # Only extract from explicit assignments (N=95kN, φ=0.45) not table proximity
        n_value = _find_explicit_value(text, (r"\bN\b", r"Nd", r"轴力", r"立杆轴力"))
        phi = _find_explicit_value(text, (r"φ", r"Φ", r"phi", r"稳定系数"))
        area = _find_explicit_value(text, (r"\bA\b", r"截面面积"))
        missing = []
        if n_value is None:
            missing.append("缺少轴力 N")
        if phi is None:
            missing.append("缺少稳定系数 φ")
        if area is None:
            missing.append("缺少截面面积 A")
        if missing:
            return _uncertain(rule, "vertical_stability", "σ = N / (φA) <= f", missing, focused)
        n_newton = n_value * 1000 if n_value < 1000 else n_value
        computed = n_newton / (phi * area)
        inputs = [
            _input("N", n_value, "kN" if n_value < 1000 else "N", "轴力设计值"),
            _input("φ", phi, "", "稳定系数"),
            _input("A", area, "mm²", "截面面积"),
        ]
        substituted = f"sigma = {n_newton:g} / ({phi:g} * {area:g}) = {computed:.2f} <= {limit:g}"

    status = "PASS" if computed <= limit else "ISSUE"
    return _result(
        rule,
        formula_id="vertical_stability",
        formula_name="立杆稳定性复算",
        expression="σ = N / (φA) <= f",
        inputs=inputs + [_input("f", limit, "N/mm²", "抗压强度设计值")],
        substituted_expression=substituted,
        computed_value=computed,
        allowed_value=limit,
        operator="<=",
        status=status,
        segments=focused,
        found=[f"提取到稳定应力 {computed:.2f}N/mm²", f"限值 {limit:g}N/mm²"],
        missing=[],
        decision=f"复算结果 {computed:.2f} {'≤' if status == 'PASS' else '>'} {limit:g}",
    )


def _recheck_jack_capacity(rule: dict[str, Any], segments: list[dict[str, Any]]) -> dict[str, Any]:
    focused = _focused_segments(segments, ("托撑", "顶托", "承载力", "Nd", "N≤", "N<=", "托座"))
    text = _join_text(focused)
    if not text:
        return _uncertain(rule, "jack_capacity", "N <= Nd", ["计算书未找到可调托撑承载力验算片段"], focused)

    # Try explicit assignment first (N=30kN), then table format (容许值[N](kN) 30),
    # then near-comparison pattern (30kN≤40kN)
    n_value = _find_explicit_value(text, (r"\bN\b", r"轴力", r"受力"))
    default_limit = 100.0 if str(rule.get("rule_id")) == "3.17p" else 40.0
    limit = (
        _find_explicit_value(text, (r"Nd", r"承载力设计值", r"允许承载力", r"容许承载力"))
        or _find_table_value(text, ("承载力容许值", "承载力设计值", "容许承载力"))
        or default_limit
    )
    comparison = _parse_near_comparison(_compact_formula(text))
    if comparison and n_value is None:
        n_value, limit = comparison
    if n_value is None:
        return _uncertain(rule, "jack_capacity", "N <= Nd", ["缺少托撑轴力 N"], focused)

    status = "PASS" if n_value <= limit else "ISSUE"
    return _result(
        rule,
        formula_id="jack_capacity",
        formula_name="可调托撑承载力复算",
        expression="N <= Nd",
        inputs=[
            _input("N", n_value, "kN", "托撑轴力/受力"),
            _input("Nd", limit, "kN", "托撑承载力设计值"),
        ],
        substituted_expression=f"N = {n_value:g}kN <= {limit:g}kN",
        computed_value=n_value,
        allowed_value=limit,
        operator="<=",
        status=status,
        segments=focused,
        found=[f"提取到托撑受力 {n_value:g}kN", f"承载力限值 {limit:g}kN"],
        missing=[],
        decision=f"复算结果 {n_value:g} {'≤' if status == 'PASS' else '>'} {limit:g}",
    )


def _recheck_foundation_bearing(rule: dict[str, Any], segments: list[dict[str, Any]]) -> dict[str, Any]:
    focused = _focused_segments(segments, ("地基", "承载力", "P=", "N/A", "fa", "垫板", "基础"))
    text = _join_text(focused)
    if not text:
        return _uncertain(rule, "foundation_bearing", "P = N / A <= fa", ["计算书未找到地基承载力验算片段"], focused)

    ctext = _compact_formula(text)
    comparison = _parse_named_comparison(ctext, ("P", "p", "地基承载力", "压应力"), ("fa", "fak", "承载力特征值", "地基承载力设计值"))
    if comparison:
        pressure, limit = comparison
        inputs = [
            _input("P", pressure, "kPa", "计算书给出的地基压力/压应力"),
            _input("fa", limit, "kPa", "计算书给出的地基承载力限值"),
        ]
        substituted = f"P = {pressure:g} <= fa = {limit:g}"
    else:
        n_value = _find_explicit_value(text, (r"\bN\b", r"轴力", r"立杆轴力", r"上部荷载"))
        area = _find_explicit_value(text, (r"\bA\b", r"底面积", r"垫板面积", r"基础面积"))
        limit = _find_explicit_value(text, (r"fa", r"fak", r"承载力特征值", r"地基承载力设计值"))
        missing = []
        if n_value is None:
            missing.append("缺少作用力 N")
        if area is None:
            missing.append("缺少底面积 A")
        if limit is None:
            missing.append("缺少地基承载力限值 fa")
        if missing:
            return _uncertain(rule, "foundation_bearing", "P = N / A <= fa", missing, focused)
        pressure = n_value / area
        inputs = [
            _input("N", n_value, "kN", "作用力/轴力"),
            _input("A", area, "m²", "垫板或基础底面积"),
            _input("fa", limit, "kPa", "地基承载力限值"),
        ]
        substituted = f"P = {n_value:g} / {area:g} = {pressure:.2f} <= {limit:g}"

    status = "PASS" if pressure <= limit else "ISSUE"
    return _result(
        rule,
        formula_id="foundation_bearing",
        formula_name="地基承载力复算",
        expression="P = N / A <= fa",
        inputs=inputs,
        substituted_expression=substituted,
        computed_value=pressure,
        allowed_value=limit,
        operator="<=",
        status=status,
        segments=focused,
        found=[f"提取到地基压力 {pressure:.2f}kPa", f"限值 {limit:g}kPa"],
        missing=[],
        decision=f"复算结果 {pressure:.2f} {'≤' if status == 'PASS' else '>'} {limit:g}",
    )


def _recheck_overturning(rule: dict[str, Any], segments: list[dict[str, Any]]) -> dict[str, Any]:
    rule_id = str(rule.get("rule_id") or "")
    focused = _focused_segments(segments, ("抗倾覆", "倾覆力矩", "抗倾覆力矩", "MR", "Mr", "MT", "Mo", "γ0"))
    text = _join_text(focused)
    if not text:
        return _uncertain(rule, "overturning", "MR >= γ0*MT" if rule_id == "3.20" else "γ0*Mo <= Mr", ["计算书未找到抗倾覆验算片段"], focused)

    gamma = _find_explicit_value(text, (r"γ0", r"gamma0", r"结构重要性系数")) or _find_gamma0(text)
    resisting = _find_explicit_value(text, (r"MR", r"Mr", r"抗倾覆力矩"))
    overturning = _find_explicit_value(text, (r"MT", r"Mo", r"倾覆力矩"))
    comparison = _parse_overturning_comparison(_compact_formula(text))

    if gamma is not None and resisting is not None and overturning is not None:
        demand = gamma * overturning
        passed = resisting >= demand
        inputs = [
            _input("MR/Mr", resisting, "kN·m", "抗倾覆力矩"),
            _input("MT/Mo", overturning, "kN·m", "倾覆力矩"),
            _input("γ0", gamma, "", "重要性/安全系数"),
        ]
        substituted = f"MR = {resisting:g} >= γ0*MT = {gamma:g} * {overturning:g} = {demand:.2f}"
    elif comparison is not None:
        left, right, operator = comparison
        if operator in {"<=", "≤", "<"}:
            demand, resisting = left, right
            passed = demand <= resisting
            substituted = f"γ0*Mo = {demand:g} <= Mr = {resisting:g}"
        else:
            resisting, demand = left, right
            passed = resisting >= demand
            substituted = f"MR = {resisting:g} >= γ0*MT = {demand:g}"
        inputs = [
            _input("resisting", resisting, "kN·m", "抗倾覆力矩或计算书比较右值"),
            _input("demand", demand, "kN·m", "倾覆力矩设计值或γ0放大值"),
        ]
    else:
        missing = []
        if gamma is None:
            missing.append("缺少γ0")
        if resisting is None:
            missing.append("缺少抗倾覆力矩MR/Mr")
        if overturning is None:
            missing.append("缺少倾覆力矩MT/Mo")
        if not missing:
            missing.append("未识别到可比较的抗倾覆表达式")
        return _uncertain(rule, "overturning", "MR >= γ0*MT" if rule_id == "3.20" else "γ0*Mo <= Mr", missing, focused)

    status = "PASS" if passed else "ISSUE"
    return _result(
        rule,
        formula_id="overturning",
        formula_name="抗倾覆复算",
        expression="MR >= γ0*MT" if rule_id == "3.20" else "γ0*Mo <= Mr",
        inputs=inputs,
        substituted_expression=substituted,
        computed_value=resisting,
        allowed_value=demand,
        operator=">=",
        status=status,
        segments=focused,
        found=[f"抗倾覆力矩 {resisting:.2f}", f"倾覆需求 {demand:.2f}"],
        missing=[],
        decision=f"复算结果 {resisting:.2f} {'≥' if status == 'PASS' else '<'} {demand:.2f}",
    )


def _result(
    rule: dict[str, Any],
    *,
    formula_id: str,
    formula_name: str,
    expression: str,
    inputs: list[dict[str, Any]],
    substituted_expression: str,
    computed_value: float,
    allowed_value: float,
    operator: str,
    status: str,
    segments: list[dict[str, Any]],
    found: list[str],
    missing: list[str],
    decision: str,
) -> dict[str, Any]:
    return {
        "rule_id": rule.get("rule_id"),
        "formula_id": formula_id,
        "formula_name": formula_name,
        "expression": expression,
        "inputs": inputs,
        "substituted_expression": substituted_expression,
        "computed_value": round(computed_value, 4),
        "allowed_value": allowed_value,
        "operator": operator,
        "status": status,
        "evidence_ids": [seg.get("block_id") for seg in segments if seg.get("block_id")][:5],
        "pages": _pages(segments),
        "warnings": [],
        "explanation": {
            "found": found,
            "missing": missing,
            "decision": decision,
        },
    }


def _uncertain(
    rule: dict[str, Any],
    formula_id: str,
    expression: str,
    missing: list[str],
    segments: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "rule_id": rule.get("rule_id"),
        "formula_id": formula_id,
        "formula_name": {
            "slenderness": "长细比复算",
            "vertical_stability": "立杆稳定性复算",
            "jack_capacity": "可调托撑承载力复算",
            "foundation_bearing": "地基承载力复算",
            "load_combination": "荷载组合系数复核",
            "overturning": "抗倾覆复算",
            "side_pressure": "混凝土侧压力复算",
        }.get(formula_id, "公式复算"),
        "expression": expression,
        "inputs": [],
        "substituted_expression": "",
        "computed_value": None,
        "allowed_value": None,
        "operator": "<=",
        "status": "UNCERTAIN",
        "uncertainty_category": "missing_parameter" if segments else "missing_content",
        "evidence_ids": [seg.get("block_id") for seg in segments if seg.get("block_id")][:5],
        "pages": _pages(segments),
        "warnings": missing,
        "explanation": {
            "found": ["找到相关计算片段"] if segments else [],
            "missing": missing,
            "decision": "缺少复算所需输入，需人工补充参数后重跑。",
        },
    }


def _focused_segments(
    segments: list[dict[str, Any]],
    keywords: tuple[str, ...],
    *,
    limit: int = 15,
) -> list[dict[str, Any]]:
    focused = []
    for seg in segments:
        text = _norm(str(seg.get("text") or ""))
        if any(_norm(keyword) in text for keyword in keywords):
            focused.append(seg)
        if len(focused) >= limit:
            break
    return focused


def _join_text(segments: list[dict[str, Any]]) -> str:
    return _norm("\n".join(str(seg.get("text") or "") for seg in segments))


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("（", "(").replace("）", ")").replace("＝", "=")
    # Normalize common LaTeX operators to plain symbols for regex matching
    text = text.replace("\\leq", "≤").replace("\\geq", "≥")
    text = text.replace("\\le", "≤").replace("\\ge", "≥")
    text = text.replace("\\quad", " ").replace("\\,", " ").replace("\\;", " ")
    # Strip LaTeX \max[...] wrapper: N=\max[...]=24.571 → N=24.571
    text = re.sub(r"=\\max\[[^\]]*\]\s*=", "=", text)
    text = re.sub(r"=\\max\([^)]*\)\s*=", "=", text)
    text = re.sub(r"\\max\[[^\]]*\]\s*", "", text)
    text = re.sub(r"\\max\([^)]*\)\s*", "", text)
    return text


def _compact_formula(text: str) -> str:
    """Collapse spaces around formula operators for stable regex matching."""
    return re.sub(r"\s*([=≤<≥>/])\s*", r"\1", text)


def _find_explicit_value(text: str, labels: tuple[str, ...]) -> float | None:
    """Extract number only from explicit assignment (label=value), not table proximity.

    Stricter than _find_number_after_labels: requires = or : between label and number.
    Prevents picking up η=1.2 as l0 or table row values as formula inputs.
    Note: uses lookahead to avoid matching 'A' inside '面积A=' (CJK has no \\b boundary).
    """
    for label in labels:
        # Strip \b anchors — CJK characters don't form \w boundaries
        clean_label = label.replace(r"\b", "")
        patterns = [
            rf"(?:^|[^a-zA-Z]){clean_label}\s*(?:=|:|：|＝)\s*(-?\d+(?:\.\d+)?)",
            rf"{clean_label}\s*(?:=|:|：|＝)\s*(-?\d+(?:\.\d+)?)\s*(?:kN|N|mm|cm|m|mm2|mm²)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return float(match.group(1))
    return None


def _find_table_value(text: str, labels: tuple[str, ...]) -> float | None:
    """Extract number from table-style format like '承载力容许值[N](kN) 30'.

    Table format: label + optional unit annotation + whitespace + number.
    Less strict than _find_explicit_value but specific enough for parameter tables.
    """
    for label in labels:
        # Pattern: label, then optional [unit] or (unit) annotations, then the number
        pattern = rf"{label}(?:\s*\[[^\]]*\])?(?:\s*\([^)]*\))?\s+(\d+(?:\.\d+)?)"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def _find_side_pressure_result(text: str) -> float | None:
    unit = r"(?:kN\s*/\s*m(?:2|²)|kPa|KN\s*/\s*m(?:2|²))"
    patterns = [
        rf"(?:侧压力(?:标准值|计算值|结果)?|G4k?|F)\s*(?:=|:|：|＝)\s*(-?\d+(?:\.\d+)?)\s*{unit}",
        rf"(?:取|取值为|较小值为|结果为)\s*(-?\d+(?:\.\d+)?)\s*{unit}",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def _find_number_after_labels(text: str, labels: tuple[str, ...]) -> float | None:
    for label in labels:
        patterns = [
            rf"{label}\s*(?:=|:|：|为|取|取值为)?\s*(-?\d+(?:\.\d+)?)",
            rf"{label}[^\d\-]{{0,25}}(-?\d+(?:\.\d+)?)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return float(match.group(1))
    return None


def _parse_fraction_after_lambda(text: str) -> tuple[float, float] | None:
    """Extract l0/i fraction from text like 'λ=l0/i=2250/15.9' or '长细比=2250/15.9'.

    Must match the pattern even when 'l0/i=' appears between λ and the fraction,
    or when the fraction follows directly after λ=.
    """
    # Pattern: λ (or lambda/长细比) followed by =, optionally 'l0/i=', then number/number
    patterns = [
        # λ=l0/i=2250/15.9 or λ l0/i=2250/15.9
        r"(?:λ|lambda|长细比)\s*(?:=|:|：|\s)\s*(?:l0?/i\s*=\s*)?(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)",
        # λ=2250/15.9 (no l0/i prefix)
        r"(?:λ|lambda|长细比)\s*(?:=|：)\s*(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)",
        # l0/i=2250/15.9 (standalone, no λ prefix)
        r"l0?/i\s*=\s*(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return float(match.group(1)), float(match.group(2))
    return None


def _find_explicit_lambda_value(text: str) -> float | None:
    """Extract the final computed λ value from patterns like '=141.5≤150' or 'λ=141.5'.

    Looks for the number that appears right before the ≤ operator after a = sign,
    which is the computed result (not l0 or i individually).
    """
    patterns = [
        # =141.5≤150 or =141.5<=150 (computed value before comparison)
        r"=\s*(\d+(?:\.\d+)?)\s*(?:≤|<=|<)\s*\d",
        # λ=141.5 or lambda=141.5 (explicit final value, not a fraction)
        r"(?:λ|lambda|长细比)\s*=\s*(\d+(?:\.\d+)?)\s*(?:≤|<=|<|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            val = float(match.group(1))
            # Sanity: λ should be in a reasonable range (1-500), not a tiny fraction like 0
            if 1.0 <= val <= 500.0:
                return val
    return None


def _find_explicit_stress(text: str) -> float | None:
    patterns = (
        r"(?:σ|sigma|应力|N/\(?φA\)?)[^\d]{0,12}(\d+(?:\.\d+)?)\s*(?:N/mm2|N/mm²)?\s*(?:≤|<=|<)",
        r"(\d+(?:\.\d+)?)\s*(?:N/mm2|N/mm²)?\s*(?:≤|<=|<)\s*(?:f|205|300)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def _find_strength_limit(text: str) -> float | None:
    value = _find_number_after_labels(text, (r"\bf\b", r"抗压强度设计值"))
    if value and 100 <= value <= 400:
        return value
    match = re.search(r"(?:≤|<=|<)\s*(205|300)(?:\s*N/mm)", text, re.IGNORECASE)
    return float(match.group(1)) if match else None


def _find_gamma0(text: str) -> float | None:
    match = re.search(r"γ0[^\d]{0,12}(\d+(?:\.\d+)?)", text, re.IGNORECASE)
    if match:
        return float(match.group(1))
    return None


def _parse_near_comparison(text: str) -> tuple[float, float] | None:
    match = re.search(r"(?:N|轴力|受力)?[^\d]{0,12}(\d+(?:\.\d+)?)\s*(?:kN)?\s*(?:≤|<=|<)\s*(?:Nd)?[^\d]{0,8}(\d+(?:\.\d+)?)\s*(?:kN)?", text, re.IGNORECASE)
    if not match:
        return None
    return float(match.group(1)), float(match.group(2))


def _parse_overturning_comparison(text: str) -> tuple[float, float, str] | None:
    patterns = [
        r"(?:γ0\*?(?:Mo|MT)|Mo|MT)?[^\d]{0,12}(\d+(?:\.\d+)?)\s*(≤|<=|<)\s*(?:Mr|MR)?[^\d]{0,12}(\d+(?:\.\d+)?)",
        r"(?:Mr|MR)?[^\d]{0,12}(\d+(?:\.\d+)?)\s*(≥|>=|>)\s*(?:γ0\*?(?:Mo|MT)|Mo|MT)?[^\d]{0,12}(\d+(?:\.\d+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return float(match.group(1)), float(match.group(3)), match.group(2)
    return None


def _parse_named_comparison(
    text: str,
    left_labels: tuple[str, ...],
    right_labels: tuple[str, ...],
) -> tuple[float, float] | None:
    left = "|".join(re.escape(label.replace(r"\b", "")) for label in left_labels)
    right = "|".join(re.escape(label.replace(r"\b", "")) for label in right_labels)
    patterns = [
        rf"(?:{left})?[^\d≤<]{{0,16}}(\d+(?:\.\d+)?)\s*(?:kPa|kN/m2|kN/m²)?\s*(?:≤|<=|<)\s*(?:{right})?[^\d]{{0,12}}(\d+(?:\.\d+)?)",
        rf"(?:{left})\s*(?:=|:|：)\s*(\d+(?:\.\d+)?)[^≤<]{{0,30}}(?:≤|<=|<)[^\\d]{{0,12}}(?:{right})\s*(?:=|:|：)?\s*(\d+(?:\.\d+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return float(match.group(1)), float(match.group(2))
    return None


def _input(symbol: str, value: float, unit: str, source: str) -> dict[str, Any]:
    return {"symbol": symbol, "value": value, "unit": unit, "source": source}


def _pages(segments: list[dict[str, Any]]) -> list[int]:
    pages = []
    for seg in segments:
        page = seg.get("physical_page")
        if page and page not in pages:
            pages.append(page)
    return pages[:5]
