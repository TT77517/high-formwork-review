"""Task 2: Drawing Agent 数据模型 smoke test。

只测 3 个 dataclass 的字段、默认值与 mutable default 隔离，
不测任何业务逻辑 / Agent / Tool 调用。
"""
from __future__ import annotations


def test_drawing_agent_data_models() -> None:
    from app.drawing_agent import (
        DrawingAgentState,
        DrawingReviewTask,
        Evidence,
    )

    # Case 1: DrawingReviewTask 正常构造
    task = DrawingReviewTask(
        fact_id="upright_spacing",
        display_name="立杆间距",
        aliases=["立杆间距", "立杆纵距"],
        text_value=[900, 900],
        unit="mm",
    )
    assert task.fact_id == "upright_spacing"
    assert task.display_name == "立杆间距"
    assert task.aliases == ["立杆间距", "立杆纵距"]
    assert task.text_value == [900, 900]
    assert task.unit == "mm"
    assert task.priority == "medium"
    assert task.source == "project_fact"
    assert task.scope == {}

    # Case 2: text_value=None 合法（仅证明数据模型允许）
    missing_task = DrawingReviewTask(
        fact_id="head_jack_insertion_length",
        display_name="可调托撑插入长度",
        aliases=["托撑插入长度"],
        text_value=None,
    )
    assert missing_task.text_value is None
    assert missing_task.priority == "medium"
    assert missing_task.source == "project_fact"

    # Case 3: Evidence 正常构造
    evidence = Evidence(
        fact_id="upright_spacing",
        source_type="drawing_text",
        value=[900, 900],
        unit="mm",
        page=88,
        evidence_text="立杆间距900×900",
        confidence=0.95,
        source_role="drawing_annotation",
    )
    assert evidence.fact_id == "upright_spacing"
    assert evidence.source_type == "drawing_text"
    assert evidence.value == [900, 900]
    assert evidence.unit == "mm"
    assert evidence.page == 88
    assert evidence.evidence_text == "立杆间距900×900"
    assert evidence.confidence == 0.95
    assert evidence.source_role == "drawing_annotation"
    assert evidence.scope == {}

    # Case 4: DrawingAgentState 正常构造（默认值）
    state = DrawingAgentState(task=task)
    assert state.task is task
    assert state.text_evidence == []
    assert state.drawing_evidence == []
    assert state.candidate_pages == []
    assert state.actions_taken == []
    assert state.iteration == 0
    assert state.ocr_pages == 0
    assert state.vlm_calls == 0
    assert state.finished is False
    assert state.finish_reason is None

    # Case 5: mutable default 隔离
    state1 = DrawingAgentState(task=task)
    state2 = DrawingAgentState(task=task)
    state1.text_evidence.append(evidence)
    assert state2.text_evidence == []  # state2 不受 state1 污染

    task1 = DrawingReviewTask(fact_id="a", display_name="a", aliases=["a"])
    task2 = DrawingReviewTask(fact_id="b", display_name="b", aliases=["b"])
    task1.scope["member_type"] = "beam"
    assert task2.scope == {}  # task2 不受 task1 污染

    ev1 = Evidence(fact_id="x", source_type="text")
    ev2 = Evidence(fact_id="y", source_type="text")
    ev1.scope["loc"] = "beam_bottom"
    assert ev2.scope == {}  # ev2 不受 ev1 污染


def test_build_drawing_review_tasks_keeps_missing_project_facts() -> None:
    """Task 3: ProjectFact 缺失（含 value=None）也必须生成 Task。

    用真实 DRAWING_PARAM_REGISTRY 验证：
    - 顺序、总数与 registry 一致
    - 有 value 的 fact → source="project_fact"
    - 缺 key 的 fact → Task 仍在, text_value=None, source="critical_fact"
    - value=None 的 fact → Task 仍在, text_value=None, source="critical_fact"
    - aliases 是新 list，不与 registry 共享可变对象
    """
    from app.drawing_agent import build_drawing_review_tasks
    from app.drawing_review import DRAWING_PARAM_REGISTRY

    # 选三条不同 fact_id 做覆盖
    c0 = DRAWING_PARAM_REGISTRY[0]
    c1 = DRAWING_PARAM_REGISTRY[1]
    c2 = DRAWING_PARAM_REGISTRY[2]
    fid0 = c0["fact_id"]
    fid1 = c1["fact_id"]
    fid2 = c2["fact_id"]

    facts = {
        fid0: {"value": 1500, "unit": "mm"},
        # fid1 完全不提供（key 缺失）
        fid2: {"value": None},  # key 在但 value=None
    }
    tasks = build_drawing_review_tasks(facts, DRAWING_PARAM_REGISTRY)

    # Case 5: 数量与顺序
    assert len(tasks) == len(DRAWING_PARAM_REGISTRY)
    assert [t.fact_id for t in tasks] == [c["fact_id"] for c in DRAWING_PARAM_REGISTRY]

    by_fid = {t.fact_id: t for t in tasks}

    # Case 2: 有 value → project_fact
    t0 = by_fid[fid0]
    assert t0.text_value == 1500
    assert t0.unit == "mm"
    assert t0.source == "project_fact"

    # Case 3: key 缺失 → 仍有 Task, text_value=None, source="critical_fact"
    t1 = by_fid[fid1]
    assert t1 is not None
    assert t1.text_value is None
    assert t1.source == "critical_fact"

    # Case 4: value=None → 仍有 Task, text_value=None, source="critical_fact"
    t2 = by_fid[fid2]
    assert t2 is not None
    assert t2.text_value is None
    assert t2.source == "critical_fact"

    # Case 6: aliases 不污染 registry
    t0.aliases.append("MUTATED")
    assert "MUTATED" not in c0["keywords"]  # registry 未被污染
    # task.aliases 是新 list（不是 config 同一对象）
    assert t0.aliases is not c0["keywords"]


