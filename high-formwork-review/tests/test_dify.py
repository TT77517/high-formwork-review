import asyncio
import json
from pathlib import Path

import httpx
import pytest

import app.main as main_module
from app.dify_scheme import (
    IMAGE_REVIEW_MARKER,
    build_dify_scheme_payload,
    build_dify_scheme_text,
    build_rule_driven_batches,
    build_rule_evidence_packages,
    normalize_section_title,
)
from app.models import (
    CompletenessResult,
    CompletenessSummary,
    MinerUDocument,
    MinerUPage,
    MinerUSection,
)
from app.services.dify_client import (
    DifyClient,
    DifyError,
    extract_review_result,
    merge_batch_review_results,
    validate_review_result,
    validate_review_result_with_warnings,
)


def _document_dict() -> dict:
    return {
        "document_id": "mineru-test",
        "physical_page_count": 4,
        "sections": [
            {
                "section_id": "s1",
                "title": "1.1 工程简介",
                "level": 2,
                "path": ["1. 工程概况", "1.1 工程简介"],
                "physical_page_start": 2,
                "physical_page_end": 2,
            },
            {
                "section_id": "s2",
                "title": "第七章 验收要求",
                "level": 1,
                "path": ["第七章 验收要求"],
                "physical_page_start": 3,
                "physical_page_end": 4,
            },
        ],
        "pages": [
            {
                "physical_page": 1,
                "height": 300,
                "warnings": ["识别为目录页，标题不会生成正文 section"],
                "parse_status": "complete",
                "blocks": [
                    {
                        "block_type": "paragraph",
                        "text": "1. 工程概况....1",
                        "bbox": {"x0": 10, "y0": 30, "x1": 200, "y1": 80},
                    }
                ],
            },
            {
                "physical_page": 2,
                "height": 300,
                "warnings": [],
                "parse_status": "complete",
                "blocks": [
                    {
                        "block_type": "title",
                        "text": "1.1 工程简介",
                        "bbox": {"x0": 10, "y0": 30, "x1": 200, "y1": 50},
                    },
                    {
                        "block_type": "paragraph",
                        "text": "工程名称为测试项目。",
                        "bbox": {"x0": 10, "y0": 60, "x1": 200, "y1": 90},
                    },
                    {
                        "block_type": "table",
                        "text": "支模高度 8m\n建筑面积 10000㎡",
                        "bbox": {"x0": 10, "y0": 100, "x1": 250, "y1": 180},
                    },
                    {
                        "block_type": "page_number",
                        "text": "1",
                        "bbox": {"x0": 140, "y0": 285, "x1": 150, "y1": 295},
                    },
                ],
            },
            {
                "physical_page": 3,
                "height": 300,
                "warnings": [],
                "parse_status": "complete",
                "blocks": [
                    {
                        "block_type": "paragraph",
                        "text": "支架验收应由项目负责人组织。",
                        "bbox": {"x0": 10, "y0": 50, "x1": 250, "y1": 90},
                    }
                ],
            },
            {
                "physical_page": 4,
                "height": 300,
                "warnings": ["图片无可用 OCR 文本"],
                "parse_status": "partial",
                "blocks": [
                    {
                        "block_type": "image",
                        "text": "",
                        "bbox": {"x0": 10, "y0": 20, "x1": 280, "y1": 260},
                    }
                ],
            },
        ],
    }


def _rules() -> list[dict]:
    return [
        {
            "rule_id": "HF-COMP-001",
            "name": "工程概况",
            "section_aliases": ["工程简介", "项目概况"],
        },
        {
            "rule_id": "HF-COMP-007",
            "name": "验收要求",
            "section_aliases": ["验收要求"],
        },
    ]


def test_build_dify_scheme_text_keeps_pages_table_and_image_marker() -> None:
    text = build_dify_scheme_text(_document_dict())

    assert "【第1页】" not in text
    assert "【第2页】" in text
    assert "工程名称为测试项目" in text
    assert "支模高度 8m" in text
    assert "【第4页】" in text
    assert IMAGE_REVIEW_MARKER in text
    assert "\n1\n" not in text


