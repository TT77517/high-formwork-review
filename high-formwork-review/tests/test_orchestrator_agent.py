"""总控 Agent 汇总对象测试。"""

from __future__ import annotations

import json

from app.drawing_integration import AgentDrawingReviewItem, AgentDrawingReviewResult
from app.models import MinerUDocument
from app.orchestrator_agent import build_orchestrator_state


def _document() -> MinerUDocument:
    return MinerUDocument(
        document_id="DOC-ORCH",
        source_file_name="demo.pdf",
        source_sha256="sha",
        physical_page_count=8,
    )


def _minimal_state_kwargs(**overrides):
    kwargs = {
        "project_facts": {"facts": {}},
        "project_qualification": {"support_system_label": "承插型盘扣式"},
        "completeness_summary": {
            "total_rules": 1,
            "pass_count": 1,
            "missing_count": 0,
            "uncertain_count": 0,
        },
        "completeness_results": [],
        "rule_engine": {"total_rules": 0, "results": []},
        "semantic": {"total_rules": 0, "results": []},
        "calculation": {"total_rules": 0, "results": []},
        "substantive_review": [],
        "consistency_review": [],
        "drawing_review": [],
    }
    kwargs.update(overrides)
    return kwargs


def test_orchestrator_wraps_four_review_tools_and_dispatch_plan():
    state = build_orchestrator_state(
        _document(),
        project_facts={
            "facts": {
                "support_height": {
                    "status": "conflict",
                    "value": None,
                    "unit": "m",
                    "has_conflict": True,
                    "requires_human_review": True,
                    "candidates": [
                        {
                            "value": 8.05,
                            "unit": "m",
                            "raw_value": "8.05m",
                            "confidence": 0.82,
                            "evidence": {"physical_page": 3, "block_id": "p3-b1", "text": "高度8.05m"},
                        },
                        {
                            "value": 13.88,
                            "unit": "m",
                            "raw_value": "13.88m",
                            "confidence": 0.9,
                            "evidence": {"physical_page": 4, "block_id": "p4-b1", "text": "高度13.88m"},
                        },
                    ],
                }
            }
        },
        project_qualification={"support_system_label": "承插型盘扣式"},
        completeness_summary={"total_rules": 10, "pass_count": 8, "missing_count": 1, "uncertain_count": 1},
        completeness_results=[
            {
                "rule_id": "HF-COMP-009",
                "name": "计算书",
                "status": "UNCERTAIN",
                "reason": "全文检查后未发现目标正文章节、相关内容或相关解析风险",
                "requires_human_review": True,
            }
        ],
        rule_engine={
            "total_rules": 3,
            "compliant": 1,
            "violated": 1,
            "uncertain": 1,
            "pending_confirmation": 0,
            "results": [
                {
                    "rule_id": "4.12",
                    "rule_name": "可调托撑悬臂长度",
                    "status": "UNCERTAIN",
                    "reason": "未从方案中提取到「head_jack_cantilever_length」参数",
                    "param_name": "head_jack_cantilever_length",
                }
            ],
        },
        semantic={
            "total_rules": 4,
            "compliant": 1,
            "violated": 0,
            "uncertain": 3,
            "pending_confirmation": 0,
            "mode": "agent_llm_semantic",
            "route_stats": {"AGENT_REQUIRED": 1, "HUMAN_REQUIRED": 1},
            "route_decisions": [
                {"rule_id": "5.1", "route": "AGENT_REQUIRED"},
                {"rule_id": "4.21", "route": "HUMAN_REQUIRED"},
            ],
            "results": [
                {
                    "rule_id": "5.1",
                    "rule_name": "钢管规格",
                    "status": "UNCERTAIN",
                    "reason": "初始证据召回不足，证据不足",
                    "route": "AGENT_REQUIRED",
                    "agent": {"steps": []},
                },
                {
                    "rule_id": "4.21",
                    "rule_name": "扫地杆距底板高度限值",
                    "status": "UNCERTAIN",
                    "route": "HUMAN_REQUIRED",
                    "manual_review": True,
                    "reason": "关键参数未识别（扫地杆高度）",
                },
                {
                    "rule_id": "9.9",
                    "rule_name": "宽泛规则",
                    "status": "UNCERTAIN",
                    "reason": "规则 9.9 未配置关键词，无法进行本地关键词匹配，需人工复核",
                },
            ],
        },
        calculation={
            "total_rules": 1,
            "compliant": 1,
            "violated": 0,
            "uncertain": 1,
            "results": [
                {
                    "rule_id": "3.9",
                    "rule_name": "立杆稳定性",
                    "status": "COMPLIANT",
                    "evidence": [{"page": 7, "quote": "计算结果 132.5≤205"}],
                    "calculation_recheck": {
                        "formula_id": "vertical_stability",
                        "formula_name": "立杆稳定性复算",
                        "pages": [7],
                        "expression": "σ = N / (φA) <= f",
                        "substituted_expression": "sigma = 60000 / (0.65 * 489) = 188.78 <= 205",
                        "computed_value": 188.78,
                        "operator": "<=",
                        "allowed_value": 205,
                        "status": "PASS",
                        "warnings": [],
                    },
                },
                {
                    "rule_id": "3.99",
                    "rule_name": "缺计算片段",
                    "status": "UNCERTAIN",
                    "reason": "计算书中找到部分关键词（1/5），验算内容可能不完整",
                    "evidence": [{"page": 8, "quote": "仅有稳定字样"}],
                }
            ],
        },
        substantive_review=[],
        consistency_review=[{"status": "ISSUE"}],
        drawing_review=[{
            "review_item_id": "DR-01",
            "title": "步距图文交叉验证",
            "status": "ISSUE",
            "requires_human_review": True,
            "evidence_quality": {"level": "conflict", "label": "数值冲突", "reasons": ["多个候选值"]},
        }],
        review_plan={"generated_by": "local_stats", "focus_areas": [{"area": "构造", "priority": "HIGH"}]},
        decisions=[
            {
                "source": "document_parse",
                "item_key": "document_parse:PAGE-4",
                "human_decision": "need_supplement",
                "note": "第4页高度表应按13.88m参与重跑",
                "decided_at": "2026-08-25T00:00:00+00:00",
            }
        ],
        human_overrides={"overrides": {"support_height": "13.88"}},
    )

    assert [item["stage"] for item in state["dispatch_plan"]] == [
        "plan",
        "dispatch",
        "evidence_chase",
        "human_confirmation",
        "rerun",
    ]
    assert [item["tool_id"] for item in state["tool_observations"]] == [
        "completeness_review",
        "semantic_review",
        "calculation_review",
        "drawing_review",
    ]
    assert state["parameter_conflicts"][0]["parameter"] == "support_height"
    assert state["uncertainty_analysis"]["total_uncertain"] == 6
    by_category = {
        item["category"]: item["count"]
        for item in state["uncertainty_analysis"]["categories"]
    }
    assert by_category["missing_content"] == 1
    assert by_category["missing_parameter"] == 2
    assert by_category["insufficient_evidence"] == 2
    assert by_category["broad_rule"] == 1
    assert any(
        item["type"] == "semantic_human_required" and item["rule_id"] == "4.21"
        for item in state["human_confirmation"]["items"]
    )
    assert state["rerun_context"]["document_corrections_participate"] is True
    assert state["formula_recalculations"][0]["recalculated_status"] == "PASS"
    assert state["formula_recalculations"][0]["formula_id"] == "vertical_stability"
    assert state["drawing_evidence_quality"]["counts"]["数值冲突"] == 1
    assert state["parameter_to_rules"]["head_jack_cantilever_length"][0]["rule_id"] == "4.12"
    assert any(
        ref["source"] == "calculation_engine" and ref["rule_id"] == "3.9"
        for ref in state["parameter_to_rules"]["standard_step_height"]
    )


