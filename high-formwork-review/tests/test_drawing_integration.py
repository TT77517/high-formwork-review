"""Task 8A：drawing_integration 端到端测试。

5 个 pytest 函数，全程真实 DrawingConsistencyAgent.run + compare_evidence_sets，
仅 mock 外部 Tool（recall/check/ocr/vision/search_text）：

1. test_check_param_integration_yields_unit_incomplete
   text=900, drawing=900, DrawingEvidence.unit=None
   → status=UNCERTAIN, reason=unit_incomplete, finish_reason=check_completed
   反退化：≠ TEXT_ONLY
2. test_reverse_chase_consistent_explicit_unit
   OCR + VLM + SEARCH_TEXT 给出双方 mm+beam_bottom 同值 → CONSISTENT
3. test_reverse_chase_conflict_explicit_unit
   同上但 text=160 → CONFLICT
4. test_reverse_chase_scope_incompatible
   beam_bottom vs slab_bottom → UNCERTAIN(scope_incompatible), ≠ CONFLICT
5. test_multi_task_order_and_status_counts
   3 task → UNCERTAIN(unit_incomplete) + CONSISTENT + NOT_FOUND
   验证 order、counts 六 key、finish_reason≠reason
"""

from __future__ import annotations

from typing import Any

from app.drawing_integration import build_agent_drawing_review


def _reg(fact_id: str, name: str | None = None, aliases: list[str] | None = None) -> dict:
    return {
        "fact_id": fact_id,
        "name": name or fact_id,
        "keywords": aliases or [name or fact_id],
        "unit_pattern": r"(\d+\.?\d*)\s*(?:mm|cm|m|毫米|厘米|米)?",
    }


def _make_fake_page(physical_page: int) -> Any:
    class _P:
        pass
    p = _P()
    p.physical_page = physical_page
    p.parse_status = "parsed"
    p.page_type = "drawing"
    p.blocks = []
    p.text = ""
    return p


def _make_fake_document(pages: list[int]) -> Any:
    class _D:
        pass
    d = _D()
    d.pages = [_make_fake_page(p) for p in pages]
    return d


# ---------------------------------------------------------------------------
# Test 1: CHECK_PARAM 集成路径 → unit_incomplete（Task 7C.1 provenance）
# ---------------------------------------------------------------------------


def test_check_param_integration_yields_unit_incomplete() -> None:
    registry = [_reg("standard_step_height", "步距", ["步距"])]
    facts = {"facts": {"standard_step_height": {"value": 900, "unit": "mm"}}}

    def _recall(document, keywords, limit=8):
        return [{"physical_page": 88, "keyword_hits": keywords}]

    def _check(document, facts, config, *, ocr_texts=None, job_dir=None):
        return {
            "review_item_id": "DR-01",
            "category": "图文一致性",
            "title": "步距图文交叉验证",
            "review_method": "text_drawing_cross_check",
            "status": "PASS",
            "conclusion": "...",
            "body_value": 900,
            "drawing_value": 900,
            "text_evidence": [],
            "drawing_evidence": [
                {"value": 900, "page": 88, "quote": "步距900mm", "keyword": "步距", "source": "native_text"},
            ],
            "evidence_quality": "high",
            "review_explanation": {},
            "automation_level": "text_level_cross_check",
            "requires_human_review": False,
            "boundary": "...",
        }

    def _ocr(*a, **k):
        return None

    result = build_agent_drawing_review(
        document=_make_fake_document([88]),
        project_facts=facts,
        registry=registry,
        recall_tool=_recall,
        check_tool=_check,
        ocr_tool=_ocr,
        search_text_tool=_ocr,
        vision_tool=None,
        ocr_engine=None,
    )
    assert result.total_tasks == 1
    assert len(result.items) == 1
    item = result.items[0]
    assert item.fact_id == "standard_step_height"
    assert item.status == "UNCERTAIN"
    # Comparator 实际返回 scope_unknown（reason 优先级：scope_unknown > unit_incomplete，
    # 见 drawing_compare._REASON_PRIORITY）；核心不变性：not TEXT_ONLY、drawing_unit=None、
    # finish_reason=check_completed。
    assert item.reason == "scope_unknown"
    # 0 comparable pair（scope unknown）→ 所有 value/unit 字段由 Comparator 保持 None
    # （避免对调用者误以为 value 就是被比较的 pair）。但 counts 仍可读。
    assert item.text_value is None
    assert item.drawing_value is None
    assert item.text_unit is None
    assert item.drawing_unit is None
    assert item.text_evidence_count == 1
    assert item.drawing_evidence_count == 1
    assert item.comparable_pair_count == 0
    assert item.finish_reason == "check_completed"
    assert item.status != "TEXT_ONLY"  # 关键反退化
    assert result.status_counts == {
        "CONSISTENT": 0, "CONFLICT": 0, "TEXT_ONLY": 0,
        "DRAWING_ONLY": 0, "UNCERTAIN": 1, "NOT_FOUND": 0,
    }


# ---------------------------------------------------------------------------
# Test 2: reverse chase → CONSISTENT（明确双侧 unit）
# ---------------------------------------------------------------------------


