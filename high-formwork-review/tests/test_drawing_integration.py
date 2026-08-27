"""Task 8A：drawing_integration 端到端测试。

5 个 pytest 函数；真实 DrawingConsistencyAgent.run + 真实 compare_evidence_sets；
仅 mock 外部 Tool（recall/check/ocr/vision/search_text）。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from app.drawing_integration import build_agent_drawing_review


_BEAM_B = {"member_type": "beam", "location": "beam_bottom"}
_SLAB_B = {"member_type": "slab", "location": "slab_bottom"}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _reg(fact_id: str, *, aliases: list[str] | None = None, scope: dict | None = None) -> dict:
    """Build a registry entry. ``scope`` is opt-in passthrough for explicit task scope."""
    return {
        "fact_id": fact_id,
        "name": fact_id,
        "keywords": aliases or [fact_id],
        "unit_pattern": r"(\d+\.?\d*)\s*(?:mm|cm|m|毫米|厘米|米)?",
        **({"scope": scope} if scope else {}),
    }


def _doc(image_path: str | None = None) -> Any:
    """Single-page fake drawing document with optional image block."""
    img = image_path
    class _B:
        block_type = "image"
        image_path = img
        text = ""
        block_index = 0
    class _P:
        physical_page = 88
        parse_status = "parsed"
        page_type = "drawing"
        blocks = [_B()] if img else []
        text = ""
    class _D:
        pages = [_P()]
    return _D()


def _setup_job(tmp_path, rel: str = "x.jpg", content: bytes = b"x"):
    raw_dir = tmp_path / "mineru_api" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / rel).write_bytes(content)
    return tmp_path, rel


def _recall(document, keywords, limit=8) -> list[dict]:
    return [{"physical_page": 88, "keyword_hits": keywords}]


def _ocr(page, engine, *, job_dir=None) -> str | None:
    return None


def _check_must_not_run(*a, **k):
    raise AssertionError("CHECK_PARAM must not run")


def _check_payload(value=900) -> dict:
    return {
        "review_item_id": "DR-99", "category": ".", "title": ".",
        "review_method": "text_drawing_cross_check", "status": "PASS",
        "conclusion": ".", "body_value": value, "drawing_value": value,
        "text_evidence": [],
        "drawing_evidence": [{"value": value, "page": 88, "quote": f"梁底参数{value}mm"}],
        "evidence_quality": "high", "review_explanation": {},
        "automation_level": ".", "requires_human_review": False, "boundary": ".",
    }


def _run(
    registry: list[dict],
    facts: dict,
    *,
    check_tool: Callable = _check_must_not_run,
    ocr_text: str | None = None,
    vision_result: dict | None = None,
    search_results: list[dict] | None = None,
    job_dir=None,
) -> Any:
    """Run build_agent_drawing_review with shared fakes."""
    def _ocr_factory(page, engine, *, job_dir=None):
        return ocr_text

    def _vision_factory(page, task, **kwargs):
        return vision_result if vision_result is not None else {
            "found": False, "value": None, "unit": None,
            "evidence_text": None, "confidence": None, "scope": {},
        }

    def _search_factory(document, aliases, *, target_value=None, unit=None, limit=3):
        if not search_results:
            return []
        # 按 task.aliases 任何一项匹配 candidate.matched_alias
        alias_set = set(aliases or [])
        return [c for c in search_results if c.get("matched_alias") in alias_set]

    return build_agent_drawing_review(
        document=_doc(job_dir[1] if job_dir else None),
        project_facts=facts, registry=registry,
        recall_tool=_recall, check_tool=check_tool,
        ocr_tool=_ocr_factory, search_text_tool=_search_factory,
        vision_tool=_vision_factory, ocr_engine=object(),
        job_dir=job_dir[0] if job_dir else None,
    )


# ---------------------------------------------------------------------------
# Test 1: CHECK_PARAM 路径 → unit_incomplete（drawing unit None，scope compatible）
# ---------------------------------------------------------------------------


def test_check_param_integration_yields_unit_incomplete() -> None:
    registry = [_reg("upright_spacing", aliases=["立杆间距"], scope=_BEAM_B)]
    facts = {"facts": {"upright_spacing": {"value": 900, "unit": "mm"}}}

    def _check(document, facts, config, *, ocr_texts=None, job_dir=None):
        return {
            "review_item_id": "DR-01", "category": ".", "title": ".",
            "review_method": "text_drawing_cross_check", "status": "PASS",
            "conclusion": ".", "body_value": 900, "drawing_value": 900,
            "text_evidence": [],
            "drawing_evidence": [
                {"value": 900, "page": 10, "quote": "梁底立杆间距900mm",
                 "keyword": "立杆间距", "source": "native_text"},
            ],
            "evidence_quality": "high", "review_explanation": {},
            "automation_level": "text_level_cross_check",
            "requires_human_review": False, "boundary": ".",
        }

    result = _run(registry, facts, check_tool=_check)
    item = result.items[0]
    assert item.status == "UNCERTAIN"
    assert item.reason == "unit_incomplete"
    assert item.scope_alignment == "compatible"
    assert item.status != "TEXT_ONLY"  # 关键反退化
    assert item.text_evidence_count == 1
    assert item.drawing_evidence_count == 1
    assert item.finish_reason == "check_completed"
    assert result.status_counts["UNCERTAIN"] == 1


# ---------------------------------------------------------------------------
# Test 2: reverse chase → CONSISTENT（双侧 mm + beam_bottom 同值）
# ---------------------------------------------------------------------------


def test_reverse_chase_consistent_explicit_unit(tmp_path) -> None:
    job_dir = _setup_job(tmp_path)
    registry = [_reg("insertion", aliases=["托撑插入"])]
    facts = {"facts": {"insertion": {"value": None}}}
    result = _run(
        registry, facts,
        ocr_text="梁底节点详图：托撑插入150mm",
        vision_result={"found": True, "value": 150, "unit": "mm",
                       "evidence_text": "梁底插入150", "confidence": 0.94, "scope": _BEAM_B},
        search_results=[{"physical_page": 12, "printed_page": "12",
                        "evidence_text": "梁底可调托撑插入立杆长度为150mm",
                        "value": 150, "unit": "mm",
                        "matched_alias": "托撑插入", "matched_value": True}],
        job_dir=job_dir,
    )
    item = result.items[0]
    assert item.status == "CONSISTENT"
    assert item.reason == "values_equal"
    assert item.scope_alignment == "compatible"
    assert item.text_value == 150 and item.drawing_value == 150
    assert item.text_unit == "mm" and item.drawing_unit == "mm"


# ---------------------------------------------------------------------------
# Test 3: reverse chase → CONFLICT（双侧 mm + beam_bottom，值不同）
# ---------------------------------------------------------------------------


def test_reverse_chase_conflict_explicit_unit(tmp_path) -> None:
    job_dir = _setup_job(tmp_path)
    registry = [_reg("insertion", aliases=["托撑插入"])]
    facts = {"facts": {"insertion": {"value": None}}}
    result = _run(
        registry, facts,
        ocr_text="梁底节点详图：托撑插入150mm",
        vision_result={"found": True, "value": 150, "unit": "mm",
                       "evidence_text": "梁底插入150", "confidence": 0.94, "scope": _BEAM_B},
        search_results=[{"physical_page": 12, "printed_page": "12",
                        "evidence_text": "梁底可调托撑插入立杆长度为160mm",
                        "value": 160, "unit": "mm",
                        "matched_alias": "托撑插入", "matched_value": False}],
        job_dir=job_dir,
    )
    item = result.items[0]
    assert item.status == "CONFLICT"
    assert item.reason == "values_differ"
    assert item.text_value == 160 and item.drawing_value == 150


# ---------------------------------------------------------------------------
# Test 4: reverse chase → scope_incompatible（beam_bottom vs slab_bottom）
# ---------------------------------------------------------------------------


def test_reverse_chase_scope_incompatible(tmp_path) -> None:
    job_dir = _setup_job(tmp_path)
    registry = [_reg("spacing", aliases=["立杆纵距"])]
    facts = {"facts": {"spacing": {"value": None}}}
    result = _run(
        registry, facts,
        ocr_text="梁底立杆间距900×900mm 详图",
        vision_result={"found": True, "value": [900, 900], "unit": "mm",
                       "evidence_text": "梁底立杆间距900×900", "confidence": 0.9, "scope": _BEAM_B},
        search_results=[{"physical_page": 12, "printed_page": "12",
                        "evidence_text": "板底立杆间距1200×1200mm",
                        "value": [1200, 1200], "unit": "mm",
                        "matched_alias": "立杆纵距", "matched_value": False}],
        job_dir=job_dir,
    )
    item = result.items[0]
    assert item.status == "UNCERTAIN"
    assert item.reason == "scope_incompatible"
    assert item.status != "CONFLICT"


# ---------------------------------------------------------------------------
# Test 5: 3 task 混合路径 → order / counts / reason 分离
# ---------------------------------------------------------------------------


def test_multi_task_order_and_status_counts(tmp_path) -> None:
    job_dir = _setup_job(tmp_path)
    registry = [
        _reg("param_a", aliases=["参数A"], scope=_BEAM_B),
        _reg("param_b", aliases=["参数B"]),
        _reg("param_c", aliases=["参数C"]),
    ]
    facts = {"facts": {
        "param_a": {"value": 900, "unit": "mm"},
        "param_b": {"value": None},
        "param_c": {"value": None},
    }}

    def _check(document, facts, config, *, ocr_texts=None, job_dir=None):
        if config["fact_id"] != "param_a":
            raise AssertionError("CHECK_PARAM only for param_a")
        return {
            "review_item_id": "DR-99", "category": ".", "title": ".",
            "review_method": ".", "status": "PASS", "conclusion": ".",
            "body_value": 900, "drawing_value": 900, "text_evidence": [],
            "drawing_evidence": [{"value": 900, "page": 88,
                                  "quote": "梁底参数A 900mm", "keyword": "参数A",
                                  "source": "native_text"}],
            "evidence_quality": "high", "review_explanation": {},
            "automation_level": ".", "requires_human_review": False, "boundary": ".",
        }

    def _vision(page, task):
        if task.fact_id == "param_b":
            return {"found": True, "value": 150, "unit": "mm",
                    "evidence_text": "梁底参数B 150", "confidence": 0.9, "scope": _BEAM_B}
        return {"found": False, "value": None, "unit": None,
                "evidence_text": None, "confidence": None, "scope": {}}

    search_results = [{"physical_page": 12, "printed_page": "12",
                       "evidence_text": "梁底参数B 150mm", "value": 150, "unit": "mm",
                       "matched_alias": "参数B", "matched_value": True}]
    def _vision_factory(page, task, **kwargs):
        return _vision(page, task)
    def _ocr_factory(page, engine, *, job_dir=None):
        return "梁底参数B 150mm 节点详图"
    def _search_factory(document, aliases, *, target_value=None, unit=None, limit=3):
        return [c for c in search_results if c["matched_alias"] == aliases[0]] if aliases else []

    result = build_agent_drawing_review(
        document=_doc(job_dir[1]), project_facts=facts, registry=registry,
        recall_tool=_recall, check_tool=_check,
        ocr_tool=_ocr_factory, search_text_tool=_search_factory,
        vision_tool=_vision_factory, ocr_engine=object(),
        job_dir=job_dir[0],
    )
    assert result.total_tasks == 3
    assert result.reviewed_tasks == 3
    assert len(result.items) == 3
    # order == registry order
    assert [i.fact_id for i in result.items] == ["param_a", "param_b", "param_c"]
    # 六 status_counts key 全存在
    assert set(result.status_counts.keys()) == {
        "CONSISTENT", "CONFLICT", "TEXT_ONLY", "DRAWING_ONLY", "UNCERTAIN", "NOT_FOUND"
    }
    assert result.status_counts == {
        "CONSISTENT": 1, "CONFLICT": 0, "TEXT_ONLY": 0,
        "DRAWING_ONLY": 0, "UNCERTAIN": 1, "NOT_FOUND": 1,
    }
    # finish_reason 与 reason 分离
    item_a, item_b, item_c = result.items
    assert item_a.status == "UNCERTAIN" and item_a.reason == "unit_incomplete"
    assert item_a.finish_reason == "check_completed"
    assert item_a.finish_reason != item_a.reason
    assert item_b.status == "CONSISTENT"
    assert item_c.status == "NOT_FOUND"


def test_integration_check_tool_receives_full_registry_config() -> None:
    captured = {}
    registry = [{
        "fact_id": "demo_fact", "name": "Demo", "keywords": ["别名A", "别名B"],
        "aliases": ["别名A", "别名B"], "unit": "mm",
        "unit_pattern": r"(\d+)", "scope": {"member_type": "beam"},
        "custom_marker": "REGISTRY_SENTINEL",
    }]

    def _check(document, facts, config, *, ocr_texts=None, job_dir=None):
        captured.update(config)
        return _check_payload()

    _run(registry, {"facts": {"demo_fact": {"value": 900, "unit": "mm"}}}, check_tool=_check)
    assert captured["fact_id"] == "demo_fact"
    assert captured["aliases"] == ["别名A", "别名B"]
    assert captured["keywords"] == ["别名A", "别名B"]
    assert captured["unit"] == "mm"
    assert captured["scope"] == {"member_type": "beam"}
    assert captured["custom_marker"] == "REGISTRY_SENTINEL"


def test_integration_registry_config_binding_does_not_mutate_registry() -> None:
    registry = [_reg("demo_fact", aliases=["参数A"], scope=_BEAM_B)]
    registry[0]["custom_marker"] = "REGISTRY_SENTINEL"
    before = deepcopy(registry)

    def _check(document, facts, config, *, ocr_texts=None, job_dir=None):
        config["custom_marker"] = "MUTATED_RUNTIME_COPY"
        return _check_payload()

    _run(registry, {"facts": {"demo_fact": {"value": 900, "unit": "mm"}}}, check_tool=_check)
    assert registry == before


def test_integration_injected_check_tool_contract_preserved() -> None:
    calls = []

    def _check(document, facts, config, *, ocr_texts=None, job_dir=None):
        calls.append(config["custom_marker"])
        return _check_payload()

    registry = [_reg("demo_fact", aliases=["参数A"], scope=_BEAM_B)]
    registry[0]["custom_marker"] = "REGISTRY_SENTINEL"
    result = _run(
        registry, {"facts": {"demo_fact": {"value": 900, "unit": "mm"}}},
        check_tool=_check,
    )
    assert calls == ["REGISTRY_SENTINEL"]
    item = result.items[0]
    assert item.finish_reason == "check_completed"
    assert item.text_evidence_count == 1
    assert item.drawing_evidence_count == 1


def test_integration_direct_check_path_matches_workaround_path() -> None:
    registry = [_reg("demo_fact", aliases=["参数A"], scope=_BEAM_B)]
    registry[0]["custom_marker"] = "REGISTRY_SENTINEL"
    facts = {"facts": {"demo_fact": {"value": 900, "unit": "mm"}}}

    def _core_check(document, facts, config, *, ocr_texts=None, job_dir=None):
        assert config["custom_marker"] == "REGISTRY_SENTINEL"
        return _check_payload()

    def _old_workaround(document, facts, config, *, ocr_texts=None, job_dir=None):
        return _core_check(
            document, facts, {**registry[0], **config},
            ocr_texts=ocr_texts, job_dir=job_dir,
        )

    old = _run(registry, facts, check_tool=_old_workaround).items[0]
    new = _run(registry, facts, check_tool=_core_check).items[0]
    assert (
        old.fact_id, old.status, old.reason, old.text_evidence_count,
        old.drawing_evidence_count, old.finish_reason,
    ) == (
        new.fact_id, new.status, new.reason, new.text_evidence_count,
        new.drawing_evidence_count, new.finish_reason,
    )
