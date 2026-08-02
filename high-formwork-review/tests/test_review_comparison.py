from app.review_comparison import build_review_comparison


def test_review_comparison_counts_agreement() -> None:
    comparison = build_review_comparison(
        [{"rule_id": "HF-COMP-001", "name": "工程概况", "status": "PASS"}],
        {"results": [{"rule_id": "HF-COMP-001", "status": "PASS"}]},
    )

    assert comparison["total_rules"] == 1
    assert comparison["agreement_count"] == 1
    assert comparison["disagreement_count"] == 0
    assert comparison["manual_review_count"] == 0
    assert comparison["results"][0]["comparison_status"] == "AGREEMENT"
    assert comparison["results"][0]["manual_review"] is False


def test_review_comparison_flags_status_disagreement() -> None:
    comparison = build_review_comparison(
        [{"rule_id": "HF-COMP-001", "name": "工程概况", "status": "PASS"}],
        {"results": [{"rule_id": "HF-COMP-001", "status": "MISSING"}]},
    )

    item = comparison["results"][0]
    assert comparison["agreement_count"] == 0
    assert comparison["disagreement_count"] == 1
    assert comparison["manual_review_count"] == 1
    assert item["agreement"] is False
    assert item["manual_review"] is True
    assert item["comparison_status"] == "DISAGREEMENT"
    assert "PASS" in item["difference_reason"]
    assert "MISSING" in item["difference_reason"]


def test_review_comparison_flags_uncertain_even_when_agreed() -> None:
    comparison = build_review_comparison(
        [{"rule_id": "HF-COMP-001", "name": "工程概况", "status": "UNCERTAIN"}],
        {"results": [{"rule_id": "HF-COMP-001", "status": "UNCERTAIN"}]},
    )

    item = comparison["results"][0]
    assert item["agreement"] is True
    assert item["manual_review"] is True
    assert comparison["manual_review_count"] == 1
    assert item["comparison_status"] == "BOTH_UNCERTAIN"
    assert "UNCERTAIN" in item["difference_reason"]


def test_review_comparison_marks_not_requested() -> None:
    comparison = build_review_comparison(
        [
            {
                "rule_id": "HF-COMP-001",
                "name": "工程概况",
                "status": "PASS",
                "confidence": 0.9,
                "needs_semantic_review": False,
            }
        ],
        None,
        selection={"mode": "on_demand", "selected_rule_ids": []},
    )

    item = comparison["results"][0]
    assert item["comparison_status"] == "NOT_REQUESTED"
    assert item["requested_to_dify"] is False
    assert item["dify_result_source"] == "not_requested"
    assert item["agreement"] is None
    assert item["manual_review"] is False
    assert comparison["not_requested_count"] == 1


def test_review_comparison_marks_dify_failed() -> None:
    comparison = build_review_comparison(
        [{"rule_id": "HF-COMP-001", "status": "PASS"}],
        None,
        selection={"mode": "full", "selected_rule_ids": ["HF-COMP-001"]},
        audit={
            "requested_rule_ids": ["HF-COMP-001"],
            "failed_rule_ids": ["HF-COMP-001"],
            "status": "api_failed",
        },
        dify_error={"status": "DIFY_FAILED", "message": "连接失败"},
    )

    item = comparison["results"][0]
    assert item["comparison_status"] == "DIFY_FAILED"
    assert item["dify_result_source"] == "failed"
    assert item["requires_human_review"] is True
    assert comparison["dify_failed_count"] == 1


def test_review_comparison_uses_cache_source() -> None:
    comparison = build_review_comparison(
        [{"rule_id": "HF-COMP-001", "status": "PASS"}],
        {"results": [{"rule_id": "HF-COMP-001", "status": "PASS"}]},
        audit={
            "requested_rule_ids": ["HF-COMP-001"],
            "cache_hit_rule_ids": ["HF-COMP-001"],
            "status": "cache_only",
        },
    )

    assert comparison["results"][0]["comparison_status"] == "AGREEMENT"
    assert comparison["results"][0]["dify_result_source"] == "cache"


def test_review_comparison_partial_failure_keeps_successful_rule() -> None:
    comparison = build_review_comparison(
        [
            {"rule_id": "HF-COMP-001", "status": "PASS"},
            {"rule_id": "HF-COMP-002", "status": "MISSING"},
        ],
        {"results": [{"rule_id": "HF-COMP-001", "status": "PASS"}]},
        selection={"mode": "full"},
        audit={
            "requested_rule_ids": ["HF-COMP-001", "HF-COMP-002"],
            "cache_hit_rule_ids": ["HF-COMP-001"],
            "failed_rule_ids": ["HF-COMP-002"],
            "status": "partial_api_failure",
        },
        dify_error={
            "status": "DIFY_FAILED",
            "failed_rule_ids": ["HF-COMP-002"],
            "message": "第二批失败",
        },
    )

    by_id = {item["rule_id"]: item for item in comparison["results"]}
    assert by_id["HF-COMP-001"]["comparison_status"] == "AGREEMENT"
    assert by_id["HF-COMP-001"]["dify_result_source"] == "cache"
    assert by_id["HF-COMP-002"]["comparison_status"] == "DIFY_FAILED"
    assert comparison["agreement_count"] + comparison["disagreement_count"] + comparison["not_requested_count"] + comparison["dify_failed_count"] + comparison["both_uncertain_count"] == comparison["total_rules"]