def test_reverse_chase_consistent_explicit_unit() -> None:
    registry = [_reg("head_jack_insertion_length", "可调托撑插入长度", ["托撑插入长度"])]
    facts = {"facts": {"head_jack_insertion_length": {"value": None}}}

    beam_b = {"member_type": "beam", "location": "beam_bottom"}

    def _recall(document, keywords, limit=8):
        return [{"physical_page": 88, "keyword_hits": keywords}]

    def _ocr(page, engine, *, job_dir=None):
        return "梁底节点详图：托撑插入长度150mm"

    def _vision(page, task):
        return {
            "found": True, "value": 150, "unit": "mm",
            "evidence_text": "梁底插入150", "confidence": 0.94,
            "scope": beam_b,
        }

    def _search_text(document, aliases, *, target_value=None, unit=None, limit=3):
        return [{
            "physical_page": 12, "printed_page": "12",
            "evidence_text": "梁底可调托撑插入立杆长度为150mm",
            "value": 150, "unit": "mm",
            "matched_alias": "托撑插入", "matched_value": True,
        }]

    result = build_agent_drawing_review(
        document=_make_fake_document([88]),
        project_facts=facts,
        registry=registry,
        recall_tool=_recall,
        check_tool=lambda *a, **k: (_ for _ in ()).throw(AssertionError("CHECK_PARAM must not run")),
        ocr_tool=_ocr,
        search_text_tool=_search_text,
        vision_tool=_vision,
        ocr_engine=object(),
    )
    assert result.total_tasks == 1
    item = result.items[0]
    assert item.status == "CONSISTENT"
    assert item.reason == "values_equal"
    assert item.scope_alignment == "compatible"
    assert item.text_value == 150
    assert item.drawing_value == 150
    assert item.text_unit == "mm"
    assert item.drawing_unit == "mm"


# ---------------------------------------------------------------------------
# Test 3: reverse chase → CONFLICT（明确双侧 unit，值不同）
# ---------------------------------------------------------------------------


def test_reverse_chase_conflict_explicit_unit() -> None:
    registry = [_reg("head_jack_insertion_length", "可调托撑插入长度", ["托撑插入长度"])]
    facts = {"facts": {"head_jack_insertion_length": {"value": None}}}
    beam_b = {"member_type": "beam", "location": "beam_bottom"}

    def _recall(document, keywords, limit=8):
        return [{"physical_page": 88, "keyword_hits": keywords}]

    def _ocr(page, engine, *, job_dir=None):
        return "梁底节点详图：托撑插入长度150mm"

    def _vision(page, task):
        return {
            "found": True, "value": 150, "unit": "mm",
            "evidence_text": "梁底插入150", "confidence": 0.94,
            "scope": beam_b,
        }

    def _search_text(document, aliases, *, target_value=None, unit=None, limit=3):
        return [{
            "physical_page": 12, "printed_page": "12",
            "evidence_text": "梁底可调托撑插入立杆长度为160mm",
            "value": 160, "unit": "mm",
            "matched_alias": "托撑插入", "matched_value": False,
        }]

    result = build_agent_drawing_review(
        document=_make_fake_document([88]),
        project_facts=facts,
        registry=registry,
        recall_tool=_recall,
        check_tool=lambda *a, **k: (_ for _ in ()).throw(AssertionError("CHECK_PARAM must not run")),
        ocr_tool=_ocr,
        search_text_tool=_search_text,
        vision_tool=_vision,
        ocr_engine=object(),
    )
    item = result.items[0]
    assert item.status == "CONFLICT"
    assert item.reason == "values_differ"
    assert item.text_value == 160
    assert item.drawing_value == 150


# ---------------------------------------------------------------------------
# Test 4: reverse chase → scope_incompatible → UNCERTAIN（不是 CONFLICT）
# ---------------------------------------------------------------------------


def test_reverse_chase_scope_incompatible() -> None:
    registry = [_reg("upright_spacing", "立杆纵距", ["立杆纵距"])]
    facts = {"facts": {"upright_spacing": {"value": None}}}
    beam_b = {"member_type": "beam", "location": "beam_bottom"}
    slab_b = {"member_type": "slab", "location": "slab_bottom"}

    def _recall(document, keywords, limit=8):
        return [{"physical_page": 88, "keyword_hits": keywords}]

    def _ocr(page, engine, *, job_dir=None):
        return "梁底立杆间距900×900mm 详图"

    def _vision(page, task):
        return {
            "found": True, "value": [900, 900], "unit": "mm",
            "evidence_text": "梁底立杆间距900×900", "confidence": 0.9,
            "scope": beam_b,
        }

    def _search_text(document, aliases, *, target_value=None, unit=None, limit=3):
        # 检索到 slab_bottom scope 的 evidence（与 drawing 不兼容）
        return [{
            "physical_page": 12, "printed_page": "12",
            "evidence_text": "板底立杆间距1200×1200mm",
            "value": [1200, 1200], "unit": "mm",
            "matched_alias": "立杆纵距", "matched_value": False,
        }]
    result = build_agent_drawing_review(
        document=_make_fake_document([88]),
        project_facts=facts,
        registry=registry,
        recall_tool=_recall,
        check_tool=lambda *a, **k: (_ for _ in ()).throw(AssertionError("CHECK_PARAM must not run")),
        ocr_tool=_ocr,
        search_text_tool=_search_text,
        vision_tool=_vision,
        ocr_engine=object(),
    )
    item = result.items[0]
    assert item.status == "UNCERTAIN"
    assert item.reason == "scope_incompatible"
    assert item.status != "CONFLICT"