def _make_recall_tool(pages, counter):
    def _recall(document, aliases, limit=8):
        counter["n"] += 1
        return list(pages)
    return _recall


def _make_check_tool(payload, counter):
    def _check(document, facts, config, *, ocr_texts=None, job_dir=None):
        counter["n"] += 1
        return payload
    return _check


def test_drawing_agent_v1_happy_path() -> None:
    """Task 4 Case 1: text 有值 + candidate 有 → SEARCH → CHECK → FINISH。"""
    from app.drawing_agent import (
        CHECK_PARAM,
        MAX_ITERATIONS,
        MAX_OCR_PAGES,
        MAX_TEXT_SEARCHES,
        MAX_VLM_CALLS,
        DrawingAgentState,
        DrawingConsistencyAgent,
        DrawingReviewTask,
        FINISH,
        SEARCH_DRAWING,
    )
    from app.drawing_review import (
        cross_check_param,
        ocr_drawing_page,
        recall_drawing_pages,
    )

    # 真实 Tool 注入兼容性（不要求跑 document，只验证构造器能接）
    real_agent = DrawingConsistencyAgent(
        recall_tool=recall_drawing_pages,
        check_tool=cross_check_param,
        ocr_tool=ocr_drawing_page,
    )
    assert real_agent is not None
    assert callable(ocr_drawing_page)
    assert MAX_ITERATIONS == 5
    assert MAX_OCR_PAGES == 2
    assert MAX_VLM_CALLS == 1
    assert MAX_TEXT_SEARCHES == 1

    recall_counter = {"n": 0}
    check_counter = {"n": 0}
    agent = DrawingConsistencyAgent(
        recall_tool=_make_recall_tool(
            [{"physical_page": 88, "keyword_hits": ["立杆间距"]}],
            recall_counter,
        ),
        check_tool=_make_check_tool({"status": "PASS"}, check_counter),
        ocr_tool=lambda *a, **k: None,
    )

    task = DrawingReviewTask(
        fact_id="upright_spacing",
        display_name="立杆间距",
        aliases=["立杆间距"],
        text_value=900,
        unit="mm",
    )
    state = agent.run(
        task=task,
        document=None,
        facts={},
        config={"fact_id": "upright_spacing"},
    )

    assert isinstance(state, DrawingAgentState)
    assert state.finished is True
    assert state.finish_reason == "check_completed"
    assert state.iteration == 2
    assert [a["action"] for a in state.actions_taken] == [SEARCH_DRAWING, CHECK_PARAM]
    assert len(state.candidate_pages) == 1
    assert recall_counter["n"] == 1
    assert check_counter["n"] == 1


def test_drawing_agent_v1_missing_text_value_still_searches() -> None:
    """Task 4→5A: text_value=None 仍先 SEARCH_DRAWING，再尝试 OCR_PAGE。

    本轮升级为 OCR 路径：单 candidate + OCR 返回无 alias 的文本 → FINISH(ocr_no_evidence)。
    """
    from app.drawing_agent import (
        DrawingConsistencyAgent,
        DrawingReviewTask,
        MAX_ITERATIONS,
        OCR_PAGE,
        SEARCH_DRAWING,
    )

    recall_counter = {"n": 0}
    ocr_counter = {"n": 0}

    def _raise_if_check_called(*args, **kwargs):
        raise AssertionError("CHECK_PARAM must not run when text_value is None")

    def _fake_ocr(page, engine, *, job_dir=None):
        ocr_counter["n"] += 1
        return "无 alias 的 OCR 文本"

    candidate_page = _make_fake_page(12)
    document = _make_fake_document([candidate_page])
    agent = DrawingConsistencyAgent(
        recall_tool=_make_recall_tool(
            [{"physical_page": 12, "keyword_hits": ["托撑插入长度"]}],
            recall_counter,
        ),
        check_tool=_raise_if_check_called,
        ocr_tool=_fake_ocr,
    )
    task = DrawingReviewTask(
        fact_id="head_jack_insertion_length",
        display_name="可调托撑插入长度",
        aliases=["托撑插入长度"],
        text_value=None,
    )
    state = agent.run(
        task=task,
        document=document,
        facts={},
        config={"fact_id": "head_jack_insertion_length"},
        ocr_engine=object(),  # 任意 truthy
    )

    assert state.finished is True
    assert state.finish_reason == "vision_unavailable"  # OCR miss → drawing_evidence=[] → 不 SEARCH_TEXT
    assert state.iteration == 2
    assert [a["action"] for a in state.actions_taken] == [SEARCH_DRAWING, OCR_PAGE]
    assert state.drawing_evidence == []  # OCR 返回 "无 alias" → 不生成 Evidence
    assert len(state.candidate_pages) == 1
    assert state.ocr_pages == 1
    assert recall_counter["n"] == 1
    assert ocr_counter["n"] == 1


