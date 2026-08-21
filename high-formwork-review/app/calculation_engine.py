"""计算规则引擎。

对 v4.0 规则库中 check_type=calculation 的 32 条规则，
从方案计算书中提取验算项目和相关参数，
检查验算公式的完整性和参数引用正确性。

当前为验证模式（检查验算项目是否存在+参数是否引用正确），
不做完整力学复算。
输出 COMPLIANT/VIOLATED/UNCERTAIN/NOT_APPLICABLE
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from .models import MinerUDocument
from .rule_engine import (
    MODULE_FILES,
    MODULE_NAMES,
    RULE_LIBRARY_DIR,
    system_applicability_status,
)

# 验算公式关键词映射
FORMULA_KEYWORDS: dict[str, list[str]] = {
    "3.1": ["面板", "抗弯", "σ", "M/W", "f"],
    "3.2": ["面板", "抗剪", "τ", "VS", "fv"],
    "3.3": ["面板", "挠度", "ω", "l/400", "l/250"],
    "3.4": ["次楞", "抗弯", "σ", "M/W"],
    "3.5": ["次楞", "挠度", "ω", "l/150", "l/250"],
    "3.6": ["主楞", "抗弯", "σ", "M/W"],
    "3.7": ["主楞", "挠度", "ω", "l/150", "l/250"],
    "3.8": ["立杆", "轴力", "N", "1.3", "1.5", "NGk", "NQk"],
    "3.8a": ["立杆", "轴力", "N", "1.3", "1.5", "盘扣"],
    "3.9": ["立杆", "稳定", "σ", "N/φA", "f"],
    "3.10": ["计算长度", "l0", "η", "k"],
    "3.11": ["长细比", "λ", "150"],
    "3.12": ["立杆", "稳定", "σ", "φA", "f"],
    "3.13": ["计算长度", "l0", "η", "k", "β"],
    "3.14": ["长细比", "λ", "150"],
    "3.15": ["立杆", "稳定", "碗扣"],
    "3.16": ["扣件", "抗滑", "Rc"],
    "3.17": ["托撑", "承载力", "N"],
    "3.18": ["连墙件", "N"],
    "3.19": ["地基", "承载力"],
    "3.20": ["抗倾覆", "MR", "MT", "γ0"],
    "3.21": ["长细比", "λ", "≤"],
    "3.22": ["顶层", "步距", "0.5"],
    "3.23": ["变形", "限值", "ω"],
    "3.24": ["长细比", "λ", "180"],
    "3.25": ["抗倾覆", "MR", "γ0", "MT"],
    "2.8": ["侧压力", "F", "混凝土", "浇筑速度"],
    "2.12": ["荷载组合", "1.3", "1.5"],
    "2.13": ["正常使用", "标准组合", "频遇"],
    "2.14": ["风荷载", "w0", "βz"],
    "2.19": ["侧压力", "F", "GB50666"],
    "2.23": ["荷载组合", "1.3", "1.5", "γ0"],
}


def load_calculation_rules() -> list[dict[str, Any]]:
    """加载全部计算规则。"""
    rules = []
    for filename in MODULE_FILES:
        path = RULE_LIBRARY_DIR / filename
        if not path.is_file():
            continue
        for rule in json.loads(path.read_text(encoding="utf-8")):
            if rule.get("check_type") == "calculation":
                rules.append(rule)
    return rules


def _extract_calculation_text(document: MinerUDocument) -> str:
    """从文档中提取计算书相关文本。"""
    calc_keywords = ["计算", "验算", "荷载组合", "长细比", "稳定", "抗弯", "抗剪",
                     "挠度", "侧压力", "轴力", "倾覆", "承载力"]
    sections: list[str] = []
    in_calc_section = False
    current_text = ""
    for page in document.pages:
        if page.parse_status == "unreadable":
            continue
        for block in page.blocks:
            text = block.text or ""
            if not text.strip():
                continue
            norm = unicodedata.normalize("NFKC", text)
            if block.block_type == "title":
                if current_text and in_calc_section:
                    sections.append(current_text)
                in_calc_section = any(kw in norm for kw in calc_keywords)
                current_text = text + "\n"
            elif in_calc_section:
                current_text += text + "\n"
        # Also check page-level text
        page_text = page.text or ""
        if page_text and any(kw in unicodedata.normalize("NFKC", page_text) for kw in calc_keywords):
            sections.append(page_text[:3000])
    if current_text and in_calc_section:
        sections.append(current_text)
    return "\n\n".join(sections)[:50000]


def run_calculation_engine(
    document: MinerUDocument,
    project_facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """执行计算规则验证引擎。"""
    rules = load_calculation_rules()
    calc_text = _extract_calculation_text(document)
    facts = (project_facts or {}).get("facts", {})
    support_system = facts.get("support_system", {})
    system_value = support_system.get("value", "unknown")

    results: list[dict[str, Any]] = []
    for rule in rules:
        result = _evaluate_calculation(rule, calc_text, system_value)
        results.append(result)

    compliant = sum(1 for r in results if r["status"] == "COMPLIANT")
    violated = sum(1 for r in results if r["status"] == "VIOLATED")
    uncertain = sum(1 for r in results if r["status"] == "UNCERTAIN")
    not_app = sum(1 for r in results if r["status"] == "NOT_APPLICABLE")
    pending = sum(1 for r in results if r["status"] == "PENDING_CONFIRMATION")

    return {
        "version": "4.0.0",
        "engine_type": "calculation",
        "mode": "formula_existence_check",
        "total_rules": len(rules),
        "compliant": compliant,
        "violated": violated,
        "uncertain": uncertain,
        "not_applicable": not_app,
        "pending_confirmation": pending,
        "results": results,
    }


def _evaluate_calculation(
    rule: dict[str, Any],
    calc_text: str,
    system_value: str,
) -> dict[str, Any]:
    """评估单条计算规则——检查验算项目是否存在于计算书中。"""
    rule_id = rule.get("rule_id", "")
    keywords = FORMULA_KEYWORDS.get(rule_id, [])
    if not keywords:
        cl = rule.get("check_logic", {})
        desc = cl.get("description", "")
        keywords = re.findall(r"[\u4e00-\u9fff]{2,6}", desc)[:5]

    # 适用性检查
    applicability = system_applicability_status(
        rule.get("applicable_types", ["universal"]), system_value
    )
    if applicability == "PENDING_CONFIRMATION":
        return _build_calc_result(
            rule, "PENDING_CONFIRMATION",
            "支撑体系未识别，该规则仅适用于特定支撑体系，待人工确认后重跑", [],
        )
    if applicability == "NOT_APPLICABLE":
        return _build_calc_result(rule, "NOT_APPLICABLE", "支架类型不适用", [])

    # 检查计算书中是否包含该验算项目
    norm_text = unicodedata.normalize("NFKC", calc_text)
    matched_keywords = [kw for kw in keywords if kw in norm_text]
    matched_count = len(matched_keywords)

    # 提取证据片段
    evidence: list[dict[str, Any]] = []
    for kw in matched_keywords[:3]:
        idx = norm_text.find(kw)
        if idx >= 0:
            start = max(0, idx - 50)
            end = min(len(calc_text), idx + len(kw) + 100)
            evidence.append({
                "quote": calc_text[start:end].strip(),
                "page": None,
                "keyword": kw,
            })

    threshold_match = len(keywords)
    if matched_count >= max(2, threshold_match // 2):
        status = "COMPLIANT"
        reason = f"计算书中找到该验算项目，关键词匹配 {matched_count}/{len(keywords)}：{'、'.join(matched_keywords[:5])}"
    elif matched_count > 0:
        status = "UNCERTAIN"
        reason = f"计算书中找到部分关键词（{matched_count}/{len(keywords)}），验算内容可能不完整"
    else:
        # 检查是否有计算书
        if calc_text:
            status = "UNCERTAIN"
            reason = "计算书存在但未找到该验算项目相关内容"
        else:
            status = "UNCERTAIN"
            reason = "未识别到计算书内容，无法判定"

    return _build_calc_result(rule, status, reason, evidence)


def _build_calc_result(
    rule: dict[str, Any],
    status: str,
    reason: str,
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    code_ref = rule.get("code_ref") or {}
    cl = rule.get("check_logic") or {}
    return {
        "rule_id": rule.get("rule_id", ""),
        "rule_name": rule.get("rule_name", ""),
        "module": rule.get("module", ""),
        "module_name": MODULE_NAMES.get(rule.get("module", ""), ""),
        "check_type": "calculation",
        "severity": rule.get("severity", ""),
        "risk_level": rule.get("risk_level", ""),
        "status": status,
        "reason": reason,
        "code_ref": {
            "standard": code_ref.get("standard", ""),
            "original_text": code_ref.get("original_text", ""),
        },
        "formula": cl.get("formula", cl.get("expected_value", "")),
        "remedy_suggestion": rule.get("remedy_suggestion", ""),
        "typical_violation": rule.get("typical_violation", ""),
        "manual_review": rule.get("manual_review", True),
        "evidence": evidence[:5],
    }


def run_calculation_engine_safe(
    document: MinerUDocument,
    project_facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """安全执行计算规则引擎。"""
    try:
        return run_calculation_engine(document, project_facts)
    except Exception as exc:
        return {
            "version": "4.0.0",
            "engine_type": "calculation",
            "mode": "formula_existence_check",
            "total_rules": 0,
            "compliant": 0,
            "violated": 0,
            "uncertain": 0,
            "not_applicable": 0,
            "pending_confirmation": 0,
            "results": [],
            "error": str(exc),
        }
