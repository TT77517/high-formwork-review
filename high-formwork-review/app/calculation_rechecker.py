"""轻量确定性计算复核。

只处理首批高价值公式；所有输入必须来自计算书证据片段，缺值不推测。
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any


SUPPORTED_RULES = {"3.9", "3.11", "3.12", "3.14", "3.15", "3.17"}


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
    if rule_id in {"3.9", "3.12", "3.15"}:
        return _recheck_stability(rule, segments)
    if rule_id == "3.17":
        return _recheck_jack_capacity(rule, segments)
    return None


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
    focused = _focused_segments(segments, ("托撑", "顶托", "承载力", "Nd", "N≤", "N<="))
    text = _join_text(focused)
    if not text:
        return _uncertain(rule, "jack_capacity", "N <= Nd", ["计算书未找到可调托撑承载力验算片段"], focused)

    n_value = _find_explicit_value(text, (r"\bN\b", r"轴力", r"受力"))
    limit = _find_explicit_value(text, (r"Nd", r"承载力设计值", r"允许承载力", r"容许承载力")) or 40.0
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
    limit: int = 5,
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
    return text.replace("（", "(").replace("）", ")").replace("＝", "=")


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


def _parse_near_comparison(text: str) -> tuple[float, float] | None:
    match = re.search(r"(?:N|轴力|受力)?[^\d]{0,12}(\d+(?:\.\d+)?)\s*(?:kN)?\s*(?:≤|<=|<)\s*(?:Nd)?[^\d]{0,8}(\d+(?:\.\d+)?)\s*(?:kN)?", text, re.IGNORECASE)
    if not match:
        return None
    return float(match.group(1)), float(match.group(2))


def _input(symbol: str, value: float, unit: str, source: str) -> dict[str, Any]:
    return {"symbol": symbol, "value": value, "unit": unit, "source": source}


def _pages(segments: list[dict[str, Any]]) -> list[int]:
    pages = []
    for seg in segments:
        page = seg.get("physical_page")
        if page and page not in pages:
            pages.append(page)
    return pages[:5]
