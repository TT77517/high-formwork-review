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

from .condition_evaluator import evaluate_applicability_conditions
from .calculation_rechecker import recheck_calculation
from .models import MinerUDocument
from .rule_engine import (
    MODULE_FILES,
    MODULE_NAMES,
    RULE_LIBRARY_DIR,
    system_applicability_status,
)
from .services.calculation_agent import (
    calculation_agent_route,
    should_run_calculation_agent,
    trace_calculation_evidence,
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
    "3.8": ["立杆", "轴力", "N", "1.2", "1.4", "NGk", "NQk"],
    "3.8a": ["立杆", "轴力", "N", "1.3", "1.5", "盘扣"],
    "3.9": ["立杆", "稳定", "σ", "N/φA", "f"],
    "3.10": ["计算长度", "l0", "η", "k"],
    "3.11": ["长细比", "λ", "210"],
    "3.26": ["计算长度", "l0", "k", "μ", "1.155"],
    "3.27": ["立杆", "稳定", "N/φA", "Mw/W", "205"],
    "3.12": ["立杆", "稳定", "σ", "φA", "f"],
    "3.13": ["计算长度", "l0", "η", "k", "β"],
    "3.14": ["长细比", "λ", "150"],
    "3.15": ["立杆", "稳定", "碗扣"],
    "3.16": ["扣件", "抗滑", "Rc"],
    "3.17": ["托撑", "承载力", "N"],
    "3.17p": ["盘扣", "托撑", "承载力", "100", "140"],
    "3.18": ["连墙件", "N"],
    "3.19": ["地基", "承载力"],
    "3.20": ["盘扣", "抗倾覆", "MR", "MT", "γ0"],
    "3.21": ["长细比", "λ", "≤"],
    "3.22": ["顶层", "步距", "0.5"],
    "3.23": ["变形", "限值", "ω"],
    "3.24": ["长细比", "λ", "180"],
    "3.25": ["抗倾覆", "MR", "γ0", "MT"],
    "2.8": ["侧压力", "F", "0.22", "β1", "β2", "浇筑速度"],
    "2.12": ["荷载组合", "1.3", "1.5"],
    "2.13": ["正常使用", "标准组合", "频遇"],
    "2.14": ["风荷载", "w0", "βz"],
    "2.19": ["侧压力", "F", "0.28", "γc", "t0", "β"],
    "2.23": ["荷载组合", "1.3", "1.5", "γ0"],
}

CALC_SECTION_TITLE_KEYWORDS = (
    "计算书",
    "设计计算",
    "计算说明",
    "验算书",
    "计算复核",
    "模板支架计算",
    "支撑架计算",
    "高支模计算",
    "结构计算",
    "荷载计算",
    "立杆稳定性计算",
)

NON_CALC_SECTION_TITLE_KEYWORDS = (
    "编制依据",
    "工程概况",
    "施工部署",
    "施工准备",
    "施工方法",
    "构造措施",
    "搭设要求",
    "检查验收",
    "安全保证",
    "应急预案",
    "监测措施",
    "文明施工",
)

FORMULA_SIGNAL_KEYWORDS = (
    "σ",
    "τ",
    "λ",
    "φ",
    "≤",
    ">=",
    "<=",
    "kN",
    "N/mm",
    "Mmax",
    "Nmax",
    "l0",
    "M/W",
    "φA",
    "Mo",
    "Mr",
    "γ0",
)


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


def _extract_calculation_segments(
    document: MinerUDocument,
) -> list[dict[str, Any]]:
    """从文档中按 block 收集计算书相关文本段（带 block 定位，供证据回溯图片/页码）。

    计算关键词会出现在施工方法、构造措施和规范依据中；这些内容只能说明方案提到
    过某个概念，不能作为计算书验算证据。这里以强计算书标题作为主入口，并在标题
    切换到明显非计算章节时退出，减少普通正文被误召回为公式证据。
    """
    calc_keywords = ["计算", "验算", "荷载组合", "长细比", "稳定", "抗弯", "抗剪",
                     "挠度", "侧压力", "轴力", "倾覆", "承载力"]
    segments: list[dict[str, Any]] = []
    in_calc_section = False
    for page in document.pages:
        if page.parse_status == "unreadable":
            continue
        for block in page.blocks:
            text = block.text or ""
            if not text.strip():
                continue
            norm = unicodedata.normalize("NFKC", text)
            if block.block_type == "title":
                if _is_calculation_section_title(norm):
                    in_calc_section = True
                elif _is_non_calculation_section_title(norm):
                    in_calc_section = False
            score = _calculation_segment_score(norm, block.block_type, in_calc_section)
            if score > 0:
                segments.append({
                    "text": text,
                    "block_id": block.block_id,
                    "block_type": block.block_type,
                    "physical_page": page.physical_page,
                    "calculation_score": score,
                    "in_calculation_section": in_calc_section,
                })
        # Also check page-level text
        page_text = page.text or ""
        page_norm = unicodedata.normalize("NFKC", page_text)
        page_score = _calculation_segment_score(page_norm, "page", in_calc_section)
        if page_text and page_score >= 4 and any(kw in page_norm for kw in calc_keywords):
            segments.append({
                "text": page_text[:3000],
                "block_id": None,
                "block_type": "page",
                "physical_page": page.physical_page,
                "calculation_score": page_score,
                "in_calculation_section": in_calc_section,
            })
    return segments


