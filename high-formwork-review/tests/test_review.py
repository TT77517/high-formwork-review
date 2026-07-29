from dataclasses import replace
from pathlib import Path

from app.completeness_review import (
    build_evidence_check_markdown,
    load_rules,
    review_completeness,
    review_completeness_with_details,
)
from app.models import (
    BoundingBox,
    MinerUBlock,
    MinerUDocument,
    MinerUPage,
    MinerUSection,
)


RULES_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "completeness_rules.json"
)


def _block(
    block_id: str,
    block_type: str,
    text: str,
    block_index: int,
    *,
    image_path: str | None = None,
    table_html: str | None = None,
    title_level: int | None = None,
) -> MinerUBlock:
    return MinerUBlock(
        block_id=block_id,
        physical_page=1,
        block_index=block_index,
        block_type=block_type,
        text=text,
        title_level=title_level,
        bbox=BoundingBox(10, 10, 100, 40),
        image_path=image_path,
        table_html=table_html,
        source_file="fixture_content_list_v2.json",
        source_pointer=f"/0/{block_index}",
    )


def _document(
    blocks: list[MinerUBlock],
    *,
    page_type: str = "text",
    parse_status: str = "complete",
    warnings: list[str] | None = None,
    sections: list[MinerUSection] | None = None,
) -> MinerUDocument:
    page = MinerUPage(
        physical_page=1,
        source_page_index=0,
        width=1000,
        height=1400,
        printed_page="1",
        page_type=page_type,
        parse_status=parse_status,
        text="\n".join(block.text for block in blocks),
        blocks=blocks,
        warnings=warnings or [],
        requires_human_review=parse_status != "complete",
    )
    return MinerUDocument(
        document_id="fixture-document",
        source_file_name="fixture_content_list_v2.json",
        source_sha256="0" * 64,
        physical_page_count=1,
        pages=[page],
        sections=sections or [],
        warnings=[],
        requires_human_review=parse_status != "complete",
    )


def _multi_page_document(
    page_blocks: dict[int, list[MinerUBlock]],
    *,
    sections: list[MinerUSection] | None = None,
) -> MinerUDocument:
    pages = []
    for physical_page, blocks in sorted(page_blocks.items()):
        adjusted_blocks = [
            replace(
                block,
                physical_page=physical_page,
                block_index=index,
                source_pointer=f"/{physical_page - 1}/{index}",
            )
            for index, block in enumerate(blocks)
        ]
        has_image = any(
            block.block_type in {"image", "chart"} for block in adjusted_blocks
        )
        pages.append(
            MinerUPage(
                physical_page=physical_page,
                source_page_index=physical_page - 1,
                width=1000,
                height=1400,
                printed_page=str(physical_page),
                page_type="drawing" if has_image else "text",
                parse_status="complete",
                text="\n".join(block.text for block in adjusted_blocks),
                blocks=adjusted_blocks,
                warnings=[],
                requires_human_review=False,
            )
        )
    return MinerUDocument(
        document_id="fixture-multi-page-document",
        source_file_name="fixture_content_list_v2.json",
        source_sha256="0" * 64,
        physical_page_count=max(page_blocks),
        pages=pages,
        sections=sections or [],
        warnings=[],
        requires_human_review=False,
    )


def _section(
    title: str,
    level: int = 1,
    *,
    start: int = 1,
    end: int = 1,
) -> MinerUSection:
    return MinerUSection(
        section_id="section-0001",
        title=title,
        level=level,
        path=[title],
        physical_page_start=start,
        physical_page_end=end,
    )


def _result(document: MinerUDocument, rule_id: str):
    summary = review_completeness(document, load_rules(RULES_PATH))
    assert summary.total_rules == 10
    return next(item for item in summary.results if item.rule_id == rule_id)


def test_clear_body_evidence_passes() -> None:
    document = _document(
        [
            _block("title", "title", "工程概况", 0, title_level=1),
            _block(
                "body",
                "paragraph",
                "工程名称为测试工程，建设地点明确，采用框架结构。"
                "高支模部位为报告厅，搭设高度为九米。",
                1,
            ),
        ],
        sections=[_section("工程概况")],
    )

    result = _result(document, "HF-COMP-001")
    assert result.status == "PASS"
    assert result.evidence
    assert result.evidence[0].physical_page == 1


def test_section_title_without_required_subitems_is_uncertain() -> None:
    document = _document(
        [_block("title", "title", "施工计划", 0, title_level=1)],
        sections=[_section("施工计划")],
    )

    result = _result(document, "HF-COMP-003")
    assert result.status == "UNCERTAIN"
    assert "只满足 0/4" in result.reason


def test_high_formwork_mandatory_subitem_is_required() -> None:
    document = _document(
        [
            _block("title", "title", "工程概况", 0, title_level=1),
            _block(
                "body",
                "paragraph",
                "工程名称为测试工程，建设地点明确，采用框架结构。",
                1,
            ),
        ],
        sections=[_section("工程概况")],
    )

    result = _result(document, "HF-COMP-001")
    assert result.status == "UNCERTAIN"
    assert "高支模部位或主要参数" in result.reason


def test_partial_page_subitems_do_not_pass() -> None:
    document = _document(
        [
            _block("title", "title", "应急处置措施", 0, title_level=1),
            _block(
                "body",
                "paragraph",
                "项目设置应急救援组织并明确应急职责，发生事故后启动应急响应。",
                1,
            ),
        ],
        parse_status="partial",
        sections=[_section("应急处置措施")],
    )

    result = _result(document, "HF-COMP-008")
    assert result.status == "UNCERTAIN"
    assert result.requires_human_review is True