def test_orchestrator_preserves_agent_drawing_review_domain_statuses():
    payload = AgentDrawingReviewResult(
        total_tasks=6,
        reviewed_tasks=6,
        status_counts={
            "CONSISTENT": 1,
            "CONFLICT": 1,
            "TEXT_ONLY": 1,
            "DRAWING_ONLY": 1,
            "UNCERTAIN": 1,
            "NOT_FOUND": 1,
        },
        items=[
            AgentDrawingReviewItem("a", "A", "CONSISTENT", "values_equal", "compatible", 900, 900, "mm", "mm", 1, 1, 1),
            AgentDrawingReviewItem("b", "B", "CONFLICT", "values_differ", "compatible", 900, 1200, "mm", "mm", 1, 1, 1),
            AgentDrawingReviewItem("c", "C", "TEXT_ONLY", "text_evidence_only", "unknown", 150, None, "mm", None, 1, 0, 0),
            AgentDrawingReviewItem("d", "D", "DRAWING_ONLY", "drawing_evidence_only", "unknown", None, 150, None, "mm", 0, 1, 0),
            AgentDrawingReviewItem("e", "E", "UNCERTAIN", "scope_unknown", "unknown", None, None, None, None, 1, 1, 0),
            AgentDrawingReviewItem("f", "F", "NOT_FOUND", "no_evidence", "unknown"),
        ],
    )

    state = build_orchestrator_state(
        _document(),
        **_minimal_state_kwargs(agent_drawing_review=payload),
    )

    domain = state["agent_drawing_review"]
    assert domain["status_counts"] == payload.status_counts
    assert [item["status"] for item in domain["items"]] == [
        "CONSISTENT",
        "CONFLICT",
        "TEXT_ONLY",
        "DRAWING_ONLY",
        "UNCERTAIN",
        "NOT_FOUND",
    ]
    assert domain["items"][1]["status"] == "CONFLICT"
    assert domain["items"][4]["status"] == "UNCERTAIN"
    assert state["tool_observations"][3]["agent_domain"]["status_counts"]["CONFLICT"] == 1
    assert state["human_confirmation"]["items"] == []
    json.dumps(state, ensure_ascii=False)


