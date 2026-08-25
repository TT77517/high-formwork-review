"""总控 Agent 汇总对象测试。"""

from __future__ import annotations

from app.models import MinerUDocument
from app.orchestrator_agent import build_orchestrator_state


def _document() -> MinerUDocument:
    return MinerUDocument(
        document_id="DOC-ORCH",
        source_file_name="demo.pdf",
        source_sha256="sha",
        physical_page_count=8,
    )


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