def test_scheme_payload_under_limit_has_no_omissions() -> None:
    text, metadata = build_dify_scheme_payload(_document_dict(), character_limit=50_000)

    assert metadata == {
        "character_limit": 50_000,
        "character_count": len(text),
        "omitted_sections": [],
        "truncation_warning": None,
    }
    assert build_dify_scheme_text(_document_dict()) == text


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("1.工程概况", "工程概况"),
        ("1.1 工程简介", "工程简介"),
        ("第七章 验收要求", "验收要求"),
        ("１．２　施工计划", "施工计划"),
    ],
)
def test_section_title_normalization(source: str, expected: str) -> None:
    assert normalize_section_title(source) == expected


def test_rule_evidence_package_records_matches_and_character_count() -> None:
    packages, warnings, fallback = build_rule_evidence_packages(
        _document_dict(), _rules()
    )

    assert warnings == []
    assert fallback == []
    engineering = packages[0]
    assert engineering["rule_id"] == "HF-COMP-001"
    assert engineering["section_aliases"] == ["工程简介", "项目概况"]
    assert engineering["matched_sections"][0]["title"] == "1.1 工程简介"
    assert engineering["unmatched_aliases"] == ["项目概况"]
    assert engineering["page_ranges"] == [{"start_page": 2, "end_page": 2}]
    assert engineering["character_count"] == len(engineering["evidence_text"])


def test_missing_section_aliases_do_not_match_all_sections() -> None:
    packages, warnings, fallback = build_rule_evidence_packages(
        _document_dict(),
        [{"rule_id": "HF-X", "name": "坏配置", "section_aliases": []}],
    )

    assert packages == []
    assert warnings[0]["code"] == "RULE_CONFIG_WARNING"
    assert fallback[0]["status"] == "UNCERTAIN"
    assert fallback[0]["manual_review"] is True


def test_selected_rule_ids_filter_packages_in_config_order() -> None:
    packages, warnings, fallback = build_rule_evidence_packages(
        _document_dict(),
        _rules(),
        selected_rule_ids=["HF-COMP-007"],
    )

    assert warnings == []
    assert fallback == []
    assert [item["rule_id"] for item in packages] == ["HF-COMP-007"]
    assert build_rule_evidence_packages(
        _document_dict(), _rules(), selected_rule_ids=[]
    ) == ([], [], [])


def test_selected_rule_ids_reject_unknown_rule() -> None:
    with pytest.raises(ValueError, match="unknown rule_id"):
        build_rule_evidence_packages(
            _document_dict(), _rules(), selected_rule_ids=["HF-COMP-404"]
        )


def test_rule_evidence_is_deduplicated_and_capped_without_tail_cut() -> None:
    document = _document_dict()
    repeated = "正文命中内容-完整片段。" * 200
    document["pages"][2]["blocks"] = [
        {
            "block_type": "paragraph",
            "text": repeated,
            "bbox": {"x0": 10, "y0": 50, "x1": 250, "y1": 90},
        },
        {
            "block_type": "paragraph",
            "text": repeated,
            "bbox": {"x0": 10, "y0": 100, "x1": 250, "y1": 140},
        },
    ]
    packages, _, _ = build_rule_evidence_packages(
        document,
        _rules(),
        selected_rule_ids=["HF-COMP-007"],
        character_limit=800,
    )

    evidence = packages[0]["evidence_text"]
    assert len(evidence) <= 800
    assert evidence.count("正文命中内容-完整片段。") <= 1
    assert not evidence.endswith("正文命中内容-")


