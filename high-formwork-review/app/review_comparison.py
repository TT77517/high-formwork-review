"""Compare local completeness results with the requested Dify results."""

from __future__ import annotations

from typing import Any


PASS = "PASS"
MISSING = "MISSING"
UNCERTAIN = "UNCERTAIN"
VALID_STATUSES = {PASS, MISSING, UNCERTAIN}

AGREEMENT = "AGREEMENT"
DISAGREEMENT = "DISAGREEMENT"
NOT_REQUESTED = "NOT_REQUESTED"
DIFY_FAILED = "DIFY_FAILED"
BOTH_UNCERTAIN = "BOTH_UNCERTAIN"


def build_review_comparison(
    local_results: Any,
    dify_review_result: Any = None,
    *,
    selection: dict[str, Any] | None = None,
    audit: dict[str, Any] | None = None,
    dify_error: dict[str, Any] | None = None,
    mode: str | None = None,
) -> dict[str, Any]:
    """Build per-rule comparison without changing either original verdict.

    ``selection`` and ``audit`` are optional for backwards compatibility with
    callers that previously compared only two result files.
    """
    local_items = _result_items(local_results)
    dify_items = _result_items(dify_review_result)
    local_by_rule = {_rule_id(item): item for item in local_items if _rule_id(item)}
    dify_by_rule = {_rule_id(item): item for item in dify_items if _rule_id(item)}
    rule_ids = _ordered_rule_ids(local_by_rule, dify_by_rule, selection, audit)
    requested_rule_ids = _requested_rule_ids(
        rule_ids,
        selection=selection,
        audit=audit,
        dify_by_rule=dify_by_rule,
        mode=mode,
    )
    failed_rule_ids = _failed_rule_ids(
        requested_rule_ids,
        dify_by_rule=dify_by_rule,
        audit=audit,
        dify_error=dify_error,
    )
    cache_rule_ids = _string_list((audit or {}).get("cache_hit_rule_ids"))
    api_rule_ids = _string_list((audit or {}).get("api_requested_rule_ids"))
    invalid_dify_ids = {
        rule_id
        for rule_id, item in dify_by_rule.items()
        if _status(item) not in VALID_STATUSES
    }
    failed_rule_ids.update(invalid_dify_ids & set(requested_rule_ids))

    items: list[dict[str, Any]] = []
    status_counts = {
        AGREEMENT: 0,
        DISAGREEMENT: 0,
        NOT_REQUESTED: 0,
        DIFY_FAILED: 0,
        BOTH_UNCERTAIN: 0,
    }
    for rule_id in rule_ids:
        local = local_by_rule.get(rule_id, {})
        dify = dify_by_rule.get(rule_id, {})
        local_status = _status(local)
        dify_status = _status(dify)
        requested = rule_id in requested_rule_ids
        comparison_status = _comparison_status(
            rule_id,
            requested=requested,
            local_status=local_status,
            dify_status=dify_status,
            failed_rule_ids=failed_rule_ids,
        )
        status_counts[comparison_status] += 1
        agreement = _legacy_agreement(comparison_status)
        manual_review = _manual_review(
            comparison_status,
            local=local,
            local_status=local_status,
            dify_status=dify_status,
        )
        source = _dify_result_source(
            rule_id,
            requested=requested,
            failed=rule_id in failed_rule_ids,
            has_result=rule_id in dify_by_rule,
            cache_rule_ids=cache_rule_ids,
            api_rule_ids=api_rule_ids,
        )
        item_warnings = _warnings(local, dify)
        if rule_id in failed_rule_ids and dify_error:
            item_warnings.append(
                {
                    "code": "DIFY_FAILED",
                    "message": str(dify_error.get("message") or "Dify 审查失败"),
                }
            )
        items.append(
            {
                "rule_id": rule_id,
                "rule_name": _item_name(local, dify),
                "item_name": _item_name(local, dify),
                "local_status": local_status,
                "dify_status": dify_status if rule_id in dify_by_rule else None,
                "comparison_status": comparison_status,
                "requested_to_dify": requested,
                "dify_result_source": source,
                "difference_reason": _difference_reason(
                    comparison_status,
                    local_status,
                    dify_status,
                ),
                "requires_human_review": manual_review,
                "local_reason": local.get("reason"),
                "dify_reason": dify.get("reason"),
                "local_evidence": local.get("evidence", []),
                "dify_evidence": dify.get("evidence", []),
                "warnings": item_warnings,
                # Backwards-compatible fields used by the first comparison UI.
                "agreement": agreement,
                "manual_review": manual_review,
            }
        )

    human_review_count = sum(
        1 for item in items if item["requires_human_review"]
    )
    return {
        "total_rules": len(items),
        "agreement_count": status_counts[AGREEMENT],
        "disagreement_count": status_counts[DISAGREEMENT],
        "not_requested_count": status_counts[NOT_REQUESTED],
        "dify_failed_count": status_counts[DIFY_FAILED],
        "both_uncertain_count": status_counts[BOTH_UNCERTAIN],
        "human_review_count": human_review_count,
        "manual_review_count": human_review_count,
        "status_counts": status_counts,
        "results": items,
    }


