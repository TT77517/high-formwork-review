"""Task 7B：drawing_compare 单元测试。

8 个测试函数：

1. presence 三态（NOT_FOUND / TEXT_ONLY / DRAWING_ONLY）
2. scalar CONSISTENT（150 vs 150.0, MM, beam_bottom）
3. scalar CONFLICT（150 vs 160, mm, beam_bottom）
4. scope gate（incompatible / unknown）
5. unit gate（mm vs m / mm vs None）
6. 2D compare（[900,900] vs "900×900" / [900,900] vs [1200,1200]）
7. 2D orientation safety（[900,1200] vs [1200,900]）
8. duplicate collapse + ambiguity
"""

from __future__ import annotations

from types import SimpleNamespace

from app.drawing_compare import (
    CONSISTENT,
    CONFLICT,
    DRAWING_ONLY,
    NOT_FOUND,
    TEXT_ONLY,
    UNCERTAIN,
    compare_evidence_sets,
)


def _ev(fact_id: str, value, unit=None, page=None, scope=None, source_type="text") -> SimpleNamespace:
    return SimpleNamespace(
        fact_id=fact_id, value=value, unit=unit, page=page,
        scope=scope or {}, source_type=source_type,
    )


# ---------------------------------------------------------------------------
# Test 1: presence 三态
# ---------------------------------------------------------------------------


def test_compare_presence_three_states() -> None:
    # none / none → NOT_FOUND
    r1 = compare_evidence_sets("upright_spacing", [], [])
    assert r1.status == NOT_FOUND
    assert r1.reason == "no_evidence"
    assert r1.text_evidence_count == 0 and r1.drawing_evidence_count == 0

    # text / none → TEXT_ONLY
    t = [_ev("upright_spacing", 900, "mm", 5)]
    r2 = compare_evidence_sets("upright_spacing", t, [])
    assert r2.status == TEXT_ONLY
    assert r2.reason == "text_evidence_only"
    assert r2.text_evidence_count == 1 and r2.drawing_evidence_count == 0

    # none / drawing → DRAWING_ONLY
    d = [_ev("upright_spacing", 900, "mm", 88, source_type="ocr")]
    r3 = compare_evidence_sets("upright_spacing", [], d)
    assert r3.status == DRAWING_ONLY
    assert r3.reason == "drawing_evidence_only"
    assert r3.drawing_evidence_count == 1 and r3.text_evidence_count == 0


# ---------------------------------------------------------------------------
# Test 2: scalar CONSISTENT
# ---------------------------------------------------------------------------


def test_compare_scalar_consistent() -> None:
    beam_bot = {"member_type": "beam", "location": "beam_bottom"}
    t = [_ev("upright_spacing", 150, "mm", 12, scope=beam_bot)]
    d = [_ev("upright_spacing", 150.0, "MM", 88, scope=beam_bot, source_type="vlm")]
    r = compare_evidence_sets("upright_spacing", t, d)
    assert r.status == CONSISTENT
    assert r.reason == "values_equal"
    assert r.scope_alignment == "compatible"
    assert r.comparable_pair_count == 1
    assert r.text_value == 150 and r.drawing_value == 150.0
    assert r.text_unit == "mm" and r.drawing_unit == "MM"


# ---------------------------------------------------------------------------
# Test 3: scalar CONFLICT（Task 6.1 经典场景）
# ---------------------------------------------------------------------------


def test_compare_scalar_conflict() -> None:
    beam_bot = {"member_type": "beam", "location": "beam_bottom"}
    t = [_ev("head_jack_insertion_length", 160, "mm", 12, scope=beam_bot)]
    d = [_ev("head_jack_insertion_length", 150, "mm", 88, scope=beam_bot, source_type="vlm")]
    r = compare_evidence_sets("head_jack_insertion_length", t, d)
    assert r.status == CONFLICT
    assert r.reason == "values_differ"
    assert r.scope_alignment == "compatible"
    assert r.comparable_pair_count == 1


# ---------------------------------------------------------------------------
# Test 4: scope gate（incompatible + unknown）
# ---------------------------------------------------------------------------