def test_orchestrator_agent_drawing_review_does_not_scalarize_constraints():
    payload = {
        "total_tasks": 1,
        "reviewed_tasks": 1,
        "status_counts": {"UNCERTAIN": 1},
        "items": [
            {
                "fact_id": "support_height",
                "display_name": "搭设高度",
                "status": "UNCERTAIN",
                "reason": "scope_unknown",
                "scope_alignment": "unknown",
                "text_value": None,
                "drawing_value": None,
                "text_evidence_count": 1,
                "drawing_evidence_count": 1,
            }
        ],
    }

    state = build_orchestrator_state(
        _document(),
        **_minimal_state_kwargs(agent_drawing_review=payload),
    )

    item = state["agent_drawing_review"]["items"][0]
    assert item["status"] == "UNCERTAIN"
    assert item["drawing_value"] is None
    assert state["agent_drawing_review"]["status_counts"]["UNCERTAIN"] == 1


def test_orchestrator_agent_drawing_review_empty_result_is_safe():
    state = build_orchestrator_state(_document(), **_minimal_state_kwargs())

    assert state["agent_drawing_review"]["source"] is None
    assert state["agent_drawing_review"]["authoritative"] is False
    assert state["agent_drawing_review"]["policy"] == "legacy_drawing_review_authoritative"
    assert state["agent_drawing_review"]["total_tasks"] == 0
    assert state["agent_drawing_review"]["items"] == []
    assert state["agent_drawing_review"]["status_counts"] == {
        "CONSISTENT": 0,
        "CONFLICT": 0,
        "TEXT_ONLY": 0,
        "DRAWING_ONLY": 0,
        "UNCERTAIN": 0,
        "NOT_FOUND": 0,
    }