def _ordered_rule_ids(
    local_by_rule: dict[str, dict[str, Any]],
    dify_by_rule: dict[str, dict[str, Any]],
    selection: dict[str, Any] | None,
    audit: dict[str, Any] | None,
) -> list[str]:
    ids: list[str] = [*local_by_rule, *dify_by_rule]
    ids.extend(_string_list((selection or {}).get("selected_rule_ids")))
    ids.extend(_string_list((audit or {}).get("requested_rule_ids")))
    return list(dict.fromkeys(ids))


def _requested_rule_ids(
    rule_ids: list[str],
    *,
    selection: dict[str, Any] | None,
    audit: dict[str, Any] | None,
    dify_by_rule: dict[str, dict[str, Any]],
    mode: str | None,
) -> list[str]:
    if audit is not None and "requested_rule_ids" in audit:
        return list(dict.fromkeys(_string_list(audit.get("requested_rule_ids"))))
    effective_mode = str(mode or (selection or {}).get("mode") or "").strip().lower()
    if effective_mode == "off":
        return []
    if effective_mode == "on_demand":
        return list(
            dict.fromkeys(_string_list((selection or {}).get("selected_rule_ids")))
        )
    if effective_mode == "full":
        return list(rule_ids)
    # Legacy output directories had no selection/audit files. If a Dify result
    # exists, treat its returned rules as requested; otherwise it is local-only.
    if dify_by_rule:
        return list(dify_by_rule)
    return []


def _failed_rule_ids(
    requested_rule_ids: list[str],
    *,
    dify_by_rule: dict[str, dict[str, Any]],
    audit: dict[str, Any] | None,
    dify_error: dict[str, Any] | None,
) -> set[str]:
    requested = set(requested_rule_ids)
    failed = set(_string_list((audit or {}).get("failed_rule_ids"))) & requested
    error_failed = _string_list((dify_error or {}).get("failed_rule_ids"))
    failed.update(set(error_failed) & requested)
    # Every requested rule must have a valid Dify result.  A missing item is
    # therefore a failure even when the batch-level audit file is incomplete.
    failed.update(requested - set(dify_by_rule))
    return failed


def _comparison_status(
    rule_id: str,
    *,
    requested: bool,
    local_status: str | None,
    dify_status: str | None,
    failed_rule_ids: set[str],
) -> str:
    if not requested:
        return NOT_REQUESTED
    if rule_id in failed_rule_ids or dify_status not in VALID_STATUSES:
        return DIFY_FAILED
    if local_status == UNCERTAIN and dify_status == UNCERTAIN:
        return BOTH_UNCERTAIN
    if local_status == dify_status:
        return AGREEMENT
    return DISAGREEMENT


def _legacy_agreement(comparison_status: str) -> bool | None:
    if comparison_status in {NOT_REQUESTED, DIFY_FAILED}:
        return None
    return comparison_status in {AGREEMENT, BOTH_UNCERTAIN}


def _manual_review(
    comparison_status: str,
    *,
    local: dict[str, Any],
    local_status: str | None,
    dify_status: str | None,
) -> bool:
    if comparison_status in {DISAGREEMENT, DIFY_FAILED, BOTH_UNCERTAIN}:
        return True
    if comparison_status == NOT_REQUESTED:
        confidence = local.get("confidence")
        return bool(
            local.get("requires_human_review")
            or local.get("needs_semantic_review")
            or local_status == UNCERTAIN
            or not isinstance(confidence, (int, float))
            or confidence < 0.8
        )
    return bool(
        local.get("requires_human_review")
        or local_status == UNCERTAIN
        or dify_status == UNCERTAIN
    )


def _dify_result_source(
    rule_id: str,
    *,
    requested: bool,
    failed: bool,
    has_result: bool,
    cache_rule_ids: list[str],
    api_rule_ids: list[str],
) -> str:
    if not requested:
        return "not_requested"
    if failed or not has_result:
        return "failed"
    if rule_id in cache_rule_ids:
        return "cache"
    if rule_id in api_rule_ids or has_result:
        return "api"
    return "failed"


def _warnings(local: dict[str, Any], dify: dict[str, Any]) -> list[Any]:
    values: list[Any] = []
    for item in (local, dify):
        warning = item.get("warnings")
        if isinstance(warning, list):
            values.extend(warning)
    return values


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


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


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
    comparison_status: str,
    local_status: str | None,
    dify_status: str | None,
) -> str:
    if comparison_status == NOT_REQUESTED:
        return "该规则未请求 Dify，保留本地结果"
    if comparison_status == DIFY_FAILED:
        return "该规则已请求 Dify，但 Dify 结果失败、缺失或结构无效"
    if comparison_status == BOTH_UNCERTAIN:
        return "本地与 Dify 均为 UNCERTAIN，需人工复核"
    if comparison_status == DISAGREEMENT:
        return f"本地为 {local_status}，Dify 为 {dify_status}，结论不一致"
    return "本地与 Dify 结果一致"