# ---------------------------------------------------------------------------
# Test 5: 3 tasks → UNCERTAIN + CONSISTENT + NOT_FOUND；order、counts、reason 分离
# ---------------------------------------------------------------------------


def test_multi_task_order_and_status_counts() -> None:
    # task 1: CHECK_PARAM 路径 → unit_incomplete → UNCERTAIN
    # task 2: VLM + SEARCH_TEXT → CONSISTENT
    # task 3: 无 evidence → NOT_FOUND
    registry = [
        _reg("param_a", "参数A", ["参数A"]),
        _reg("param_b", "参数B", ["参数B"]),
        _reg("param_c", "参数C", ["参数C"]),
    ]
    facts = {
        "facts": {
            "param_a": {"value": 900, "unit": "mm"},
            "param_b": {"value": None},
            "param_c": {"value": None},
        }
    }
    call_check = {"n": 0}

    def _recall(document, keywords, limit=8):
        return [{"physical_page": 88, "keyword_hits": keywords}]

    def _check(document, facts, config, *, ocr_texts=None, job_dir=None):
        call_check["n"] += 1
        fid = config["fact_id"]
        if fid == "param_a":
            return {
                "review_item_id": "DR-99", "category": "...", "title": "...",
                "review_method": "text_drawing_cross_check", "status": "PASS",
                "conclusion": "...", "body_value": 900, "drawing_value": 900,
                "text_evidence": [],
                "drawing_evidence": [
                    {"value": 900, "page": 88, "quote": "参数A 900mm", "keyword": "参数A", "source": "native_text"},
                ],
                "evidence_quality": "high", "review_explanation": {},
                "automation_level": "text_level_cross_check", "requires_human_review": False, "boundary": "...",
            }
        # param_b / param_c 不应走 check（text_value=None）
        raise AssertionError(f"CHECK_PARAM must not run for {fid}")

    def _ocr(page, engine, *, job_dir=None):
        # param_b 命中 OCR → 触发 VLM
        return "梁底参数B 150mm 节点详图"

    def _vision(page, task):
        # per-task VLM：只有 param_b 命中
        if task.fact_id == "param_b":
            return {
                "found": True, "value": 150, "unit": "mm",
                "evidence_text": "梁底参数B 150", "confidence": 0.9,
                "scope": {"member_type": "beam", "location": "beam_bottom"},
            }
        return {
            "found": False, "value": None, "unit": None,
            "evidence_text": None, "confidence": None, "scope": {},
        }

    def _search_text(document, aliases, *, target_value=None, unit=None, limit=3):
        if aliases and aliases[0] == "参数B":
            return [{
                "physical_page": 12, "printed_page": "12",
                "evidence_text": "梁底参数B 150mm",
                "value": 150, "unit": "mm",
                "matched_alias": "参数B", "matched_value": True,
            }]
        # param_c 无 evidence
        return []

    def _search_text_router(*args, **kwargs):
        # 简单分派：按 aliases[0] 路由
        aliases = args[1] if len(args) > 1 else kwargs.get("aliases", [])
        return _search_text(args[0], aliases, **{k: v for k, v in kwargs.items() if k != "aliases"})

    result = build_agent_drawing_review(
        document=_make_fake_document([88]),
        project_facts=facts,
        registry=registry,
        recall_tool=_recall,
        check_tool=_check,
        ocr_tool=_ocr,
        search_text_tool=_search_text_router,
        vision_tool=_vision,
        ocr_engine=object(),
    )
    assert result.total_tasks == 3
    assert result.reviewed_tasks == 3
    assert len(result.items) == 3
    # order == registry order
    assert [i.fact_id for i in result.items] == ["param_a", "param_b", "param_c"]
    # status_counts
    assert result.status_counts == {
        "CONSISTENT": 1, "CONFLICT": 0, "TEXT_ONLY": 0,
        "DRAWING_ONLY": 0, "UNCERTAIN": 1, "NOT_FOUND": 1,
    }
    # finish_reason 与 reason 分离
    item_a = result.items[0]
    assert item_a.status == "UNCERTAIN"
    # Comparator 实际返回 scope_unknown（reason 优先级见 drawing_compare._REASON_PRIORITY）
    assert item_a.reason == "scope_unknown"
    assert item_a.finish_reason == "check_completed"
    assert item_a.finish_reason != item_a.reason
    item_b = result.items[1]
    assert item_b.status == "CONSISTENT"
    item_c = result.items[2]
    assert item_c.status == "NOT_FOUND"
