"""Phase 1 Evidence Layer 测试：Evidence Registry / Validator / 检索工具。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.models import BoundingBox, MinerUBlock, MinerUDocument, MinerUPage, MinerUSection
from app.services.agent_guardrails import (
    EvidenceRegistry,
    build_evidence_id,
    normalize_for_match,
    validate_finish,
)
from app.services.agent_tools import (
    get_context,
    get_page,
    get_table,
    search_document,
)


def _block(
    block_id: str,
    block_type: str,
    text: str,
    block_index: int,
    *,
    page: int = 1,
    table_html: str | None = None,
) -> MinerUBlock:
    return MinerUBlock(
        block_id=block_id,
        physical_page=page,
        block_index=block_index,
        block_type=block_type,
        text=text,
        title_level=None,
        bbox=BoundingBox(10, 10, 100, 40),
        image_path=None,
        table_html=table_html,
        source_file="fixture.json",
        source_pointer=f"/{page}/{block_index}",
    )


def _document(pages: dict[int, list[MinerUBlock]]) -> MinerUDocument:
    page_objects = [
        MinerUPage(
            physical_page=page_no,
            source_page_index=page_no - 1,
            width=None,
            height=None,
            printed_page=None,
            page_type="text",
            parse_status="complete",
            text="",
            blocks=blocks,
        )
        for page_no, blocks in sorted(pages.items())
    ]
    return MinerUDocument(
        document_id="DOC-TEST",
        source_file_name="fixture.pdf",
        source_sha256="sha256",
        physical_page_count=len(page_objects),
        pages=page_objects,
        sections=[MinerUSection("SEC-1", "测试章节", 1, ["测试章节"], 1, 1)],
    )


@pytest.fixture
def document() -> MinerUDocument:
    return _document(
        {
            1: [
                _block("p0001-b0000", "title", "二、材料与设备计划", 0),
                _block(
                    "p0001-b0001",
                    "paragraph",
                    "钢材应符合现行国家标准的规定。",
                    1,
                ),
                _block(
                    "p0001-b0002",
                    "table",
                    "序号 施工部位 材料名称 规格 单位 数量 备注 "
                    "4 钢管 $\\Phi 48 \\times 3.0$ 吨 约138",
                    2,
                    table_html="<table><tr><td>钢管</td><td>Φ48×3.0</td></tr></table>",
                ),
                _block(
                    "p0001-b0003",
                    "table",
                    "可变荷载的分项系数γQ 1 1.5 永久荷载的分项系数γG 1 1.3",
                    3,
                ),
            ],
            2: [
                _block("p0002-b0000", "paragraph", "第二页内容：扫地杆距地面200mm。", 0),
            ],
        }
    )


# ---------------------------------------------------------------------------
# 归一化
# ---------------------------------------------------------------------------

class TestNormalize:
    def test_latex_symbol_conversion(self):
        # 匹配归一化：小写化（Φ->φ），符号直写
        assert "φ48×3.0" in normalize_for_match("钢管 $\\Phi 48 \\times 3.0$ 吨")

    def test_display_normalize_keeps_case(self):
        from app.services.agent_guardrails import display_normalize
        assert "Φ 48 × 3.0" in display_normalize("钢管 $\\Phi 48 \\times 3.0$ 吨")

    def test_whitespace_and_case(self):
        assert normalize_for_match("  A B  c ") == "abc"

    def test_empty(self):
        assert normalize_for_match("") == ""


# ---------------------------------------------------------------------------
# Evidence Registry
# ---------------------------------------------------------------------------

class TestEvidenceRegistry:
    def test_register_returns_stable_id(self):
        registry = EvidenceRegistry(document_id="DOC")
        eid = registry.register(page=1, text="证据原文", source_tool="search_document",
                                block_id="p0001-b0002", block_type="table")
        assert eid == "EV-P1-B0002"
        obj = registry.get(eid)
        assert obj is not None
        assert obj.page == 1
        assert obj.source_tool == "search_document"

    def test_page_level_id(self):
        registry = EvidenceRegistry()
        eid = registry.register(page=3, text="整页", source_tool="get_page",
                                block_id=None, block_type="page")
        assert eid == "EV-P3-PAGE"

    def test_duplicate_registration_dedupes(self):
        registry = EvidenceRegistry()
        first = registry.register(page=1, text="同一段证据", source_tool="search_document",
                                   block_id="p0001-b0001", block_type="paragraph")
        second = registry.register(page=1, text="同一段证据", source_tool="get_context",
                                    block_id="p0001-b0001", block_type="paragraph")
        assert first == second
        assert len(registry.all_evidence()) == 1

    def test_resolve_reports_missing(self):
        registry = EvidenceRegistry()
        eid = registry.register(page=1, text="证据", source_tool="search_document",
                                 block_id="p0001-b0001", block_type="paragraph")
        found, missing = registry.resolve([eid, "EV-P9-B9999"])
        assert len(found) == 1 and missing == ["EV-P9-B9999"]

    def test_save_and_load_roundtrip(self, tmp_path: Path):
        registry = EvidenceRegistry(document_id="DOC-TEST")
        registry.register(page=2, text="证据", source_tool="get_page",
                          block_id=None, block_type="page")
        path = tmp_path / "evidence_registry.json"
        registry.save(path)
        loaded = EvidenceRegistry.load(path)
        assert loaded.document_id == "DOC-TEST"
        assert len(loaded.all_evidence()) == 1
        assert loaded.get("EV-P2-PAGE") is not None


# ---------------------------------------------------------------------------
# Result Validator
# ---------------------------------------------------------------------------

class TestValidateFinish:
    def _registry_with(self, *evidence_ids: str) -> EvidenceRegistry:
        registry = EvidenceRegistry()
        for eid in evidence_ids:
            registry._evidence[eid] = None  # type: ignore[assignment]
        return registry

    def test_valid_finish(self):
        registry = EvidenceRegistry()
        eid = registry.register(page=1, text="证据", source_tool="search_document",
                                 block_id="p0001-b0001", block_type="paragraph")
        ok, errors = validate_finish(
            {"status": "VIOLATED", "reason": "超限", "evidence_ids": [eid], "page": 1},
            registry=registry, rule_id="4.34", total_pages=214,
        )
        assert ok and not errors

    def test_invalid_status_rejected(self):
        ok, errors = validate_finish(
            {"status": "PASS", "reason": "x"},
            registry=EvidenceRegistry(), rule_id="4.34", total_pages=214,
        )
        assert not ok and any("status" in e for e in errors)

    def test_violated_without_evidence_rejected(self):
        ok, errors = validate_finish(
            {"status": "VIOLATED", "reason": "超限", "evidence_ids": []},
            registry=EvidenceRegistry(), rule_id="4.34", total_pages=214,
        )
        assert not ok and any("VIOLATED" in e for e in errors)

    def test_unknown_evidence_id_rejected(self):
        ok, errors = validate_finish(
            {"status": "VIOLATED", "reason": "超限", "evidence_ids": ["EV-P99-B9999"]},
            registry=EvidenceRegistry(), rule_id="4.34", total_pages=214,
        )
        assert not ok and any("不存在" in e for e in errors)

    def test_page_out_of_range_rejected(self):
        ok, errors = validate_finish(
            {"status": "UNCERTAIN", "reason": "证据不足", "page": -1},
            registry=EvidenceRegistry(), rule_id="4.34", total_pages=214,
        )
        assert not ok and any("page" in e for e in errors)

    def test_page_bounds_edge(self):
        ok, errors = validate_finish(
            {"status": "UNCERTAIN", "reason": "证据不足", "page": 214},
            registry=EvidenceRegistry(), rule_id="4.34", total_pages=214,
        )
        assert ok and not errors


# ---------------------------------------------------------------------------
# 检索工具（LaTeX 归一化 + 关键词中心窗口）
# ---------------------------------------------------------------------------

class TestSearchDocument:
    def test_latex_normalized_hit(self, document: MinerUDocument):
        registry = EvidenceRegistry()
        text, eids = search_document(document, registry, keywords=["Φ48", "钢管"])
        assert "Φ48×3.0" in text.replace(" ", "")
        assert eids and registry.get(eids[0]) is not None

    def test_window_centers_on_keyword(self, document: MinerUDocument):
        """关键词在长 block 中部时，窗口应围绕关键词而非从头截断。"""
        registry = EvidenceRegistry()
        long_table = _document(
            {
                5: [
                    _block(
                        "p0005-b0000",
                        "table",
                        "项目A 111 项目B 222 项目C 333 项目D 444 "
                        "支撑立柱钢管型号(mm) Φ48×3 "
                        "项目E 555 项目F 666 项目G 777 项目H 888",
                        0,
                    ),
                ]
            }
        )
        text, _ = search_document(long_table, registry, keywords=["钢管型号"])
        assert "Φ48×3" in text

    def test_hit_sorted_by_term_count(self, document: MinerUDocument):
        registry = EvidenceRegistry()
        text, _ = search_document(document, registry,
                                  keywords=["钢管", "Φ48", "规格"])
        first_line = text.splitlines()[0]
        assert "B0002" in first_line  # 双词命中的材料表排最前

    def test_no_hit_message(self, document: MinerUDocument):
        registry = EvidenceRegistry()
        text, eids = search_document(document, registry, keywords=["不存在的词"])
        assert "未找到" in text
        assert eids == []


class TestGetPage:
    def test_returns_page_blocks_with_evidence_id(self, document: MinerUDocument):
        registry = EvidenceRegistry()
        text, eids = get_page(document, registry, page=2)
        assert "扫地杆" in text
        assert eids == ["EV-P2-PAGE"]
        assert registry.get("EV-P2-PAGE") is not None

    def test_missing_page(self, document: MinerUDocument):
        text, eids = get_page(document, EvidenceRegistry(), page=99)
        assert "无文本" in text
        assert eids == []


class TestGetTable:
    def test_returns_table_text(self, document: MinerUDocument):
        registry = EvidenceRegistry()
        text, eids = get_table(document, registry, block_id="p0001-b0002")
        assert "钢管" in text
        assert eids and registry.get(eids[0]).block_type == "table"

    def test_missing_block(self, document: MinerUDocument):
        text, eids = get_table(document, EvidenceRegistry(), block_id="nope")
        assert "不存在" in text
        assert eids == []


class TestGetContext:
    def test_neighbors_included(self, document: MinerUDocument):
        registry = EvidenceRegistry()
        text, eids = get_context(document, registry, block_id="p0001-b0001",
                                 before=1, after=1)
        assert "钢材应符合" in text       # 目标 block
        assert "材料与设备计划" in text   # 前 block
        assert "钢管" in text            # 后 block
        assert "→" in text
        assert eids

    def test_missing_block(self, document: MinerUDocument):
        text, _ = get_context(document, EvidenceRegistry(), block_id="nope")
        assert "不存在" in text


# ---------------------------------------------------------------------------
# build_evidence_id 格式
# ---------------------------------------------------------------------------

class TestEvidenceIdFormat:
    def test_block_suffix_strips_b(self):
        assert build_evidence_id(13, "p0013-b0002") == "EV-P13-B0002"

    def test_block_without_dash(self):
        assert build_evidence_id(1, "b0007") == "EV-P1-B0007"


class TestEvIdReference:
    """模型把 EV ID 当 block_id 传时的解析（Phase 2 E2E 发现）。"""

    def test_get_context_accepts_ev_id(self, document: MinerUDocument):
        registry = EvidenceRegistry()
        _, eids = search_document(document, registry, keywords=["γQ"])
        assert eids
        text, _ = get_context(document, registry, block_id=eids[0], before=1, after=1)
        assert "上下文" in text  # EV ID 被解析成真实 block_id 并成功取上下文

    def test_get_table_accepts_ev_id(self, document: MinerUDocument):
        registry = EvidenceRegistry()
        _, eids = search_document(document, registry, keywords=["Φ48", "钢管"])
        assert eids
        text, _ = get_table(document, registry, block_id=eids[0])
        assert "钢管" in text or "Φ" in text

    def test_unknown_reference_passthrough(self, document: MinerUDocument):
        text, _ = get_context(document, EvidenceRegistry(), block_id="nope")
        assert "不存在" in text