def test_drawing_agent_v1_empty_candidate_pages_stops() -> None:
    """Task 4 Case 3: candidate_pages 为空自动停止。"""
    from app.drawing_agent import (
        DrawingConsistencyAgent,
        DrawingReviewTask,
        SEARCH_DRAWING,
    )

    recall_counter = {"n": 0}

    def _raise_if_check_called(*args, **kwargs):
        raise AssertionError("CHECK_PARAM must not run when candidate_pages is empty")

    agent = DrawingConsistencyAgent(
        recall_tool=_make_recall_tool([], recall_counter),
        check_tool=_raise_if_check_called,
        ocr_tool=lambda *a, **k: None,
    )
    task = DrawingReviewTask(
        fact_id="standard_step_height",
        display_name="步距",
        aliases=["步距"],
        text_value=1500,
        unit="mm",
    )
    state = agent.run(
        task=task,
        document=None,
        facts={},
        config={"fact_id": "standard_step_height"},
    )

    assert state.finished is True
    assert state.finish_reason == "no_candidate_pages"
    assert state.iteration == 1
    assert [a["action"] for a in state.actions_taken] == [SEARCH_DRAWING]
    assert state.candidate_pages == []
    assert recall_counter["n"] == 1


def _make_fake_page(physical_page: int):
    class _P:
        pass
    p = _P()
    p.physical_page = physical_page
    return p


def _make_fake_document(pages):
    class _D:
        pass
    d = _D()
    d.pages = list(pages)
    return d


def test_drawing_agent_v1_text_evidence_initialized_once() -> None:
    """Task 5A Case 1: text_value 有值时初始化 TextEvidence（且只一次）。"""
    from app.drawing_agent import (
        DrawingConsistencyAgent,
        DrawingReviewTask,
    )
    agent = DrawingConsistencyAgent(
        recall_tool=_make_recall_tool(
            [{"physical_page": 5, "keyword_hits": ["步距"]}], {"n": 0},
        ),
        check_tool=_make_check_tool({"status": "PASS"}, {"n": 0}),
        ocr_tool=lambda *a, **k: None,
    )
    task = DrawingReviewTask(
        fact_id="standard_step_height", display_name="步距",
        aliases=["步距"], text_value=900, unit="mm",
    )
    state = agent.run(
        task=task, document=None, facts={},
        config={"fact_id": "standard_step_height"},
    )
    assert len(state.text_evidence) == 1
    ev = state.text_evidence[0]
    assert ev.fact_id == "standard_step_height"
    assert ev.source_type == "text"
    assert ev.value == 900
    assert ev.unit == "mm"
    assert ev.source_role == "design_parameter"


def test_drawing_agent_v1_ocr_evidence_found_single_page() -> None:
    """Task 5A Case 2: missing text + OCR 命中 alias → DrawingEvidence + FINISH。"""
    from app.drawing_agent import (
        DrawingConsistencyAgent, DrawingReviewTask,
        MAX_OCR_PAGES, OCR_PAGE, SEARCH_DRAWING,
    )
    recall_counter = {"n": 0}
    ocr_counter = {"n": 0}

    def _raise_if_check_called(*args, **kwargs):
        raise AssertionError("CHECK_PARAM must not run when text_value is None")

    def _fake_ocr(page, engine, *, job_dir=None):
        ocr_counter["n"] += 1
        return "梁底托撑插入长度150mm"

    document = _make_fake_document([_make_fake_page(88)])
    agent = DrawingConsistencyAgent(
        recall_tool=_make_recall_tool(
            [{"physical_page": 88, "keyword_hits": ["托撑插入长度"]}],
            recall_counter,
        ),
        check_tool=_raise_if_check_called,
        ocr_tool=_fake_ocr,
    )
    task = DrawingReviewTask(
        fact_id="head_jack_insertion_length", display_name="可调托撑插入长度",
        aliases=["托撑插入长度"], text_value=None,
    )
    state = agent.run(
        task=task, document=document, facts={},
        config={"fact_id": "head_jack_insertion_length"},
        ocr_engine=object(),
    )
    assert state.finished is True
    assert state.finish_reason == "text_search_unavailable"
    assert state.iteration == 2
    assert state.ocr_pages == 1
    assert MAX_OCR_PAGES == 2
    assert [a["action"] for a in state.actions_taken] == [SEARCH_DRAWING, OCR_PAGE]
    assert len(state.drawing_evidence) >= 1
    ev = state.drawing_evidence[0]
    assert ev.fact_id == "head_jack_insertion_length"
    assert ev.source_type == "ocr"
    assert ev.page == 88
    assert ev.source_role == "drawing_annotation"
    assert "托撑插入长度" in (ev.evidence_text or "")
    assert recall_counter["n"] == 1
    assert ocr_counter["n"] == 1
    # Task 7A：OCR Evidence scope 由文本推断（梁底 → beam_bottom）
    assert ev.scope == {"member_type": "beam", "location": "beam_bottom"}


