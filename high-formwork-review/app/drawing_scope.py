"""Drawing Scope：Evidence 工程对象范围（member_type + location）。

Task 7A 范围：不 compare value（属于 Task 7B）、不调 LLM/VLM、
不接 Pipeline、不写 ProjectFacts。

本轮只支持两个维度：

- ``member_type`` 取值 ``beam`` / ``slab`` / ``column``
- ``location``   取值 ``beam_bottom`` / ``slab_bottom``

无法识别的输入一律通过「不写该 key / scope 为空字典」表达，
绝不写 ``"unknown"`` 之类的假字符串。

公共函数：

- :func:`normalize_scope`  标准化显式 scope dict
- :func:`infer_scope_from_text`  从 evidence 文本按 alias 邻域推断 scope
- :func:`resolve_evidence_scope`  合并 explicit + inferred
- :func:`align_scopes`   返回 ``SCOPE_COMPATIBLE`` / ``SCOPE_INCOMPATIBLE`` / ``SCOPE_UNKNOWN``
"""

from __future__ import annotations

from typing import Iterable, Mapping


SCOPE_COMPATIBLE = "compatible"
SCOPE_INCOMPATIBLE = "incompatible"
SCOPE_UNKNOWN = "unknown"


_VALID_MEMBER_TYPES = frozenset({"beam", "slab", "column"})
_VALID_LOCATIONS = frozenset({"beam_bottom", "slab_bottom"})

_MEMBER_TYPE_FROM_LOCATION: dict[str, str] = {
    "beam_bottom": "beam",
    "slab_bottom": "slab",
}

# 强 location 信号（命中即返回 member_type + location）。
# "梁板" 类会同时覆盖梁 + 板 → ambiguous → 不写任何 key。
_LOCATION_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("梁底", "beam_bottom"),
    ("楼板底", "slab_bottom"),
    ("板底", "slab_bottom"),
)
_AMBIGUOUS_KEYWORDS: tuple[str, ...] = ("梁板支撑", "梁板模板", "梁板")

# 仅 member_type 信号（命中即返回 member_type，无 location）。
_MEMBER_TYPE_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("板模板", "slab"),
    ("梁模板", "beam"),
    ("梁支撑", "beam"),
    ("楼板", "slab"),
    ("柱", "column"),
    ("梁", "beam"),
)


def normalize_scope(scope: Mapping[str, object] | None) -> dict[str, str]:
    """只保留 ``member_type`` / ``location``，非法值整 key 丢弃，``location`` 隐含 member_type。"""
    if not isinstance(scope, Mapping):
        return {}
    member = _canon_member(scope.get("member_type"))
    location = _canon_location(scope.get("location"))
    if location and not member:
        member = _MEMBER_TYPE_FROM_LOCATION.get(location)
    out: dict[str, str] = {}
    if member:
        out["member_type"] = member
    if location:
        out["location"] = location
    return out


def infer_scope_from_text(
    text: str | None,
    aliases: Iterable[str] = (),
) -> dict[str, str]:
    """按 alias 邻域（前后 60 字）推断；alias 未命中退化为整段（≤300 字）。"""
    if not text:
        return {}
    windows: list[str] = []
    for alias in aliases:
        if not alias:
            continue
        idx = text.find(alias)
        if idx < 0:
            continue
        windows.append(text[max(0, idx - 60): idx + len(alias) + 60])
    if not windows:
        windows.append(text[:300])
    for window in windows:
        if _is_ambiguous(window):
            return {}
        scope = _scan_window(window)
        if scope:
            return scope
    return {}


def resolve_evidence_scope(
    explicit_scope: Mapping[str, object] | None,
    evidence_text: str | None,
    aliases: Iterable[str] = (),
) -> dict[str, str]:
    """合并 explicit + inferred。冲突 → ``{}``（保守）。"""
    explicit = normalize_scope(explicit_scope)
    inferred = infer_scope_from_text(evidence_text, aliases)
    if not explicit:
        return inferred
    if not inferred:
        return explicit
    if explicit == inferred:
        return explicit
    merged: dict[str, str] = {}
    for key in ("member_type", "location"):
        l_val, r_val = explicit.get(key), inferred.get(key)
        if l_val and r_val and l_val != r_val:
            return {}
        merged[key] = l_val or r_val  # type: ignore[assignment]
    return {k: v for k, v in merged.items() if v}


def align_scopes(
    left_scope: Mapping[str, object] | None,
    right_scope: Mapping[str, object] | None,
) -> str:
    """同 dim 同值 → ``compatible``；同 dim 不同值 → ``incompatible``；不对称 / 任一空 → ``unknown``。"""
    left = normalize_scope(left_scope)
    right = normalize_scope(right_scope)
    if not left or not right or set(left.keys()) != set(right.keys()):
        return SCOPE_UNKNOWN
    for key, l_val in left.items():
        r_val = right.get(key)
        if not r_val:
            return SCOPE_UNKNOWN
        if r_val != l_val:
            return SCOPE_INCOMPATIBLE
    return SCOPE_COMPATIBLE


def _canon_member(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    s = value.strip()
    if s in _VALID_MEMBER_TYPES or s in {"梁", "板", "楼板", "柱"}:
        return {"梁": "beam", "板": "slab", "楼板": "slab", "柱": "column"}.get(s, s)
    return None


def _canon_location(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    s = value.strip()
    if s in _VALID_LOCATIONS or s in {"梁底", "板底", "楼板底"}:
        return {"梁底": "beam_bottom", "板底": "slab_bottom", "楼板底": "slab_bottom"}.get(s, s)
    return None


def _scan_window(window: str) -> dict[str, str]:
    for keyword, mapped in _LOCATION_KEYWORDS:
        if keyword in window:
            member = _MEMBER_TYPE_FROM_LOCATION.get(mapped)
            if not member:
                return {}
            return {"member_type": member, "location": mapped}
    for keyword, mapped in _MEMBER_TYPE_KEYWORDS:
        if keyword in window:
            return {"member_type": mapped}
    return {}


def _is_ambiguous(window: str) -> bool:
    return any(k in window for k in _AMBIGUOUS_KEYWORDS)