def test_compare_scope_gate_blocks_value_compare() -> None:
    # incompatible：beam_bottom vs slab_bottom → 不能 CONFLICT
    beam_bot = {"member_type": "beam", "location": "beam_bottom"}
    slab_bot = {"member_type": "slab", "location": "slab_bottom"}
    t = [_ev("upright_spacing", [900, 900], "mm", 12, scope=beam_bot)]
    d = [_ev("upright_spacing", [1200, 1200], "mm", 88, scope=slab_bot, source_type="vlm")]
    r1 = compare_evidence_sets("upright_spacing", t, d)
    assert r1.status == UNCERTAIN
    assert r1.reason == "scope_incompatible"
    assert r1.status != CONFLICT

    # unknown：beam_bottom vs beam only → 即使 value 相同也不能 CONSISTENT
    beam_only = {"member_type": "beam"}
    t2 = [_ev("upright_spacing", 150, "mm", 12, scope=beam_bot)]
    d2 = [_ev("upright_spacing", 150, "mm", 88, scope=beam_only, source_type="vlm")]
    r2 = compare_evidence_sets("upright_spacing", t2, d2)
    assert r2.status == UNCERTAIN
    assert r2.reason == "scope_unknown"
    assert r2.status != CONSISTENT


# ---------------------------------------------------------------------------
# Test 5: unit gate
# ---------------------------------------------------------------------------


def test_compare_unit_gate_no_conversion() -> None:
    beam_bot = {"member_type": "beam", "location": "beam_bottom"}
    # mm vs m → UNCERTAIN (unit_mismatch, 不做换算)
    t = [_ev("upright_spacing", 150, "mm", 12, scope=beam_bot)]
    d = [_ev("upright_spacing", 0.15, "m", 88, scope=beam_bot, source_type="vlm")]
    r1 = compare_evidence_sets("upright_spacing", t, d)
    assert r1.status == UNCERTAIN
    assert r1.reason == "unit_mismatch"

    # mm vs None → UNCERTAIN (unit_incomplete)
    d2 = [_ev("upright_spacing", 150, None, 88, scope=beam_bot, source_type="vlm")]
    r2 = compare_evidence_sets("upright_spacing", t, d2)
    assert r2.status == UNCERTAIN
    assert r2.reason == "unit_incomplete"


# ---------------------------------------------------------------------------
# Test 6: 2D compare
# ---------------------------------------------------------------------------


def test_compare_2d_equal_and_conflict() -> None:
    beam_bot = {"member_type": "beam", "location": "beam_bottom"}
    # [900,900] vs "900×900" → CONSISTENT
    t = [_ev("upright_spacing", [900, 900], "mm", 12, scope=beam_bot)]
    d = [_ev("upright_spacing", "900×900", "mm", 88, scope=beam_bot, source_type="vlm")]
    r1 = compare_evidence_sets("upright_spacing", t, d)
    assert r1.status == CONSISTENT
    assert r1.reason == "values_equal"

    # [900,900] vs [1200,1200] → CONFLICT
    d2 = [_ev("upright_spacing", [1200, 1200], "mm", 88, scope=beam_bot, source_type="vlm")]
    r2 = compare_evidence_sets("upright_spacing", t, d2)
    assert r2.status == CONFLICT
    assert r2.reason == "values_differ"


# ---------------------------------------------------------------------------
# Test 7: 2D orientation safety
# ---------------------------------------------------------------------------


def test_compare_2d_orientation_unknown() -> None:
    beam_bot = {"member_type": "beam", "location": "beam_bottom"}
    # [900, 1200] vs [1200, 900] → UNCERTAIN（orientation_unknown, 不能 CONFLICT）
    t = [_ev("upright_spacing", [900, 1200], "mm", 12, scope=beam_bot)]
    d = [_ev("upright_spacing", [1200, 900], "mm", 88, scope=beam_bot, source_type="vlm")]
    r = compare_evidence_sets("upright_spacing", t, d)
    assert r.status == UNCERTAIN
    assert r.reason == "orientation_unknown"
    assert r.status != CONFLICT


# ---------------------------------------------------------------------------
# Test 8: duplicate collapse + ambiguity
# ---------------------------------------------------------------------------


def test_compare_duplicate_collapse_and_ambiguity() -> None:
    beam_bot = {"member_type": "beam", "location": "beam_bottom"}
    # 重复 collapse：text 两条 150mm，drawing 一条 150mm → CONSISTENT
    t = [
        _ev("upright_spacing", 150, "mm", 10, scope=beam_bot),
        _ev("upright_spacing", 150, "mm", 20, scope=beam_bot),
    ]
    d = [_ev("upright_spacing", 150, "mm", 30, scope=beam_bot, source_type="vlm")]
    r1 = compare_evidence_sets("upright_spacing", t, d)
    assert r1.status == CONSISTENT
    assert r1.reason == "values_equal"
    assert r1.comparable_pair_count == 1

    # 增加一条 160mm 的 text → multiple distinct pairs → UNCERTAIN
    t2 = t + [_ev("upright_spacing", 160, "mm", 25, scope=beam_bot)]
    r2 = compare_evidence_sets("upright_spacing", t2, d)
    assert r2.status == UNCERTAIN
    assert r2.reason == "multiple_comparable_pairs"
