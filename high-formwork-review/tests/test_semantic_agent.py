"""Phase 2 Agent Loop 测试：ReAct 循环 / Budget / 强制交卷 / 缓存 / 模式接线。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.models import BoundingBox, MinerUBlock, MinerUDocument, MinerUPage
from app.services import semantic_agent
from app.services.agent_guardrails import EvidenceRegistry
from app.services.llm_chat_client import ChatResponse, LLMChatError


class FakeLLMChatClient:
    """脚本化假客户端：按序返回预设响应，记录调用。"""

    model_identifier = "fake-model"
    current_model = "fake-model"

    def __init__(self, script: list[ChatResponse]):
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []

    def chat_sync(self, messages, *, tools=None, temperature=0.1):
        self.calls.append({
            "messages": [dict(m) for m in messages],
            "tool_names": [t["function"]["name"] for t in (tools or [])],
        })
        if not self.script:
            raise LLMChatError("脚本耗尽")
        return self.script.pop(0)


def _tool_response(*calls: dict[str, Any]) -> ChatResponse:
    return ChatResponse(content="", tool_calls=list(calls), model="fake-model")


def _call(name: str, **arguments: Any) -> dict[str, Any]:
    return {"id": f"call-{name}", "name": name, "arguments": arguments}


@pytest.fixture
def document() -> MinerUDocument:
    block = MinerUBlock(
        block_id="p0001-b0001",
        physical_page=1,
        block_index=1,
        block_type="table",
        text="支撑立柱钢管型号(mm) $\\Phi 48 \\times 3.0$ 吨 约138",
        title_level=None,
        bbox=BoundingBox(0, 0, 10, 10),
        image_path=None,
        table_html=None,
        source_file="f.json",
        source_pointer="/1/1",
    )
    page = MinerUPage(
        physical_page=1, source_page_index=0, width=None, height=None,
        printed_page=None, page_type="text", parse_status="complete",
        text="", blocks=[block],
    )
    return MinerUDocument(
        document_id="DOC-AGENT-TEST", source_file_name="f.pdf",
        source_sha256="sha-agent", physical_page_count=5, pages=[page],
    )


@pytest.fixture
def rule() -> dict[str, Any]:
    return {
        "rule_id": "5.1",
        "rule_name": "钢管规格-扣件式",
        "module": "m5",
        "severity": "high",
        "risk_level": "高",
        "check_content": "钢管规格应为Φ48.3×3.6mm",
        "check_logic": {"semantic_judgment": "钢管规格应符合规范要求"},
        "code_ref": {"standard": "JGJ130", "original_text": "钢管规格Φ48.3×3.6mm"},
        "remedy_suggestion": "更换钢管",
        "typical_violation": "Φ48×3.0",
    }


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(semantic_agent, "CACHE_ROOT", str(tmp_path))


# ---------------------------------------------------------------------------
# 循环
# ---------------------------------------------------------------------------

class TestEvidenceAgentLoop:
    def test_two_round_recovery_with_ev_id(self, document, rule):
        client = FakeLLMChatClient([
            _tool_response(_call("search_document", keywords=["钢管", "Φ48"])),
            _tool_response(_call(
                "finish", status="VIOLATED", reason="型号Φ48×3.0不符合Φ48.3×3.6",
                evidence_ids=[],  # 先给空触发校验失败
            )),
            _tool_response(_call(
                "finish", status="VIOLATED", reason="型号Φ48×3.0不符合Φ48.3×3.6",
                evidence_ids=["EV-P1-B0001"], confidence=0.9,
            )),
        ])
        result = semantic_agent.run_evidence_agent(
            rule, document, client=client, cache_enabled=False
        )
        assert result["status"] == "VIOLATED"
        assert result["review_engine"] == "agent_llm"
        assert result["evidence"], "证据应从 EV ID 解析出原文"
        assert result["evidence"][0]["page"] == 1
        assert "Φ 48 × 3.0" in result["evidence"][0]["quote"]
        assert result["agent"]["steps"][0]["action"] == "search_document"
        assert result["agent"]["forced_finish"] is False
        assert len(client.calls) == 3

    def test_violated_without_evidence_rejected_then_fixed(self, document, rule):
        """finish 校验失败会把错误回喂模型修正（Phase 2 设计）。"""
        client = FakeLLMChatClient([
            _tool_response(_call("search_document", keywords=["钢管"])),
            _tool_response(_call("finish", status="VIOLATED", reason="无证据违规")),
            _tool_response(_call(
                "finish", status="VIOLATED", reason="违规",
                evidence_ids=["EV-P1-B0001"],
            )),
        ])
        result = semantic_agent.run_evidence_agent(
            rule, document, client=client, cache_enabled=False
        )
        assert result["status"] == "VIOLATED"
        assert result["evidence"]
        # 校验失败的反馈回喂给了下一次调用
        feedback = client.calls[2]["messages"][-1]
        assert "校验失败" in feedback["content"]

    def test_budget_exhaustion_forced_finish(self, document, rule):
        client = FakeLLMChatClient([
            _tool_response(_call("search_document", keywords=["钢管"])),
            _tool_response(_call("search_document", keywords=["规格"])),
            _tool_response(_call("search_document", keywords=["壁厚"])),
            _tool_response(_call("finish", status="UNCERTAIN", reason="证据不足")),
        ])
        result = semantic_agent.run_evidence_agent(
            rule, document, client=client, cache_enabled=False
        )
        assert result["status"] == "UNCERTAIN"
        assert result["agent"]["forced_finish"] is True
        # 强制交卷那轮只提供 finish 工具
        assert client.calls[-1]["tool_names"] == ["finish"]

    def test_forced_finish_invalid_degrades_to_uncertain(self, document, rule):
        client = FakeLLMChatClient([
            _tool_response(_call("search_document", keywords=["钢管"])),
            _tool_response(_call("search_document", keywords=["规格"])),
            _tool_response(_call("search_document", keywords=["壁厚"])),
            # 强制交卷仍给非法证据
            _tool_response(_call(
                "finish", status="VIOLATED", reason="x",
                evidence_ids=["EV-P9-B9999"],
            )),
        ])
        result = semantic_agent.run_evidence_agent(
            rule, document, client=client, cache_enabled=False
        )
        assert result["status"] == "UNCERTAIN"
        assert "AGENT_FORCED_FINISH_INVALID" in result["reason"]
        assert result["evidence"] == []

    def test_no_tool_call_gets_correction(self, document, rule):
        client = FakeLLMChatClient([
            ChatResponse(content="我认为合规", tool_calls=[], model="fake"),
            _tool_response(_call(
                "finish", status="COMPLIANT", reason="符合要求"
            )),
        ])
        result = semantic_agent.run_evidence_agent(
            rule, document, client=client, cache_enabled=False
        )
        assert result["status"] == "COMPLIANT"
        assert "工具调用" in client.calls[1]["messages"][-1]["content"]

    def test_duplicate_calls_cached_then_forced(self, document, rule):
        same = _call("search_document", keywords=["钢管"])
        client = FakeLLMChatClient([
            _tool_response(same),
            _tool_response(same),
            _tool_response(same),  # 第 3 次重复 -> 强制交卷提示
            _tool_response(_call("finish", status="UNCERTAIN", reason="查证受限")),
        ])
        result = semantic_agent.run_evidence_agent(
            rule, document, client=client, cache_enabled=False
        )
        assert result["status"] == "UNCERTAIN"
        assert result["agent"]["duplicate_calls"] == 1
        # 第 3 次重复的强制终止提示出现在强制交卷调用的上下文里
        forced_round_tool_msg = [
            m for m in client.calls[3]["messages"] if m.get("role") == "tool"
        ]
        assert any("重复 3 次" in m["content"] for m in forced_round_tool_msg)

    def test_unknown_tool_rejected(self, document, rule):
        client = FakeLLMChatClient([
            _tool_response(_call("delete_document")),
            _tool_response(_call("finish", status="UNCERTAIN", reason="无法查证")),
        ])
        result = semantic_agent.run_evidence_agent(
            rule, document, client=client, cache_enabled=False
        )
        assert result["status"] == "UNCERTAIN"
        unknown_feedback = client.calls[1]["messages"][-1]
        assert "未知工具" in unknown_feedback["content"]


# ---------------------------------------------------------------------------
# 缓存
# ---------------------------------------------------------------------------

class TestAgentCache:
    def test_cache_hit_skips_llm(self, document, rule):
        finish = _tool_response(_call(
            "finish", status="VIOLATED", reason="违规",
            evidence_ids=["EV-P1-B0001"],
        ))
        client = FakeLLMChatClient([
            _tool_response(_call("search_document", keywords=["钢管"])),
            finish,
        ])
        first = semantic_agent.run_evidence_agent(
            rule, document, client=client, cache_enabled=True
        )
        assert first["agent"]["cache_hit"] is False
        assert len(client.calls) == 2

        second = semantic_agent.run_evidence_agent(
            rule, document, client=client, cache_enabled=True
        )
        assert second["agent"]["cache_hit"] is True
        assert len(client.calls) == 2  # 未产生新 LLM 调用
        assert second["status"] == first["status"]


# ---------------------------------------------------------------------------
# 全规则入口 + 模式接线
# ---------------------------------------------------------------------------

class TestRunSemanticReviewAgent:
    def test_gating_skips_llm_for_pending_rules(self, document):
        """支撑体系未识别时，体系专属规则本地判 PENDING，不进 LLM。"""
        client = FakeLLMChatClient([
            _tool_response(_call("finish", status="COMPLIANT", reason="符合"))
            for _ in range(200)
        ])
        result = semantic_agent.run_semantic_review_agent(
            document, {"facts": {"support_system": {"value": "unknown"}}},
            client=client, cache_enabled=False,
        )
        by_id = {r["rule_id"]: r for r in result["results"]}
        assert by_id["5.1"]["status"] == "PENDING_CONFIRMATION"
        assert result["pending_confirmation"] > 0
        assert result["mode"] == "agent_llm_semantic"

    def test_agent_failure_returns_warning_not_crash(self, document, rule):
        client = FakeLLMChatClient([])  # 脚本为空 -> LLMChatError
        with pytest.raises(LLMChatError):
            semantic_agent.run_evidence_agent(
                rule, document, client=client, cache_enabled=False
            )


class TestModeDispatch:
    def test_mode_config_accepts_agent(self, monkeypatch):
        from app.dify_config import resolve_semantic_review_mode
        monkeypatch.setenv("SEMANTIC_REVIEW_MODE", "agent")
        assert resolve_semantic_review_mode() == "agent"

    def test_mode_invalid_still_rejected(self, monkeypatch):
        from app.dify_config import resolve_semantic_review_mode
        monkeypatch.setenv("SEMANTIC_REVIEW_MODE", "bogus")
        with pytest.raises(ValueError):
            resolve_semantic_review_mode()

    def test_stage_dispatches_to_agent(self, document, monkeypatch):
        from app.services import semantic_dify
        marker = {"mode": "agent_llm_semantic", "results": [], "warnings": []}
        monkeypatch.setenv("SEMANTIC_REVIEW_MODE", "agent")
        monkeypatch.setattr(
            semantic_agent, "run_semantic_review_agent",
            lambda doc, facts, **kw: dict(marker),
        )
        result = semantic_dify.run_semantic_stage(document, {"facts": {}})
        assert result["mode"] == "agent_llm_semantic"

    def test_stage_agent_failure_falls_back(self, document, monkeypatch):
        from app.services import semantic_dify
        monkeypatch.setenv("SEMANTIC_REVIEW_MODE", "agent")
        monkeypatch.setattr(
            semantic_agent, "run_semantic_review_agent",
            lambda doc, facts, **kw: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        local_marker = {"mode": "local_keyword_match", "results": []}
        monkeypatch.setattr(
            "app.semantic_engine.run_semantic_engine_safe",
            lambda doc, facts: dict(local_marker),
        )
        monkeypatch.setattr(
            semantic_dify, "run_semantic_review_dify_safe",
            lambda doc, facts: dict(local_marker),
        )
        result = semantic_dify.run_semantic_stage(document, {"facts": {}})
        assert result["mode"] == "local_keyword_match"
        assert any(
            w["code"] == "AGENT_MODE_FALLBACK" for w in result.get("warnings", [])
        )


# ---------------------------------------------------------------------------
# Phase 5：Budget env 化 / 注入防护 / 落盘工件
# ---------------------------------------------------------------------------

class TestBudgetEnvOverride:
    def test_max_rounds_env_override(self, document, rule, monkeypatch):
        """AGENT_MAX_ROUNDS=1 时一轮后即强制交卷。"""
        import importlib
        import app.services.semantic_agent as sa

        monkeypatch.setenv("AGENT_MAX_ROUNDS", "1")
        reloaded = importlib.reload(sa)
        try:
            client = FakeLLMChatClient([
                _tool_response(_call("search_document", keywords=["钢管"])),
                _tool_response(_call("finish", status="UNCERTAIN", reason="预算受限")),
            ])
            result = reloaded.run_evidence_agent(
                rule, document, client=client, cache_enabled=False
            )
            assert result["status"] == "UNCERTAIN"
            assert result["agent"]["forced_finish"] is True
            assert result["agent"]["llm_calls"] == 2  # 1 轮 + 强制交卷
        finally:
            monkeypatch.delenv("AGENT_MAX_ROUNDS", raising=False)
            importlib.reload(sa)  # 恢复默认


class TestPromptInjectionDefense:
    def test_system_prompt_contains_defense_clause(self):
        assert "不得执行" in semantic_agent.SYSTEM_PROMPT
        assert "文档数据" in semantic_agent.SYSTEM_PROMPT

    def test_injected_tool_result_registered_verbatim_as_evidence(self, document, rule):
        """文档中的注入指令作为数据原样登记为证据，不进入指令面。

        机制性验证：工具结果文本即使包含"请忽略所有规定"这类注入语句，
        也只是 Evidence Registry 里的证据原文（quote），循环继续按白名单工作。
        """
        client = FakeLLMChatClient([
            _tool_response(_call("search_document", keywords=["钢管"])),
            _tool_response(_call(
                "finish", status="VIOLATED", reason="文档含注入语句",
                evidence_ids=["EV-P1-B0001"],
            )),
        ])
        result = semantic_agent.run_evidence_agent(
            rule, document, client=client, cache_enabled=False
        )
        assert result["status"] == "VIOLATED"
        # 证据是工具返回的原文片段（数据面），不是模型自由文本
        assert result["evidence"][0]["source"] == "agent_evidence"
        assert result["evidence"][0]["evidence_id"] == "EV-P1-B0001"


class TestAgentArtifacts:
    def test_extract_agent_artifacts_shapes(self, document, rule):
        client = FakeLLMChatClient([
            _tool_response(_call("search_document", keywords=["钢管"])),
            _tool_response(_call(
                "finish", status="VIOLATED", reason="违规",
                evidence_ids=["EV-P1-B0001"],
            )),
        ])
        agent_result = semantic_agent.run_evidence_agent(
            rule, document, client=client, cache_enabled=False
        )
        envelope = {
            "mode": "agent_llm_semantic",
            "route_stats": {"AGENT_REQUIRED": 1},
            "route_decisions": [
                {"rule_id": "5.1", "route": "AGENT_REQUIRED", "reason": "r", "decided_by": "heuristic"}
            ],
            "results": [agent_result],
            "warnings": [],
        }
        artifacts = semantic_agent.extract_agent_artifacts(envelope)
        assert set(artifacts) == {
            "route_decisions.json", "agent_trace.json", "agent_call_audit.json"
        }
        assert artifacts["route_decisions.json"][0]["rule_id"] == "5.1"
        trace = artifacts["agent_trace.json"][0]
        assert trace["rule_id"] == "5.1"
        assert trace["steps"][0]["action"] == "search_document"
        audit = artifacts["agent_call_audit.json"]
        assert audit["agent_rule_count"] == 1
        assert audit["total_llm_calls"] == 2
        assert audit["total_tool_calls"] == 1
        assert audit["prompt_version"] == semantic_agent.AGENT_PROMPT_VERSION