def test_construction_plan_rule_collects_cross_section_labor_evidence() -> None:
    rules_path = Path(__file__).resolve().parents[1] / "config" / "completeness_rules.json"
    rules = json.loads(rules_path.read_text(encoding="utf-8"))
    rule = next(item for item in rules if item["rule_id"] == "HF-COMP-003")
    document = {
        "document_id": "cross-section-plan",
        "physical_page_count": 74,
        "sections": [
            {
                "section_id": "s-plan",
                "title": "3. 施工计划",
                "level": 1,
                "path": ["3. 施工计划"],
                "physical_page_start": 12,
                "physical_page_end": 17,
            },
            {
                "section_id": "s-labor",
                "title": "6.4 其他作业人员配备及分工",
                "level": 2,
                "path": [
                    "6. 施工管理及作业人员配备",
                    "6.4 其他作业人员配备及分工",
                ],
                "physical_page_start": 74,
                "physical_page_end": 74,
            },
        ],
        "pages": [
            {
                "physical_page": 12,
                "height": 300,
                "warnings": [],
                "parse_status": "complete",
                "blocks": [
                    {
                        "block_type": "paragraph",
                        "text": "施工进度计划、材料需用计划和设备需用计划。",
                        "bbox": {"x0": 10, "y0": 50, "x1": 250, "y1": 90},
                    }
                ],
            },
            {
                "physical_page": 74,
                "height": 300,
                "warnings": [],
                "parse_status": "complete",
                "blocks": [
                    {
                        "block_type": "table",
                        "text": "劳动力投入计划表：木工160人，架子工60人。",
                        "bbox": {"x0": 10, "y0": 50, "x1": 250, "y1": 120},
                    }
                ],
            },
        ],
    }

    packages, warnings, fallback = build_rule_evidence_packages(document, [rule])

    assert warnings == []
    assert fallback == []
    assert packages[0]["section_aliases"] == rule["section_aliases"]
    assert "劳动力投入计划表" in packages[0]["evidence_text"]
    assert packages[0]["page_ranges"] == [
        {"start_page": 12, "end_page": 17},
        {"start_page": 74, "end_page": 74},
    ]
    assert rule["required_elements"] == [
        "施工进度计划",
        "材料计划",
        "设备计划",
        "劳动力计划",
    ]


def test_rule_driven_batches_send_each_rule_once_and_actual_rule_string() -> None:
    packages, _, _ = build_rule_evidence_packages(_document_dict(), _rules())
    batches = build_rule_driven_batches(
        packages, _rules(), "task-1", character_limit=50_000
    )

    assert len(batches) == 1
    batch = batches[0]
    assert batch["rule_ids"] == ["HF-COMP-001", "HF-COMP-007"]
    assert batch["expected_rule_count"] == 2
    assert batch["inputs"]["expected_rule_count"] == 2
    assert json.loads(batch["inputs"]["review_rules"]) == _rules()
    assert batch["character_count"] == len(batch["inputs"]["scheme_text"])
    assert batch["scheme_text_metadata"]["omitted_sections"] == []


def test_oversized_rule_is_split_by_complete_paragraphs() -> None:
    rules = [{"rule_id": "HF-LARGE", "name": "超大规则", "section_aliases": ["大章"]}]
    paragraph = "完整段落内容" * 20
    package = {
        "rule_id": "HF-LARGE",
        "item_name": "超大规则",
        "section_aliases": ["大章"],
        "matched_sections": [
            {"title": "1. 大章", "level": 1, "path": ["1. 大章"], "start_page": 1, "end_page": 3}
        ],
        "unmatched_aliases": [],
        "page_ranges": [{"start_page": 1, "end_page": 3}],
        "evidence_text": "\n\n".join([paragraph] * 6),
        "character_count": len("\n\n".join([paragraph] * 6)),
        "_page_chunks": [
            f"【第1页】\n\n{paragraph}",
            f"【第2页】\n\n{paragraph}",
            f"【第3页】\n\n{paragraph}",
        ],
    }

    batches = build_rule_driven_batches(
        [package], rules, "task-large", character_limit=500
    )

    assert len(batches) > 1
    assert all(batch["rule_ids"] == ["HF-LARGE"] for batch in batches)
    assert all(batch["character_count"] <= 500 for batch in batches)
    assert all("本分片只是完整证据的一部分" in batch["inputs"]["scheme_text"] for batch in batches)
    covered_pages = {
        page
        for batch in batches
        for page in range(batch["start_page"], batch["end_page"] + 1)
    }
    assert covered_pages == {1, 2, 3}
    assert all(
        f"【第{batch['start_page']}页】" in batch["inputs"]["scheme_text"]
        for batch in batches
    )
    assert [batch["oversized_rule_part"]["part_index"] for batch in batches] == list(
        range(1, len(batches) + 1)
    )