def test_drawing_agent_v1_ocr_skips_to_second_page_on_miss() -> None:
    """Task 5A Case 3: 第 1 页无 alias → 第 2 页命中（不重复 OCR 同页）。"""
    from app.drawing_agent import (
        DrawingConsistencyAgent, DrawingReviewTask, OCR_PAGE, SEARCH_DRAWING,
    )
    ocr_calls: list[int] = []

    def _raise_if_check_called(*args, **kwargs):
        raise AssertionError("CHECK_PARAM must not run when text_value is None")

    def _fake_ocr(page, engine, *, job_dir=None):
        ocr_calls.append(page.physical_page)
        if page.physical_page == 7:
            return "施工平面布置图 安全通道"  # 无 alias
        if page.physical_page == 9:
            return "详图：扫地杆高度 200mm"  # 含 alias
        return ""

    document = _make_fake_document([_make_fake_page(7), _make_fake_page(9)])
    agent = DrawingConsistencyAgent(
        recall_tool=_make_recall_tool(
            [
                {"physical_page": 7, "keyword_hits": ["扫地杆高度"]},
                {"physical_page": 9, "keyword_hits": ["扫地杆高度"]},
            ],
            {"n": 0},
        ),
        check_tool=_raise_if_check_called,
        ocr_tool=_fake_ocr,
    )
    task = DrawingReviewTask(
        fact_id="sweeper_centerline_height_above_base_plate",
        display_name="扫地杆高度", aliases=["扫地杆高度"], text_value=None,
    )
    state = agent.run(
        task=task, document=document, facts={},
        config={"fact_id": "sweeper_centerline_height_above_base_plate"},
        ocr_engine=object(),
    )
    assert state.finished is True
    assert state.finish_reason == "text_search_unavailable"
    assert state.iteration == 3
    assert state.ocr_pages == 2
    assert ocr_calls == [7, 9]  # page A 不重复
    assert [a["action"] for a in state.actions_taken] == [SEARCH_DRAWING, OCR_PAGE, OCR_PAGE]
    assert len(state.drawing_evidence) == 1
    assert state.drawing_evidence[0].page == 9


def test_drawing_agent_v1_ocr_unavailable() -> None:
    """Task 5A Case 4: ocr_engine=None → FINISH(ocr_unavailable)，OCR Tool 0 次调用。"""
    from app.drawing_agent import (
        DrawingConsistencyAgent, DrawingReviewTask, SEARCH_DRAWING,
    )
    ocr_counter = {"n": 0}

    def _raise_if_check_called(*args, **kwargs):
        raise AssertionError("CHECK_PARAM must not run when text_value is None")

    def _fake_ocr(page, engine, *, job_dir=None):
        ocr_counter["n"] += 1
        return None

    agent = DrawingConsistencyAgent(
        recall_tool=_make_recall_tool(
            [{"physical_page": 3, "keyword_hits": ["步距"]}], {"n": 0},
        ),
        check_tool=_raise_if_check_called,
        ocr_tool=_fake_ocr,
    )
    task = DrawingReviewTask(
        fact_id="standard_step_height", display_name="步距",
        aliases=["步距"], text_value=None,
    )
    state = agent.run(
        task=task, document=None, facts={},
        config={"fact_id": "standard_step_height"},
        ocr_engine=None,  # 关键：engine 不传
    )
    assert state.finished is True
    assert state.finish_reason == "ocr_unavailable"
    assert state.iteration == 1
    assert [a["action"] for a in state.actions_taken] == [SEARCH_DRAWING]
    assert ocr_counter["n"] == 0


def test_drawing_agent_v1_ocr_evidence_triggers_vlm() -> None:
    """Task 5B Case 1: OCR alias 命中 + VLM found=True → OCR + VLM 双 Evidence。"""
    from app.drawing_agent import (
        DrawingConsistencyAgent, DrawingReviewTask,
        INSPECT_IMAGE, OCR_PAGE, SEARCH_DRAWING,
    )
    def _check_never_called(*a, **k): raise AssertionError("CHECK_PARAM must not run")
    def _fake_ocr(page, engine, *, job_dir=None): return "梁底节点详图：托撑插入长度150mm"
    # Task 7A Test 58：VLM scope 含中文 + 多余 floor 字段
    def _fake_vision(page, task): return {"found": True, "value": 150, "unit": "mm", "evidence_text": "梁底插入150", "confidence": 0.94, "scope": {"member_type": "梁", "location": "梁底", "floor": "3F"}}
    agent = DrawingConsistencyAgent(
        recall_tool=_make_recall_tool([{"physical_page": 88, "keyword_hits": ["托撑插入长度"]}], {"n": 0}),
        check_tool=_check_never_called, ocr_tool=_fake_ocr, vision_tool=_fake_vision,
    )
    task = DrawingReviewTask(
        fact_id="head_jack_insertion_length", display_name="可调托撑插入长度",
        aliases=["托撑插入长度"], text_value=None,
    )
    state = agent.run(
        task=task, document=_make_fake_document([_make_fake_page(88)]), facts={},
        config={"fact_id": "head_jack_insertion_length"}, ocr_engine=object(),
    )
    assert state.finished is True and state.finish_reason == "text_search_unavailable"
    assert state.iteration == 3 and state.ocr_pages == 1 and state.vlm_calls == 1
    assert [a["action"] for a in state.actions_taken] == [SEARCH_DRAWING, OCR_PAGE, INSPECT_IMAGE]
    assert sorted(ev.source_type for ev in state.drawing_evidence) == ["ocr", "vlm"]
    vlm_ev = next(ev for ev in state.drawing_evidence if ev.source_type == "vlm")
    assert vlm_ev.value == 150 and vlm_ev.unit == "mm" and vlm_ev.confidence == 0.94
    assert vlm_ev.page == 88 and vlm_ev.fact_id == "head_jack_insertion_length"
    # Task 7A：VLM scope 经 normalize 后只保留 member_type/location（floor 丢弃）
    assert vlm_ev.scope == {"member_type": "beam", "location": "beam_bottom"}