def _is_calculation_section_title(text: str) -> bool:
    if any(keyword in text for keyword in CALC_SECTION_TITLE_KEYWORDS):
        return True
    if "计算" in text and any(keyword in text for keyword in ("模板", "支架", "立杆", "荷载", "验算")):
        return True
    return False


def _is_non_calculation_section_title(text: str) -> bool:
    if _is_calculation_section_title(text):
        return False
    return any(keyword in text for keyword in NON_CALC_SECTION_TITLE_KEYWORDS)


def _calculation_segment_score(text: str, block_type: str, in_calc_section: bool) -> int:
    score = 0
    if in_calc_section:
        score += 4
    if _is_calculation_section_title(text):
        score += 4
    if block_type in {"table", "formula", "equation"}:
        score += 2
    formula_hits = sum(1 for keyword in FORMULA_SIGNAL_KEYWORDS if keyword in text)
    calc_hits = sum(1 for keyword in ("验算", "计算", "荷载组合", "长细比", "稳定", "承载力") if keyword in text)
    score += min(formula_hits, 3)
    score += min(calc_hits, 2)
    if not in_calc_section and score < 4:
        return 0
    return score


def _quote_around(text: str, keyword: str, before: int = 50, after: int = 100) -> str:
    """在片段中截取关键词前后文；NFKC 归一化后才能命中时退回归一化文本截取。"""
    idx = text.find(keyword)
    target = text
    if idx < 0:
        target = unicodedata.normalize("NFKC", text)
        idx = target.find(keyword)
    if idx < 0:
        return text[: before + after].strip()
    start = max(0, idx - before)
    return target[start: idx + len(keyword) + after].strip()