def test_dify_client_does_not_send_metadata() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "data": {
                    "status": "succeeded",
                    "outputs": {
                        "result_json": json.dumps(
                            {"results": [{"rule_id": "HF-COMP-001", "status": "PASS"}]}
                        )
                    },
                }
            },
        )

    async def run() -> dict:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http_client:
            client = DifyClient(
                "https://dify.example/v1",
                "secret",
                http_client=http_client,
            )
            return await client.run_workflow(
                {
                    "task_id": "task-1",
                    "scheme_text": "文本",
                    "review_rules": "[]",
                    "expected_rule_count": 1,
                },
                user="task-1",
            )

    raw = asyncio.run(run())

    assert "scheme_text_metadata" not in captured
    assert set(captured["inputs"]) == {
        "task_id",
        "scheme_text",
        "review_rules",
        "expected_rule_count",
    }
    assert captured["response_mode"] == "blocking"
    assert extract_review_result(raw)["results"][0]["status"] == "PASS"
    assert validate_review_result(
        extract_review_result(raw), ["HF-COMP-001"]
    ) == extract_review_result(raw)


def test_dify_client_records_http_status_for_non_json_gateway_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            504,
            content=b"<html>gateway timeout</html>",
            headers={"content-type": "text/html"},
        )

    async def run() -> DifyError:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http_client:
            client = DifyClient(
                "https://dify.example/v1",
                "secret",
                http_client=http_client,
            )
            with pytest.raises(DifyError) as caught:
                await client.run_workflow({"scheme_text": "text"}, user="task-1")
            return caught.value

    error = asyncio.run(run())

    assert "504" in str(error)
    assert error.technical_details["http_status"] == 504
    assert error.technical_details["content_type"] == "text/html"
    assert "gateway timeout" in error.technical_details["body_preview"]


def test_batch_result_validation_rejects_wrong_rule_or_status() -> None:
    with pytest.raises(DifyError, match="rule_id"):
        validate_review_result(
            {"results": [{"rule_id": "HF-WRONG", "status": "PASS"}]},
            ["HF-COMP-001"],
        )
    with pytest.raises(DifyError, match="无效状态"):
        validate_review_result(
            {"results": [{"rule_id": "HF-COMP-001", "status": "UNKNOWN"}]},
            ["HF-COMP-001"],
        )


def test_partial_result_validation_ignores_unrequested_rules_with_warning() -> None:
    result, warnings = validate_review_result_with_warnings(
        {
            "results": [
                {"rule_id": "HF-COMP-001", "status": "PASS"},
                {"rule_id": "HF-COMP-999", "status": "PASS"},
            ]
        },
        ["HF-COMP-001"],
        allow_unrequested=True,
    )

    assert [item["rule_id"] for item in result["results"]] == ["HF-COMP-001"]
    assert warnings[0]["code"] == "UNREQUESTED_RULE_IGNORED"


def test_oversized_fragment_results_are_conservatively_merged() -> None:
    merged = merge_batch_review_results(
        [
            {"result": {"results": [{"rule_id": "HF-LARGE", "status": "PASS", "evidence": [{"p": 1}]}]}},
            {"result": {"results": [{"rule_id": "HF-LARGE", "status": "MISSING", "evidence": []}]}},
        ],
        expected_rule_ids=["HF-LARGE"],
        oversized_rule_ids={"HF-LARGE"},
    )

    result = merged["results"][0]
    assert result["status"] == "UNCERTAIN"
    assert result["manual_review"] is True
    assert result["evidence"] == [{"p": 1}]


