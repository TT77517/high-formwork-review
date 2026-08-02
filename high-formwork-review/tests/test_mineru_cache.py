import json
import threading
import time
from dataclasses import asdict
from pathlib import Path

import pytest

import app.web as web
from app.mineru_cache import (
    PARSER_CONFIG_VERSION,
    PARSER_VERSION,
    build_cache_key,
    cache_directory,
    parse_pdf_with_cache,
    sha256_file,
)
from app.models import (
    CompletenessResult,
    CompletenessSummary,
    MinerUDocument,
    MinerUPage,
    MinerUSection,
)


def _document() -> MinerUDocument:
    return MinerUDocument(
        document_id="cached-document",
        source_file_name="content_list.json",
        source_sha256="raw-result-sha",
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
                title="工程概况",
                level=1,
                path=["工程概况"],
                physical_page_start=1,
                physical_page_end=1,
            )
        ],
    )


class _FakeClient:
    calls = 0
    lock = threading.Lock()

    def parse_pdf(self, pdf_path: Path, output_dir: Path) -> Path:
        with self.lock:
            type(self).calls += 1
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir / "raw"


def _run(
    pdf_path: Path,
    output_dir: Path,
    cache_root: Path,
    *,
    parser_version: str = PARSER_VERSION,
    parser_config_version: str = PARSER_CONFIG_VERSION,
    parser=None,
):
    return parse_pdf_with_cache(
        pdf_path,
        output_dir / "raw",
        output_dir / "mineru_document.json",
        cache_root=cache_root,
        parser_version=parser_version,
        parser_config_version=parser_config_version,
        client_factory=_FakeClient,
        parser=parser or (lambda raw_dir: _document()),
    )


def test_sha256_and_cache_key_include_file_and_parser_versions(tmp_path: Path) -> None:
    pdf = tmp_path / "方案.pdf"
    pdf.write_bytes(b"%PDF-content-a")
    digest = sha256_file(pdf)

    assert len(digest) == 64
    key = build_cache_key(digest, "parser-v1", "config-v1")
    assert digest in key
    assert key != build_cache_key(digest, "parser-v2", "config-v1")
    assert key != build_cache_key(digest, "parser-v1", "config-v2")


def test_first_parse_writes_cache_and_second_same_content_hits(tmp_path: Path) -> None:
    _FakeClient.calls = 0
    cache_root = tmp_path / "cache"
    first_pdf = tmp_path / "first.pdf"
    second_pdf = tmp_path / "renamed.pdf"
    first_pdf.write_bytes(b"%PDF-same-content")
    second_pdf.write_bytes(first_pdf.read_bytes())

    first_doc, first_info = _run(first_pdf, tmp_path / "job-1", cache_root)
    second_doc, second_info = _run(second_pdf, tmp_path / "job-2", cache_root)

    assert first_info.cache_hit is False
    assert second_info.cache_hit is True
    assert _FakeClient.calls == 1
    assert first_doc.document_id == second_doc.document_id
    cache_dir = cache_directory(first_info.cache_key, cache_root)
    assert (cache_dir / "mineru_document.json").is_file()
    metadata = json.loads((cache_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["source_sha256"] == first_info.source_sha256
    assert metadata["parser_name"] == "app.mineru_parser.parse_mineru"
    assert metadata["parse_status"] == "success"
    assert (tmp_path / "job-2" / "mineru_document.json").is_file()


def test_same_name_different_content_does_not_hit(tmp_path: Path) -> None:
    _FakeClient.calls = 0
    cache_root = tmp_path / "cache"
    first = tmp_path / "方案.pdf"
    second_dir = tmp_path / "other"
    second_dir.mkdir()
    second = second_dir / "方案.pdf"
    first.write_bytes(b"%PDF-one")
    second.write_bytes(b"%PDF-two")

    _, first_info = _run(first, tmp_path / "job-1", cache_root)
    _, second_info = _run(second, tmp_path / "job-2", cache_root)

    assert first_info.cache_hit is False
    assert second_info.cache_hit is False
    assert _FakeClient.calls == 2


def test_corrupt_cache_is_ignored_and_rebuilt(tmp_path: Path) -> None:
    _FakeClient.calls = 0
    cache_root = tmp_path / "cache"
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"%PDF-corrupt-cache")
    _, info = _run(pdf, tmp_path / "job-1", cache_root)
    cache_dir = cache_directory(info.cache_key, cache_root)
    (cache_dir / "mineru_document.json").write_text("{broken", encoding="utf-8")

    _, rebuilt = _run(pdf, tmp_path / "job-2", cache_root)

    assert rebuilt.cache_hit is False
    assert "缓存" in (rebuilt.warning or "")
    assert _FakeClient.calls == 2
    json.loads((cache_dir / "mineru_document.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("parser_version", "parser_config_version"),
    [("parser-v2", PARSER_CONFIG_VERSION), (PARSER_VERSION, "config-v2")],
)
def test_parser_or_config_version_change_invalidates_cache(
    tmp_path: Path,
    parser_version: str,
    parser_config_version: str,
) -> None:
    _FakeClient.calls = 0
    cache_root = tmp_path / "cache"
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"%PDF-version-change")
    _run(pdf, tmp_path / "job-1", cache_root)

    _, info = _run(
        pdf,
        tmp_path / "job-2",
        cache_root,
        parser_version=parser_version,
        parser_config_version=parser_config_version,
    )

    assert info.cache_hit is False
    assert _FakeClient.calls == 2


def test_mineru_failure_does_not_write_success_cache(tmp_path: Path) -> None:
    cache_root = tmp_path / "cache"
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"%PDF-failure")

    class FailingClient(_FakeClient):
        def parse_pdf(self, pdf_path: Path, output_dir: Path) -> Path:
            type(self).calls += 1
            raise RuntimeError("mock MinerU failure")

    with pytest.raises(RuntimeError, match="mock MinerU failure"):
        parse_pdf_with_cache(
            pdf,
            tmp_path / "job" / "raw",
            tmp_path / "job" / "mineru_document.json",
            cache_root=cache_root,
            client_factory=FailingClient,
            parser=lambda raw_dir: _document(),
        )

    digest = sha256_file(pdf)
    assert not (cache_root / build_cache_key(digest)).exists()
    assert not (tmp_path / "job" / "mineru_document.json").exists()