def test_drawing_agent_v1_ocr_miss_falls_back_to_vlm() -> None:
    """Task 5B Case 2: OCR miss → VLM fallback 仍产生 VLM Evidence。"""
    from app.drawing_agent import (
        DrawingConsistencyAgent, DrawingReviewTask,
        INSPECT_IMAGE, OCR_PAGE, SEARCH_DRAWING,
    )
    def _check_never_called(*a, **k): raise AssertionError("CHECK_PARAM must not run")
    def _fake_ocr(page, engine, *, job_dir=None): return "施工平面布置图 安全通道"
    def _fake_vision(page, task): return {"found": True, "value": 150, "unit": "mm", "evidence_text": "插入长度150", "confidence": 0.9, "scope": {}}
    agent = DrawingConsistencyAgent(
        recall_tool=_make_recall_tool([{"physical_page": 88, "keyword_hits": ["托撑插入长度"]}], {"n": 0}),
        check_tool=_check_never_called, ocr_tool=_fake_ocr, vision_tool=_fake_vision,
    )
    task = DrawingReviewTask(
        fact_id="head_jack_insertion_length", display_name="可调托撑插入长度",
        aliases=["托撑插入长度"], text_value=None,
    )
    state = agent.run(
        task=task, document=_make_fake_document([_make_fake_page(88)]), facts={},
        config={"fact_id": "head_jack_insertion_length"}, ocr_engine=object(),
    )
    assert state.finished is True and state.finish_reason == "text_search_unavailable"
    assert state.iteration == 3 and state.vlm_calls == 1
    assert [a["action"] for a in state.actions_taken] == [SEARCH_DRAWING, OCR_PAGE, INSPECT_IMAGE]
    assert all(ev.source_type != "ocr" for ev in state.drawing_evidence)
    assert len(state.drawing_evidence) == 1 and state.drawing_evidence[0].source_type == "vlm"


def test_drawing_agent_v1_vision_unavailable_preserves_ocr_evidence() -> None:
    """Task 5B Case 3: vision_tool=None → FINISH(vision_unavailable)，OCR Evidence 保留。"""
    from app.drawing_agent import (
        DrawingConsistencyAgent, DrawingReviewTask,
        OCR_PAGE, SEARCH_DRAWING,
    )
    def _check_never_called(*a, **k): raise AssertionError("CHECK_PARAM must not run")
    def _fake_ocr(page, engine, *, job_dir=None): return "节点详图：托撑插入长度150mm"
    agent = DrawingConsistencyAgent(
        recall_tool=_make_recall_tool([{"physical_page": 88, "keyword_hits": ["托撑插入长度"]}], {"n": 0}),
        check_tool=_check_never_called, ocr_tool=_fake_ocr,  # vision_tool 默认 None
    )
    task = DrawingReviewTask(
        fact_id="head_jack_insertion_length", display_name="可调托撑插入长度",
        aliases=["托撑插入长度"], text_value=None,
    )
    state = agent.run(
        task=task, document=_make_fake_document([_make_fake_page(88)]), facts={},
        config={"fact_id": "head_jack_insertion_length"}, ocr_engine=object(),
    )
    assert state.finished is True and state.finish_reason == "text_search_unavailable"
    assert state.iteration == 2 and state.vlm_calls == 0
    assert [a["action"] for a in state.actions_taken] == [SEARCH_DRAWING, OCR_PAGE]
    # OCR alias 命中 → drawing_evidence 有 1 条；vision_tool=None → 跳过 VLM；
    # drawing_evidence 非空 + search_text_tool 默认 None → text_search_unavailable
    assert len(state.drawing_evidence) == 1
    assert state.drawing_evidence[0].source_type == "ocr"


def test_drawing_agent_v1_vision_found_false_no_evidence() -> None:
    """Task 5B Case 4: vision_tool 返回 found=False → FINISH(vision_no_evidence)。"""
    from app.drawing_agent import (
        DrawingConsistencyAgent, DrawingReviewTask,
        INSPECT_IMAGE, OCR_PAGE, SEARCH_DRAWING,
    )
    def _check_never_called(*a, **k): raise AssertionError("CHECK_PARAM must not run")
    def _fake_ocr(page, engine, *, job_dir=None): return "无 alias 文本"
    def _fake_vision(page, task): return {"found": False, "value": None, "unit": None, "evidence_text": None, "confidence": None, "scope": {}}
    agent = DrawingConsistencyAgent(
        recall_tool=_make_recall_tool([{"physical_page": 88, "keyword_hits": ["托撑插入长度"]}], {"n": 0}),
        check_tool=_check_never_called, ocr_tool=_fake_ocr, vision_tool=_fake_vision,
    )
    task = DrawingReviewTask(
        fact_id="head_jack_insertion_length", display_name="可调托撑插入长度",
        aliases=["托撑插入长度"], text_value=None,
    )
    state = agent.run(
        task=task, document=_make_fake_document([_make_fake_page(88)]), facts={},
        config={"fact_id": "head_jack_insertion_length"}, ocr_engine=object(),
    )
    assert state.finished is True and state.finish_reason == "ocr_no_evidence"  # VLM found=false + drawing_evidence=[] → fallback
    assert state.iteration == 3 and state.ocr_pages == 1 and state.vlm_calls == 1
    assert [a["action"] for a in state.actions_taken] == [SEARCH_DRAWING, OCR_PAGE, INSPECT_IMAGE]
    assert all(ev.source_type != "vlm" for ev in state.drawing_evidence)


