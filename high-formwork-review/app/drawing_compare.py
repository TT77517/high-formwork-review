"""Drawing Evidence Comparator：确定性六状态结果模型（Task 7B）。

输入：同 fact_id 的 ``TextEvidence`` / ``DrawingEvidence`` 列表（duck typing）
输出：:class:`DrawingComparisonResult`，六状态之一：

- ``CONSISTENT`` / ``CONFLICT``  /  ``TEXT_ONLY`` / ``DRAWING_ONLY``
- ``UNCERTAIN`` / ``NOT_FOUND``

不依赖 LLM / VLM；纯 deterministic Python。
不 ``import`` :mod:`app.drawing_agent`；仅通过 ``getattr`` 读取 Evidence 字段。
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

from .drawing_scope import align_scopes, normalize_scope


# --- 6 个状态常量 -----------------------------------------------------------

CONSISTENT = "CONSISTENT"
CONFLICT = "CONFLICT"
TEXT_ONLY = "TEXT_ONLY"
DRAWING_ONLY = "DRAWING_ONLY"
UNCERTAIN = "UNCERTAIN"
NOT_FOUND = "NOT_FOUND"


# --- Result model -----------------------------------------------------------


@dataclass(frozen=True)
class DrawingComparisonResult:
    fact_id: str
    status: str
    reason: str
    scope_alignment: str = "unknown"
    text_value: object | None = None
    drawing_value: object | None = None
    text_unit: str | None = None
    drawing_unit: str | None = None
    text_page: Optional[int] = None
    drawing_page: Optional[int] = None
    text_evidence_count: int = 0
    drawing_evidence_count: int = 0
    comparable_pair_count: int = 0


# --- Reason 优先级（Section 58） -------------------------------------------

_REASON_PRIORITY = (
    "scope_unknown", "scope_incompatible",
    "unit_incomplete", "unit_mismatch",
    "unsupported_value", "missing_comparable_value",
    "no_comparable_pair", "values_equal", "values_differ",
    "orientation_unknown", "multiple_comparable_pairs",
    "text_evidence_only", "drawing_evidence_only", "no_evidence",
)


def _max_priority_reason(reasons: list[str]) -> str:
    return min(reasons, key=lambda r: _REASON_PRIORITY.index(r) if r in _REASON_PRIORITY else 999)


# --- Public entry -----------------------------------------------------------


def compare_evidence_sets(
    fact_id: str,
    text_evidence: Iterable[object],
    drawing_evidence: Iterable[object],
) -> DrawingComparisonResult:
    """对同 fact_id 的双侧 Evidence 列表做确定性比较。"""
    t_list = [e for e in (text_evidence or []) if e is not None and getattr(e, "fact_id", None) == fact_id]
    d_list = [e for e in (drawing_evidence or []) if e is not None and getattr(e, "fact_id", None) == fact_id]

    if not t_list and not d_list:
        return DrawingComparisonResult(fact_id=fact_id, status=NOT_FOUND, reason="no_evidence")
    if t_list and not d_list:
        return DrawingComparisonResult(fact_id=fact_id, status=TEXT_ONLY, reason="text_evidence_only",
                                       text_evidence_count=len(t_list))
    if d_list and not t_list:
        return DrawingComparisonResult(fact_id=fact_id, status=DRAWING_ONLY, reason="drawing_evidence_only",
                                       drawing_evidence_count=len(d_list))
    return _compare_pairs(fact_id, _dedup(t_list), _dedup(d_list))


# --- Dedup by (scope, value, unit) signature ------------------------------


def _dedup(evidence_list: list[object]) -> list[object]:
    seen: dict[tuple, object] = {}
    for ev in evidence_list:
        scope = normalize_scope(getattr(ev, "scope", None))
        val = _normalize_value(getattr(ev, "value", None))
        unit = _normalize_unit(getattr(ev, "unit", None))
        sig = (tuple(sorted(scope.items())), val, unit)
        if sig not in seen:
            seen[sig] = ev
    return list(seen.values())


# --- Pair comparison --------------------------------------------------------


def _compare_pairs(fact_id: str, t_list: list[object], d_list: list[object]) -> DrawingComparisonResult:
    """对每对 (t, d) 跑 scope/unit/value gate，统计一致 pair。"""
    pairs: list[tuple[object, object]] = []
    reasons: list[str] = []
    last_align = "unknown"

    for t_ev in t_list:
        for d_ev in d_list:
            align = align_scopes(getattr(t_ev, "scope", None), getattr(d_ev, "scope", None))
            last_align = align
            if align == "incompatible":
                reasons.append("scope_incompatible")
                continue
            if align == "unknown":
                reasons.append("scope_unknown")
                continue
            unit = _unit_gate(getattr(t_ev, "unit", None), getattr(d_ev, "unit", None))
            if unit == "incomplete":
                reasons.append("unit_incomplete")
                continue
            if unit == "mismatch":
                reasons.append("unit_mismatch")
                continue
            t_val = getattr(t_ev, "value", None)
            d_val = getattr(d_ev, "value", None)
            if t_val is None or d_val is None:
                reasons.append("missing_comparable_value")
                continue
            t_norm = _normalize_value(t_val)
            d_norm = _normalize_value(d_val)
            if t_norm is None or d_norm is None or not _is_valid_pair(t_norm, d_norm):
                reasons.append("unsupported_value")
                continue
            cmp = _compare(t_norm, d_norm)
            if cmp == "orientation_unknown":
                reasons.append("orientation_unknown")
                continue
            if cmp == "unsupported":
                reasons.append("unsupported_value")
                continue
            pairs.append((t_ev, d_ev))
            reasons.append("values_equal" if cmp == "equal" else "values_differ")

    if not pairs:
        return DrawingComparisonResult(
            fact_id=fact_id, status=UNCERTAIN,
            reason=_max_priority_reason(reasons) if reasons else "no_comparable_pair",
            scope_alignment=last_align,
            text_evidence_count=len(t_list), drawing_evidence_count=len(d_list),
        )

    verdicts = {_compare(_normalize_value(getattr(t, "value", None)),
                         _normalize_value(getattr(d, "value", None))) for t, d in pairs}
    if len(verdicts) > 1 or len(pairs) > 1 and not _all_agree(pairs):
        return DrawingComparisonResult(
            fact_id=fact_id, status=UNCERTAIN, reason="multiple_comparable_pairs",
            scope_alignment="compatible",
            text_evidence_count=len(t_list), drawing_evidence_count=len(d_list),
            comparable_pair_count=len(pairs),
        )

    t_ev, d_ev = pairs[0]
    is_equal = next(iter(verdicts)) == "equal"
    return DrawingComparisonResult(
        fact_id=fact_id, status=CONSISTENT if is_equal else CONFLICT,
        reason="values_equal" if is_equal else "values_differ",
        scope_alignment="compatible",
        text_value=getattr(t_ev, "value", None), drawing_value=getattr(d_ev, "value", None),
        text_unit=getattr(t_ev, "unit", None), drawing_unit=getattr(d_ev, "unit", None),
        text_page=getattr(t_ev, "page", None), drawing_page=getattr(d_ev, "page", None),
        text_evidence_count=len(t_list), drawing_evidence_count=len(d_list),
        comparable_pair_count=len(pairs),
    )


def _all_agree(pairs: list[tuple[object, object]]) -> bool:
    return len({
        _compare(_normalize_value(getattr(t, "value", None)),
                 _normalize_value(getattr(d, "value", None)))
        for t, d in pairs
    }) == 1


# --- Unit gate --------------------------------------------------------------


def _normalize_unit(unit: object) -> Optional[str]:
    if not isinstance(unit, str):
        return None
    s = unit.strip().lower()
    return s or None


def _unit_gate(t: object, d: object) -> str:
    tn, dn = _normalize_unit(t), _normalize_unit(d)
    if tn is None and dn is None:
        return "ok"
    if tn is None or dn is None:
        return "incomplete"
    return "ok" if tn == dn else "mismatch"


# --- Value normalize --------------------------------------------------------

_2D_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*[xX×*·]\s*(\d+(?:\.\d+)?)\s*$")
_NUM_RE = re.compile(r"^\s*-?\d+(?:\.\d+)?\s*$")


def _normalize_value(v: object) -> object:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(v, (list, tuple)) and len(v) == 2:
        try:
            a, b = float(v[0]), float(v[1])  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        if any(math.isnan(x) or math.isinf(x) for x in (a, b)):
            return None
        return (a, b)
    if isinstance(v, str):
        s = v.strip()
        m = _2D_RE.match(s)
        if m:
            return (float(m.group(1)), float(m.group(2)))
        if _NUM_RE.match(s):
            return float(s)
        return None
    return None


def _is_valid_pair(t: object, d: object) -> bool:
    for v in (t, d):
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return False
        if isinstance(v, tuple) and any(math.isnan(x) or math.isinf(x) for x in v):
            return False
    return True


# --- Compare ----------------------------------------------------------------

_TOL = 1e-9


def _compare(t: object, d: object) -> str:
    if t is None or d is None:
        return "unsupported"
    t2d, d2d = isinstance(t, tuple), isinstance(d, tuple)
    if t2d != d2d:
        return "unsupported"
    if not t2d:
        return "equal" if math.isclose(float(t), float(d), rel_tol=0.0, abs_tol=_TOL) else "differ"
    # 2D
    if math.isclose(t[0], d[0], rel_tol=0.0, abs_tol=_TOL) and math.isclose(t[1], d[1], rel_tol=0.0, abs_tol=_TOL):
        return "equal"
    if math.isclose(t[0], d[1], rel_tol=0.0, abs_tol=_TOL) and math.isclose(t[1], d[0], rel_tol=0.0, abs_tol=_TOL) \
            and not (math.isclose(t[0], t[1], rel_tol=0.0, abs_tol=_TOL) and math.isclose(d[0], d[1], rel_tol=0.0, abs_tol=_TOL)):
        return "orientation_unknown"
    return "differ"
