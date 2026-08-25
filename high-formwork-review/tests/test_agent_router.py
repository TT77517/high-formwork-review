"""Phase 4 Router 测试：路由两层决策 / 混合分流 / 首轮证据种子。"""

from __future__ import annotations

from typing import Any

import pytest

from app.models import BoundingBox, MinerUBlock, MinerUDocument, MinerUPage, MinerUSection
from app.services import semantic_agent
from app.services.agent_guardrails import EvidenceRegistry
from app.services.agent_tools import search_document
from app.services.agent_router import (
    conflicting_fact_keys,
    missing_fact_keys,
    route_rule,
    route_rules,
)
from tests.test_semantic_agent import FakeLLMChatClient, _call, _tool_response


def _block(block_id: str, text: str, *, page: int = 1) -> MinerUBlock:
    return MinerUBlock(
        block_id=block_id, physical_page=page, block_index=0,
        block_type="paragraph", text=text, title_level=None,
        bbox=BoundingBox(0, 0, 1, 1), image_path=None, table_html=None,
        source_file="f.json", source_pointer="/0/0",
    )


def _document(blocks: list[MinerUBlock]) -> MinerUDocument:
    page = MinerUPage(
        physical_page=1, source_page_index=0, width=None, height=None,
        printed_page=None, page_type="text", parse_status="complete",
        text="", blocks=blocks,
    )
    return MinerUDocument(
        document_id="DOC-ROUTER", source_file_name="f.pdf",
        source_sha256="sha-router", physical_page_count=1, pages=[page],
    )


def _document_with_pages(pages: list[MinerUPage]) -> MinerUDocument:
    return MinerUDocument(
        document_id="DOC-ROUTER",
        source_file_name="f.pdf",
        source_sha256="sha-router",
        physical_page_count=len(pages),
        pages=pages,
    )


@pytest.fixture
def doc() -> MinerUDocument:
    return _document([
        _block("p0001-b0000", "扫地杆距地面高度不应大于200mm，扫地杆设置要求"),
        _block("p0001-b0001", "扫地杆设置高度按规范执行"),
    ])


