from __future__ import annotations

import json
from pathlib import Path

import pytest

import app.dify_cache as dify_cache
import app.main as main_module
from app.services.dify_client import DifyError
from tests.test_dify import _document_dict, _rules


def _write_job(output_dir: Path, document: dict | None = None) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "mineru_document.json").write_text(
        json.dumps(document or _document_dict(), ensure_ascii=False),
        encoding="utf-8",
    )


def _fake_execute_factory(calls: list[list[str]]):
    async def fake_execute(batches, task_id, target_dir):
        calls.append([rule_id for batch in batches for rule_id in batch["rule_ids"]])
        parsed = []
        raw = []
        for batch in batches:
            raw.append(
                {
                    "batch_index": batch["batch_index"],
                    "rule_ids": batch["rule_ids"],
                    "response": {"data": {"status": "succeeded"}},
                }
            )
            parsed.append(
                {
                    "batch_index": batch["batch_index"],
                    "rule_ids": batch["rule_ids"],
                    "result": {
                        "results": [
                            {
                                "rule_id": rule_id,
                                "name": rule_id,
                                "status": "PASS",
                                "reason": "mock evidence",
                                "evidence": [],
                            }
                            for rule_id in batch["rule_ids"]
                        ]
                    },
                    "warnings": [],
                }
            )
        return raw, parsed

    return fake_execute


def _audit(output_dir: Path) -> dict:
    return json.loads(
        (output_dir / "dify_call_audit.json").read_text(encoding="utf-8")
    )


@pytest.fixture
def cache_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("DIFY_CACHE_ENABLED", "true")
    monkeypatch.setenv("DIFY_WORKFLOW_VERSION", "workflow-v1")
    monkeypatch.setenv("DIFY_PROMPT_VERSION", "prompt-v1")
    monkeypatch.setenv("DIFY_MODEL_IDENTIFIER", "unknown")
    monkeypatch.setenv("DIFY_OUTPUT_SCHEMA_VERSION", "schema-v1")
    cache_root = tmp_path / "dify-cache"
    monkeypatch.setattr(dify_cache, "CACHE_ROOT", cache_root)
    return cache_root


def test_stable_evidence_hash_excludes_transient_fields() -> None:
    package = {
        "rule_id": "HF-1",
        "item_name": "demo",
        "evidence_text": "evidence",
        "character_count": 8,
        "matched_sections": [],
        "job_id": "temporary-job",
        "_page_chunks": ["temporary-path"],
    }
    altered = dict(package, job_id="another-job", _page_chunks=["another-path"])

    assert dify_cache.stable_evidence_package_hash(package) == dify_cache.stable_evidence_package_hash(altered)


@pytest.mark.parametrize(
    "field",
    [
        "workflow_version",
        "prompt_version",
        "model_identifier",
        "output_schema_version",
    ],
)
def test_cache_key_changes_for_each_version_dimension(field: str) -> None:
    values = {
        "source_sha256": "source",
        "rule_id": "HF-1",
        "evidence_package_hash": "evidence",
        "workflow_version": "workflow-v1",
        "prompt_version": "prompt-v1",
        "model_identifier": "model-v1",
        "output_schema_version": "schema-v1",
    }
    first = dify_cache.build_dify_cache_key(**values)
    values[field] = values[field] + "-changed"
    second = dify_cache.build_dify_cache_key(**values)

    assert first != second


def test_first_call_writes_per_rule_cache_and_second_is_all_cache_hit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cache_environment: Path,
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(main_module, "_execute_dify_batches", _fake_execute_factory(calls))
    rules = _rules()

    first = tmp_path / "first"
    second = tmp_path / "second"
    _write_job(first)
    _write_job(second)
    main_module._run_dify_review(first, rules)
    main_module._run_dify_review(second, rules)

    assert calls == [["HF-COMP-001", "HF-COMP-007"]]
    first_audit = _audit(first)
    second_audit = _audit(second)
    assert first_audit["requested_rule_count"] == 2
    assert first_audit["api_requested_rule_count"] == 2
    assert second_audit["requested_rule_count"] == 2
    assert second_audit["cache_hit_count"] == 2
    assert second_audit["api_requested_rule_count"] == 0
    assert second_audit["batch_count"] == 0
    assert second_audit["status"] == "cache_hit_complete"
    assert (second / "dify_review_result.json").is_file()
    assert not (second / "dify_raw_response.json").exists()

    cache_files = list(cache_environment.rglob("*.json"))
    assert len(cache_files) == 4
    assert all("DIFY_API_KEY" not in path.read_text(encoding="utf-8") for path in cache_files)


