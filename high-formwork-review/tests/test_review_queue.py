"""统一人工复核队列构建测试。"""

from __future__ import annotations

from app.review_summary import build_review_results


def _qual(system="unknown"):
    q = {
        "project_type": "concrete_formwork_support",
        "support_system": system,
        "requires_human_review": system == "unknown",
        "human_review_reason": "关键工程识别参数未完全识别",
    }
    if system == "unknown":
        q["pending_confirmation"] = {
            "field": "support_system",
            "note": "支撑体系未识别",
            "options": [
                {"value": "disk_lock", "label": "承插型盘扣式", "pending_rule_count": 13}
            ],
        }
    return q


def _comp():
    return {
        "total_rules": 1,
        "pass_count": 0,
        "missing_count": 1,
        "uncertain_count": 0,
        "results": [
            {
                "rule_id": "HF-COMP-001",
                "name": "工程概况",
                "status": "MISSING",
                "reason": "r",
                "evidence": [],
            }
        ],
    }


def test_queue_order_item_keys_and_new_sources():
    rule_engine = {
        "pending_confirmation": 2,
        "results": [
            {
                "rule_id": "4.1",
                "rule_name": "r1",
                "status": "VIOLATED",
                "reason": "bad",
                "evidence": [],
                "code_ref": {"standard": "JGJ 162-2016"},
                "severity": "A-mandatory",
                "module": "04_construction_requirements",
            },
            {
                "rule_id": "4.2",
                "rule_name": "r2",
                "status": "PENDING_CONFIRMATION",
                "reason": "x",
                "evidence": [],
            },
        ],
    }
    semantic = {
        "pending_confirmation": 1,
        "results": [
            {"rule_id": "6.1", "rule_name": "s1", "status": "VIOLATED", "reason": "bad", "evidence": []}
        ],
    }
    pages = [
        {"physical_page": 4, "requires_human_review": True},
        {"physical_page": 5, "requires_human_review": False},
    ]

    out = build_review_results(
        _qual(), _comp(), [],
        rule_engine=rule_engine, semantic=semantic, document_pages=pages,
    )
    q = out["human_review_queue"]
    keys = [i["item_key"] for i in q]

    assert keys[0] == "project_qualification:PQ-01"
    assert q[0]["actionable"]["options"][0]["value"] == "disk_lock"
    assert keys[1] == "engine_scope:PENDING-SYSTEM"
    assert "rule_engine:4.1" in keys and "semantic_engine:6.1" in keys
    assert keys.index("rule_engine:4.1") < keys.index("semantic_engine:6.1")
    assert "completeness_review:HF-COMP-001" in keys
    assert keys[-1] == "document_parse:DOC-RISK-PAGES"
    assert q[-1]["link"] == {"tab": "document", "filter": "human-review"}
    assert q[-1]["meta"]["pages"] == [4]


def test_queue_without_new_args_keeps_legacy_items():
    out = build_review_results(_qual("disk_lock"), _comp(), [])
    keys = [i["item_key"] for i in out["human_review_queue"]]
    assert keys == ["completeness_review:HF-COMP-001"]
