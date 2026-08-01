import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
import app.web as web
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


def test_home_page_is_accessible(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "高支模方案审查工作台" in response.text


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
        files={"file": ("方案.pdf", b"%PDF-1.7\n%%EOF", "application/pdf")},
    )
    assert response.status_code == 202
    data = response.json()
    job_dir = web.JOBS_ROOT / data["job_id"]
    assert (job_dir / "source.pdf").is_file()
    assert data["status"] == "uploaded"


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
        lambda output_dir, rules: pytest.fail("WEB_ENABLE_DIFY=false 时不应调用 Dify"),
    )
    job_id = _pending_job(web.JOBS_ROOT)

    web._process_job(job_id)

    job_dir = web.JOBS_ROOT / job_id
    status = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
    assert status["status"] == "completed"
    assert (job_dir / "completeness_results.json").is_file()
    assert not (job_dir / "dify_review_result.json").exists()
    assert not (job_dir / "review_comparison.json").exists()


def test_web_pipeline_dify_enabled_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(web, "JOBS_ROOT", tmp_path / "jobs")
    monkeypatch.setenv("WEB_ENABLE_DIFY", "true")
    monkeypatch.setenv("DIFY_COMPLETENESS_MODE", "on_demand")
    _mock_web_pipeline(monkeypatch)

    def fake_dify(output_dir: Path, rules: list[dict]) -> None:
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
    monkeypatch.setenv("DIFY_COMPLETENESS_MODE", "on_demand")
    _mock_web_pipeline(monkeypatch)

    def fail_dify(output_dir: Path, rules: list[dict]) -> None:
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
    assert not (job_dir / "review_comparison.json").exists()


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
    response = client.get(f"/api/jobs/{job_id}/timeline")
    assert response.status_code == 200
    data = response.json()
    assert "events" in data
    assert len(data["events"]) >= 4  # 至少包含上传、三个阶段和完成


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