def test_drawing_agent_v6_vlm_value_triggers_search_text() -> None:
    """Task 6 Case 1: VLM value → SEARCH_TEXT (value anchor) → TextEvidence。"""
    from app.drawing_agent import (
        DrawingConsistencyAgent, DrawingReviewTask,
        INSPECT_IMAGE, OCR_PAGE, SEARCH_DRAWING, SEARCH_TEXT,
    )
    search_calls: list[dict] = []

    def _check_never_called(*a, **k): raise AssertionError("CHECK_PARAM must not run")
    def _fake_ocr(page, engine, *, job_dir=None): return "节点详图：托撑插入长度150mm"
    def _fake_vision(page, task): return {"found": True, "value": 150, "unit": "mm", "evidence_text": "150mm", "confidence": 0.94, "scope": {}}
    def _fake_search_text(document, aliases, *, target_value=None, unit=None, limit=3):
        search_calls.append({"aliases": aliases, "target_value": target_value, "unit": unit})
        return [{
            "physical_page": 12, "printed_page": "12",
            "evidence_text": "可调托撑插入立杆长度为150mm",
            "value": 150, "unit": "mm",
            "matched_alias": "托撑插入", "matched_value": True,
        }]

    document = _make_fake_document([_make_fake_page(88)])
    agent = DrawingConsistencyAgent(
        recall_tool=_make_recall_tool([{"physical_page": 88, "keyword_hits": ["托撑插入长度"]}], {"n": 0}),
        check_tool=_check_never_called,
        ocr_tool=_fake_ocr, vision_tool=_fake_vision,
        search_text_tool=_fake_search_text,
    )
    task = DrawingReviewTask(
        fact_id="head_jack_insertion_length", display_name="可调托撑插入长度",
        aliases=["托撑插入长度"], text_value=None, unit="mm",
    )
    state = agent.run(
        task=task, document=document, facts={},
        config={"fact_id": "head_jack_insertion_length"}, ocr_engine=object(),
    )
    assert state.finished is True and state.finish_reason == "text_evidence_found"
    assert state.iteration == 4 and state.ocr_pages == 1 and state.vlm_calls == 1
    assert [a["action"] for a in state.actions_taken] == [SEARCH_DRAWING, OCR_PAGE, INSPECT_IMAGE, SEARCH_TEXT]
    assert len(state.drawing_evidence) >= 1  # OCR + VLM
    assert len(state.text_evidence) == 1
    assert state.text_evidence[0].source_type == "text"
    assert state.text_evidence[0].value == 150
    assert state.text_evidence[0].source_role == "unknown"
    # search_text_tool 收到 target_value=150（来自 VLM Evidence）
    assert search_calls[0]["target_value"] == 150
    assert search_calls[0]["unit"] == "mm"


def test_drawing_agent_v6_ocr_evidence_then_alias_only_search_text() -> None:
    """Task 6 Case 2: OCR Evidence + vision unavailable → alias-only SEARCH_TEXT。"""
    from app.drawing_agent import (
        DrawingConsistencyAgent, DrawingReviewTask,
        OCR_PAGE, SEARCH_DRAWING, SEARCH_TEXT,
    )
    search_calls: list[dict] = []

    def _check_never_called(*a, **k): raise AssertionError("CHECK_PARAM must not run")
    def _fake_ocr(page, engine, *, job_dir=None): return "节点详图：托撑插入长度详见节点"
    def _fake_search_text(document, aliases, *, target_value=None, unit=None, limit=3):
        search_calls.append({"aliases": aliases, "target_value": target_value, "unit": unit})
        return [{
            "physical_page": 5, "printed_page": "5",
            "evidence_text": "板底可调托撑插入长度详见节点详图",
            "value": None, "unit": None,
            "matched_alias": "托撑插入长度", "matched_value": False,
        }]

    document = _make_fake_document([_make_fake_page(88)])
    agent = DrawingConsistencyAgent(
        recall_tool=_make_recall_tool([{"physical_page": 88, "keyword_hits": ["托撑插入长度"]}], {"n": 0}),
        check_tool=_check_never_called,
        ocr_tool=_fake_ocr,
        # vision_tool 默认 None
        search_text_tool=_fake_search_text,
    )
    task = DrawingReviewTask(
        fact_id="head_jack_insertion_length", display_name="可调托撑插入长度",
        aliases=["托撑插入长度"], text_value=None, unit="mm",
    )
    state = agent.run(
        task=task, document=document, facts={},
        config={"fact_id": "head_jack_insertion_length"}, ocr_engine=object(),
    )
    assert state.finished is True and state.finish_reason == "text_evidence_found"
    assert state.vlm_calls == 0
    assert [a["action"] for a in state.actions_taken] == [SEARCH_DRAWING, OCR_PAGE, SEARCH_TEXT]
    assert len(state.text_evidence) == 1
    assert state.text_evidence[0].value is None  # alias-only，value=None
    # search_text_tool 收到 target_value=None（OCR Evidence 没有 value）
    assert search_calls[0]["target_value"] is None
    # Task 7A：reverse TextEvidence scope 由文本推断（板底 → slab_bottom）
    assert state.text_evidence[0].scope == {"member_type": "slab", "location": "slab_bottom"}


