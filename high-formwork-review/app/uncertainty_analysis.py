"""无法判定结果归因分析。

把规则引擎/语义/计算/完整性中的 UNCERTAIN 拆成审查人能理解的
四类：真缺内容、缺参数、证据不足、规则过宽。
"""

from __future__ import annotations

from typing import Any

CATEGORY_ORDER = [
    "missing_content",
    "missing_parameter",
    "insufficient_evidence",
    "broad_rule",
]

CATEGORY_LABELS = {
    "missing_content": "真缺内容",
    "missing_parameter": "缺参数",
    "insufficient_evidence": "证据不足",
    "broad_rule": "规则过宽",
}

CATEGORY_ACTIONS = {
    "missing_content": "请审查人核对原 PDF；若方案确未编写对应内容，进入补充资料流程。",
    "missing_parameter": "优先在人工复核页填入或修正关键参数，然后触发重跑。",
    "insufficient_evidence": "打开证据页或 Agent 查证轨迹，确认是否需要补充 OCR/表格解析或人工判读。",
    "broad_rule": "规则描述或关键词不足，建议收窄关键词、补充阈值或改为人工复核规则。",
}

PARAM_LABELS = {
    "support_height": "搭设高度",
    "support_span": "搭设跨度",
    "step_height": "步距",
    "standard_step_height": "标准步距",
    "total_load": "施工总荷载",
    "concentrated_line_load": "集中线荷载",
    "head_jack_cantilever_length": "可调托撑悬臂长度",
    "head_jack_screw_exposed_length": "可调托撑丝杆外露长度",
    "sweeper_centerline_height_above_base_plate": "扫地杆高度",
    "vertical_spacing": "立杆纵距",
    "horizontal_spacing": "立杆横距",
    "framework_height": "架体高度",
    "height_to_width_ratio": "高宽比",
}


def build_uncertainty_analysis(
    *,
    project_facts: dict[str, Any] | None = None,
    completeness_results: list[dict[str, Any]] | None = None,
    rule_engine: dict[str, Any] | None = None,
    semantic: dict[str, Any] | None = None,
    calculation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """归并全部无法判定项，输出分类统计与代表样例。"""
    facts = (project_facts or {}).get("facts", {})
    items: list[dict[str, Any]] = []
    items.extend(
        _from_result_list("completeness_review", completeness_results or [], facts)
    )
    items.extend(_from_result_list("rule_engine", (rule_engine or {}).get("results", []), facts))
    items.extend(_from_result_list("semantic_engine", (semantic or {}).get("results", []), facts))
    items.extend(_from_result_list("calculation_engine", (calculation or {}).get("results", []), facts))

    categories = []
    for category in CATEGORY_ORDER:
        grouped = [item for item in items if item["category"] == category]
        categories.append({
            "category": category,
            "label": CATEGORY_LABELS[category],
            "count": len(grouped),
            "action": CATEGORY_ACTIONS[category],
            "items": grouped[:8],
        })

    return {
        "total_uncertain": len(items),
        "categories": categories,
        "items": items,
    }


def _from_result_list(
    source: str,
    results: list[dict[str, Any]],
    facts: dict[str, Any],
) -> list[dict[str, Any]]:
    out = []
    for result in results:
        if result.get("status") != "UNCERTAIN":
            continue
        category, category_reason, related_parameters = _classify(result, facts)
        out.append({
            "source": source,
            "rule_id": result.get("rule_id") or result.get("review_item_id"),
            "rule_name": result.get("rule_name") or result.get("name") or result.get("title"),
            "module": result.get("module"),
            "severity": result.get("severity"),
            "reason": result.get("reason") or result.get("conclusion") or "",
            "category": category,
            "category_label": CATEGORY_LABELS[category],
            "category_reason": category_reason,
            "related_parameters": related_parameters,
            "evidence_count": len(result.get("evidence") or []),
            "route": result.get("route"),
            "review_engine": result.get("review_engine") or result.get("source"),
        })
    return out


def _classify(
    result: dict[str, Any],
    facts: dict[str, Any],
) -> tuple[str, str, list[dict[str, Any]]]:
    reason = str(result.get("reason") or result.get("conclusion") or "")
    source = str(result.get("source") or result.get("review_engine") or "")
    evidence = result.get("evidence") or []
    raw_evidence = str(result.get("raw_evidence_snippet") or "")
    param_name = str(result.get("param_name") or "")
    related_parameters = _related_parameters(result, facts)

    if related_parameters or _has_any(reason, ("参数", "未提取", "未识别", "补值", "关键参数")):
        return (
            "missing_parameter",
            "规则判定依赖关键参数，但当前参数缺失、冲突或未被确认。",
            related_parameters,
        )
    if _has_any(reason, ("未配置关键词", "规则阈值格式异常", "规则无明确阈值", "无可评估子项")):
        return "broad_rule", "规则配置缺少可稳定执行的关键词、阈值或可评估子项。", []
    if not evidence and not raw_evidence and _has_any(reason, ("未找到", "未发现", "全文检查")):
        return "missing_content", "系统未召回到对应章节、正文或结构化证据。", []
    if result.get("route") == "AGENT_REQUIRED" and _has_any(reason, ("召回不足", "证据不足", "无法查证")):
        return "insufficient_evidence", "初始证据不足，已进入或需要进入 Agent 深挖证据。", []
    if evidence or raw_evidence or _has_any(reason, ("部分关键词", "内容可能不充分", "无法确认", "目录", "partial", "unreadable")):
        return "insufficient_evidence", "已有线索但证据链不足，暂不能支撑确定判定。", []
    if param_name:
        return (
            "missing_parameter",
            f"未取得规则所需参数：{param_name}。",
            _parameter_detail(param_name, facts),
        )
    return "missing_content", "未发现可支撑该规则判定的方案内容。", []


def _related_parameters(
    result: dict[str, Any],
    facts: dict[str, Any],
) -> list[dict[str, Any]]:
    params: list[dict[str, Any]] = []
    param_name = str(result.get("param_name") or "")
    if param_name:
        params.extend(_parameter_detail(param_name, facts))
    reason = str(result.get("reason") or "")
    text = f"{result.get('rule_name', '')} {result.get('check_content', '')} {reason}"
    for key, label in PARAM_LABELS.items():
        if label not in text and key not in text:
            continue
        fact = facts.get(key)
        if not isinstance(fact, dict):
            continue
        status = str(fact.get("status") or "")
        if status in {"missing", "uncertain", "conflict"} or fact.get("value") in (None, ""):
            detail = _fact_detail(key, fact)
            if detail not in params:
                params.append(detail)
    return params


def _parameter_detail(param_name: str, facts: dict[str, Any]) -> list[dict[str, Any]]:
    if param_name in facts and isinstance(facts[param_name], dict):
        return [_fact_detail(param_name, facts[param_name])]
    for key, label in PARAM_LABELS.items():
        if param_name in {key, label} and isinstance(facts.get(key), dict):
            return [_fact_detail(key, facts[key])]
    return [{"parameter": param_name, "label": PARAM_LABELS.get(param_name, param_name), "status": "missing"}]


def _fact_detail(key: str, fact: dict[str, Any]) -> dict[str, Any]:
    candidates = fact.get("candidates") or []
    return {
        "parameter": key,
        "label": PARAM_LABELS.get(key, key),
        "status": fact.get("status"),
        "value": fact.get("value"),
        "candidate_count": len(candidates),
    }


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)
