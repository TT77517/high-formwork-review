"""统一智能预审汇总。"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any


def build_review_results(
    project_qualification: dict[str, Any],
    completeness_summary: Any,
    substantive_review: list[dict[str, Any]],
    *,
    comparison: dict[str, Any] | None = None,
    consistency_review: list[dict[str, Any]] | None = None,
    drawing_review: list[dict[str, Any]] | None = None,
    rule_engine: dict[str, Any] | None = None,
) -> dict[str, Any]:
    completeness = _completeness_dict(completeness_summary)
    consistency_review = consistency_review or []
    drawing_review = drawing_review or []
    queue = []
    for item in completeness.get("results", []):
        if item.get("status") in {"MISSING", "UNCERTAIN"}:
            queue.append(
                {
                    "source": "completeness_review",
                    "review_item_id": item.get("rule_id"),
                    "title": item.get("name"),
                    "system_result": item.get("status"),
                    "reason": item.get("reason"),
                    "evidence": item.get("evidence", []),
                    "basis": [],
                }
            )
    for item in substantive_review:
        if item.get("status") in {"ISSUE", "REVIEW"}:
            queue.append(
                {
                    "source": "substantive_review",
                    "review_item_id": item.get("review_item_id"),
                    "title": item.get("title"),
                    "system_result": item.get("status"),
                    "reason": item.get("conclusion"),
                    "evidence": item.get("evidence", []),
                    "basis": item.get("basis", []),
                }
            )
    for item in consistency_review:
        if item.get("status") in {"ISSUE", "REVIEW", "UNCERTAIN"}:
            queue.append(
                {
                    "source": "consistency_review",
                    "review_item_id": item.get("review_item_id"),
                    "title": item.get("title"),
                    "system_result": item.get("status"),
                    "reason": item.get("conclusion"),
                    "evidence": [
                        *item.get("design_side", {}).get("evidence", []),
                        *item.get("calculation_side", {}).get("evidence", []),
                    ],
                    "basis": [],
                }
            )
    for item in drawing_review:
        if item.get("requires_human_review"):
            queue.append(
                {
                    "source": "drawing_review",
                    "review_item_id": item.get("review_item_id"),
                    "title": item.get("title"),
                    "system_result": item.get("status"),
                    "reason": item.get("conclusion"),
                    "evidence": [
                        *item.get("text_evidence", []),
                        *item.get("drawing_evidence", []),
                    ],
                    "basis": [],
                }
            )
    if project_qualification.get("requires_human_review"):
        queue.insert(
            0,
            {
                "source": "project_qualification",
                "review_item_id": "PQ-01",
                "title": "工程识别",
                "system_result": "REVIEW",
                "reason": project_qualification.get("human_review_reason"),
                "evidence": [],
                "basis": [],
            },
        )
    return {
        "project_qualification": project_qualification,
        "completeness_review": {
            "local_result": completeness,
            "dify_result": comparison,
        },
        "substantive_review": substantive_review,
        "consistency_review": consistency_review,
        "drawing_review": drawing_review,
        "rule_engine": rule_engine or {},
        "summary": {
            "completeness_total": completeness.get("total_rules", 0),
            "completeness_pass": completeness.get("pass_count", 0),
            "completeness_missing": completeness.get("missing_count", 0),
            "completeness_uncertain": completeness.get("uncertain_count", 0),
            "substantive_total": len(substantive_review),
            "substantive_pass": sum(item.get("status") == "PASS" for item in substantive_review),
            "substantive_issue": sum(item.get("status") == "ISSUE" for item in substantive_review),
            "substantive_review": sum(item.get("status") == "REVIEW" for item in substantive_review),
            "consistency_total": len(consistency_review),
            "consistency_pass": sum(item.get("status") == "PASS" for item in consistency_review),
            "consistency_issue": sum(item.get("status") == "ISSUE" for item in consistency_review),
            "consistency_review": sum(item.get("status") == "REVIEW" for item in consistency_review),
            "drawing_total": len(drawing_review),
            "drawing_review": sum(item.get("requires_human_review") for item in drawing_review),
            "rule_engine_total": (rule_engine or {}).get("total_rules", 0),
            "rule_engine_compliant": (rule_engine or {}).get("compliant", 0),
            "rule_engine_violated": (rule_engine or {}).get("violated", 0),
            "rule_engine_uncertain": (rule_engine or {}).get("uncertain", 0),
            "rule_engine_not_applicable": (rule_engine or {}).get("not_applicable", 0),
        },
        "human_review_queue": queue,
        "notice": "系统结果仅作为专项施工方案预审辅助，需由审查人员人工确认，不作为最终审查结论。",
    }


def _completeness_dict(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        return asdict(value)
    return value if isinstance(value, dict) else {}