def _cli_document() -> MinerUDocument:
    return MinerUDocument(
        document_id="mineru-cli",
        source_file_name="fixture.json",
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


def _mock_existing_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    result = CompletenessResult(
        rule_id="HF-COMP-001",
        name="工程概况",
        status="PASS",
        reason="测试通过",
    )
    summary = CompletenessSummary(
        total_rules=1,
        pass_count=1,
        missing_count=0,
        uncertain_count=0,
        results=[result],
    )
    monkeypatch.setattr(main_module, "parse_mineru", lambda raw_dir: _cli_document())
    monkeypatch.setattr(main_module, "load_rules", lambda path: [_rules()[0]])
    monkeypatch.setattr(
        main_module,
        "review_completeness_with_details",
        lambda document, rules: (summary, [{}]),
    )
    monkeypatch.setattr(
        main_module,
        "build_evidence_check_markdown",
        lambda document, summary, details: "# evidence\n",
    )


def test_cli_without_dify_never_calls_dify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_existing_pipeline(monkeypatch)
    monkeypatch.setattr(
        main_module,
        "_run_dify_review",
        lambda output_dir, rules: pytest.fail("不应调用 Dify"),
    )

    code = main_module.main(
        ["--raw-dir", str(tmp_path), "--output-dir", str(tmp_path / "out")]
    )

    assert code == 0
    assert not (tmp_path / "out" / "dify_request.json").exists()
    comparison = json.loads(
        (tmp_path / "out" / "review_comparison.json").read_text(encoding="utf-8")
    )
    assert comparison["not_requested_count"] == comparison["total_rules"]


def test_cli_with_dify_calls_after_parse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_existing_pipeline(monkeypatch)
    monkeypatch.setenv("DIFY_COMPLETENESS_MODE", "on_demand")
    called: dict = {}

    def fake_dify(output_dir: Path, rules: list[dict]) -> None:
        assert (output_dir / "mineru_document.json").is_file()
        called["output_dir"] = output_dir

    monkeypatch.setattr(main_module, "_run_dify_review", fake_dify)
    output_dir = tmp_path / "out"

    code = main_module.main(
        [
            "--raw-dir",
            str(tmp_path),
            "--output-dir",
            str(output_dir),
            "--dify",
        ]
    )

    assert code == 0
    assert called["output_dir"] == output_dir


def test_cli_parse_failure_does_not_call_dify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        main_module,
        "parse_mineru",
        lambda raw_dir: (_ for _ in ()).throw(ValueError("解析失败")),
    )
    monkeypatch.setattr(
        main_module,
        "_run_dify_review",
        lambda output_dir, rules: pytest.fail("解析失败后不应调用 Dify"),
    )

    code = main_module.main(
        [
            "--raw-dir",
            str(tmp_path),
            "--output-dir",
            str(tmp_path / "out"),
            "--dify",
        ]
    )

    assert code == 1


def test_cli_dify_failure_preserves_existing_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_existing_pipeline(monkeypatch)
    monkeypatch.setenv("DIFY_COMPLETENESS_MODE", "full")
    monkeypatch.setattr(
        main_module,
        "_run_dify_review",
        lambda output_dir, rules: (_ for _ in ()).throw(RuntimeError("Dify 失败")),
    )
    output_dir = tmp_path / "out"

    code = main_module.main(
        [
            "--raw-dir",
            str(tmp_path),
            "--output-dir",
            str(output_dir),
            "--dify",
        ]
    )

    assert code == 1
    assert (output_dir / "mineru_document.json").is_file()
    assert (output_dir / "completeness_results.json").is_file()
    assert (output_dir / "completeness_summary.json").is_file()
    assert (output_dir / "completeness_evidence_check.md").is_file()
    comparison = json.loads(
        (output_dir / "review_comparison.json").read_text(encoding="utf-8")
    )
    assert comparison["dify_failed_count"] == comparison["total_rules"]