def test_cache_metadata_contains_auditable_dimensions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cache_environment: Path,
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(main_module, "_execute_dify_batches", _fake_execute_factory(calls))
    output_dir = tmp_path / "metadata"
    _write_job(output_dir, _document_dict())
    main_module._run_dify_review(output_dir, [_rules()[0]])

    metadata = json.loads(next(cache_environment.rglob("metadata.json")).read_text(encoding="utf-8"))
    assert metadata["status"] == "success"
    assert metadata["source_sha256"]
    assert metadata["rule_id"] == "HF-COMP-001"
    assert metadata["evidence_package_hash"]
    assert metadata["workflow_version"] == "workflow-v1"
    assert metadata["prompt_version"] == "prompt-v1"
    assert metadata["model_identifier"] == "unknown"
    assert metadata["output_schema_version"] == "schema-v1"
    assert isinstance(metadata["input_chars"], int)
    assert isinstance(metadata["duration_ms"], int)


@pytest.mark.parametrize(
    "environment_name",
    ["DIFY_PROMPT_VERSION", "DIFY_MODEL_IDENTIFIER", "DIFY_OUTPUT_SCHEMA_VERSION"],
)
def test_prompt_model_and_schema_versions_invalidate_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cache_environment: Path,
    environment_name: str,
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(main_module, "_execute_dify_batches", _fake_execute_factory(calls))
    first = tmp_path / "first"
    second = tmp_path / "second"
    _write_job(first, _document_dict())
    main_module._run_dify_review(first, [_rules()[0]])
    monkeypatch.setenv(environment_name, "changed-version")
    _write_job(second, _document_dict())
    main_module._run_dify_review(second, [_rules()[0]])

    assert calls == [["HF-COMP-001"], ["HF-COMP-001"]]
    assert _audit(second)["cache_hit_count"] == 0


def test_call_audit_records_requested_count_equation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cache_environment: Path,
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(main_module, "_execute_dify_batches", _fake_execute_factory(calls))
    first = tmp_path / "first"
    second = tmp_path / "second"
    _write_job(first, _document_dict())
    main_module._run_dify_review(first, _rules())
    changed = _document_dict()
    changed["pages"][2]["blocks"][0]["text"] += " changed"
    _write_job(second, changed)
    main_module._run_dify_review(second, _rules())

    audit = _audit(second)
    assert audit["requested_rule_count"] == (
        audit["cache_hit_count"] + audit["api_requested_rule_count"]
    )
    assert audit["requested_rule_count"] == 2


