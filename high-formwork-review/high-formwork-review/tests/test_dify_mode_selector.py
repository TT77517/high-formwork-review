from pathlib import Path

import pytest

from app.completeness_review import (
    _attach_semantic_metadata,
    calculate_completeness_confidence,
)
from app.completeness_review_selector import select_rules_for_dify_review
from app.dify_config import resolve_dify_completeness_mode
from app.models import (
    CompletenessResult,
    MinerUDocument,
    MinerUPage,
    MinerUSection,
    ReviewEvidence,
)


def _document(*, parse_status: str = "complete", toc: bool = False) -> MinerUDocument:
    return MinerUDocument(
        document_id="semantic-test",
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
                parse_status=parse_status,
                text="施工进度计划、材料计划、设备计划、劳动力计划",
                warnings=["目录页"] if toc else [],
                requires_human_review=parse_status != "complete",
            )
        ],
        sections=[
            MinerUSection(
                section_id="s1",
                title="施工计划",
                level=1,
                path=["施工计划"],
                physical_page_start=1,
                physical_page_end=1,
            )
        ],
        requires_human_review=parse_status != "complete",
    )


def _evidence(block_type: str = "paragraph") -> ReviewEvidence:
    return ReviewEvidence(
        physical_page=1,
        printed_page="1",
        section_path=["施工计划"],
        block_id="p1-b1",
        block_type=block_type,
        quote="施工进度计划、材料计划、设备计划、劳动力计划",
        description="测试证据",
        bbox=None,
        image_path=None,
        table_html=None,
        source_pointer="/pages/0/blocks/0",
    )


def _detail(*, satisfied_count: int = 4, subitem_count: int = 4) -> dict:
    return {
        "matched_sections": [{"title": "施工计划"}],
        "matched_terms": ["施工进度计划", "材料计划"],
        "matched_subitems": [
            {"name": f"子项{i}", "satisfied": i <= satisfied_count}
            for i in range(1, subitem_count + 1)
        ],
    }


def test_dify_completeness_mode_resolution_defaults_and_compatibility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DIFY_COMPLETENESS_MODE", raising=False)
    monkeypatch.delenv("WEB_ENABLE_DIFY", raising=False)

    assert (
        resolve_dify_completeness_mode(web_enable_dify=True, load_environment=False)
        == "on_demand"
    )
    assert (
        resolve_dify_completeness_mode(
            explicit_mode="full",
            web_enable_dify="false",
            load_environment=False,
        )
        == "off"
    )
    assert (
        resolve_dify_completeness_mode(
            explicit_mode="FULL",
            web_enable_dify="true",
            load_environment=False,
        )
        == "full"
    )


def test_invalid_dify_completeness_mode_is_rejected() -> None:
    with pytest.raises(ValueError, match="DIFY_COMPLETENESS_MODE"):
        resolve_dify_completeness_mode(
            explicit_mode="sometimes",
            web_enable_dify=True,
            load_environment=False,
        )


def test_completeness_result_extension_defaults_keep_old_callers_compatible() -> None:
    result = CompletenessResult(
        rule_id="HF-COMP-001",
        name="工程概况",
        status="PASS",
        reason="测试",
    )

    assert result.confidence is None
    assert result.needs_semantic_review is False
    assert result.semantic_review_reason is None


def test_confidence_high_for_complete_body_evidence() -> None:
    result = CompletenessResult(
        rule_id="HF-COMP-003",
        name="施工计划",
        status="PASS",
        reason="满足必要子项",
        evidence=[_evidence()],
    )
    detail = _detail()

    score = calculate_completeness_confidence(result, detail, _document())
    _attach_semantic_metadata(result, detail, _document())

    assert score >= 0.8
    assert result.confidence == score
    assert result.needs_semantic_review is False


def test_uncertain_and_title_only_evidence_need_semantic_review() -> None:
    uncertain = CompletenessResult(
        rule_id="HF-COMP-003",
        name="施工计划",
        status="UNCERTAIN",
        reason="无法确认正文内容",
        evidence=[_evidence()],
        requires_human_review=True,
    )
    uncertain_detail = _detail(satisfied_count=1)
    _attach_semantic_metadata(uncertain, uncertain_detail, _document())

    title_only = CompletenessResult(
        rule_id="HF-COMP-004",
        name="施工工艺技术",
        status="PASS",
        reason="命中标题",
        evidence=[_evidence("title")],
    )
    title_detail = _detail()
    _attach_semantic_metadata(title_only, title_detail, _document())

    assert uncertain.needs_semantic_review is True
    assert "UNCERTAIN" in uncertain.semantic_review_reason
    assert title_only.needs_semantic_review is True
    assert "标题" in title_only.semantic_review_reason


def test_selector_uses_mode_and_on_demand_flags() -> None:
    local_results = [
        {
            "rule_id": "HF-COMP-001",
            "needs_semantic_review": False,
            "semantic_review_reason": "无需语义复核",
        },
        {
            "rule_id": "HF-COMP-002",
            "needs_semantic_review": True,
            "semantic_review_reason": "低置信度",
        },
    ]

    off = select_rules_for_dify_review(local_results, "off")
    on_demand = select_rules_for_dify_review(local_results, "on_demand")
    full = select_rules_for_dify_review(local_results, "full")
    manual = select_rules_for_dify_review(
        local_results, "on_demand", manually_selected_rule_ids=["HF-COMP-001"]
    )

    assert off["selected_rule_ids"] == []
    assert on_demand["selected_rule_ids"] == ["HF-COMP-002"]
    assert full["selected_rule_ids"] == ["HF-COMP-001", "HF-COMP-002"]
    assert manual["selected_rule_ids"] == ["HF-COMP-001", "HF-COMP-002"]


def test_selector_rejects_unknown_manual_rule_id() -> None:
    with pytest.raises(ValueError, match="不存在"):
        select_rules_for_dify_review(
            [{"rule_id": "HF-COMP-001"}],
            "on_demand",
            manually_selected_rule_ids=["HF-COMP-404"],
        )
