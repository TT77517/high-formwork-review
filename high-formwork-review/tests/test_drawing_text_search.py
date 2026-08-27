"""Task 6: 确定性 search_text_evidence Tool 单测（不依赖网络/Provider）。"""
from __future__ import annotations


def _make_doc(pages):
    """构造 fake MinerUDocument。pages: [(physical_page, page_type, text), ...]"""
    class _P:
        pass

    page_objs = []
    for physical_page, page_type, text in pages:
        p = _P()
        p.physical_page = physical_page
        p.printed_page = str(physical_page)
        p.page_type = page_type
        p.parse_status = "complete"
        p.text = text
        p.blocks = []
        page_objs.append(p)

    class _D:
        pass

    d = _D()
    d.pages = page_objs
    return d


def test_search_text_evidence_alias_and_scalar_value_match() -> None:
    """Case 1: alias + scalar value 命中 → matched_value=True；smoke：Tool callable + Agent 构造兼容。

    Task 6.2 覆盖 Case A "高度5m，托撑插入长度150mm" → value=150, unit=mm。
    """
    from app.drawing_agent import DrawingConsistencyAgent
    from app.drawing_review import (
        cross_check_param,
        ocr_drawing_page,
        recall_drawing_pages,
        search_text_evidence,
    )

    # smoke: callable + 注入 Agent 构造器
    assert callable(search_text_evidence)
    agent = DrawingConsistencyAgent(
        recall_tool=recall_drawing_pages,
        check_tool=cross_check_param,
        ocr_tool=ocr_drawing_page,
        search_text_tool=search_text_evidence,
    )
    assert agent is not None

    # --- Case A: alias 附近 binding：高度 5m 在前，托撑插入长度 150mm 在后 ---
    doc_a = _make_doc([
        (1, "text", "梁底支撑高度5m，可调托撑插入长度为150mm。"),
    ])
    cands_a = search_text_evidence(
        doc_a, aliases=["托撑插入长度"], target_value=150, unit="mm", limit=3,
    )
    assert len(cands_a) == 1
    c = cands_a[0]
    assert c["value"] == 150
    assert c["unit"] == "mm"
    assert c["matched_value"] is True
    assert c["matched_alias"] == "托撑插入长度"
    assert "150mm" in c["evidence_text"]
    # Task 6.2 关键回归断言：value 必须来自 alias 附近，不能是整个 snippet 第一个数字
    assert c["value"] != 5

    # --- Case B: 2D 形式 "层高5.4m，立杆间距900×900mm" → value=[900,900], unit=mm ---
    doc_b = _make_doc([
        (2, "text", "层高5.4m，立杆间距900×900mm。"),
    ])
    cands_b = search_text_evidence(
        doc_b, aliases=["立杆间距"], target_value=[900, 900], unit="mm", limit=3,
    )
    assert len(cands_b) == 1
    c2 = cands_b[0]
    assert c2["value"] == [900, 900]
    assert c2["unit"] == "mm"
    assert c2["matched_value"] is True
    # Task 6.2 关键回归断言：value 必须来自 alias 附近，不能是 5.4
    assert c2["value"] != 5.4


def test_search_text_evidence_value_mismatch_returns_empty() -> None:
    """Case 2 (Task 6.1+6.2): alias 命中但 value 不同 → 保留 candidate，value 来自正文。

    Task 6.2 覆盖 Case C "高度5m，托撑插入长度160mm" / target=150 → value=160, matched=False。
    """
    from app.drawing_review import search_text_evidence

    # --- Case C: 高度 5m 在前，托撑插入长度 160mm 在后；target=150 ---
    doc = _make_doc([(3, "text", "高度5m，可调托撑插入长度160mm。")])
    cands = search_text_evidence(
        doc, aliases=["托撑插入长度"], target_value=150, unit="mm", limit=3,
    )
    assert len(cands) == 1  # 保留 candidate
    c = cands[0]
    assert c["value"] == 160  # value 来自正文实际提取
    assert c["matched_value"] is False  # 150 ≠ 160
    assert c["unit"] == "mm"
    # 关键回归断言：高度 5 不能被误绑定为 value
    assert c["value"] != 5

    # --- Task 6.3 Case 1: value 在 alias 之前（after window 为空，before window 取最接近）---
    doc_c1 = _make_doc([(4, "text", "层高5m，150mm为可调托撑插入长度设计值。")])
    cands_c1 = search_text_evidence(
        doc_c1, aliases=["托撑插入长度"], target_value=150, unit="mm", limit=3,
    )
    assert len(cands_c1) == 1
    cc1 = cands_c1[0]
    assert cc1["value"] == 150  # 不是 5（before-window 取最后一个，最接近 alias）
    assert cc1["unit"] == "mm"
    assert cc1["matched_value"] is True
    assert cc1["value"] != 5  # 关键回归断言：高度不能被误绑

    # --- Task 6.3 Case 2: 2D 在 alias 之前（after window 为空，before 取最接近）---
    doc_c2 = _make_doc([(5, "text", "层高5.4m，900×900mm为梁底立杆间距。")])
    cands_c2 = search_text_evidence(
        doc_c2, aliases=["立杆间距"], target_value=[900, 900], unit="mm", limit=3,
    )
    assert len(cands_c2) == 1
    cc2 = cands_c2[0]
    assert cc2["value"] == [900, 900]  # 不是 5.4
    assert cc2["unit"] == "mm"
    assert cc2["matched_value"] is True
    assert cc2["value"] != 5.4  # 关键回归断言：层高不能被误绑


def test_search_text_evidence_target_none_alias_only() -> None:
    """Case 3: target_value=None → 允许 alias-only 候选，value=None / matched_value=False。"""
    from app.drawing_review import search_text_evidence

    doc = _make_doc([(7, "text", "可调托撑插入长度详见节点详图。")])
    cands = search_text_evidence(
        doc, aliases=["托撑插入长度"], target_value=None, unit="mm", limit=3,
    )
    assert len(cands) == 1
    c = cands[0]
    assert c["physical_page"] == 7
    assert c["value"] is None
    assert c["matched_value"] is False
    assert c["matched_alias"] == "托撑插入长度"


def test_search_text_evidence_spec_clause_filtered() -> None:
    """Case 4: 明显规范条文引用 → 即使 alias+value 都出现也不返回候选。"""
    from app.drawing_review import search_text_evidence

    doc = _make_doc([
        (12, "text", "按规范JGJ/T 231-2021第6.2.4条规定，立杆间距不得大于1.5m。"),
    ])
    cands = search_text_evidence(
        doc, aliases=["立杆间距"], target_value=1500, unit="mm", limit=3,
    )
    assert cands == []  # 被 spec clause 过滤
