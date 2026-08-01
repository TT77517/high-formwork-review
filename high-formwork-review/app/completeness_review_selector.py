"""Select completeness rules that should be sent to Dify semantic review."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from .dify_config import DifyCompletenessMode


def select_rules_for_dify_review(
    local_results: list[Any],
    mode: DifyCompletenessMode,
    manually_selected_rule_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Return rule selection metadata; this function never calls Dify."""
    items = [_result_dict(item) for item in local_results]
    known_ids = [str(item.get("rule_id")) for item in items]
    manual_ids = list(dict.fromkeys(manually_selected_rule_ids or []))
    unknown_manual = [rule_id for rule_id in manual_ids if rule_id not in known_ids]
    if unknown_manual:
        raise ValueError("手动指定的规则不存在：" + "、".join(unknown_manual))

    selected: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    manual_set = set(manual_ids)
    for item in items:
        rule_id = str(item.get("rule_id"))
        if mode == "off":
            skipped.append(
                {"rule_id": rule_id, "reason": "Dify 完整性审查模式为 off"}
            )
            continue
        if mode == "full":
            selected.append(
                {"rule_id": rule_id, "reason": "Dify 完整性审查模式为 full"}
            )
            continue
        if rule_id in manual_set:
            selected.append({"rule_id": rule_id, "reason": "用户手动指定语义复核"})
            continue
        if bool(item.get("needs_semantic_review")):
            selected.append(
                {
                    "rule_id": rule_id,
                    "reason": str(item.get("semantic_review_reason") or "需要语义复核"),
                }
            )
        else:
            skipped.append(
                {
                    "rule_id": rule_id,
                    "reason": str(item.get("semantic_review_reason") or "无需语义复核"),
                }
            )

    return {
        "mode": mode,
        "total_rules": len(items),
        "selected_count": len(selected),
        "selected_rule_ids": [item["rule_id"] for item in selected],
        "selected_rules": selected,
        "skipped_rule_ids": [item["rule_id"] for item in skipped],
        "skipped_rules": skipped,
    }


def _result_dict(item: Any) -> dict[str, Any]:
    if is_dataclass(item):
        return asdict(item)
    if isinstance(item, dict):
        return item
    raise TypeError("local_results 必须包含 CompletenessResult 或字典")
