import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
import app.web as web
from app.drawing_integration import AgentDrawingReviewItem, AgentDrawingReviewResult
from app.report_generator import build_review_report
from app.models import (
    CompletenessResult,
    CompletenessSummary,
    MinerUDocument,
    MinerUPage,
    MinerUSection,
)


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(web, "JOBS_ROOT", tmp_path / "jobs")
    monkeypatch.setattr(web, "_process_job", lambda job_id: None)
    with TestClient(web.app) as test_client:
        yield test_client


def _completed_job(root: Path) -> str:
    job_id = "a" * 32
    job_dir = root / job_id
    job_dir.mkdir(parents=True)
    _write_json(
        job_dir / "status.json",
        {
            "job_id": job_id,
            "file_name": "demo.pdf",
            "uploaded_at": "2026-07-28T00:00:00+00:00",
            "updated_at": "2026-07-28T00:01:00+00:00",
            "status": "completed",
            "stage": "completed",
            "progress": 100,
            "message": "完成",
            "error_stage": None,
        },
    )
    _write_json(
        job_dir / "mineru_document.json",
        {
            "document_id": "demo",
            "physical_page_count": 1,
            "requires_human_review": False,
            "warnings": [],
            "sections": [
                {
                    "section_id": "section-0001",
                    "title": "工程概况",
                    "level": 1,
                    "path": ["工程概况"],
                    "physical_page_start": 1,
                    "physical_page_end": 1,
                }
            ],
            "pages": [
                {
                    "physical_page": 1,
                    "printed_page": "1",
                    "page_type": "text",
                    "parse_status": "complete",
                    "text": "工程概况",
                    "warnings": [],
                    "requires_human_review": False,
                    "blocks": [
                        {
                            "block_id": "p0001-b0000",
                            "block_type": "title",
                            "text": "工程概况",
                            "title_level": 1,
                            "bbox": None,
                            "image_path": None,
                            "table_html": None,
                            "source_pointer": "/0/0",
                        }
                    ],
                }
            ],
        },
    )
    result = {
        "rule_id": "HF-COMP-001",
        "name": "工程概况",
        "status": "PASS",
        "reason": "证据完整",
        "evidence": [],
        "requires_human_review": False,
        "matched_sections": [],
        "matched_terms": [],
        "matched_subitems": [],
        "physical_pages": [1],
        "printed_pages": ["1"],
    }
    _write_json(job_dir / "completeness_results.json", [result])
    _write_json(
        job_dir / "completeness_summary.json",
        {
            "total_rules": 1,
            "pass_count": 1,
            "missing_count": 0,
            "uncertain_count": 0,
            "results": [result],
        },
    )
    _write_json(
        job_dir / "review_results.json",
        {
            "project_qualification": {
                "project_type": "concrete_formwork_support",
                "support_system": "disk_lock",
                "applicable_rule_packs": ["general_high_formwork", "disk_lock"],
            },
            "completeness_review": {"local_result": {"results": [result]}},
            "substantive_review": [
                {"review_item_id": "SR-01", "title": "支撑体系识别", "status": "PASS"}
            ],
            "summary": {
                "completeness_total": 1,
                "substantive_total": 1,
            },
            "human_review_queue": [],
        },
    )
    return job_id


def _completed_job_with_all_rules(root: Path) -> str:
    """创建包含全部 10 条规则的任务。"""
    job_id = "c" * 32
    job_dir = root / job_id
    job_dir.mkdir(parents=True)
    _write_json(
        job_dir / "status.json",
        {
            "job_id": job_id,
            "file_name": "full.pdf",
            "uploaded_at": "2026-07-28T00:00:00+00:00",
            "updated_at": "2026-07-28T00:02:00+00:00",
            "status": "completed",
            "stage": "completed",
            "progress": 100,
            "message": "解析与完整性审查已完成",
            "error_stage": None,
        },
    )
    pages = [
        {
            "physical_page": i + 1,
            "printed_page": str(i + 1),
            "page_type": "text",
            "parse_status": "complete",
            "text": f"内容第{i + 1}页",
            "warnings": [],
            "requires_human_review": False,
            "blocks": [],
        }
        for i in range(10)
    ]
    _write_json(
        job_dir / "mineru_document.json",
        {
            "document_id": "full",
            "physical_page_count": 10,
            "requires_human_review": False,
            "warnings": [],
            "sections": [],
            "pages": pages,
        },
    )
    rule_ids = [f"HF-COMP-{i:03d}" for i in range(1, 11)]
    rule_names = [
        "工程概况", "编制依据", "施工计划", "施工工艺技术",
        "施工安全保证措施", "施工管理及作业人员配备", "验收要求",
        "应急处置措施", "计算书", "相关施工图纸",
    ]
    statuses = [
        "PASS", "PASS", "MISSING", "PASS", "PASS",
        "UNCERTAIN", "PASS", "MISSING", "PASS", "MISSING",
    ]
    results = [
        {
            "rule_id": rid,
            "name": rname,
            "status": st,
            "reason": f"{rid} 检查结果",
            "evidence": [],
            "requires_human_review": st != "PASS",
            "matched_sections": [],
            "matched_terms": [],
            "matched_subitems": [],
            "physical_pages": [],
            "printed_pages": [],
        }
        for rid, rname, st in zip(rule_ids, rule_names, statuses)
    ]
    _write_json(job_dir / "completeness_results.json", results)
    _write_json(
        job_dir / "completeness_summary.json",
        {
            "total_rules": 10,
            "pass_count": 6,
            "missing_count": 3,
            "uncertain_count": 1,
        },
    )
    return job_id


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _agent_drawing_payload() -> dict:
    return {
        "total_tasks": 17,
        "reviewed_tasks": 17,
        "status_counts": {
            "CONSISTENT": 1,
            "CONFLICT": 1,
            "TEXT_ONLY": 3,
            "DRAWING_ONLY": 1,
            "UNCERTAIN": 2,
            "NOT_FOUND": 12,
        },
        "items": [
            {
                "fact_id": "horizontal_spacing",
                "display_name": "立杆横距",
                "status": "UNCERTAIN",
                "reason": "scope_unknown",
                "scope_alignment": "unknown",
                "text_value": 1.2,
                "text_unit": "m",
                "drawing_value": 1200,
                "drawing_unit": "mm",
                "text_evidence": [{"page": 109, "quote": "立杆横距1.2m"}],
                "drawing_evidence": [{"physical_page": 109, "quote": "横向间距lb(mm) 1200"}],
            },
            {
                "fact_id": "support_height",
                "display_name": "搭设高度",
                "status": "UNCERTAIN",
                "reason": "constraint_not_actual_value",
                "scope_alignment": "unknown",
                "drawing_value": None,
                "drawing_evidence": [{"physical_page": 22, "quote": "H≤8m"}],
            },
            {
                "fact_id": "base_jack_insertion_length",
                "display_name": "可调底座插入长度",
                "status": "NOT_FOUND",
                "reason": "no_candidate_pages",
                "scope_alignment": "unknown",
                "drawing_value": None,
            },
            *[
                {
                    "fact_id": status.lower(),
                    "display_name": status,
                    "status": status,
                    "reason": "no_evidence",
                    "scope_alignment": "unknown",
                }
                for status in ("CONSISTENT", "CONFLICT", "TEXT_ONLY", "DRAWING_ONLY")
            ],
        ],
    }


