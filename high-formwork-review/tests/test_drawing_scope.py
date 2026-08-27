"""Task 7A：drawing_scope 单元测试。

5 个 pytest 函数：

1. 梁底 → member_type=beam, location=beam_bottom
2. 板底 / 楼板底 → member_type=slab, location=slab_bottom
3. 梁板模板 → ``{}``（ambiguous）
4. normalize（含中文归一 + floor 丢弃 + explicit/inferred 冲突）
5. align_scopes 三态（compatible / incompatible / unknown / empty）
"""

from __future__ import annotations


def test_scope_infer_beam_bottom() -> None:
    from app.drawing_scope import infer_scope_from_text

    text = "梁底立杆间距900×900mm"
    scope = infer_scope_from_text(text, aliases=["立杆间距"])
    assert scope == {"member_type": "beam", "location": "beam_bottom"}


def test_scope_infer_slab_bottom() -> None:
    from app.drawing_scope import infer_scope_from_text

    # 板底 + 楼板底 两种表达
    assert infer_scope_from_text("板底立杆间距1200×1200mm", aliases=["立杆间距"]) == {
        "member_type": "slab", "location": "slab_bottom",
    }
    assert infer_scope_from_text("楼板底立杆间距900×900", aliases=["立杆间距"]) == {
        "member_type": "slab", "location": "slab_bottom",
    }
    # "模板" 不被误判为 slab（裸"板"无 location 强信号 → 退化为楼板）
    assert infer_scope_from_text("板模板按方案布置", aliases=["模板"]) == {
        "member_type": "slab"
    }


def test_scope_infer_ambiguous_returns_empty() -> None:
    from app.drawing_scope import infer_scope_from_text

    # "梁板模板支撑体系" 含梁 + 板 + 模板
    # 当前 member_type_keyword 顺序下，"楼板"不在其中 → "梁"先命中 beam
    # 但 location 关键词里有 "梁板" 触发 ambiguous → 必须返回 {}
    text = "梁板模板支撑体系立杆间距按方案布置"
    scope = infer_scope_from_text(text, aliases=["立杆间距"])
    assert scope == {}


def test_scope_normalize_and_conflict_resolution() -> None:
    from app.drawing_scope import (
        normalize_scope,
        resolve_evidence_scope,
    )

    # Case A: 中文 + 多余字段 → 归一为 beam_bottom，floor/axis 丢弃
    normed = normalize_scope({
        "member_type": "梁",
        "location": "梁底",
        "floor": "3F",
        "axis": "A-1",
    })
    assert normed == {"member_type": "beam", "location": "beam_bottom"}

    # Case B: 不支持 member_type（wall） → 整 key 丢弃 → 剩余 location
    # location 是合法值，自动反推 member_type → beam_bottom
    only_location = normalize_scope({"member_type": "wall", "location": "beam_bottom"})
    assert only_location == {"member_type": "beam", "location": "beam_bottom"}

    # Case B2: 双向都不支持 → {}
    both_invalid = normalize_scope({"member_type": "wall", "location": "random_place"})
    assert both_invalid == {}

    # Case C: 非 mapping 输入 → {}
    assert normalize_scope(None) == {}
    assert normalize_scope("not a dict") == {}

    # Case D: location 隐含 member_type
    implied = normalize_scope({"location": "slab_bottom"})
    assert implied == {"member_type": "slab", "location": "slab_bottom"}

    # Case E: explicit beam + text inferred slab → 冲突 → {}
    merged = resolve_evidence_scope(
        {"member_type": "beam"},
        "板底立杆间距1200×1200",
        aliases=["立杆间距"],
    )
    assert merged == {}

    # Case F: explicit 缺 location，inferred 带 → 取并集
    extended = resolve_evidence_scope(
        {"member_type": "beam"},
        "梁底立杆间距900×900",
        aliases=["立杆间距"],
    )
    assert extended == {"member_type": "beam", "location": "beam_bottom"}


def test_scope_alignment_three_states() -> None:
    from app.drawing_scope import (
        SCOPE_COMPATIBLE,
        SCOPE_INCOMPATIBLE,
        SCOPE_UNKNOWN,
        align_scopes,
    )

    # compatible: 同 dim 同值
    assert align_scopes(
        {"member_type": "beam", "location": "beam_bottom"},
        {"member_type": "beam", "location": "beam_bottom"},
    ) == SCOPE_COMPATIBLE

    # compatible: 双方都只 member_type
    assert align_scopes(
        {"member_type": "beam"},
        {"member_type": "beam"},
    ) == SCOPE_COMPATIBLE

    # incompatible: 同一 dim 不同值
    assert align_scopes(
        {"member_type": "beam", "location": "beam_bottom"},
        {"member_type": "slab", "location": "slab_bottom"},
    ) == SCOPE_INCOMPATIBLE

    # incompatible: 成员类型冲突
    assert align_scopes(
        {"member_type": "beam"},
        {"member_type": "slab"},
    ) == SCOPE_INCOMPATIBLE

    # unknown: 信息不对称（一边有 location，一边没有）
    assert align_scopes(
        {"member_type": "beam", "location": "beam_bottom"},
        {"member_type": "beam"},
    ) == SCOPE_UNKNOWN

    # unknown: {} vs {}
    assert align_scopes({}, {}) == SCOPE_UNKNOWN

    # unknown: {} vs partial
    assert align_scopes({}, {"member_type": "beam"}) == SCOPE_UNKNOWN

    # unknown: None 输入
    assert align_scopes(None, {"member_type": "beam"}) == SCOPE_UNKNOWN