def test_drawing_agent_v6_search_text_tool_unavailable_keeps_drawing_evidence() -> None:
    """Task 6 Case 3: DrawingEvidence 存在 + search_text_tool=None → text_search_unavailable。"""
    from app.drawing_agent import (
        DrawingConsistencyAgent, DrawingReviewTask,
        OCR_PAGE, SEARCH_DRAWING,
    )

    def _check_never_called(*a, **k): raise AssertionError("CHECK_PARAM must not run")
    def _fake_ocr(page, engine, *, job_dir=None): return "节点详图：托撑插入长度150mm"
    # search_text_tool 默认 None

    document = _make_fake_document([_make_fake_page(88)])
    agent = DrawingConsistencyAgent(
        recall_tool=_make_recall_tool([{"physical_page": 88, "keyword_hits": ["托撑插入长度"]}], {"n": 0}),
        check_tool=_check_never_called,
        ocr_tool=_fake_ocr,
        # vision_tool 默认 None，search_text_tool 默认 None
    )
    task = DrawingReviewTask(
        fact_id="head_jack_insertion_length", display_name="可调托撑插入长度",
        aliases=["托撑插入长度"], text_value=None, unit="mm",
    )
    state = agent.run(
        task=task, document=document, facts={},
        config={"fact_id": "head_jack_insertion_length"}, ocr_engine=object(),
    )
    assert state.finished is True and state.finish_reason == "text_search_unavailable"
    # 不增加 SEARCH_TEXT action
    assert SEARCH_DRAWING in [a["action"] for a in state.actions_taken]
    assert all(a["action"] != "SEARCH_TEXT" for a in state.actions_taken)
    # DrawingEvidence 必须保留
    assert len(state.drawing_evidence) == 1
    assert state.drawing_evidence[0].source_type == "ocr"


# ---------------------------------------------------------------------------
# Task 7C: CHECK_PARAM → structured DrawingEvidence
# ---------------------------------------------------------------------------


def _fake_legacy_check_result(*, body, drawing, drawing_evidence, status="PASS"):
    """构造一个模仿真实 cross_check_param schema 的 check result dict。

    只覆盖 adapter 关心的字段（drawing_value + drawing_evidence + body_value + status），
    其余字段（category / title / explanation / boundary 等）填占位符。
    """
    return {
        "review_item_id": "DR-99",
        "category": "图文一致性",
        "title": "...",
        "review_method": "text_drawing_cross_check",
        "status": status,
        "conclusion": "...",
        "body_value": body,
        "drawing_value": drawing,
        "text_evidence": [],
        "drawing_evidence": drawing_evidence,
        "evidence_quality": "high" if status == "PASS" else "medium",
        "review_explanation": {},
        "automation_level": "text_level_cross_check",
        "requires_human_review": status != "PASS",
        "boundary": "...",
    }


def _run_check_param_test(*, text_value, unit, aliases, fact_id, check_result):
    """最小 Agent 编排：recall 1 candidate + check_tool 返 check_result。"""
    from app.drawing_agent import DrawingConsistencyAgent, DrawingReviewTask

    def _check(document, facts, config, *, ocr_texts=None, job_dir=None):
        return check_result
    agent = DrawingConsistencyAgent(
        recall_tool=_make_recall_tool(
            [{"physical_page": 88, "keyword_hits": aliases}], {"n": 0},
        ),
        check_tool=_check,
        ocr_tool=lambda *a, **k: None,
    )
    task = DrawingReviewTask(
        fact_id=fact_id, display_name=fact_id, aliases=aliases,
        text_value=text_value, unit=unit,
    )
    return agent.run(task=task, document=None, facts={}, config={"fact_id": fact_id})


def test_check_param_same_value_creates_drawing_evidence() -> None:
    """Task 7C Test 1: text=drawing=900 → DrawingEvidence(source_type='legacy_check', value=900)。"""
    from app.drawing_agent import CHECK_PARAM, SEARCH_DRAWING
    check_result = _fake_legacy_check_result(
        body=900, drawing=900,
        drawing_evidence=[{"value": 900, "page": 88, "quote": "步距900mm", "keyword": "步距", "source": "native_text"}],
        status="PASS",
    )
    state = _run_check_param_test(
        text_value=900, unit="mm", aliases=["步距"],
        fact_id="standard_step_height", check_result=check_result,
    )
    assert [a["action"] for a in state.actions_taken] == [SEARCH_DRAWING, CHECK_PARAM]
    assert len(state.text_evidence) == 1
    assert len(state.drawing_evidence) == 1
    d_ev = state.drawing_evidence[0]
    assert d_ev.fact_id == "standard_step_height"
    assert d_ev.source_type == "legacy_check"
    assert d_ev.value == 900
    # Task 7C.1：unit provenance 修正。legacy drawing_evidence entry 不带
    # drawing-side unit 字段 → DrawingEvidence.unit 必须为 None，让 Comparator
    # Unit Gate 报 unit_incomplete → UNCERTAIN，不偷偷用 task.unit 伪造
    # "图纸明确单位"。
    assert d_ev.unit is None
    assert d_ev.page == 88
    assert d_ev.evidence_text == "步距900mm"
    assert d_ev.source_role == "drawing_annotation"
    assert d_ev.confidence is None
    assert state.finish_reason == "check_completed"


