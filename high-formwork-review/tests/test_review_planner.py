"""Phase 6 Planner 测试：本地计划生成 / LLM 计划解析与降级 / Mandatory Checks。"""

from __future__ import annotations

import pytest

from app.services.llm_chat_client import ChatResponse, LLMChatError
from app.services.review_planner import (
    MANDATORY_CHECKS,
    _parse_plan_json,
    build_review_plan,
    build_review_plan_local,
)


class FakeChatClient:
    model_identifier = "fake"
    current_model = "fake"

    def __init__(self, content: str = "", error: Exception | None = None):
        self.content = content
        self.error = error
        self.calls = 0

    def chat_sync(self, messages, *, tools=None, temperature=0.1):
        self.calls += 1
        if self.error:
            raise self.error
        return ChatResponse(content=self.content, tool_calls=[], model="fake")


@pytest.fixture
def qualification() -> dict:
    return {
        "project_type": "concrete_formwork_support",
        "support_system": "disk_lock",
        "support_system_label": "承插型盘扣式",
        "risk_classification": "over_scale_dangerous",
    }


@pytest.fixture
def facts() -> dict:
    return {
        "support_height": {
            "status": "uncertain",
            "candidates": [{"value": 8.05}, {"value": 13.62}, {"value": 5.87}],
        },
        "total_load": {"status": "missing", "candidates": []},
        "step_height": {"status": "confirmed", "value": 1.5, "candidates": []},
    }


class TestLocalPlan:
    def test_focus_area_from_support_system(self, qualification, facts):
        plan = build_review_plan_local(qualification, facts)
        assert plan["focus_areas"][0]["area"] == "承插型盘扣式支撑体系构造要求"
        assert plan["focus_areas"][0]["priority"] == "HIGH"

    def test_missing_fact_becomes_agent_target(self, qualification, facts):
        plan = build_review_plan_local(qualification, facts)
        targets = {t["target"] for t in plan["agent_targets"]}
        assert "total_load" in targets
        assert "step_height" not in targets  # 已确认的不进 Agent 目标

    def test_conflicting_fact_becomes_human_confirmation(self, qualification, facts):
        plan = build_review_plan_local(qualification, facts)
        facts_confirmed = {c["fact"] for c in plan["human_confirmations"]}
        assert "support_height" in facts_confirmed

    def test_unknown_system_prompts_human_confirmation(self, facts):
        plan = build_review_plan_local({"support_system": "unknown"}, facts)
        assert plan["human_confirmations"][0]["fact"] == "support_system"

    def test_mandatory_checks_always_present(self, qualification, facts):
        plan = build_review_plan_local(qualification, facts)
        assert plan["mandatory_checks"] == MANDATORY_CHECKS
        assert "完整性审查" in plan["mandatory_checks"]


class TestLLMPlan:
    def test_llm_plan_used_when_valid(self, qualification, facts):
        llm_output = """```json
{
  "focus_areas": [{"area": "盘扣斜撑构造", "priority": "HIGH", "reason": "8m以上高架"}],
  "agent_targets": [{"target": "support_span", "reason": "跨度值需查证"}],
  "human_confirmations": []
}
```"""
        client = FakeChatClient(content=llm_output)
        plan = build_review_plan(qualification, facts, client=client)
        assert plan["generated_by"] == "llm"
        assert plan["focus_areas"][0]["area"] == "盘扣斜撑构造"
        assert client.calls == 1

    def test_invalid_json_falls_back_to_local(self, qualification, facts):
        client = FakeChatClient(content="这不是JSON")
        plan = build_review_plan(qualification, facts, client=client)
        assert plan["generated_by"] == "local_stats"
        assert plan["focus_areas"][0]["area"] == "承插型盘扣式支撑体系构造要求"

    def test_llm_error_falls_back_silently(self, qualification, facts):
        client = FakeChatClient(error=LLMChatError("模型链全部不可用"))
        plan = build_review_plan(qualification, facts, client=client)
        assert plan["generated_by"] == "local_stats"
        assert plan["focus_areas"]  # 本地计划完整可用

    def test_invalid_priority_filtered(self):
        parsed = _parse_plan_json(
            '{"focus_areas": [{"area": "x", "priority": "超高"}]}'
        )
        assert parsed is not None
        assert parsed["focus_areas"] == []  # 非法优先级条目被过滤

    def test_llm_output_capped_at_five(self, qualification, facts):
        items = [{"area": f"重点{i}", "priority": "HIGH", "reason": "r"} for i in range(8)]
        client = FakeChatClient(
            content='{"focus_areas": ' + str(items).replace("'", '"') + "}"
        )
        plan = build_review_plan(qualification, facts, client=client)
        assert len(plan["focus_areas"]) == 5
