from __future__ import annotations

from app.models import MinerUBlock, MinerUDocument, MinerUPage
from app.semantic_engine import build_semantic_evidence, collect_ranked_semantic_evidence_blocks
from app.services.semantic_dify import build_semantic_batches


def _block(block_id: str, text: str, *, page: int, block_type: str = "paragraph") -> MinerUBlock:
    return MinerUBlock(
        block_id=block_id,
        physical_page=page,
        block_index=0,
        block_type=block_type,
        text=text,
        title_level=None,
        bbox=None,
        image_path=None,
        table_html=None,
        source_file="test.json",
        source_pointer=block_id,
    )


def _document() -> MinerUDocument:
    return MinerUDocument(
        document_id="doc-semantic-evidence",
        source_file_name="demo.pdf",
        source_sha256="sha",
        physical_page_count=3,
        pages=[
            MinerUPage(
                physical_page=1,
                source_page_index=0,
                width=None,
                height=None,
                printed_page=None,
                page_type="toc",
                parse_status="complete",
                warnings=["识别为目录页，标题不会生成正文 section"],
                text="目录\n5.2.7 监测频率……67",
                blocks=[_block("toc-1", "目录\n5.2.7 监测频率……67", page=1)],
            ),
            MinerUPage(
                physical_page=2,
                source_page_index=1,
                width=None,
                height=None,
                printed_page=None,
                page_type="body",
                parse_status="complete",
                text="5.2.7 监测频率\n混凝土浇筑过程中应连续监测，监测频率不低于每30分钟一次。",
                blocks=[
                    _block("title-2", "5.2.7 监测频率", page=2, block_type="title"),
                    _block(
                        "body-2",
                        "混凝土浇筑过程中应连续监测，监测频率不低于每30分钟一次。",
                        page=2,
                    ),
                ],
            ),
            MinerUPage(
                physical_page=3,
                source_page_index=2,
                width=None,
                height=None,
                printed_page=None,
                page_type="body",
                parse_status="complete",
                text="普通段落",
                blocks=[_block("body-3", "普通段落", page=3)],
            ),
        ],
    )


def _rule() -> dict:
    return {
        "rule_id": "6.9",
        "rule_name": "监测频率",
        "check_content": "方案应明确监测频率。",
        "check_logic": {"extraction_keywords": ["监测频率", "连续监测", "30分钟"]},
        "code_ref": {"standard": "JGJ 300-2013", "original_text": "监测频率不低于每30分钟一次"},
        "severity": "B-required",
    }


def test_semantic_evidence_prefers_body_over_toc() -> None:
    evidence = build_semantic_evidence(_document(), _rule())

    assert "第2页" in evidence
    assert "连续监测" in evidence
    assert "第1页" not in evidence
    assert "……67" not in evidence


def test_dify_batches_use_ranked_body_blocks_for_quote_location() -> None:
    batches = build_semantic_batches([_rule()], _document(), batch_size=1)
    blocks = batches[0]["evidence_blocks"]["6.9"]

    assert blocks[0]["block_id"] == "body-2"
    assert blocks[0]["is_toc"] is False
    assert "连续监测" in blocks[0]["text"]


def test_ranked_evidence_keeps_toc_after_body_when_noisy() -> None:
    blocks = collect_ranked_semantic_evidence_blocks(_document(), _rule(), limit=3)

    assert blocks[0]["block_id"] == "body-2"
    assert any(item["block_id"] == "toc-1" for item in blocks)


def test_title_hit_expands_following_section_context() -> None:
    document = MinerUDocument(
        document_id="doc-title-context",
        source_file_name="demo.pdf",
        source_sha256="sha",
        physical_page_count=1,
        pages=[
            MinerUPage(
                physical_page=8,
                source_page_index=0,
                width=None,
                height=None,
                printed_page=None,
                page_type="body",
                parse_status="complete",
                text="5.2.7 监测频率\n浇筑期间由专职人员持续观察模板支架变形。",
                blocks=[
                    _block("title-8", "5.2.7 监测频率", page=8, block_type="title"),
                    _block("body-8", "浇筑期间由专职人员持续观察模板支架变形。", page=8),
                ],
            )
        ],
    )
    rule = {
        "rule_id": "6.9",
        "rule_name": "监测频率",
        "check_logic": {"extraction_keywords": ["监测频率"]},
    }

    evidence = build_semantic_evidence(document, rule)
    batches = build_semantic_batches([rule], document, batch_size=1)
    batch_blocks = batches[0]["evidence_blocks"]["6.9"]

    assert "5.2.7 监测频率" in evidence
    assert "持续观察模板支架变形" in evidence
    assert [item["block_id"] for item in batch_blocks[:2]] == ["title-8", "body-8"]
