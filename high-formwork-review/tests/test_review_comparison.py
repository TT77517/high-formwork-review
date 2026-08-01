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
    assert "本地为 PASS，Dify 为 MISSING" in item["difference_reason"]


def test_review_comparison_flags_uncertain_even_when_agreed() -> None:
    comparison = build_review_comparison(
        [{"rule_id": "HF-COMP-001", "name": "工程概况", "status": "UNCERTAIN"}],
        {"results": [{"rule_id": "HF-COMP-001", "status": "UNCERTAIN"}]},
    )

    item = comparison["results"][0]
    assert item["agreement"] is True
    assert item["manual_review"] is True
    assert comparison["manual_review_count"] == 1
    assert item["difference_reason"] == "两套结果一致但为 UNCERTAIN，仍需人工复核"