def test_same_key_concurrent_calls_do_not_corrupt_cache(tmp_path: Path) -> None:
    _FakeClient.calls = 0
    cache_root = tmp_path / "cache"
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"%PDF-concurrent")

    def run(index: int):
        return _run(pdf, tmp_path / f"job-{index}", cache_root)

    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(run, [1, 2]))

    assert sorted(info.cache_hit for _, info in results) == [False, True]
    assert _FakeClient.calls == 1
    for _, info in results:
        json.loads(
            (
                cache_directory(info.cache_key, cache_root) / "mineru_document.json"
            ).read_text(encoding="utf-8")
        )


def test_web_reuses_cache_but_repeats_local_review(tmp_path: Path, monkeypatch) -> None:
    jobs_root = tmp_path / "jobs"
    cache_root = tmp_path / "cache"
    monkeypatch.setattr(web, "JOBS_ROOT", jobs_root)
    monkeypatch.setattr(web, "MINERU_CACHE_ROOT", cache_root)
    monkeypatch.setenv("WEB_ENABLE_DIFY", "false")
    _FakeClient.calls = 0
    review_calls = 0

    monkeypatch.setattr(web, "MinerUClient", _FakeClient)
    monkeypatch.setattr(web, "parse_mineru", lambda raw_dir: _document())
    monkeypatch.setattr(web, "load_rules", lambda path: [{"rule_id": "HF-COMP-001"}])

    result = CompletenessResult(
        rule_id="HF-COMP-001",
        name="工程概况",
        status="PASS",
        reason="mock",
    )
    summary = CompletenessSummary(
        total_rules=1,
        pass_count=1,
        missing_count=0,
        uncertain_count=0,
        results=[result],
    )

    def review(document, rules):
        nonlocal review_calls
        review_calls += 1
        return summary, [{"matched_sections": [], "matched_terms": [], "matched_subitems": [], "physical_pages": [], "printed_pages": []}]

    monkeypatch.setattr(web, "review_completeness_with_details", review)
    monkeypatch.setattr(web, "build_evidence_check_markdown", lambda *args: "# mock\n")

    for index in (1, 2):
        job_id = f"{index:032x}"
        job_dir = jobs_root / job_id
        job_dir.mkdir(parents=True)
        (job_dir / "source.pdf").write_bytes(b"%PDF-web-same")
        (job_dir / "status.json").write_text(
            json.dumps(
                {
                    "job_id": job_id,
                    "file_name": f"{index}.pdf",
                    "status": "uploaded",
                    "stage": "uploaded",
                    "progress": 10,
                    "message": "uploaded",
                    "error_stage": None,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        web._process_job(job_id)

    first_status = json.loads((jobs_root / f"{1:032x}" / "status.json").read_text(encoding="utf-8"))
    second_status = json.loads((jobs_root / f"{2:032x}" / "status.json").read_text(encoding="utf-8"))
    assert _FakeClient.calls == 1
    assert review_calls == 2
    assert first_status["parse_cache_hit"] is False
    assert second_status["parse_cache_hit"] is True
    assert second_status["parse_cache_source"] == "cache"
    assert second_status["document_parse_message"] == "文档解析：复用缓存"
    assert (jobs_root / f"{2:032x}" / "mineru_document.json").is_file()