def test_partial_cache_hit_only_sends_changed_rule(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cache_environment: Path,
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(main_module, "_execute_dify_batches", _fake_execute_factory(calls))
    first = tmp_path / "first"
    second = tmp_path / "second"
    document = _document_dict()
    _write_job(first, document)
    main_module._run_dify_review(first, _rules())

    changed = json.loads(json.dumps(document, ensure_ascii=False))
    changed["pages"][2]["blocks"][0]["text"] += " 证据变化"
    _write_job(second, changed)
    main_module._run_dify_review(second, _rules())

    assert calls == [["HF-COMP-001", "HF-COMP-007"], ["HF-COMP-007"]]
    audit = _audit(second)
    assert audit["requested_rule_count"] == 2
    assert audit["cache_hit_count"] == 1
    assert audit["api_requested_rule_count"] == 1
    assert audit["cache_hit_rule_ids"] == ["HF-COMP-001"]
    assert audit["api_requested_rule_ids"] == ["HF-COMP-007"]
    request = json.loads((second / "dify_request.json").read_text(encoding="utf-8"))
    assert request["batches"][0]["rule_ids"] == ["HF-COMP-007"]
    assert audit["status"] == "partial_cache_hit"


def test_evidence_change_does_not_hit_same_pdf_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cache_environment: Path,
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(main_module, "_execute_dify_batches", _fake_execute_factory(calls))
    document = _document_dict()
    first = tmp_path / "first"
    second = tmp_path / "second"
    _write_job(first, document)
    main_module._run_dify_review(first, [_rules()[0]])
    changed = json.loads(json.dumps(document, ensure_ascii=False))
    changed["pages"][1]["blocks"][1]["text"] += " 证据变化"
    _write_job(second, changed)
    main_module._run_dify_review(second, [_rules()[0]])

    assert calls == [["HF-COMP-001"], ["HF-COMP-001"]]
    assert _audit(second)["cache_hit_count"] == 0


def test_workflow_version_invalidates_existing_rule_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cache_environment: Path,
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(main_module, "_execute_dify_batches", _fake_execute_factory(calls))
    first = tmp_path / "first"
    second = tmp_path / "second"
    _write_job(first, _document_dict())
    main_module._run_dify_review(first, [_rules()[0]])
    monkeypatch.setenv("DIFY_WORKFLOW_VERSION", "workflow-v2")
    _write_job(second, _document_dict())
    main_module._run_dify_review(second, [_rules()[0]])

    assert calls == [["HF-COMP-001"], ["HF-COMP-001"]]
    assert _audit(second)["cache_hit_count"] == 0


def test_corrupt_cache_is_warning_and_recalled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cache_environment: Path,
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(main_module, "_execute_dify_batches", _fake_execute_factory(calls))
    first = tmp_path / "first"
    second = tmp_path / "second"
    _write_job(first, _document_dict())
    main_module._run_dify_review(first, [_rules()[0]])
    result_file = next(cache_environment.rglob("result.json"))
    result_file.write_text("{", encoding="utf-8")
    _write_job(second, _document_dict())
    main_module._run_dify_review(second, [_rules()[0]])

    assert calls == [["HF-COMP-001"], ["HF-COMP-001"]]
    assert any(item["code"] == "DIFY_CACHE_WARNING" for item in _audit(second)["warnings"])


def test_dify_failure_does_not_write_success_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cache_environment: Path,
) -> None:
    async def fail_execute(*args, **kwargs):
        raise DifyError("mock Dify failure")

    monkeypatch.setattr(main_module, "_execute_dify_batches", fail_execute)
    output_dir = tmp_path / "failed"
    _write_job(output_dir, _document_dict())

    with pytest.raises(RuntimeError, match="mock Dify failure"):
        main_module._run_dify_review(output_dir, [_rules()[0]])

    assert not list(cache_environment.rglob("result.json"))
    audit = _audit(output_dir)
    assert audit["status"] == "api_failed"
    assert audit["error_summary"] == "mock Dify failure"
    assert (output_dir / "dify_error.json").is_file()


def test_partial_api_failure_caches_only_completed_rules(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cache_environment: Path,
) -> None:
    async def partial_failure(batches, task_id, target_dir):
        error = DifyError("mock partial failure")
        error.batch_index = 2
        error.partial_raw_records = []
        error.partial_parsed_records = [
            {
                "batch_index": 1,
                "rule_ids": ["HF-COMP-001"],
                "result": {
                    "results": [
                        {
                            "rule_id": "HF-COMP-001",
                            "status": "PASS",
                            "reason": "done",
                            "evidence": [],
                        }
                    ]
                },
            }
        ]
        raise error

    monkeypatch.setattr(main_module, "_execute_dify_batches", partial_failure)
    output_dir = tmp_path / "partial"
    _write_job(output_dir, _document_dict())

    with pytest.raises(RuntimeError, match="mock partial failure"):
        main_module._run_dify_review(output_dir, _rules())

    assert len(list(cache_environment.rglob("result.json"))) == 1
    audit = _audit(output_dir)
    assert audit["status"] == "partial_api_failure"
    assert audit["failed_rule_ids"] == ["HF-COMP-007"]


def test_cache_disabled_does_not_lookup_or_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cache_environment: Path,
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setenv("DIFY_CACHE_ENABLED", "false")
    monkeypatch.setattr(main_module, "_execute_dify_batches", _fake_execute_factory(calls))
    output_dir = tmp_path / "disabled"
    _write_job(output_dir, _document_dict())
    main_module._run_dify_review(output_dir, [_rules()[0]])

    assert calls == [["HF-COMP-001"]]
    assert not list(cache_environment.rglob("result.json"))
    assert _audit(output_dir)["cache_hit_count"] == 0


def test_off_mode_does_not_create_cache_or_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cache_environment: Path,
) -> None:
    monkeypatch.setenv("DIFY_CACHE_ENABLED", "true")
    output_dir = tmp_path / "off"
    _write_job(output_dir, _document_dict())

    main_module._run_dify_review(output_dir, [_rules()[0]], mode="off")

    assert not list(cache_environment.rglob("result.json"))
    assert not (output_dir / "dify_call_audit.json").exists()
