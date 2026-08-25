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
        completeness_results=[{"requires_human_review": True}],
        rule_engine={"total_rules": 2, "compliant": 1, "violated": 1, "uncertain": 0, "pending_confirmation": 0},
        semantic={
            "total_rules": 3,
            "compliant": 1,
            "violated": 0,
            "uncertain": 2,
            "pending_confirmation": 0,
            "mode": "agent_llm_semantic",
            "route_stats": {"AGENT_REQUIRED": 1},
            "route_decisions": [{"rule_id": "5.1", "route": "AGENT_REQUIRED"}],
            "results": [{"rule_id": "5.1", "route": "AGENT_REQUIRED", "agent": {"steps": []}}],
        },
        calculation={
            "total_rules": 1,
            "compliant": 1,
            "violated": 0,
            "uncertain": 0,
            "results": [
                {
                    "rule_id": "3.9",
                    "rule_name": "立杆稳定性",
                    "status": "COMPLIANT",
                    "evidence": [{"page": 7, "quote": "计算结果 132.5≤205"}],
                }
            ],
        },
        substantive_review=[],
        consistency_review=[{"status": "ISSUE"}],
        drawing_review=[{"status": "ISSUE", "requires_human_review": True}],
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
    assert state["rerun_context"]["document_corrections_participate"] is True
    assert state["formula_recalculations"][0]["recalculated_status"] == "PASS"
