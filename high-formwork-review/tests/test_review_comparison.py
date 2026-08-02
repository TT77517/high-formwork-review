from app.review_comparison import build_review_comparison


def _ten_local_results() -> list[dict]:
    return [
        {
            "rule_id": f"HF-COMP-{index:03d}",
            "name": f"rule-{index}",
            "status": "PASS",
            "reason": "local reason",
            "evidence": [{"physical_page": index, "quote": "local evidence"}],
            "confidence": 0.95,
            "needs_semantic_review": False,
        }
        for index in range(1, 11)
    ]


def _on_demand_selection(rule_ids: list[str]) -> dict:
    return {"mode": "on_demand", "selected_rule_ids": rule_ids}


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


def test_six_requested_rules_fail_and_four_remain_not_requested() -> None:
    requested = [f"HF-COMP-{index:03d}" for index in range(1, 7)]
    comparison = build_review_comparison(
        _ten_local_results(),
        None,
        selection=_on_demand_selection(requested),
        audit={
            "requested_rule_ids": requested,
            "failed_rule_ids": requested,
            "status": "api_failed",
        },
        dify_error={"status": "DIFY_FAILED", "message": "HTTP 504"},
    )

    assert comparison["status_counts"] == {
        "AGREEMENT": 0,
        "DISAGREEMENT": 0,
        "NOT_REQUESTED": 4,
        "DIFY_FAILED": 6,
        "BOTH_UNCERTAIN": 0,
    }
    assert comparison["human_review_count"] == 6
    assert all(
        item["comparison_status"] == "DIFY_FAILED"
        for item in comparison["results"][:6]
    )
    assert all(
        item["comparison_status"] == "NOT_REQUESTED"
        for item in comparison["results"][6:]
    )


def test_mixed_cache_success_and_api_failure_preserves_unrequested_rules() -> None:
    requested = [f"HF-COMP-{index:03d}" for index in range(1, 7)]
    cached = requested[:3]
    failed = requested[3:]
    comparison = build_review_comparison(
        _ten_local_results(),
        {
            "results": [
                {"rule_id": rule_id, "status": "PASS"} for rule_id in cached
            ]
        },
        selection=_on_demand_selection(requested),
        audit={
            "requested_rule_ids": requested,
            "cache_hit_rule_ids": cached,
            "api_requested_rule_ids": failed,
            "failed_rule_ids": failed,
            "status": "partial_api_failure",
        },
        dify_error={
            "status": "DIFY_FAILED",
            "failed_rule_ids": failed,
            "message": "HTTP 504",
        },
    )

    by_id = {item["rule_id"]: item for item in comparison["results"]}
    assert all(by_id[rule_id]["comparison_status"] == "AGREEMENT" for rule_id in cached)
    assert all(by_id[rule_id]["dify_result_source"] == "cache" for rule_id in cached)
    assert all(by_id[rule_id]["comparison_status"] == "DIFY_FAILED" for rule_id in failed)
    assert all(
        by_id[rule_id]["comparison_status"] == "NOT_REQUESTED"
        for rule_id in [f"HF-COMP-{index:03d}" for index in range(7, 11)]
    )
    assert comparison["agreement_count"] == 3
    assert comparison["dify_failed_count"] == 3
    assert comparison["not_requested_count"] == 4


def test_none_dify_result_cannot_be_reported_as_disagreement() -> None:
    comparison = build_review_comparison(
        [{"rule_id": "HF-COMP-001", "status": "PASS"}],
        {"results": [{"rule_id": "HF-COMP-001", "status": None}]},
        selection={"mode": "full"},
        audit={"requested_rule_ids": ["HF-COMP-001"]},
    )

    item = comparison["results"][0]
    assert item["comparison_status"] == "DIFY_FAILED"
    assert comparison["disagreement_count"] == 0


def test_dify_failure_does_not_change_local_result_or_evidence() -> None:
    local = {
        "rule_id": "HF-COMP-001",
        "status": "PASS",
        "reason": "local reason",
        "evidence": [{"physical_page": 3, "quote": "important evidence"}],
        "confidence": 0.93,
        "needs_semantic_review": False,
    }
    original = dict(local)
    comparison = build_review_comparison(
        [local],
        None,
        selection={"mode": "full"},
        audit={
            "requested_rule_ids": ["HF-COMP-001"],
            "failed_rule_ids": ["HF-COMP-001"],
        },
        dify_error={"status": "DIFY_FAILED", "message": "HTTP 504"},
    )

    item = comparison["results"][0]
    assert local == original
    assert item["local_status"] == original["status"]
    assert item["local_reason"] == original["reason"]
    assert item["local_evidence"] == original["evidence"]
    assert item["comparison_status"] == "DIFY_FAILED"