def run_calculation_engine(
    document: MinerUDocument,
    project_facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """执行计算规则验证引擎。"""
    rules = load_calculation_rules()
    segments = _extract_calculation_segments(document)
    calc_text = "\n".join(seg["text"] for seg in segments)[:50000]
    facts = (project_facts or {}).get("facts", {})
    support_system = facts.get("support_system", {})
    system_value = support_system.get("value", "unknown")

    results: list[dict[str, Any]] = []
    for rule in rules:
        result = _evaluate_calculation(rule, calc_text, system_value, segments, document, facts)
        results.append(result)

    compliant = sum(1 for r in results if r["status"] == "COMPLIANT")
    violated = sum(1 for r in results if r["status"] == "VIOLATED")
    uncertain = sum(1 for r in results if r["status"] == "UNCERTAIN")
    not_app = sum(1 for r in results if r["status"] == "NOT_APPLICABLE")
    pending = sum(1 for r in results if r["status"] == "PENDING_CONFIRMATION")

    return {
        "version": "4.0.0",
        "engine_type": "calculation",
        "mode": "formula_existence_and_recheck_v1",
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
    segments: list[dict[str, Any]] | None = None,
    document: MinerUDocument | None = None,
    facts: dict[str, Any] | None = None,
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

    # 提取证据片段（定位到来源 block，便于回查表格图像与页码）
    evidence: list[dict[str, Any]] = []
    for kw in matched_keywords[:3]:
        seg = _best_evidence_segment(segments or [], kw)
        if seg is not None:
            evidence.append({
                "quote": _quote_around(seg["text"], kw),
                "page": seg["physical_page"],
                "keyword": kw,
                "block_id": seg["block_id"],
                "block_type": seg["block_type"],
                "calculation_score": seg.get("calculation_score"),
                "in_calculation_section": seg.get("in_calculation_section"),
            })
        elif kw in norm_text:
            idx = norm_text.find(kw)
            start = max(0, idx - 50)
            end = min(len(calc_text), idx + len(kw) + 100)
            evidence.append({
                "quote": calc_text[start:end].strip(),
                "page": None,
                "keyword": kw,
            })

    threshold_match = len(keywords)
    condition_evaluation = evaluate_applicability_conditions(rule, facts=facts, text=calc_text)
    recheck = recheck_calculation(rule, segments or [])
    route = calculation_agent_route(str(rule_id), recheck)
    calc_agent: dict[str, Any] | None = None
    if document is not None and should_run_calculation_agent(str(rule_id)):
        calc_agent = trace_calculation_evidence(
            rule,
            document,
            segments or [],
            facts=facts,
            condition_evaluation=condition_evaluation,
        )
        agent_evidence = _agent_evidence_to_review_evidence(calc_agent)
        if agent_evidence:
            evidence = agent_evidence
    if recheck is not None and recheck.get("status") in {"PASS", "ISSUE"}:
        status = "COMPLIANT" if recheck["status"] == "PASS" else "VIOLATED"
        reason = (
            f"已进行公式复算：{recheck.get('substituted_expression')}，"
            f"结果{'满足' if status == 'COMPLIANT' else '不满足'}限值要求"
        )
        return _build_calc_result(
            rule,
            status,
            reason,
            evidence,
            recheck=recheck,
            route=route,
            calc_agent=calc_agent,
            condition_evaluation=condition_evaluation,
        )

    if matched_count >= max(2, threshold_match // 2):
        if calc_agent is not None:
            status = "UNCERTAIN"
            reason = (
                f"计算书中找到该验算项目候选证据，关键词匹配 {matched_count}/{len(keywords)}："
                f"{'、'.join(matched_keywords[:5])}；该规则已进入 Agent 追证，仍需复算或人工确认。"
            )
        else:
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

    return _build_calc_result(
        rule,
        status,
        reason,
        evidence,
        recheck=recheck,
        route=route,
        calc_agent=calc_agent,
        condition_evaluation=condition_evaluation,
    )


def _agent_evidence_to_review_evidence(agent: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for item in agent.get("evidence", [])[:5]:
        out.append({
            "quote": item.get("quote"),
            "page": item.get("page"),
            "keyword": "Agent追证",
            "block_id": item.get("block_id"),
            "block_type": item.get("block_type"),
            "calculation_score": item.get("score"),
            "in_calculation_section": item.get("in_calculation_section"),
            "evidence_id": item.get("evidence_id"),
        })
    return out


def _best_evidence_segment(
    segments: list[dict[str, Any]],
    keyword: str,
) -> dict[str, Any] | None:
    matches = [
        seg for seg in segments
        if keyword in unicodedata.normalize("NFKC", str(seg.get("text") or ""))
    ]
    if not matches:
        return None
    return max(
        matches,
        key=lambda seg: (
            int(seg.get("calculation_score") or 0),
            1 if seg.get("block_type") in {"table", "formula", "equation"} else 0,
            -int(seg.get("physical_page") or 0),
        ),
    )


def _build_calc_result(
    rule: dict[str, Any],
    status: str,
    reason: str,
    evidence: list[dict[str, Any]],
    *,
    recheck: dict[str, Any] | None = None,
    route: str = "presence_check",
    calc_agent: dict[str, Any] | None = None,
    condition_evaluation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    code_ref = rule.get("code_ref") or {}
    cl = rule.get("check_logic") or {}
    explanation = _calculation_explanation(status, reason, evidence, recheck)
    result = {
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
        "applicable_types": rule.get("applicable_types", ["universal"]),
        "applicability_conditions": rule.get("applicability_conditions", []),
        "evidence": evidence[:5],
        "review_explanation": explanation,
        "route": route,
    }
    if condition_evaluation is not None:
        result["condition_evaluation"] = condition_evaluation
    if route in {"agent_evidence", "human_review"}:
        result["manual_review"] = True
    if recheck is not None:
        result["calculation_recheck"] = recheck
        if recheck.get("uncertainty_category"):
            result["uncertainty_category"] = recheck.get("uncertainty_category")
    if calc_agent is not None:
        result["calculation_agent"] = calc_agent
        explanation["found"].extend(calc_agent.get("found") or [])
        explanation["missing"].extend(calc_agent.get("missing") or [])
    return result


def _calculation_explanation(
    status: str,
    reason: str,
    evidence: list[dict[str, Any]],
    recheck: dict[str, Any] | None,
) -> dict[str, Any]:
    if recheck and isinstance(recheck.get("explanation"), dict):
        exp = recheck["explanation"]
        return {
            "found": list(exp.get("found") or []),
            "missing": list(exp.get("missing") or []),
            "decision": exp.get("decision") or reason,
        }
    found = []
    if evidence:
        found.append(f"找到 {len(evidence)} 条计算书证据")
    missing = [] if status in {"COMPLIANT", "VIOLATED"} else ["尚未取得可复算的完整参数或公式片段"]
    return {"found": found, "missing": missing, "decision": reason}


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