def _pending_job(root: Path) -> str:
    job_id = "b" * 32
    job_dir = root / job_id
    job_dir.mkdir(parents=True)
    (job_dir / "source.pdf").write_bytes(b"%PDF-1.4\n%%EOF")
    _write_json(
        job_dir / "status.json",
        {
            "job_id": job_id,
            "file_name": "demo.pdf",
            "uploaded_at": "2026-07-28T00:00:00+00:00",
            "status": "uploaded",
            "stage": "uploaded",
            "progress": 10,
            "message": "uploaded",
            "error_stage": None,
        },
    )
    return job_id


def _mock_web_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeMinerUClient:
        def parse_pdf(self, pdf_path: Path, output_dir: Path) -> Path:
            raw_dir = output_dir / "raw"
            raw_dir.mkdir(parents=True)
            return raw_dir

    document = MinerUDocument(
        document_id="web-demo",
        source_file_name="source.pdf",
        source_sha256="abc",
        physical_page_count=1,
        pages=[
            MinerUPage(
                physical_page=1,
                source_page_index=0,
                width=100,
                height=100,
                printed_page="1",
                page_type="text",
                parse_status="complete",
                text="工程概况",
            )
        ],
        sections=[
            MinerUSection(
                section_id="s1",
                title="1. 工程概况",
                level=1,
                path=["1. 工程概况"],
                physical_page_start=1,
                physical_page_end=1,
            )
        ],
    )
    result = CompletenessResult(
        rule_id="HF-COMP-001",
        name="工程概况",
        status="PASS",
        reason="证据完整",
    )
    summary = CompletenessSummary(
        total_rules=1,
        pass_count=1,
        missing_count=0,
        uncertain_count=0,
        results=[result],
    )
    details = [
        {
            "matched_sections": [],
            "matched_terms": [],
            "matched_subitems": [],
            "physical_pages": [1],
            "printed_pages": ["1"],
        }
    ]

    monkeypatch.setattr(web, "MinerUClient", FakeMinerUClient)
    monkeypatch.setattr(web, "parse_mineru", lambda raw_dir: document)
    monkeypatch.setattr(web, "load_rules", lambda path: [{"rule_id": "HF-COMP-001"}])
    monkeypatch.setattr(
        web,
        "review_completeness_with_details",
        lambda document, rules: (summary, details),
    )
    monkeypatch.setattr(
        web,
        "build_evidence_check_markdown",
        lambda document, summary, details: "# evidence\n",
    )


def _patch_fast_review_stages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(web, "build_project_qualification", lambda *_: {})
    monkeypatch.setattr(web, "_build_agent_review_plan", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        web,
        "run_rule_engine_safe",
        lambda *_: {"total_rules": 0, "results": []},
    )
    monkeypatch.setattr(
        web,
        "_run_semantic_stage",
        lambda *_: {"total_rules": 0, "results": []},
    )
    monkeypatch.setattr(
        web,
        "run_calculation_engine_safe",
        lambda *_: {"total_rules": 0, "results": []},
    )
    monkeypatch.setattr(web, "build_substantive_review", lambda *_: [])
    monkeypatch.setattr(web, "build_consistency_review", lambda *_: [])
    monkeypatch.setattr(web, "_get_ocr_engine", lambda: None)


def _agent_review_result() -> AgentDrawingReviewResult:
    statuses = ["CONSISTENT", "CONFLICT", "TEXT_ONLY", "DRAWING_ONLY", "UNCERTAIN", "NOT_FOUND"]
    items = [
        AgentDrawingReviewItem(
            fact_id=f"case_{idx}",
            display_name=status,
            status=status,
            reason="constraint_not_actual_value" if status == "UNCERTAIN" else "no_evidence",
            scope_alignment="unknown",
            text_value=900 if status == "CONFLICT" else None,
            drawing_value=None if status == "UNCERTAIN" else 1200,
            text_unit="mm" if status == "CONFLICT" else None,
            drawing_unit="mm" if status == "CONFLICT" else None,
            text_evidence_count=1,
            drawing_evidence_count=1,
            comparable_pair_count=1 if status == "CONFLICT" else 0,
            finish_reason="completed",
            iterations=2,
        )
        for idx, status in enumerate(statuses)
    ]
    items += [
        AgentDrawingReviewItem(
            fact_id=f"missing_{idx}",
            display_name=f"未找到{idx}",
            status="NOT_FOUND",
            reason="no_candidate_pages",
            scope_alignment="unknown",
            finish_reason="no_usable_image",
            iterations=1,
        )
        for idx in range(11)
    ]
    return AgentDrawingReviewResult(
        items=items,
        total_tasks=17,
        status_counts={
            "CONSISTENT": 1,
            "CONFLICT": 1,
            "TEXT_ONLY": 1,
            "DRAWING_ONLY": 1,
            "UNCERTAIN": 1,
            "NOT_FOUND": 12,
        },
        reviewed_tasks=17,
    )


