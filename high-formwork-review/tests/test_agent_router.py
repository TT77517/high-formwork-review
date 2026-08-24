"""Phase 4 Router 测试：路由两层决策 / 混合分流 / 首轮证据种子。"""

from __future__ import annotations

from typing import Any

import pytest

from app.models import BoundingBox, MinerUBlock, MinerUDocument, MinerUPage
from app.services import semantic_agent
from app.services.agent_router import (
    conflicting_fact_keys,
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
        assert "2 个 block" in decision["reason"]

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

    def test_conflicting_fact_without_alias_ignored(self, doc):
        facts = {
            "support_height": {
                "status": "uncertain",
                "candidates": [{"value": 8.05}, {"value": 13.62}],
            }
        }
        decision = route_rule(_rule(), doc, facts)  # 规则文本不含"搭设高度"
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

    def test_single_value_not_conflict(self):
        facts = {
            "a": {"status": "uncertain", "candidates": [{"value": 1}]},
        }
        assert conflicting_fact_keys(facts) == []


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
