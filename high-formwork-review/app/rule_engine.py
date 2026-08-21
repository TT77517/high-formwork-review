"""v4.0 规则库确定性规则引擎。

加载 config/rule_library_v4/ 下的 6 个模块 JSON，
对 check_type=deterministic 且有 threshold 的规则，
从 project_facts（已有参数提取管线）中获取参数值并执行阈值比对。
project_facts 覆盖 parameter_definitions.py 中定义的全部 30 个参数。
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from .models import MinerUDocument

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RULE_LIBRARY_DIR = PROJECT_ROOT / "config" / "rule_library_v4"

MODULE_NAMES: dict[str, str] = {
    "01_procedure_compliance": "程序合规性审查",
    "02_load_values": "荷载取值审查",
    "03_structural_calculation": "结构计算审查",
    "04_construction_requirements": "构造要求审查",
    "05_material_requirements": "材料要求审查",
    "06_safety_measures": "安全措施审查",
}

MODULE_FILES = [
    "module_01_procedure_compliance.json",
    "module_02_load_values.json",
    "module_03_structural_calculation.json",
    "module_04_construction_requirements.json",
    "module_05_material_requirements.json",
    "module_06_safety_measures.json",
]

# 规则 threshold.param → project_facts parameter_id 的映射
PARAM_TO_FACTS: dict[str, str] = {
    "搭设高度": "support_height",
    "搭设跨度": "support_span",
    "施工总荷载": "total_load",
    "集中线荷载": "concentrated_line_load",
    "步距": "standard_step_height",
    "立杆纵距": "vertical_spacing",
    "立杆横距": "horizontal_spacing",
    "架体高度": "framework_height",
    "自由端长度": "free_end_length",
    "底座螺杆外伸长度": "base_jack_screw_extension",
    "顶层水平杆至托撑顶面距离": "top_level_to_jack_distance",
    "高宽比": "height_to_width_ratio",
    "面板厚度": "panel_thickness",
    "钢板厚度": "steel_plate_thickness",
    "实测壁厚/公称壁厚": "wall_thickness_ratio",
    "分层厚度": "layer_thickness",
    "浇筑速度": "pouring_speed",
    "监测点间距": "monitoring_point_spacing",
    "风力等级": "wind_force_level",
    "专家数量": "expert_count",
    "可调托撑悬臂长度": "head_jack_cantilever_length",
    "可调托撑丝杆外露长度": "head_jack_screw_exposed_length",
    "扫地杆中心线距可调底座底板高度": "sweeper_centerline_height_above_base_plate",
    "施工人员及设备荷载标准值": "personnel_equipment_load_standard",
    # List-threshold 子参数
    "螺杆外伸长度": "head_jack_screw_exposed_length",
    "调节螺杆伸出长度": "top_level_to_jack_distance",
    "悬臂长度": "head_jack_cantilever_length",
    "插入长度": "head_jack_insertion_length",
}


def load_rule_library() -> list[dict[str, Any]]:
    """加载 v4.0 规则库全部 164 条规则。"""
    rules: list[dict[str, Any]] = []
    for filename in MODULE_FILES:
        path = RULE_LIBRARY_DIR / filename
        if not path.is_file():
            continue
        rules.extend(json.loads(path.read_text(encoding="utf-8")))
    return rules


def load_deterministic_rules() -> list[dict[str, Any]]:
    """返回有 threshold 的确定性规则（含 dict 和 list 类型 threshold）。"""
    return [
        rule for rule in load_rule_library()
        if rule.get("check_type") == "deterministic" and rule.get("threshold")
    ]


def _compare(value: float, operator: str, threshold: float) -> bool:
    """True 表示合规。"""
    if operator == ">=":
        return value >= threshold
    if operator == "<=":
        return value <= threshold
    if operator == ">":
        return value > threshold
    if operator == "<":
        return value < threshold
    if operator == "==":
        return abs(value - threshold) < 1e-9
    return False


def _format_value(value: float, unit: str) -> str:
    if value == int(value):
        return f"{int(value)}{unit}"
    return f"{value}{unit}"


def _get_fact_value(facts: dict[str, Any], param_name: str) -> tuple[float | None, list[dict[str, Any]], str]:
    """从 project_facts 中获取参数值和证据。"""
    fact_id = PARAM_TO_FACTS.get(param_name, "")
    if not fact_id or fact_id not in facts:
        return None, [], ""
    fact = facts[fact_id]
    if fact.get("value") is not None:
        evidence = [
            {
                "page": ev.get("page") or ev.get("physical_page"),
                "section": ev.get("section"),
                "block_id": ev.get("block_id"),
                "quote": ev.get("quote"),
            }
            for ev in fact.get("evidence", [])
        ]
        return float(fact["value"]), evidence[:5], fact.get("status", "")
    # 降级：如果有 candidates 也尝试取值
    candidates = fact.get("candidates", [])
    values = []
    for c in candidates:
        v = c.get("value")
        if v is not None:
            try:
                values.append(float(v))
            except (ValueError, TypeError):
                continue
    if values:
        evidence = [
            {
                "page": (c.get("evidence") or {}).get("physical_page"),
                "section": " / ".join((c.get("evidence") or {}).get("section_path") or []),
                "block_id": (c.get("evidence") or {}).get("block_id"),
                "quote": (c.get("evidence") or {}).get("text"),
            }
            for c in candidates if c.get("value") is not None
        ]
        return max(values), evidence[:5], "extracted"
    return None, [], fact.get("status", "uncertain")


def _extract_from_document_fallback(
    document: MinerUDocument,
    keywords: list[str],
) -> tuple[float | None, list[dict[str, Any]]]:
    """当 project_facts 无值时，从文档全文做关键词+数值正则提取兜底。"""
    if not keywords:
        return None, []
    results: list[dict[str, Any]] = []
    for page in document.pages:
        for block in page.blocks:
            text = block.text or ""
            if not text.strip():
                continue
            norm = unicodedata.normalize("NFKC", text)
            for kw in keywords:
                if kw not in norm:
                    continue
                # 关键词后找数值
                pattern = re.compile(
                    rf"{re.escape(kw)}[^0-9\-—~～]*?"
                    r"(\d+\.?\d*)\s*"
                    r"(kN/m[²2³3]?|kN/m|kPa|mm|cm|m\b|米|毫米|厘米|MPa|N/mm[²2]|kN|级|人)?",
                    re.IGNORECASE,
                )
                for m in pattern.finditer(norm):
                    try:
                        val = float(m.group(1))
                    except ValueError:
                        continue
                    results.append({
                        "value": val,
                        "page": page.physical_page,
                        "block_id": block.block_id,
                        "section": "",
                        "quote": m.group(0).strip(),
                    })
    if not results:
        return None, []
    # 取最不利值
    max_val = max(r["value"] for r in results)
    evidence = [
        {
            "page": r["page"],
            "section": r["section"],
            "block_id": r["block_id"],
            "quote": r["quote"],
        }
        for r in results[:5]
    ]
    return max_val, evidence


def run_rule_engine(
    document: MinerUDocument,
    project_facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """执行确定性规则引擎。

    优先从 project_facts 获取参数值（精度高），
    降级用文档全文正则提取（兜底）。
    """
    facts = (project_facts or {}).get("facts", {})
    rules = load_deterministic_rules()
    results: list[dict[str, Any]] = []

    for rule in rules:
        result = _evaluate_rule(rule, document, facts)
        results.append(result)

    compliant = sum(1 for r in results if r["status"] == "COMPLIANT")
    violated = sum(1 for r in results if r["status"] == "VIOLATED")
    uncertain = sum(1 for r in results if r["status"] == "UNCERTAIN")
    not_app = sum(1 for r in results if r["status"] == "NOT_APPLICABLE")
    pending = sum(1 for r in results if r["status"] == "PENDING_CONFIRMATION")

    return {
        "version": "4.0.0",
        "total_rules": len(rules),
        "evaluated": len(results),
        "compliant": compliant,
        "violated": violated,
        "uncertain": uncertain,
        "not_applicable": not_app,
        "pending_confirmation": pending,
        "results": results,
    }


TYPE_MAP = {"pankou": "disk_lock", "koujian": "coupler", "wankou": "other"}


def system_applicability_status(
    applicable_types: list[str], system_value: Any
) -> str | None:
    """体系专属规则的适用性门禁（三引擎共享）。

    适用返回 None；支撑体系未识别返回 PENDING_CONFIRMATION
    （待人工确认后重跑）；已识别但不匹配返回 NOT_APPLICABLE。
    """
    if "universal" in applicable_types:
        return None
    if system_value in (None, "", "unknown"):
        return "PENDING_CONFIRMATION"
    if any(TYPE_MAP.get(at) == system_value for at in applicable_types):
        return None
    return "NOT_APPLICABLE"


def _evaluate_rule(
    rule: dict[str, Any],
    document: MinerUDocument,
    facts: dict[str, Any],
) -> dict[str, Any]:
    """评估单条规则，支持 dict 和 list 类型 threshold。"""
    threshold = rule.get("threshold")
    keywords = rule.get("check_logic", {}).get("extraction_keywords", [])
    applicable_types = rule.get("applicable_types", ["universal"])

    # 适用性检查
    applicability = system_applicability_status(
        applicable_types, facts.get("support_system", {}).get("value", "unknown")
    )
    if applicability == "PENDING_CONFIRMATION":
        return _build_result(
            rule, "PENDING_CONFIRMATION", "", None,
            [], "支撑体系未识别，该规则仅适用于特定支撑体系，待人工确认后重跑",
        )
    if applicability == "NOT_APPLICABLE":
        return _build_result(rule, "NOT_APPLICABLE", "", None,
                             [], "支架类型不适用")

    # list 类型 threshold（如 4.12 可调托撑多限值、4.15 立杆间距多参数）
    if isinstance(threshold, list):
        return _evaluate_multi_threshold(rule, document, facts, threshold, keywords)

    # dict 类型 threshold（常规）
    if not isinstance(threshold, dict):
        return _build_result(rule, "UNCERTAIN", "", None,
                             [], "规则阈值格式异常")

    param_name = threshold.get("param", "")
    operator = threshold.get("operator", "")
    threshold_value = threshold.get("value")
    threshold_unit = threshold.get("unit", "")

    if threshold_value is None:
        return _build_result(rule, "UNCERTAIN", param_name, None,
                             [], "规则无明确阈值")

    # 1. 优先从 project_facts 获取
    actual_value, evidence, fact_status = _get_fact_value(facts, param_name)
    source = "project_facts" if actual_value is not None else ""

    # 2. 降级：文档全文正则
    if actual_value is None and keywords:
        actual_value, evidence = _extract_from_document_fallback(document, keywords)
        source = "document_fallback" if actual_value is not None else ""

    if actual_value is None:
        return _build_result(rule, "UNCERTAIN", param_name, None,
                             evidence, f"未从方案中提取到「{param_name}」参数")

    # 比对
    is_compliant = _compare(actual_value, operator, float(threshold_value))
    if is_compliant:
        status = "COMPLIANT"
        reason = f"{param_name}={_format_value(actual_value, threshold_unit)}，满足{operator}{threshold_value}{threshold_unit}要求"
    else:
        status = "VIOLATED"
        reason = f"{param_name}={_format_value(actual_value, threshold_unit)}，不满足{operator}{threshold_value}{threshold_unit}要求"

    return _build_result(rule, status, param_name, actual_value,
                         evidence, reason, source)


def _evaluate_multi_threshold(
    rule: dict[str, Any],
    document: MinerUDocument,
    facts: dict[str, Any],
    threshold_list: list[dict[str, Any]],
    keywords: list[str],
) -> dict[str, Any]:
    """评估多阈值规则（如 4.12 有6个子限值，4.15 有3个参数）。

    对每个子项分别评估，汇总取最严重状态。
    """
    sub_results: list[dict[str, Any]] = []
    all_evidence: list[dict[str, Any]] = []
    worst_status = "COMPLIANT"

    for sub_th in threshold_list:
        if not isinstance(sub_th, dict):
            continue
        param_name = sub_th.get("param", "")
        operator = sub_th.get("operator", "")
        sub_value = sub_th.get("value")
        sub_unit = sub_th.get("unit", "")
        sub_applicable = sub_th.get("applicable", "")

        if sub_value is None:
            continue

        actual_value, evidence, _ = _get_fact_value(facts, param_name)
        if actual_value is None and keywords:
            actual_value, evidence = _extract_from_document_fallback(document, keywords)

        if actual_value is None:
            sub_results.append({
                "param": param_name,
                "applicable": sub_applicable,
                "threshold": f"{operator} {sub_value}{sub_unit}",
                "actual": "未提取到",
                "status": "UNCERTAIN",
            })
            if worst_status != "VIOLATED":
                worst_status = "UNCERTAIN"
            continue

        is_ok = _compare(actual_value, operator, float(sub_value))
        sub_status = "COMPLIANT" if is_ok else "VIOLATED"
        all_evidence.extend(evidence)

        sub_results.append({
            "param": param_name,
            "applicable": sub_applicable,
            "threshold": f"{operator} {sub_value}{sub_unit}",
            "actual": _format_value(actual_value, sub_unit),
            "status": sub_status,
        })
        if sub_status == "VIOLATED":
            worst_status = "VIOLATED"

    reason_parts = [f"{s['param']}={s['actual']}({s['status']})" for s in sub_results]
    reason = "；".join(reason_parts) if reason_parts else "无可评估子项"

    result = _build_result(rule, worst_status, "", None,
                           all_evidence[:5], reason, "project_facts")
    result["sub_results"] = sub_results
    return result


def _build_result(
    rule: dict[str, Any],
    status: str,
    param_name: str,
    actual_value: float | None,
    evidence: list[dict[str, Any]],
    reason: str,
    source: str = "",
) -> dict[str, Any]:
    threshold = rule.get("threshold") or {}
    if not isinstance(threshold, dict):
        threshold = {}
    code_ref = rule.get("code_ref") or {}
    return {
        "rule_id": rule.get("rule_id", ""),
        "rule_name": rule.get("rule_name", ""),
        "module": rule.get("module", ""),
        "module_name": MODULE_NAMES.get(rule.get("module", ""), ""),
        "check_type": rule.get("check_type", ""),
        "severity": rule.get("severity", ""),
        "risk_level": rule.get("risk_level", ""),
        "status": status,
        "param_name": param_name,
        "actual_value": actual_value,
        "threshold": threshold,
        "reason": reason,
        "code_ref": {
            "standard": code_ref.get("standard", ""),
            "original_text": code_ref.get("original_text", ""),
        },
        "remedy_suggestion": rule.get("remedy_suggestion", ""),
        "typical_violation": rule.get("typical_violation", ""),
        "manual_review": rule.get("manual_review", False),
        "evidence": evidence,
        "source": source,
    }


def run_rule_engine_safe(
    document: MinerUDocument,
    project_facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """安全执行规则引擎，失败时返回空结果。"""
    try:
        return run_rule_engine(document, project_facts)
    except Exception as exc:
        return {
            "version": "4.0.0",
            "total_rules": 0,
            "evaluated": 0,
            "compliant": 0,
            "violated": 0,
            "uncertain": 0,
            "not_applicable": 0,
            "pending_confirmation": 0,
            "results": [],
            "error": str(exc),
        }