def test_dify_orchestration_saves_request_raw_and_review_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    monkeypatch.setenv("DIFY_CACHE_ENABLED", "false")
    document = _document_dict()
    document["sections"] = [document["sections"][0]]
    document["pages"] = document["pages"][:3]
    (output_dir / "mineru_document.json").write_text(
        json.dumps(document, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "completeness_results.json").write_text(
        json.dumps(
            [{"rule_id": "HF-COMP-001", "name": "工程概况", "status": "PASS"}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    rules = [_rules()[0]]

    async def fake_execute(batches, task_id, target_dir):
        assert len(batches) == 1
        assert batches[0]["expected_rule_count"] == 1
        assert "scheme_text_metadata" not in batches[0]["inputs"]
        raw = {
            "data": {
                "status": "succeeded",
                "outputs": {"result_json": "{}"},
            }
        }
        parsed = {
            "results": [
                {
                    "rule_id": "HF-COMP-001",
                    "name": "工程概况",
                    "status": "PASS",
                    "reason": "证据完整",
                    "evidence": [],
                }
            ]
        }
        return (
            [{"batch_index": 1, "rule_ids": ["HF-COMP-001"], "response": raw}],
            [{"batch_index": 1, "rule_ids": ["HF-COMP-001"], "result": parsed}],
        )

    monkeypatch.setattr(main_module, "_execute_dify_batches", fake_execute)
    main_module._run_dify_review(output_dir, rules)

    request_audit = json.loads(
        (output_dir / "dify_request.json").read_text(encoding="utf-8")
    )
    raw_response = json.loads(
        (output_dir / "dify_raw_response.json").read_text(encoding="utf-8")
    )
    review_result = json.loads(
        (output_dir / "dify_review_result.json").read_text(encoding="utf-8")
    )
    comparison = json.loads(
        (output_dir / "review_comparison.json").read_text(encoding="utf-8")
    )
    assert request_audit["batches"][0]["rule_ids"] == ["HF-COMP-001"]
    assert isinstance(
        request_audit["batches"][0]["inputs"]["review_rules"], str
    )
    assert raw_response["batches"][0]["batch_index"] == 1
    assert review_result["results"][0]["status"] == "PASS"
    assert comparison["agreement_count"] == 1
    assert comparison["manual_review_count"] == 0
    assert not (output_dir / "dify_error.json").exists()


def test_on_demand_orchestration_requests_only_selected_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    monkeypatch.setenv("DIFY_CACHE_ENABLED", "false")
    document = _document_dict()
    (output_dir / "mineru_document.json").write_text(
        json.dumps(document, ensure_ascii=False), encoding="utf-8"
    )
    (output_dir / "dify_selection.json").write_text(
        json.dumps(
            {
                "mode": "on_demand",
                "selected_count": 1,
                "selected_rule_ids": ["HF-COMP-007"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    captured: dict = {}

    async def fake_execute(batches, task_id, target_dir):
        captured["batches"] = batches
        raw = {
            "data": {
                "status": "succeeded",
                "outputs": {"result_json": "{}"},
            }
        }
        parsed = {
            "results": [
                {
                    "rule_id": "HF-COMP-007",
                    "name": "验收要求",
                    "status": "PASS",
                    "reason": "证据完整",
                    "evidence": [],
                }
            ]
        }
        return (
            [{"batch_index": 1, "rule_ids": ["HF-COMP-007"], "response": raw}],
            [
                {
                    "batch_index": 1,
                    "rule_ids": ["HF-COMP-007"],
                    "result": parsed,
                    "warnings": [],
                }
            ],
        )

    monkeypatch.setattr(main_module, "_execute_dify_batches", fake_execute)
    main_module._run_dify_review(output_dir, _rules())

    assert captured["batches"][0]["rule_ids"] == ["HF-COMP-007"]
    request = json.loads((output_dir / "dify_request.json").read_text(encoding="utf-8"))
    assert request["mode"] == "on_demand"
    assert request["selected_rule_ids"] == ["HF-COMP-007"]
    assert request["selected_count"] == 1
    assert request["requested_rule_ids"] == ["HF-COMP-007"]
    assert request["actual_requested_rule_count"] == 1
    assert request["actual_requested_rule_count"] == len(request["requested_rule_ids"])


def test_on_demand_empty_selection_skips_without_dify_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "mineru_document.json").write_text(
        json.dumps(_document_dict(), ensure_ascii=False), encoding="utf-8"
    )
    (output_dir / "dify_selection.json").write_text(
        json.dumps(
            {"mode": "on_demand", "selected_count": 0, "selected_rule_ids": []},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    async def fail_execute(*args, **kwargs):
        pytest.fail("selected_count=0 时不应调用 Dify")

    monkeypatch.setattr(main_module, "_execute_dify_batches", fail_execute)
    main_module._run_dify_review(output_dir, _rules())

    request = json.loads((output_dir / "dify_request.json").read_text(encoding="utf-8"))
    assert request["status"] == "skipped"
    assert request["requested_rule_ids"] == []
    assert not (output_dir / "dify_review_result.json").exists()


def test_full_orchestration_keeps_all_rules_when_selection_is_full(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    monkeypatch.setenv("DIFY_CACHE_ENABLED", "false")
    (output_dir / "mineru_document.json").write_text(
        json.dumps(_document_dict(), ensure_ascii=False), encoding="utf-8"
    )
    (output_dir / "dify_selection.json").write_text(
        json.dumps({"mode": "full"}, ensure_ascii=False), encoding="utf-8"
    )
    captured: dict = {}

    async def fake_execute(batches, task_id, target_dir):
        captured["rule_ids"] = [rule_id for batch in batches for rule_id in batch["rule_ids"]]
        return [], []

    monkeypatch.setattr(main_module, "_execute_dify_batches", fake_execute)
    with pytest.raises(RuntimeError, match="缺少规则"):
        main_module._run_dify_review(output_dir, _rules())

    assert captured["rule_ids"] == ["HF-COMP-001", "HF-COMP-007"]


def test_dify_orchestration_failure_writes_error_without_deleting_parse_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    monkeypatch.setenv("DIFY_CACHE_ENABLED", "false")
    parse_path = output_dir / "mineru_document.json"
    original = json.dumps(_document_dict(), ensure_ascii=False)
    parse_path.write_text(original, encoding="utf-8")

    async def fail_execute(batches, task_id, target_dir):
        error = DifyError("模拟 Dify 失败")
        error.batch_index = 1
        raise error

    monkeypatch.setattr(main_module, "_execute_dify_batches", fail_execute)
    with pytest.raises(RuntimeError, match="模拟 Dify 失败"):
        main_module._run_dify_review(output_dir, [_rules()[0]])

    error = json.loads(
        (output_dir / "dify_error.json").read_text(encoding="utf-8")
    )
    assert error == {
        "status": "DIFY_FAILED",
        "message": "模拟 Dify 失败",
        "failed_batch_index": 1,
    }
    assert parse_path.read_text(encoding="utf-8") == original


def test_dify_orchestration_keeps_technical_failure_details_in_audit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    monkeypatch.setenv("DIFY_CACHE_ENABLED", "false")
    (output_dir / "mineru_document.json").write_text(
        json.dumps(_document_dict(), ensure_ascii=False), encoding="utf-8"
    )

    async def fail_execute(batches, task_id, target_dir):
        error = DifyError(
            "Dify 返回了非 JSON 响应（HTTP 504）",
            technical_details={
                "http_status": 504,
                "content_type": "text/html",
                "body_preview": "gateway timeout",
            },
        )
        error.batch_index = 1
        raise error

    monkeypatch.setattr(main_module, "_execute_dify_batches", fail_execute)
    with pytest.raises(RuntimeError, match="504"):
        main_module._run_dify_review(output_dir, [_rules()[0]])

    error = json.loads((output_dir / "dify_error.json").read_text(encoding="utf-8"))
    audit = json.loads((output_dir / "dify_call_audit.json").read_text(encoding="utf-8"))
    assert error["technical_details"]["http_status"] == 504
    assert audit["error_details"]["content_type"] == "text/html"
    assert audit["error_details"]["body_preview"] == "gateway timeout"


def test_dify_preparation_failure_also_writes_error(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    with pytest.raises(OSError):
        main_module._run_dify_review(output_dir, _rules())

    error = json.loads(
        (output_dir / "dify_error.json").read_text(encoding="utf-8")
    )
    assert error["status"] == "DIFY_FAILED"
    assert error["failed_batch_index"] is None
