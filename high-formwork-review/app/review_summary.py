"""统一智能预审汇总。"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

_SEVERITY_RANK = {"A-mandatory": 0, "B-required": 1, "C-recommended": 2}


def build_review_results(
    project_qualification: dict[str, Any],
    completeness_summary: Any,
    substantive_review: list[dict[str, Any]],
    *,
    comparison: dict[str, Any] | None = None,
    consistency_review: list[dict[str, Any]] | None = None,
    drawing_review: list[dict[str, Any]] | None = None,
    rule_engine: dict[str, Any] | None = None,
    semantic: dict[str, Any] | None = None,
    document_pages: list[dict[str, Any]] | None = None,
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
                    "item_key": f"completeness_review:{item.get('rule_id')}",
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
                    "item_key": f"substantive_review:{item.get('review_item_id')}",
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
                    "item_key": f"consistency_review:{item.get('review_item_id')}",
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
                    "item_key": f"drawing_review:{item.get('review_item_id')}",
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

    # 规则引擎/语义引擎需要人工确认的事项逐条入队（按强制等级排序）
    engine_items = []
    for source, payload in (("rule_engine", rule_engine), ("semantic_engine", semantic)):
        for r in (payload or {}).get("results", []):
            is_human_route = (
                source == "semantic_engine"
                and r.get("route") == "HUMAN_REQUIRED"
                and r.get("manual_review")
            )
            if r.get("status") != "VIOLATED" and not is_human_route:
                continue
            engine_items.append(
                {
                    "source": source,
                    "review_item_id": r.get("rule_id"),
                    "item_key": f"{source}:{r.get('rule_id')}",
                    "title": r.get("rule_name"),
                    "system_result": r.get("status"),
                    "reason": r.get("reason"),
                    "evidence": r.get("evidence", []),
                    "basis": [(r.get("code_ref") or {}).get("standard", "")],
                    "meta": {
                        "severity": r.get("severity"),
                        "module": r.get("module"),
                        "route": r.get("route"),
                    },
                }
            )
    engine_items.sort(
        key=lambda i: _SEVERITY_RANK.get((i.get("meta") or {}).get("severity"), 3)
    )

    # 体系专属规则待确认聚合一条
    pending_item = None
    pending_total = sum(
        (payload or {}).get("pending_confirmation", 0)
        for payload in (rule_engine, semantic)
    )
    if pending_total:
        pending_item = {
            "source": "engine_scope",
            "review_item_id": "PENDING-SYSTEM",
            "item_key": "engine_scope:PENDING-SYSTEM",
            "title": f"{pending_total} 条体系专属规则待确认支撑体系后执行",
            "system_result": "PENDING_CONFIRMATION",
            "reason": (
                f"确定性 {(rule_engine or {}).get('pending_confirmation', 0)} 条 / "
                f"语义 {(semantic or {}).get('pending_confirmation', 0)} 条"
            ),
            "evidence": [],
            "basis": [],
            "link": {"tab": "manual"},
        }

    # 解析风险页聚合一条
    doc_item = None
    risk_pages = [
        p.get("physical_page")
        for p in (document_pages or [])
        if p.get("requires_human_review")
    ]
    if risk_pages:
        doc_item = {
            "source": "document_parse",
            "review_item_id": "DOC-RISK-PAGES",
            "item_key": "document_parse:DOC-RISK-PAGES",
            "title": f"文档解析有 {len(risk_pages)} 页需人工复核",
            "system_result": "REVIEW",
            "reason": "部分解析/不可读/仅图片内容页需人工确认",
            "evidence": [],
            "basis": [],
            "link": {"tab": "document", "filter": "human-review"},
            "meta": {"pages": risk_pages},
        }

    ordered: list[dict[str, Any]] = []
    if project_qualification.get("requires_human_review"):
        qual_item = {
            "source": "project_qualification",
            "review_item_id": "PQ-01",
            "item_key": "project_qualification:PQ-01",
            "title": "工程识别",
            "system_result": "REVIEW",
            "reason": project_qualification.get("human_review_reason"),
            "evidence": [],
            "basis": [],
        }
        pending_confirmation = project_qualification.get("pending_confirmation")
        if pending_confirmation:
            qual_item["actionable"] = {
                "type": "confirm_support_system",
                "current": project_qualification.get("support_system"),
                "options": pending_confirmation.get("options", []),
            }
        ordered.append(qual_item)
    if pending_item:
        ordered.append(pending_item)
    ordered.extend(engine_items)
    ordered.extend(queue)
    if doc_item:
        ordered.append(doc_item)

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
            "rule_engine_pending_confirmation": (rule_engine or {}).get("pending_confirmation", 0),
        },
        "human_review_queue": ordered,
        "notice": "系统结果仅作为专项施工方案预审辅助，需由审查人员人工确认，不作为最终审查结论。",
    }


def _completeness_dict(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        return asdict(value)
    return value if isinstance(value, dict) else {}
