"""Compare local completeness review results with Dify review results."""

from __future__ import annotations

from typing import Any


UNCERTAIN = "UNCERTAIN"


def build_review_comparison(
    local_results: Any,
    dify_review_result: Any,
) -> dict[str, Any]:
    """Align local and Dify review results by rule_id without changing either verdict."""
    local_items = _result_items(local_results)
    dify_items = _result_items(dify_review_result)
    local_by_rule = {_rule_id(item): item for item in local_items if _rule_id(item)}
    dify_by_rule = {_rule_id(item): item for item in dify_items if _rule_id(item)}
    rule_ids = sorted(set(local_by_rule) | set(dify_by_rule))

    items: list[dict[str, Any]] = []
    agreement_count = 0
    manual_review_count = 0
    for rule_id in rule_ids:
        local = local_by_rule.get(rule_id, {})
        dify = dify_by_rule.get(rule_id, {})
        local_status = _status(local)
        dify_status = _status(dify)
        agreement = bool(local_status and dify_status and local_status == dify_status)
        manual_review = (
            not agreement
            or local_status == UNCERTAIN
            or dify_status == UNCERTAIN
        )
        if agreement:
            agreement_count += 1
        if manual_review:
            manual_review_count += 1
        items.append(
            {
                "rule_id": rule_id,
                "item_name": _item_name(local, dify),
                "local_status": local_status,
                "dify_status": dify_status,
                "agreement": agreement,
                "manual_review": manual_review,
                "difference_reason": _difference_reason(
                    local_status,
                    dify_status,
                    agreement,
                    manual_review,
                ),
            }
        )

    return {
        "total_rules": len(items),
        "agreement_count": agreement_count,
        "disagreement_count": len(items) - agreement_count,
        "manual_review_count": manual_review_count,
        "results": items,
    }


def _result_items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        items = value
    elif isinstance(value, dict) and isinstance(value.get("results"), list):
        items = value["results"]
    elif isinstance(value, dict) and value.get("rule_id"):
        items = [value]
    else:
        items = []
    return [item for item in items if isinstance(item, dict)]


def _rule_id(item: dict[str, Any]) -> str:
    return str(item.get("rule_id") or "").strip()


def _status(item: dict[str, Any]) -> str | None:
    value = item.get("status")
    if value is None:
        return None
    return str(value).strip().upper() or None


def _item_name(local: dict[str, Any], dify: dict[str, Any]) -> str:
    return str(
        local.get("name")
        or local.get("item_name")
        or dify.get("name")
        or dify.get("item_name")
        or ""
    )


def _difference_reason(
    local_status: str | None,
    dify_status: str | None,
    agreement: bool,
    manual_review: bool,
) -> str:
    if local_status is None:
        return "缺少本地审查结果，需人工复核"
    if dify_status is None:
        return "缺少 Dify 审查结果，需人工复核"
    if not agreement:
        return f"本地为 {local_status}，Dify 为 {dify_status}，结论不一致"
    if manual_review:
        return "两套结果一致但为 UNCERTAIN，仍需人工复核"
    return "两套结果一致"