def test_unreadable_page_evidence_cannot_pass() -> None:
    document = _document(
        [
            _block("title", "title", "施工计划", 0, title_level=1),
            _block(
                "body",
                "paragraph",
                "施工进度计划、材料需用计划、机械设备计划和劳动力计划齐全。",
                1,
            ),
        ],
        parse_status="unreadable",
        sections=[_section("施工计划")],
    )

    result = _result(document, "HF-COMP-003")
    assert result.status == "UNCERTAIN"


def test_toc_only_match_is_uncertain() -> None:
    document = _document(
        [_block("toc", "paragraph", "9.3 计算书....82", 0)],
        warnings=["识别为目录页，标题不会生成正文 section"],
    )

    result = _result(document, "HF-COMP-009")
    assert result.status == "UNCERTAIN"
    assert result.requires_human_review is True


def test_drawing_image_only_is_uncertain() -> None:
    document = _document(
        [_block("image", "image", "", 0, image_path="images/drawing.jpg")],
        page_type="drawing",
        parse_status="partial",
    )

    result = _result(document, "HF-COMP-010")
    assert result.status == "UNCERTAIN"
    assert result.evidence[0].image_path == "images/drawing.jpg"


def test_complete_document_without_evidence_is_missing() -> None:
    document = _document(
        [_block("body", "paragraph", "这是一段与应急处置无关的普通说明文字。", 0)]
    )

    result = _result(document, "HF-COMP-008")
    assert result.status == "MISSING"
    assert result.evidence == []


def test_material_acceptance_does_not_directly_pass_acceptance_rule() -> None:
    document = _document(
        [
            _block("title", "title", "验收要求", 0, title_level=1),
            _block(
                "body",
                "paragraph",
                "所有钢管和扣件到场后进行材料进场验收并检查合格证。",
                1,
            ),
        ],
        sections=[_section("验收要求")],
    )

    result = _result(document, "HF-COMP-007")
    assert result.status != "PASS"
    assert result.status == "UNCERTAIN"


def test_drawing_without_ocr_text_is_never_missing() -> None:
    document = _document(
        [_block("image", "image", "", 0, image_path="images/no-ocr.jpg")],
        page_type="drawing",
        parse_status="partial",
    )

    result = _result(document, "HF-COMP-010")
    assert result.status != "MISSING"


def test_associated_drawing_image_can_pass_when_partial_only_for_no_ocr() -> None:
    document = _document(
        [
            _block("title", "title", "相关施工图纸", 0, title_level=1),
            _block(
                "image",
                "image",
                "",
                1,
                image_path="images/drawing.jpg",
            ),
        ],
        page_type="drawing",
        parse_status="partial",
        sections=[_section("相关施工图纸")],
    )

    result = _result(document, "HF-COMP-010")
    assert result.status == "PASS"


def test_drawing_evidence_keeps_only_section_and_nearby_image_pages() -> None:
    page_blocks = {
        page: [
            _block(
                f"image-{page}",
                "image",
                "",
                0,
                image_path=f"images/{page}.jpg",
            )
        ]
        for page in range(1, 16)
    }
    page_blocks[7].insert(
        0,
        _block("drawing-title", "title", "相关施工图纸", 0, title_level=1),
    )
    document = _multi_page_document(
        page_blocks,
        sections=[_section("相关施工图纸", start=7, end=8)],
    )

    result = _result(document, "HF-COMP-010")
    evidence_pages = {item.physical_page for item in result.evidence}

    assert result.status == "PASS"
    assert evidence_pages == {5, 6, 7, 8, 9, 10}
    assert len(evidence_pages) < len(page_blocks)


def test_unassociated_drawing_pages_are_not_collected_globally() -> None:
    page_blocks = {
        page: [
            _block(
                f"image-{page}",
                "image",
                "",
                0,
                image_path=f"images/{page}.jpg",
            )
        ]
        for page in range(1, 13)
    }
    document = _multi_page_document(page_blocks)

    result = _result(document, "HF-COMP-010")
    evidence_pages = {item.physical_page for item in result.evidence}

    assert result.status == "UNCERTAIN"
    assert evidence_pages == {1}
    assert len(evidence_pages) <= 8


def test_drawing_evidence_page_limit_is_eight_when_association_is_unclear() -> None:
    page_blocks = {
        page: [
            _block(
                f"reference-{page}",
                "paragraph",
                "本页内容详见图纸。",
                0,
            )
        ]
        for page in range(1, 13)
    }
    document = _multi_page_document(page_blocks)

    result = _result(document, "HF-COMP-010")
    evidence_pages = {item.physical_page for item in result.evidence}

    assert result.status == "UNCERTAIN"
    assert evidence_pages == set(range(1, 9))
    assert len(evidence_pages) == 8


def test_evidence_report_contains_required_fields_and_pass_explanation() -> None:
    document = _document(
        [
            _block("title", "title", "工程概况", 0, title_level=1),
            _block(
                "body",
                "paragraph",
                "工程名称为测试工程，建设地点明确，采用框架结构。"
                "高支模部位为报告厅，搭设高度为九米。",
                1,
            ),
        ],
        sections=[_section("工程概况")],
    )
    rules = load_rules(RULES_PATH)
    summary, details = review_completeness_with_details(document, rules)

    report = build_evidence_check_markdown(document, summary, details)

    for field in (
        "matched_sections",
        "physical_pages",
        "printed_pages",
        "matched_terms",
        "matched_subitems",
        "evidence block type",
        "image_path",
        "table_html 是否存在",
        "page_type",
        "parse_status",
        "whether_from_toc",
        "requires_human_review",
    ):
        assert field in report
    assert "因此判定 PASS" in report