def _rule(**overrides: Any) -> dict[str, Any]:
    base = {
        "rule_id": "4.34", "rule_name": "扫地杆高度",
        "check_content": "扫地杆距地面不应大于200mm",
        "check_logic": {"extraction_keywords": ["扫地杆", "高度"]},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# 路由决策
# ---------------------------------------------------------------------------

class TestRouteRule:
    def test_route_hint_static(self, doc):
        decision = route_rule(_rule(route_hint="LOCAL_READY"), doc)
        assert decision["route"] == "LOCAL_READY"
        assert decision["decided_by"] == "route_hint"

    def test_invalid_hint_falls_to_heuristic(self, doc):
        decision = route_rule(_rule(route_hint="随便写"), doc)
        assert decision["decided_by"] == "heuristic"

    def test_sufficient_hits_llm_ready(self, doc):
        decision = route_rule(_rule(), doc)  # 两个 block 命中"扫地杆"
        assert decision["route"] == "LLM_READY"
        assert "2 个正文 block" in decision["reason"]

    def test_toc_heavy_hits_require_agent_chase(self):
        toc_page = MinerUPage(
            physical_page=1, source_page_index=0, width=None, height=None,
            printed_page=None, page_type="toc", parse_status="complete",
            text="", warnings=["识别为目录页，标题不会生成正文 section"],
            blocks=[
                _block("p0001-b0000", "8. 应急处置措施....73", page=1),
                _block("p0001-b0001", "8.2 应急救援组织机构及职责....74", page=1),
            ],
        )
        body_page = MinerUPage(
            physical_page=2, source_page_index=1, width=None, height=None,
            printed_page=None, page_type="text", parse_status="complete",
            text="", blocks=[_block("p0002-b0000", "应急救援组织机构设置如下", page=2)],
        )
        document = _document_with_pages([toc_page, body_page])
        rule = _rule(
            rule_id="6.30",
            rule_name="应急响应流程与处置措施可操作性",
            check_logic={"extraction_keywords": ["应急处置", "应急救援"]},
        )
        decision = route_rule(rule, document)
        assert decision["route"] == "AGENT_REQUIRED"
        assert "正文有效证据仅 1 个" in decision["reason"]
        assert "目录 2 个" in decision["reason"]

    def test_insufficient_hits_agent_required(self):
        doc = _document([_block("p0001-b0000", "完全无关的内容")])
        decision = route_rule(_rule(), doc)
        assert decision["route"] == "AGENT_REQUIRED"
        assert decision["reason"].startswith("初始证据召回为 0")

    def test_no_keywords_uses_rule_name(self):
        doc = _document([_block("p0001-b0000", "完全无关的内容")])
        rule = _rule(check_logic={"extraction_keywords": []})
        decision = route_rule(rule, doc)
        assert decision["route"] == "AGENT_REQUIRED"

    def test_conflicting_fact_routes_human(self, doc):
        facts = {
            "support_height": {
                "status": "uncertain",
                "candidates": [
                    {"value": 8.05}, {"value": 13.62}, {"value": 5.87},
                ],
            }
        }
        rule = _rule(check_content="支模架搭设高度下扫地杆距地面不应大于200mm")
        decision = route_rule(rule, doc, facts)
        assert decision["route"] == "HUMAN_REQUIRED"
        assert "搭设高度" in decision["reason"]

    def test_missing_fact_routes_human_for_parameter_rule(self, doc):
        facts = {
            "head_jack_cantilever_length": {
                "status": "missing",
                "value": None,
                "candidates": [],
            }
        }
        rule = _rule(
            rule_id="4.12",
            rule_name="可调托撑悬臂长度",
            check_content="可调托撑悬臂长度不应超限",
        )
        decision = route_rule(rule, doc, facts)
        assert decision["route"] == "HUMAN_REQUIRED"
        assert "关键参数未识别" in decision["reason"]
        assert "可调托撑悬臂" in decision["reason"]

    def test_conflicting_fact_without_alias_ignored(self, doc):
        facts = {
            "support_height": {
                "status": "uncertain",
                "candidates": [{"value": 8.05}, {"value": 13.62}],
            }
        }
        decision = route_rule(_rule(), doc, facts)  # 规则文本不含"搭设高度"
        assert decision["route"] == "LLM_READY"

    def test_absent_fact_without_missing_status_ignored(self, doc):
        decision = route_rule(_rule(), doc, {})
        assert decision["route"] == "LLM_READY"

    def test_confirmed_fact_not_conflict(self, doc):
        facts = {
            "support_height": {"status": "confirmed", "candidates": [{"value": 13.88}]},
        }
        decision = route_rule(_rule(), doc, facts)
        assert decision["route"] == "LLM_READY"


class TestConflictingFactKeys:
    def test_detects_multi_value_conflict(self):
        facts = {
            "a": {"status": "uncertain", "candidates": [{"value": 1}, {"value": 2}]},
        }
        assert conflicting_fact_keys(facts) == ["a"]

    def test_detects_explicit_conflict_status(self):
        facts = {
            "a": {
                "status": "conflict",
                "has_conflict": True,
                "candidates": [{"value": 1}, {"value": 2}],
            },
        }
        assert conflicting_fact_keys(facts) == ["a"]

    def test_single_value_not_conflict(self):
        facts = {
            "a": {"status": "uncertain", "candidates": [{"value": 1}]},
        }
        assert conflicting_fact_keys(facts) == []


class TestMissingFactKeys:
    def test_detects_declared_missing_fact(self):
        facts = {"support_span": {"status": "missing", "value": None}}
        assert missing_fact_keys(facts) == ["support_span"]

    def test_absent_fact_is_not_missing(self):
        assert missing_fact_keys({}) == []

    def test_confirmed_fact_is_not_missing(self):
        facts = {"support_span": {"status": "confirmed", "value": 18.0}}
        assert missing_fact_keys(facts) == []


class TestRouteRules:
    def test_batch_routing(self, doc):
        decisions = route_rules([_rule(), _rule(rule_id="9.9")], doc)
        assert set(decisions) == {"4.34", "9.9"}


# ---------------------------------------------------------------------------
# 首轮证据种子（Phase 3 发现：5.1 检索方向波动）
# ---------------------------------------------------------------------------

class TestSeedKeywords:
    def test_seed_evidence_in_first_message(self):
        doc = _document([
            _block("p0001-b0000", "支撑立柱钢管型号(mm) $\\Phi 48 \\times 3.0$"),
        ])
        rule = {
            "rule_id": "5.1", "rule_name": "钢管规格",
            "check_content": "钢管规格应为Φ48.3×3.6mm",
            "check_logic": {"extraction_keywords": ["钢管", "规格"]},
        }
        client = FakeLLMChatClient([
            _tool_response(_call("finish", status="VIOLATED", reason="不符",
                                 evidence_ids=["EV-P1-B0000"])),
        ])
        semantic_agent.run_evidence_agent(
            rule, doc, client=client, cache_enabled=False,
            seed_keywords=["钢管", "规格"],
        )
        first_user = client.calls[0]["messages"][1]
        assert "初始证据" in first_user["content"]
        assert "EV-P1-B0000" in first_user["content"]

    def test_search_demotes_toc_and_prefers_body_section(self):
        toc_block = _block("p0001-b0000", "目录\n3 计算书", page=1)
        title = _block("p0002-b0000", "计算书", page=2)
        title.block_type = "title"
        body_block = _block("p0002-b0001", "立杆稳定计算：132.5≤205，满足要求", page=2)
        document = _document([toc_block])
        document.physical_page_count = 2
        document.pages[0].warnings.append("目录页")
        document.pages.append(
            MinerUPage(
                physical_page=2, source_page_index=1, width=None, height=None,
                printed_page=None, page_type="text", parse_status="complete",
                text="", blocks=[title, body_block],
            )
        )
        document.sections = [
            MinerUSection(
                section_id="section-0001",
                title="计算书",
                level=1,
                path=["计算书"],
                physical_page_start=2,
                physical_page_end=2,
            )
        ]

        text, evidence_ids = search_document(
            document,
            EvidenceRegistry(document_id="DOC-ROUTER"),
            keywords=["计算书", "立杆稳定"],
            preferred_sections=["计算书"],
        )

        assert evidence_ids
        assert text.splitlines()[0].startswith("EV-P2-B0001")
        assert "目录降权" in text


# ---------------------------------------------------------------------------
# 混合分流（run_semantic_review_agent 集成）
# ---------------------------------------------------------------------------

class TestHybridDispatch:
    def test_routes_dispatch_to_channels(
        self, doc, monkeypatch: pytest.MonkeyPatch,
    ):
        from app.services import agent_router
        from app.services.dify_client import DifyError

        # 固定路由：一条 LOCAL / 一条 LLM（批式失败降级）/ 一条 AGENT / 其余 LOCAL
        forced = {
            "1.10": {"rule_id": "1.10", "route": "LLM_READY", "reason": "测试", "decided_by": "route_hint"},
            "1.12": {"rule_id": "1.12", "route": "AGENT_REQUIRED", "reason": "测试", "decided_by": "route_hint"},
        }

        def fake_route_rule(rule, document, facts=None):
            rid = str(rule.get("rule_id", ""))
            return forced.get(rid, {
                "rule_id": rid, "route": "LOCAL_READY",
                "reason": "测试默认本地", "decided_by": "route_hint",
            })

        monkeypatch.setattr(agent_router, "route_rule", fake_route_rule)

        class FailingDifyClient:
            async def run_workflow(self, inputs, *, user):
                raise DifyError("测试：批式通道不可用")

        agent_client = FakeLLMChatClient([
            _tool_response(_call("finish", status="UNCERTAIN", reason="证据不足"))
            for _ in range(50)
        ])
        result = semantic_agent.run_semantic_review_agent(
            doc, {"facts": {}},
            client=agent_client, cache_enabled=False,
            dify_client=FailingDifyClient(),
        )
        by_id = {r["rule_id"]: r for r in result["results"]}
        # LOCAL：零 LLM，本地关键词判定（1.14 是 universal 规则，未被门禁拦截）
        assert by_id["1.14"]["route"] == "LOCAL_READY"
        assert by_id["1.14"]["review_engine"] == "local_router"
        # LLM_READY：批式失败降级本地关键词 + 告警
        assert by_id["1.10"]["route"] == "LLM_READY"
        assert by_id["1.10"]["review_engine"] == "local_fallback"
        assert any(w["code"] == "SEMANTIC_LLM_BATCH_FALLBACK" for w in result["warnings"])
        # AGENT_REQUIRED：走 Agent 循环
        assert by_id["1.12"]["route"] == "AGENT_REQUIRED"
        assert by_id["1.12"]["review_engine"] == "agent_llm"
        # envelope 附路由统计与决策
        assert result["route_stats"]["LOCAL_READY"] > 0
        assert result["route_stats"]["AGENT_REQUIRED"] == 1
        assert result["route_stats"]["LLM_READY"] == 1
        assert len(result["route_decisions"]) == len(result["results"]) - \
            result["route_stats"]["PENDING_GATED"]

    def test_human_route_creates_uncertain(self, doc, monkeypatch):
        from app.services import agent_router

        def fake_route_rule(rule, document, facts=None):
            rid = str(rule.get("rule_id", ""))
            return {
                "rule_id": rid,
                "route": "HUMAN_REQUIRED" if rid == "1.10" else "LOCAL_READY",
                "reason": f"关键参数取值冲突（{rid}），需人工确认后重跑" if rid == "1.10" else "默认",
                "decided_by": "route_hint",
            }

        monkeypatch.setattr(agent_router, "route_rule", fake_route_rule)
        agent_client = FakeLLMChatClient([])
        result = semantic_agent.run_semantic_review_agent(
            doc, {"facts": {}}, client=agent_client, cache_enabled=False,
        )
        by_id = {r["rule_id"]: r for r in result["results"]}
        assert by_id["1.10"]["status"] == "UNCERTAIN"
        assert by_id["1.10"]["route"] == "HUMAN_REQUIRED"
        assert by_id["1.10"]["review_engine"] == "router"
        assert by_id["1.10"]["manual_review"] is True
        assert result["route_stats"]["HUMAN_REQUIRED"] == 1