def test_home_page_is_accessible(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "高支模方案智能审查系统" in response.text


def test_home_page_shows_modular_review_modes(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    text = response.text
    for label in ("智能预审", "完整性审查", "规范语义审查", "图文一致性校验", "计算校核"):
        assert label in text
    assert "工程识别</button>" not in text
    assert "工程基础信息" in text
    assert "总控审查 Agent 工作台" in text
    assert "总控 Agent 识别工程特征并调度完整性、规范、计算、图文四类审查工具" in text
    assert "semanticReviewMode" in text
    assert "内容符合性" not in text
    assert "规范符合性审查" not in text
    assert "Agent 工具" in text


def test_static_app_uses_ai_summary_plan_card(client: TestClient) -> None:
    response = client.get("/static/app.js")
    assert response.status_code == 200
    text = response.text
    assert "AI总结建议" in text
    assert "plan-summary" in text
    assert "ai-advice-list" in text
    assert "展开原始计划明细" in text
    assert "Agent 自主查证目标：" not in text
    assert "/orchestrator" in text
    assert "tool_observations" in text
    assert "无法判定归因" in text
    assert "uncertaintyTagHtml" in text
    assert "uncertain-panel" not in text
    assert "真缺内容" in text
    assert "缺参数" in text
    assert "证据不足" in text
    assert "规则过宽" in text
    assert "reviewExplanationHtml" in text
    assert "calcRecheckTagHtml" in text
    assert "drawingQualityTagHtml" in text
    assert "复算判定理由" in text
    assert "图文判定理由" in text


def test_non_pdf_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/jobs",
        files={"file": ("note.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 415


def test_file_over_50mb_is_rejected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(web, "MAX_UPLOAD_BYTES", 16)
    response = client.post(
        "/api/jobs",
        files={"file": ("large.pdf", b"%PDF-" + b"x" * 12, "application/pdf")},
    )
    assert response.status_code == 413


def test_upload_creates_job(client: TestClient) -> None:
    response = client.post(
        "/api/jobs",
        data={"review_mode": "smart"},
        files={"file": ("方案.pdf", b"%PDF-1.7\n%%EOF", "application/pdf")},
    )
    assert response.status_code == 202
    data = response.json()
    job_dir = web.JOBS_ROOT / data["job_id"]
    assert (job_dir / "source.pdf").is_file()
    assert data["status"] == "uploaded"
    assert data["review_mode"] == "smart"
    assert data["semantic_review_mode"] in {"local", "dify", "agent"}


def test_parameter_consistency_review_mode_is_accepted(client: TestClient) -> None:
    response = client.post(
        "/api/jobs",
        data={"review_mode": "calculation"},
        files={"file": ("方案.pdf", b"%PDF-1.7\n%%EOF", "application/pdf")},
    )
    assert response.status_code == 202
    assert response.json()["review_mode"] == "calculation"


def test_status_endpoint(client: TestClient) -> None:
    upload = client.post(
        "/api/jobs",
        files={"file": ("demo.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
    ).json()
    response = client.get(f"/api/jobs/{upload['job_id']}/status")
    assert response.status_code == 200
    assert response.json()["job_id"] == upload["job_id"]


def test_completed_document_can_be_read(client: TestClient) -> None:
    job_id = _completed_job(web.JOBS_ROOT)
    response = client.get(f"/api/jobs/{job_id}/document")
    assert response.status_code == 200
    data = response.json()
    assert data["physical_page_count"] == 1
    assert "source_sha256" not in data
    page = client.get(f"/api/jobs/{job_id}/document/pages/1")
    assert page.status_code == 200
    assert page.json()["blocks"][0]["source_pointer"] == "/0/0"


def test_completed_review_can_be_read(client: TestClient) -> None:
    job_id = _completed_job(web.JOBS_ROOT)
    response = client.get(f"/api/jobs/{job_id}/review")
    assert response.status_code == 200
    assert response.json()["results"][0]["rule_id"] == "HF-COMP-001"


def test_completed_precheck_can_be_read(client: TestClient) -> None:
    job_id = _completed_job(web.JOBS_ROOT)
    response = client.get(f"/api/jobs/{job_id}/precheck")

    assert response.status_code == 200
    data = response.json()
    assert data["project_qualification"]["support_system"] == "disk_lock"
    assert data["substantive_review"][0]["review_item_id"] == "SR-01"


def test_completed_comparison_can_be_read(client: TestClient) -> None:
    job_id = _completed_job(web.JOBS_ROOT)
    comparison = {
        "total_rules": 1,
        "agreement_count": 1,
        "disagreement_count": 0,
        "manual_review_count": 0,
        "results": [
            {
                "rule_id": "HF-COMP-001",
                "item_name": "工程概况",
                "local_status": "PASS",
                "dify_status": "PASS",
                "agreement": True,
                "manual_review": False,
                "difference_reason": "两套结果一致",
            }
        ],
    }
    _write_json(web.JOBS_ROOT / job_id / "review_comparison.json", comparison)

    response = client.get(f"/api/jobs/{job_id}/comparison")

    assert response.status_code == 200
    assert response.json()["manual_review_count"] == 0
    assert response.json()["results"][0]["dify_status"] == "PASS"


def test_web_pipeline_dify_disabled_keeps_existing_behavior(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(web, "JOBS_ROOT", tmp_path / "jobs")
    monkeypatch.setenv("WEB_ENABLE_DIFY", "false")
    _mock_web_pipeline(monkeypatch)
    monkeypatch.setattr(
        main_module,
        "_run_dify_review",
        lambda output_dir, rules, **_: pytest.fail("WEB_ENABLE_DIFY=false 时不应调用 Dify"),
    )
    job_id = _pending_job(web.JOBS_ROOT)

    web._process_job(job_id)

    job_dir = web.JOBS_ROOT / job_id
    status = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
    assert status["status"] == "completed"
    assert (job_dir / "completeness_results.json").is_file()
    assert not (job_dir / "dify_review_result.json").exists()
    comparison = json.loads(
        (job_dir / "review_comparison.json").read_text(encoding="utf-8")
    )
    assert comparison["not_requested_count"] == comparison["total_rules"]


def test_web_pipeline_dify_enabled_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(web, "JOBS_ROOT", tmp_path / "jobs")
    monkeypatch.setenv("WEB_ENABLE_DIFY", "true")
    monkeypatch.setenv("DIFY_COMPLETENESS_MODE", "on_demand")
    _mock_web_pipeline(monkeypatch)

    def fake_dify(output_dir: Path, rules: list[dict], **kwargs) -> None:
        _write_json(output_dir / "dify_request.json", {"batches": []})
        _write_json(output_dir / "dify_raw_response.json", {"batches": []})
        _write_json(
            output_dir / "dify_review_result.json",
            {"total_rules": 1, "results": [{"rule_id": "HF-COMP-001", "status": "PASS"}]},
        )
        _write_json(
            output_dir / "review_comparison.json",
            {
                "total_rules": 1,
                "agreement_count": 1,
                "disagreement_count": 0,
                "manual_review_count": 0,
                "results": [],
            },
        )

    monkeypatch.setattr(main_module, "_run_dify_review", fake_dify)
    job_id = _pending_job(web.JOBS_ROOT)

    web._process_job(job_id)

    job_dir = web.JOBS_ROOT / job_id
    status = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
    assert status["status"] == "completed"
    assert (job_dir / "dify_request.json").is_file()
    assert (job_dir / "dify_raw_response.json").is_file()
    assert (job_dir / "dify_review_result.json").is_file()
    assert (job_dir / "review_comparison.json").is_file()


def test_web_pipeline_dify_failure_keeps_local_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(web, "JOBS_ROOT", tmp_path / "jobs")
    monkeypatch.setenv("WEB_ENABLE_DIFY", "true")
    monkeypatch.setenv("DIFY_COMPLETENESS_MODE", "full")
    _mock_web_pipeline(monkeypatch)

    def fail_dify(output_dir: Path, rules: list[dict], **kwargs) -> None:
        _write_json(
            output_dir / "dify_error.json",
            {"status": "DIFY_FAILED", "message": "模拟 Dify 失败"},
        )
        raise RuntimeError("模拟 Dify 失败")

    monkeypatch.setattr(main_module, "_run_dify_review", fail_dify)
    job_id = _pending_job(web.JOBS_ROOT)

    web._process_job(job_id)

    job_dir = web.JOBS_ROOT / job_id
    status = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
    assert status["status"] == "completed_with_warning"
    assert status["error_stage"] == "dify_review"
    assert status["message"] == "Dify审查失败，本地结果可用"
    assert (job_dir / "completeness_results.json").is_file()
    assert (job_dir / "dify_error.json").is_file()
    comparison = json.loads(
        (job_dir / "review_comparison.json").read_text(encoding="utf-8")
    )
    assert comparison["dify_failed_count"] == comparison["total_rules"]


def test_decisions_can_be_saved(client: TestClient) -> None:
    job_id = _completed_job(web.JOBS_ROOT)
    response = client.post(
        f"/api/jobs/{job_id}/decisions",
        json={
            "decisions": [
                {
                    "rule_id": "HF-COMP-001",
                    "automatic_status": "PASS",
                    "human_decision": "confirmed_pass",
                    "note": "老师已核对，确认具备",
                }
            ]
        },
    )
    assert response.status_code == 200
    saved = json.loads(
        (web.JOBS_ROOT / job_id / "decisions.json").read_text(encoding="utf-8")
    )
    assert saved[0]["human_decision"] == "confirmed_pass"
    assert saved[0]["job_id"] == job_id


def test_decisions_support_extended_choices(client: TestClient) -> None:
    """验证扩展的复核选项均可保存。"""
    job_id = _completed_job(web.JOBS_ROOT)
    choices = [
        "pending", "confirmed_pass", "confirmed_missing",
        "unable_to_verify", "false_positive", "need_supplement",
    ]
    for choice in choices:
        response = client.post(
            f"/api/jobs/{job_id}/decisions",
            json={
                "decisions": [
                    {
                        "rule_id": "HF-COMP-001",
                        "automatic_status": "PASS",
                        "human_decision": choice,
                        "note": f"测试选项: {choice}",
                    }
                ]
            },
        )
        assert response.status_code == 200, f"选项 {choice} 应可保存"
        saved = json.loads(
            (web.JOBS_ROOT / job_id / "decisions.json").read_text(encoding="utf-8")
        )
        assert saved[0]["human_decision"] == choice


def test_10_rules_alignment(client: TestClient) -> None:
    """验证 10 条规则在 API 中正确对齐。"""
    job_id = _completed_job_with_all_rules(web.JOBS_ROOT)
    response = client.get(f"/api/jobs/{job_id}/review")
    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["total_rules"] == 10
    assert len(data["results"]) == 10
    rule_ids = [r["rule_id"] for r in data["results"]]
    expected = [f"HF-COMP-{i:03d}" for i in range(1, 11)]
    assert rule_ids == expected
    assert data["summary"]["pass_count"] == 6
    assert data["summary"]["missing_count"] == 3
    assert data["summary"]["uncertain_count"] == 1


def test_timeline_endpoint(client: TestClient) -> None:
    """验证时间线 API 返回正确事件。"""
    job_id = _completed_job(web.JOBS_ROOT)
    job_dir = web.JOBS_ROOT / job_id
    _write_json(
        job_dir / "stage_timings.json",
        {
            "completeness_review": {
                "description": "完整性审查工具（10 项必备内容）",
                "started_at": "2026-07-28T00:00:20+00:00",
                "finished_at": "2026-07-28T00:00:25+00:00",
                "duration_ms": 5000,
            },
            "project_facts": {
                "description": "总控 Agent 识别工程特征",
                "started_at": "2026-07-28T00:00:30+00:00",
                "finished_at": "2026-07-28T00:00:31+00:00",
                "duration_ms": 1000,
            },
            "review_plan": {
                "description": "总控 Agent 制定审查计划",
                "started_at": "2026-07-28T00:00:40+00:00",
                "finished_at": "2026-07-28T00:00:42+00:00",
                "duration_ms": 2000,
            },
            "semantic_engine": {
                "description": "规范审查 Agent（规则/Dify/自主查证分流）",
                "started_at": "2026-07-28T00:00:50+00:00",
                "finished_at": "2026-07-28T00:00:55+00:00",
                "duration_ms": 5000,
            },
        },
    )
    response = client.get(f"/api/jobs/{job_id}/timeline")
    assert response.status_code == 200
    data = response.json()
    assert "events" in data
    assert len(data["events"]) >= 4  # 至少包含上传、三个阶段和完成
    stages = [event["stage"] for event in data["events"]]
    assert stages.index("project_facts") < stages.index("review_plan")
    assert stages.index("review_plan") < stages.index("completeness_review")
    assert stages.index("completeness_review") < stages.index("semantic_engine")


def test_files_endpoint(client: TestClient) -> None:
    """验证输出文件列表 API。"""
    job_id = _completed_job(web.JOBS_ROOT)
    response = client.get(f"/api/jobs/{job_id}/files")
    assert response.status_code == 200
    data = response.json()
    assert "files" in data
    names = [f["name"] for f in data["files"]]
    assert "mineru_document.json" in names
    assert "completeness_results.json" in names


def test_dify_error_endpoint_when_no_error(client: TestClient) -> None:
    """无 Dify 错误时返回 404。"""
    job_id = _completed_job(web.JOBS_ROOT)
    response = client.get(f"/api/jobs/{job_id}/dify-error")
    assert response.status_code == 404


def test_dify_error_endpoint_when_error_exists(client: TestClient) -> None:
    """有 Dify 错误文件时返回错误内容。"""
    job_id = _completed_job(web.JOBS_ROOT)
    _write_json(
        web.JOBS_ROOT / job_id / "dify_error.json",
        {"status": "DIFY_FAILED", "message": "连接超时"},
    )
    response = client.get(f"/api/jobs/{job_id}/dify-error")
    assert response.status_code == 200
    assert response.json()["status"] == "DIFY_FAILED"


def test_download_endpoint_blocks_sensitive_files(client: TestClient) -> None:
    """敏感文件不允许下载。"""
    job_id = _completed_job(web.JOBS_ROOT)
    # 创建敏感文件
    _write_json(
        web.JOBS_ROOT / job_id / "dify_request.json",
        {"api_key": "secret"},
    )
    response = client.get(f"/api/jobs/{job_id}/download/dify_request.json")
    assert response.status_code == 403


def test_download_endpoint_allows_safe_files(client: TestClient) -> None:
    """安全文件允许下载。"""
    job_id = _completed_job(web.JOBS_ROOT)
    response = client.get(f"/api/jobs/{job_id}/download/completeness_results.json")
    assert response.status_code == 200


def test_asset_path_traversal_is_rejected(client: TestClient) -> None:
    job_id = _completed_job(web.JOBS_ROOT)
    response = client.get(
        f"/api/jobs/{job_id}/asset",
        params={"path": "../source.pdf"},
    )
    assert response.status_code == 400
    raw_dir = web.JOBS_ROOT / job_id / "mineru_api" / "raw"
    raw_dir.mkdir(parents=True)
    (raw_dir / "layout.json").write_text("{}", encoding="utf-8")
    assert client.get(
        f"/api/jobs/{job_id}/asset", params={"path": "layout.json"}
    ).status_code == 415


def test_api_response_does_not_contain_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "super-secret-mineru-token"
    monkeypatch.setenv("MINERU_API_TOKEN", secret)
    response = client.post(
        "/api/jobs",
        files={"file": ("demo.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
    )
    assert secret not in response.text
    status = client.get(f"/api/jobs/{response.json()['job_id']}/status")
    assert secret not in status.text


def test_no_sensitive_data_in_files_output(client: TestClient) -> None:
    """输出文件列表不展示 API Key 或 Authorization。"""
    job_id = _completed_job(web.JOBS_ROOT)
    # 模拟敏感文件
    _write_json(
        web.JOBS_ROOT / job_id / "dify_request.json",
        {"inputs": {"api_key": "sk-secret"}},
    )
    resp = client.get(f"/api/jobs/{job_id}/files")
    data = resp.json()
    assert resp.status_code == 200
    # 文件列表本身不应暴露 key
    output_text = json.dumps(data, ensure_ascii=False)
    assert "sk-secret" not in output_text
    assert "api_key" not in output_text
    # 敏感文件虽然列出，但描述不含敏感信息
    sensitive_files = [f for f in data["files"] if f["name"] in ("dify_request.json", "dify_raw_response.json")]
    for sf in sensitive_files:
        assert "api" not in sf["description"].lower() or "审计" in sf["description"]


def test_standards_endpoint_and_rule_standard_filter(client: TestClient) -> None:
    """规范注册表端点与规则库 standard_id 精确过滤。"""
    response = client.get("/api/standards")
    assert response.status_code == 200
    data = response.json()
    ids = {s["standard_id"]: s for s in data["standards"]}
    assert "JGJT231-2021" in ids and "JGJ162-2016" in ids
    assert ids["JGJ162-2016"]["rule_count"] > 0

    filtered = client.get("/api/rules", params={"standard": "JGJT231-2021"}).json()
    assert filtered["total"] == ids["JGJT231-2021"]["rule_count"]
    assert all("JGJT231-2021" in (r.get("standard_refs") or []) for r in filtered["rules"])

    all_rules = client.get("/api/rules").json()
    assert all("standard_id" in r for r in all_rules["rules"])


def test_decisions_support_item_key_for_engine_items(client: TestClient) -> None:
    job_id = _completed_job(web.JOBS_ROOT)
    _write_json(
        web.JOBS_ROOT / job_id / "rule_engine_results.json",
        {"results": [{"rule_id": "4.1", "status": "VIOLATED"}]},
    )

    ok = client.post(
        f"/api/jobs/{job_id}/decisions",
        json={"decisions": [{
            "item_key": "rule_engine:4.1",
            "automatic_status": "VIOLATED",
            "human_decision": "confirmed",
            "note": "确认违规",
        }]},
    )
    assert ok.status_code == 200
    saved = ok.json()["decisions"][0]
    assert saved["item_key"] == "rule_engine:4.1"
    assert saved["source"] == "rule_engine"

    bad = client.post(
        f"/api/jobs/{job_id}/decisions",
        json={"decisions": [{
            "item_key": "rule_engine:4.1",
            "automatic_status": "COMPLIANT",
            "human_decision": "confirmed",
        }]},
    )
    assert bad.status_code == 422


def test_decisions_legacy_payload_gets_item_key(client: TestClient) -> None:
    job_id = _completed_job(web.JOBS_ROOT)
    resp = client.post(
        f"/api/jobs/{job_id}/decisions",
        json={"decisions": [{
            "rule_id": "HF-COMP-001",
            "automatic_status": "PASS",
            "human_decision": "confirmed_pass",
        }]},
    )
    assert resp.status_code == 200
    saved = resp.json()["decisions"][0]
    assert saved["item_key"] == "completeness_review:HF-COMP-001"
    assert saved["rule_id"] == "HF-COMP-001"


def test_rerun_requires_completed_job(client: TestClient) -> None:
    upload = client.post(
        "/api/jobs",
        files={"file": ("demo.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
    ).json()
    resp = client.post(
        f"/api/jobs/{upload['job_id']}/rerun",
        json={"overrides": {"support_system": "coupler"}},
    )
    assert resp.status_code == 409


def test_rerun_rejects_invalid_overrides(client: TestClient) -> None:
    job_id = _completed_job(web.JOBS_ROOT)
    bad_key = client.post(f"/api/jobs/{job_id}/rerun", json={"overrides": {"foo": "bar"}})
    assert bad_key.status_code == 422
    bad_val = client.post(
        f"/api/jobs/{job_id}/rerun", json={"overrides": {"support_system": "nope"}}
    )
    assert bad_val.status_code == 422


def test_review_stage_status_updates_before_long_running_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_dir = tmp_path / "jobs" / ("b" * 32)
    job_dir.mkdir(parents=True)
    _write_json(
        job_dir / "status.json",
        {
            "job_id": "b" * 32,
            "file_name": "demo.pdf",
            "uploaded_at": "2026-08-25T00:00:00+00:00",
            "updated_at": "2026-08-25T00:00:00+00:00",
            "status": "completeness_review",
            "stage": "completeness_review",
            "progress": web.STAGE_PROGRESS["completeness_review"],
            "message": "完整性完成",
            "error_stage": None,
        },
    )
    _write_json(
        job_dir / "completeness_summary.json",
        {
            "total_rules": 0,
            "pass_count": 0,
            "missing_count": 0,
            "uncertain_count": 0,
            "results": [],
        },
    )
    document = MinerUDocument(
        document_id="demo",
        source_file_name="demo.pdf",
        source_sha256="sha",
        physical_page_count=1,
        pages=[],
        sections=[],
    )
    facts = {"facts": {}}
    monkeypatch.setattr(
        web,
        "build_project_qualification",
        lambda *_: {"support_system_label": "盘扣式"},
    )
    monkeypatch.setattr(
        web,
        "_build_agent_review_plan",
        lambda *_args, **_kwargs: {"generated_by": "local"},
    )
    monkeypatch.setattr(
        web,
        "run_rule_engine_safe",
        lambda *_: {"total_rules": 0, "compliant": 0, "violated": 0, "uncertain": 0},
    )

    def semantic_stage(*_args):
        status = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
        assert status["stage"] == "semantic_engine"
        assert status["status"] == "semantic_engine"
        assert status["message"] == "规范审查 Agent（规则/Dify/自主查证分流）进行中"
        raise RuntimeError("stop")

    monkeypatch.setattr(web, "_run_semantic_stage", semantic_stage)

    with pytest.raises(RuntimeError):
        web._run_review_stages(job_dir, document, facts)


def test_web_review_stage_runs_agent_drawing_once_and_persists_domain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = _completed_job(tmp_path / "jobs")
    job_dir = tmp_path / "jobs" / job_id
    document = web.document_from_dict(
        json.loads((job_dir / "mineru_document.json").read_text(encoding="utf-8"))
    )
    facts = {"facts": {"horizontal_spacing": {"value": 900, "unit": "mm"}}}
    calls: list[dict] = []

    _patch_fast_review_stages(monkeypatch)

    def fake_agent_review(document_arg, facts_arg, registry, **kwargs):
        calls.append(
            {
                "document": document_arg,
                "facts": facts_arg,
                "registry": list(registry),
                "kwargs": kwargs,
            }
        )
        return _agent_review_result()

    monkeypatch.setattr(web, "build_agent_drawing_review", fake_agent_review)

    web._run_review_stages(job_dir, document, facts)
    web._write_orchestrator_state_if_ready(job_dir)
    build_review_report_from_job_dir = web.build_review_report_from_job_dir
    build_review_report_from_job_dir(job_dir)

    agent_payload = json.loads(
        (job_dir / "agent_drawing_review.json").read_text(encoding="utf-8")
    )
    legacy_payload = json.loads((job_dir / "drawing_review.json").read_text(encoding="utf-8"))
    orchestrator = json.loads((job_dir / "orchestrator_agent.json").read_text(encoding="utf-8"))

    assert len(calls) == 1
    assert calls[0]["document"] is document
    assert calls[0]["facts"] is facts
    assert len(calls[0]["registry"]) == 17
    assert calls[0]["kwargs"]["recall_tool"] is web.recall_drawing_pages
    assert calls[0]["kwargs"]["check_tool"] is web.cross_check_param
    assert calls[0]["kwargs"]["ocr_tool"] is web.ocr_drawing_page
    assert calls[0]["kwargs"]["search_text_tool"] is web.search_text_evidence
    assert calls[0]["kwargs"]["vision_tool"] is web.inspect_drawing_page
    assert calls[0]["kwargs"]["ocr_engine"] is None
    assert calls[0]["kwargs"]["job_dir"] == job_dir

    assert agent_payload["total_tasks"] == 17
    assert agent_payload["reviewed_tasks"] == 17
    assert agent_payload["status_counts"] == {
        "CONSISTENT": 1,
        "CONFLICT": 1,
        "TEXT_ONLY": 1,
        "DRAWING_ONLY": 1,
        "UNCERTAIN": 1,
        "NOT_FOUND": 12,
    }
    assert {item["status"] for item in agent_payload["items"]} == {
        "CONSISTENT",
        "CONFLICT",
        "TEXT_ONLY",
        "DRAWING_ONLY",
        "UNCERTAIN",
        "NOT_FOUND",
    }
    assert next(
        item for item in agent_payload["items"] if item["status"] == "UNCERTAIN"
    )["drawing_value"] is None
    assert legacy_payload == []
    assert orchestrator["agent_drawing_review"]["total_tasks"] == 17
    assert orchestrator["agent_drawing_review"]["status_counts"]["NOT_FOUND"] == 12
    assert len(calls) == 1


def test_web_review_stage_agent_failure_does_not_fallback_to_legacy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = _completed_job(tmp_path / "jobs")
    job_dir = tmp_path / "jobs" / job_id
    document = web.document_from_dict(
        json.loads((job_dir / "mineru_document.json").read_text(encoding="utf-8"))
    )
    _patch_fast_review_stages(monkeypatch)
    calls = 0

    def fail_agent_review(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise RuntimeError("agent drawing failed")

    monkeypatch.setattr(web, "build_agent_drawing_review", fail_agent_review)

    with pytest.raises(RuntimeError, match="agent drawing failed"):
        web._run_review_stages(job_dir, document, {"facts": {}})

    assert calls == 1
    assert not (job_dir / "agent_drawing_review.json").exists()
    assert not (job_dir / "drawing_review.json").exists()
    assert not (job_dir / "orchestrator_agent.json").exists()


def test_rerun_applies_human_override(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_id = _completed_job(web.JOBS_ROOT)
    captured: dict = {}

    def fake_run(job_dir, document, project_facts=None):
        captured["facts"] = project_facts

    monkeypatch.setattr(web, "_run_review_stages", fake_run)
    resp = client.post(
        f"/api/jobs/{job_id}/rerun",
        json={"overrides": {"support_system": "coupler"}},
    )
    assert resp.status_code == 202
    assert resp.json()["status"] == "rerun_review"

    facts = captured["facts"]["facts"]["support_system"]
    assert facts["value"] == "coupler"
    assert facts["source_role"] == "human_override"
    overrides = json.loads(
        (web.JOBS_ROOT / job_id / "human_overrides.json").read_text(encoding="utf-8")
    )
    assert overrides["applied_at"]
    status = json.loads(
        (web.JOBS_ROOT / job_id / "status.json").read_text(encoding="utf-8")
    )
    assert status["status"] == "completed"


def test_rerun_accepts_numeric_param_overrides(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """人工复核参数修正：数值参数（步距/纵距等）可作为 override 重跑。"""
    job_id = _completed_job(web.JOBS_ROOT)
    captured: dict = {}

    def fake_run(job_dir, document, project_facts=None):
        captured["facts"] = project_facts

    monkeypatch.setattr(web, "_run_review_stages", fake_run)
    resp = client.post(
        f"/api/jobs/{job_id}/rerun",
        json={"overrides": {"standard_step_height": "1.8", "vertical_spacing": "0.6"}},
    )
    assert resp.status_code == 202
    facts = captured["facts"]["facts"]
    # 数值参数以 float 落盘（引擎比对需要数值类型）
    assert facts["standard_step_height"]["value"] == 1.8
    assert facts["vertical_spacing"]["value"] == 0.6
    assert facts["standard_step_height"]["source_role"] == "human_override"
    assert facts["standard_step_height"]["status"] == "confirmed"


def test_rerun_rejects_non_numeric_param_override(client: TestClient) -> None:
    """数值参数 override 必须是数字。"""
    job_id = _completed_job(web.JOBS_ROOT)
    resp = client.post(
        f"/api/jobs/{job_id}/rerun",
        json={"overrides": {"standard_step_height": "一米八"}},
    )
    assert resp.status_code == 422
    assert "数值" in resp.json()["detail"]


def test_rerun_accepts_mixed_system_and_numeric(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """支撑体系 + 数值参数可同时覆盖。"""
    job_id = _completed_job(web.JOBS_ROOT)
    captured: dict = {}

    def fake_run(job_dir, document, project_facts=None):
        captured["facts"] = project_facts

    monkeypatch.setattr(web, "_run_review_stages", fake_run)
    resp = client.post(
        f"/api/jobs/{job_id}/rerun",
        json={"overrides": {"support_system": "coupler", "support_height": "12.5"}},
    )
    assert resp.status_code == 202
    facts = captured["facts"]["facts"]
    assert facts["support_system"]["value"] == "coupler"  # 枚举保持字符串
    assert facts["support_height"]["value"] == 12.5  # 数值转 float


def test_review_plan_endpoint_404_without_plan(client: TestClient) -> None:
    """任务尚未生成 review_plan.json -> 404（前端静默忽略）。"""
    upload = client.post(
        "/api/jobs",
        data={"review_mode": "smart"},
        files={"file": ("方案.pdf", b"%PDF-1.7\n%%EOF", "application/pdf")},
    )
    job_id = upload.json()["job_id"]
    # 直接完成任务状态以通过 _completed_job_dir 校验
    job_dir = web.JOBS_ROOT / job_id
    status = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
    status["status"] = "completed"
    (job_dir / "status.json").write_text(
        json.dumps(status, ensure_ascii=False), encoding="utf-8"
    )
    response = client.get(f"/api/jobs/{job_id}/review-plan")
    assert response.status_code == 404

    # 写入计划后可读取
    (job_dir / "review_plan.json").write_text(
        json.dumps({"plan_id": "PLAN-1", "focus_areas": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    response = client.get(f"/api/jobs/{job_id}/review-plan")
    assert response.status_code == 200
    assert response.json()["plan_id"] == "PLAN-1"


def test_orchestrator_endpoint_reads_result(client: TestClient) -> None:
    job_id = _completed_job(web.JOBS_ROOT)
    job_dir = web.JOBS_ROOT / job_id
    _write_json(
        job_dir / "orchestrator_agent.json",
        {
            "agent": "orchestrator_agent",
            "dispatch_plan": [{"stage": "plan"}],
            "tool_observations": [{"tool_id": "completeness_review"}],
        },
    )
    response = client.get(f"/api/jobs/{job_id}/orchestrator")
    assert response.status_code == 200
    assert response.json()["agent"] == "orchestrator_agent"


def test_orchestrator_writer_consumes_agent_drawing_review_without_rerun(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = _completed_job(web.JOBS_ROOT)
    job_dir = web.JOBS_ROOT / job_id
    monkeypatch.setattr(
        web,
        "build_agent_drawing_review",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not rerun drawing review")),
    )
    for name, payload in {
        "project_facts.json": {"facts": {}},
        "project_qualification.json": {"support_system_label": "承插型盘扣式"},
        "rule_engine_results.json": {"total_rules": 0, "results": []},
        "semantic_results.json": {"total_rules": 0, "results": []},
        "calculation_results.json": {"total_rules": 0, "results": []},
        "substantive_review.json": [],
        "consistency_review.json": [],
        "drawing_review.json": [{"status": "ISSUE", "requires_human_review": True}],
        "agent_drawing_review.json": {
            "total_tasks": 2,
            "reviewed_tasks": 2,
            "status_counts": {"CONFLICT": 1, "UNCERTAIN": 1},
            "items": [
                {
                    "fact_id": "horizontal_spacing",
                    "display_name": "立杆横距",
                    "status": "CONFLICT",
                    "reason": "values_differ",
                    "scope_alignment": "compatible",
                    "text_value": 900,
                    "drawing_value": 1200,
                    "text_unit": "mm",
                    "drawing_unit": "mm",
                    "text_evidence_count": 1,
                    "drawing_evidence_count": 1,
                    "comparable_pair_count": 1,
                },
                {
                    "fact_id": "support_height",
                    "display_name": "搭设高度",
                    "status": "UNCERTAIN",
                    "reason": "scope_unknown",
                    "scope_alignment": "unknown",
                    "drawing_value": None,
                    "text_evidence_count": 1,
                    "drawing_evidence_count": 1,
                },
            ],
        },
    }.items():
        _write_json(job_dir / name, payload)

    web._write_orchestrator_state_if_ready(job_dir)

    state = json.loads((job_dir / "orchestrator_agent.json").read_text(encoding="utf-8"))
    domain = state["agent_drawing_review"]
    assert domain["status_counts"]["CONFLICT"] == 1
    assert domain["status_counts"]["UNCERTAIN"] == 1
    assert domain["items"][0]["status"] == "CONFLICT"
    assert domain["items"][1]["drawing_value"] is None
    assert state["tool_observations"][3]["output"]["issue"] == 1


def test_frontend_static_supports_agent_drawing_six_status_presentation() -> None:
    script = (web.PROJECT_ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")

    for label in ["图文一致", "图文冲突", "仅文本有证据", "仅图纸有证据", "暂无法确定", "未找到足够证据"]:
        assert label in script
    assert "machine status" in script
    assert "未提取到可比较的实际值" in script
    assert "DRAWING_AGENT_STATUS_CN" in script
    assert "DRAWING_AGENT_REASON_CN" in script
    assert "不合格" not in script[script.index("DRAWING_AGENT_STATUS_CN"):script.index("const DRAWING_SCOPE_CN")]


def test_report_surfaces_agent_drawing_review_without_rejudging() -> None:
    report = build_review_report(
        job_id="job",
        file_name="demo.pdf",
        project_qualification={},
        completeness_summary={"total_rules": 0, "pass_count": 0, "missing_count": 0, "uncertain_count": 0},
        agent_drawing_review=_agent_drawing_payload(),
    )

    assert "图文一致性审查" in report
    assert "检查项：17" in report
    assert "暂无法确定：2" in report
    assert "未找到足够证据：12" in report
    assert "立杆横距**：暂无法确定；文本与图纸的作用部位无法可靠对应" in report
    assert "图文冲突" in report
    assert "未找到足够证据" in report
    assert "不合格" not in report


def test_report_formats_rule_values_without_none_suffixes() -> None:
    report = build_review_report(
        job_id="job",
        file_name="demo.pdf",
        project_qualification={},
        completeness_summary={
            "total_rules": 0,
            "pass_count": 0,
            "missing_count": 0,
            "uncertain_count": 0,
        },
        rule_engine_results={
            "total_rules": 4,
            "compliant": 0,
            "violated": 4,
            "uncertain": 0,
            "results": [
                {
                    "rule_id": "R-0",
                    "rule_name": "零值",
                    "status": "VIOLATED",
                    "risk_level": "high",
                    "actual_value": 0,
                    "threshold": {"operator": "<=", "value": 300, "unit": "mm"},
                    "reason": "外伸长度=0mm，不满足<=300mm要求",
                },
                {
                    "rule_id": "R-1",
                    "rule_name": "有单位",
                    "status": "VIOLATED",
                    "risk_level": "high",
                    "actual_value": 1200,
                    "threshold": {"operator": "<=", "value": 900, "unit": "mm"},
                    "reason": "间距=1200mm，不满足<=900mm要求",
                },
                {
                    "rule_id": "R-2",
                    "rule_name": "缺单位",
                    "status": "VIOLATED",
                    "risk_level": "high",
                    "actual_value": 13.62,
                    "threshold": {"operator": "<=", "value": 3.0, "unit": None},
                    "reason": "高宽比=13.62None，不满足<=3.0None要求",
                    "remedy_suggestion": "调整设计参数使高宽比<=3.0None",
                },
                {
                    "rule_id": "R-3",
                    "rule_name": "缺实际值",
                    "status": "VIOLATED",
                    "risk_level": "high",
                    "actual_value": None,
                    "threshold": {"operator": "", "value": None, "unit": None},
                    "reason": None,
                },
            ],
        },
    )

    assert "实际值：—" in report
    assert "实际值：13.62" in report
    assert "阈值要求：<= 3.0" in report
    assert "判定依据：高宽比=13.62，不满足<=3.0要求" in report
    assert "整改建议：调整设计参数使高宽比<=3.0" in report
    assert "实际值：1200mm" in report
    assert "阈值要求：<= 900mm" in report
    assert "实际值：0mm" in report
    assert "None" not in report
    assert "13.62None" not in report
    assert "<= 3.0None" not in report


def test_report_keeps_constraint_evidence_and_null_value_safe() -> None:
    report = build_review_report(
        job_id="job",
        file_name="demo.pdf",
        project_qualification={},
        completeness_summary={"total_rules": 0, "pass_count": 0, "missing_count": 0, "uncertain_count": 0},
        agent_drawing_review=_agent_drawing_payload(),
    )

    assert "H≤8m" in report
    assert "图纸侧实际值：未提取到可比较的实际值" in report
    assert "图纸侧实际值：8m" not in report
    assert "图纸侧实际值：0" not in report
