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
            {"rule_id": "6.1", "rule_name": "s1", "status": "VIOLATED", "reason": "bad", "evidence": []},
            {
                "rule_id": "4.21",
                "rule_name": "扫地杆距底板高度限值",
                "status": "UNCERTAIN",
                "reason": "关键参数未识别",
                "evidence": [],
                "manual_review": True,
                "route": "HUMAN_REQUIRED",
                "severity": "B-required",
                "module": "04_construction_requirements",
            },
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
    assert "semantic_engine:4.21" in keys
    route_item = q[keys.index("semantic_engine:4.21")]
    assert route_item["system_result"] == "UNCERTAIN"
    assert route_item["meta"]["route"] == "HUMAN_REQUIRED"
    assert keys.index("rule_engine:4.1") < keys.index("semantic_engine:6.1")
    assert "completeness_review:HF-COMP-001" in keys
    assert keys[-1] == "document_parse:DOC-RISK-PAGES"
    assert q[-1]["link"] == {"tab": "document", "filter": "human-review"}
    assert q[-1]["meta"]["pages"] == [4]


def test_queue_without_new_args_keeps_legacy_items():
    out = build_review_results(_qual("disk_lock"), _comp(), [])
    keys = [i["item_key"] for i in out["human_review_queue"]]
    assert keys == ["completeness_review:HF-COMP-001"]


def test_calculation_condition_gap_enters_manual_queue():
    calculation = {
        "total_rules": 1,
        "results": [
            {
                "rule_id": "2.19",
                "rule_name": "新浇混凝土侧压力标准值",
                "status": "UNCERTAIN",
                "reason": "侧压力分支条件缺参",
                "severity": "B-required",
                "module": "02_load_values",
                "route": "agent_evidence",
                "code_ref": {"standard": "GB 50666-2011"},
                "evidence": [{"page": 8, "quote": "新浇混凝土侧压力标准值"}],
                "condition_evaluation": {
                    "overall_status": "UNKNOWN",
                    "selected_branch": "unknown",
                    "items": [
                        {
                            "condition": "采用内部振捣器，且浇筑速度V≤10m/h、坍落度≤180mm",
                            "expected": "按公式 F=0.28γct0βv^0.5 计算",
                            "status": "UNKNOWN",
                            "basis": "未提取到浇筑速度V或坍落度，无法选择侧压力分支",
                        }
                    ],
                },
            }
        ],
    }

    out = build_review_results(_qual("disk_lock"), _comp(), [], calculation=calculation)
    keys = [i["item_key"] for i in out["human_review_queue"]]

    assert "calculation_engine:2.19:conditions" in keys
    item = out["human_review_queue"][keys.index("calculation_engine:2.19:conditions")]
    assert item["source"] == "calculation_engine"
    assert item["link"] == {"tab": "calculation", "rule_id": "2.19"}
    assert "浇筑速度" in item["reason"]


def test_generic_calculation_condition_placeholder_is_not_queued():
    calculation = {
        "total_rules": 1,
        "results": [
            {
                "rule_id": "3.1",
                "rule_name": "受弯构件强度验算",
                "condition_evaluation": {
                    "overall_status": "UNKNOWN",
                    "selected_branch": "unknown",
                    "items": [
                        {
                            "condition": "适用条件",
                            "expected": "待人工确认",
                            "status": "UNKNOWN",
                            "basis": "当前版本未内置该条件判定",
                        }
                    ],
                },
            }
        ],
    }

    out = build_review_results(_qual("disk_lock"), _comp(), [], calculation=calculation)
    keys = [i["item_key"] for i in out["human_review_queue"]]

    assert "calculation_engine:3.1:conditions" not in keys