def test_check_param_different_value_preserves_both() -> None:
    """Task 7C Test 2（最关键）: text=900, drawing=1200 → TextEvidence=900, DrawingEvidence=1200。"""
    check_result = _fake_legacy_check_result(
        body=900, drawing=1200,
        drawing_evidence=[{"value": 1200, "page": 88, "quote": "步距1200mm", "keyword": "步距", "source": "native_text"}],
        status="ISSUE",
    )
    state = _run_check_param_test(
        text_value=900, unit="mm", aliases=["步距"],
        fact_id="standard_step_height", check_result=check_result,
    )
    assert len(state.text_evidence) == 1
    assert len(state.drawing_evidence) == 1
    assert state.text_evidence[0].value == 900
    assert state.drawing_evidence[0].value == 1200
    # 关键反退化断言：DrawingEvidence.value 绝不能复制 task.text_value
    assert state.drawing_evidence[0].value != 900


def test_check_param_scope_and_metadata() -> None:
    """Task 7C Test 3: 真实 drawing-side quote 含 '梁底' → scope=beam_bottom；保留 page/unit/quote。"""
    check_result = _fake_legacy_check_result(
        body=[900, 900], drawing=[900, 900],
        drawing_evidence=[{
            "value": [900, 900], "page": 12, "quote": "梁底立杆间距900×900mm",
            "keyword": "立杆纵距", "source": "native_text",
        }],
        status="PASS",
    )
    state = _run_check_param_test(
        text_value=[900, 900], unit="mm", aliases=["立杆纵距"],
        fact_id="vertical_spacing", check_result=check_result,
    )
    d_ev = state.drawing_evidence[0]
    assert d_ev.page == 12
    # Task 7C.1：unit 改为 None（无 drawing-side unit 字段）
    assert d_ev.unit is None
    assert d_ev.evidence_text == "梁底立杆间距900×900mm"
    assert d_ev.source_role == "drawing_annotation"
    # Task 7A scope engine：梁底 → beam_bottom
    assert d_ev.scope == {"member_type": "beam", "location": "beam_bottom"}


def test_check_param_no_drawing_evidence_does_not_crash() -> None:
    """Task 7C Test 4: drawing_value=None（REVIEW 路径）→ state.drawing_evidence=[]，不伪造空壳 Evidence。"""
    check_result = _fake_legacy_check_result(
        body=1500, drawing=None, drawing_evidence=[], status="REVIEW",
    )
    state = _run_check_param_test(
        text_value=1500, unit="mm", aliases=["步距"],
        fact_id="standard_step_height", check_result=check_result,
    )
    # 不伪造空壳 Evidence
    assert state.drawing_evidence == []
    # TextEvidence 仍存在
    assert len(state.text_evidence) == 1
    assert state.text_evidence[0].value == 1500
    # CHECK_PARAM action 正常完成
    assert state.finish_reason == "check_completed"
    assert [a["action"] for a in state.actions_taken] == ["SEARCH_DRAWING", "CHECK_PARAM"]

    # ── Task 7C.1 sub-cases（不新增 pytest 函数）──
    # (a) 多个 value-match entry 但 page/quote 不同 → 保守不生成 Evidence
    multi_diff = _fake_legacy_check_result(
        body=900, drawing=900,
        drawing_evidence=[
            {"value": 900, "page": 10, "quote": "梁底立杆间距900×900mm", "keyword": "立杆纵距"},
            {"value": 900, "page": 20, "quote": "板底立杆间距900×900mm", "keyword": "立杆纵距"},
        ],
        status="PASS",
    )
    s_a = _run_check_param_test(
        text_value=900, unit="mm", aliases=["立杆纵距"],
        fact_id="vertical_spacing", check_result=multi_diff,
    )
    assert s_a.drawing_evidence == []  # 不得任意绑定第一条（梁底 scope）

    # (b) 多个 value-match entry 且 page/quote 完全一致 → 允许 collapse 取其一
    multi_same = _fake_legacy_check_result(
        body=900, drawing=900,
        drawing_evidence=[
            {"value": 900, "page": 10, "quote": "立杆纵距900mm", "keyword": "立杆纵距"},
            {"value": 900, "page": 10, "quote": "立杆纵距900mm", "keyword": "立杆纵距"},
        ],
        status="PASS",
    )
    s_b = _run_check_param_test(
        text_value=900, unit="mm", aliases=["立杆纵距"],
        fact_id="vertical_spacing", check_result=multi_same,
    )
    assert len(s_b.drawing_evidence) == 1
    assert s_b.drawing_evidence[0].page == 10
    assert s_b.drawing_evidence[0].unit is None  # Task 7C.1 unit provenance 修正

