import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.web as web


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


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_home_page_is_accessible(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "高支模专项施工方案智能审查系统" in response.text


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


def test_decisions_can_be_saved(client: TestClient) -> None:
    job_id = _completed_job(web.JOBS_ROOT)
    response = client.post(
        f"/api/jobs/{job_id}/decisions",
        json={
            "decisions": [
                {
                    "rule_id": "HF-COMP-001",
                    "automatic_status": "PASS",
                    "human_decision": "confirmed",
                    "note": "老师已核对",
                }
            ]
        },
    )
    assert response.status_code == 200
    saved = json.loads(
        (web.JOBS_ROOT / job_id / "decisions.json").read_text(encoding="utf-8")
    )
    assert saved[0]["human_decision"] == "confirmed"
    assert saved[0]["job_id"] == job_id


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
