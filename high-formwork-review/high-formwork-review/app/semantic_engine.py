"""语义规则引擎。

对 v4.0 规则库中 check_type=semantic 的 84 条规则，
从方案文本中提取相关证据，构建语义审查 prompt，
通过 Dify workflow 调用 LLM 进行语义判断。

输出四类状态：COMPLIANT(合规) / VIOLATED(疑似不合规) / UNCERTAIN(信息不足) / NOT_APPLICABLE(不适用)
"""

from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

from .models import MinerUDocument
from .rule_engine import RULE_LIBRARY_DIR, MODULE_NAMES, MODULE_FILES

logger = logging.getLogger(__name__)

# 语义审查输出状态
SEMANTIC_STATUSES = ("COMPLIANT", "VIOLATED", "UNCERTAIN", "NOT_APPLICABLE")

# 每条语义规则发送给 LLM 的方案文本上限（字符）
SEMANTIC_EVIDENCE_LIMIT = 6000

# 语义审查 prompt 模板
SYSTEM_PROMPT = """你是高支模专项施工方案审查专家。你的任务是对照规范条款，审查方案文本是否满足要求。

对于每条审查规则，你需要：
1. 阅读方案文本中与该规则相关的内容
2. 判断方案是否满足规则要求
3. 给出四类判定结果之一：
   - COMPLIANT（合规）：方案明确包含且满足该项要求
   - VIOLATED（疑似不合规）：方案内容不满足要求，或存在明显缺陷
   - UNCERTAIN（信息不足）：方案中未找到相关内容，或内容不充分无法判定
   - NOT_APPLICABLE（不适用）：该规则不适用于本方案（如支架类型不匹配）
4. 给出判定理由
5. 引用方案原文中支持判定的关键证据

输出格式为 JSON 数组，每个元素包含：
{
  "rule_id": "规则编号",
  "status": "COMPLIANT/VIOLATED/UNCERTAIN/NOT_APPLICABLE",
  "reason": "判定理由（中文，简明扼要）",
  "evidence_quote": "方案原文引用（如有）"
}
"""


def load_semantic_rules() -> list[dict[str, Any]]:
    """加载全部语义规则。"""
    rules = []
    for filename in MODULE_FILES:
        path = RULE_LIBRARY_DIR / filename
        if not path.is_file():
            continue
        for rule in json.loads(path.read_text(encoding="utf-8")):
            if rule.get("check_type") == "semantic":
                rules.append(rule)
    return rules


def _normalize_text(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def _find_relevant_sections(
    document: MinerUDocument,
    keywords: list[str],
    aliases: list[str] | None = None,
) -> list[dict[str, Any]]:
    """根据关键词和别名找到文档中的相关章节文本。"""
    search_terms = list(keywords)
    if aliases:
        search_terms.extend(aliases)
    if not search_terms:
        return []
    sections: list[dict[str, Any]] = []
    current_section_title = ""
    current_section_text = ""
    current_section_page = 0
    for page in document.pages:
        if page.parse_status == "unreadable":
            continue
        for block in page.blocks:
            text = block.text or ""
            if not text.strip():
                continue
            norm = _normalize_text(text)
            if block.block_type == "title":
                if current_section_text:
                    matched = any(term in _normalize_text(current_section_text) for term in search_terms)
                    sections.append({
                        "title": current_section_title,
                        "text": current_section_text,
                        "page": current_section_page,
                        "matched": matched,
                    })
                current_section_title = text
                current_section_text = ""
                current_section_page = page.physical_page
            else:
                current_section_text += text + "\n"
        # page text fallback
        page_text = page.text or ""
        if page_text and not current_section_text:
            if any(term in _normalize_text(page_text) for term in search_terms):
                sections.append({
                    "title": f"第{page.physical_page}页",
                    "text": page_text[:2000],
                    "page": page.physical_page,
                    "matched": True,
                })
    # flush last section
    if current_section_text:
        matched = any(term in _normalize_text(current_section_text) for term in search_terms)
        sections.append({
            "title": current_section_title,
            "text": current_section_text,
            "page": current_section_page,
            "matched": matched,
        })
    # prioritize matched sections
    matched_sections = [s for s in sections if s["matched"]]
    other_sections = [s for s in sections if not s["matched"]]
    return (matched_sections + other_sections)[:5]


def build_semantic_evidence(
    document: MinerUDocument,
    rule: dict[str, Any],
) -> str:
    """为单条语义规则构建方案文本证据。"""
    keywords = rule.get("check_logic", {}).get("extraction_keywords", [])
    check_content = rule.get("check_content", "")
    # 从 check_content 提取关键词作为补充搜索词
    if not keywords and check_content:
        keywords = re.findall(r"[\u4e00-\u9fff]{2,6}", check_content)[:5]
    sections = _find_relevant_sections(document, keywords)
    if not sections:
        # 如果没有找到相关章节，用全文前N字符
        all_text = ""
        for page in document.pages[:20]:
            if page.parse_status == "unreadable":
                continue
            all_text += (page.text or "") + "\n"
        return all_text[:SEMANTIC_EVIDENCE_LIMIT]
    # 拼接相关章节文本
    evidence = ""
    for s in sections:
        snippet = s["text"][:2000]
        evidence += f"【{s['title']}（第{s['page']}页）】\n{snippet}\n\n"
        if len(evidence) >= SEMANTIC_EVIDENCE_LIMIT:
            break
    return evidence[:SEMANTIC_EVIDENCE_LIMIT]


def build_semantic_prompt(
    document: MinerUDocument,
    rules: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """构建语义审查 prompt 和规则清单。

    返回 (scheme_text, rule_summaries)
    rule_summaries 是精简后的规则信息，供 LLM 判断。
    """
    rule_summaries = []
    for rule in rules:
        cl = rule.get("check_logic", {})
        sj = cl.get("semantic_judgment", "")
        rule_summaries.append({
            "rule_id": rule.get("rule_id", ""),
            "rule_name": rule.get("rule_name", ""),
            "check_content": rule.get("check_content", ""),
            "semantic_judgment": sj or "",
            "code_ref": rule.get("code_ref", {}).get("standard", ""),
            "applicable_types": rule.get("applicable_types", ["universal"]),
            "remedy_suggestion": rule.get("remedy_suggestion", "")[:200],
        })
    # 构建方案文本：取规则相关证据拼接
    evidence_parts = []
    total_len = 0
    for rule in rules:
        ev = build_semantic_evidence(document, rule)
        ev_snippet = ev[:3000]
        evidence_parts.append(f"--- 规则 {rule['rule_id']} {rule['rule_name']} 相关方案文本 ---\n{ev_snippet}")
        total_len += len(ev_snippet)
        if total_len >= 45000:
            break
    scheme_text = "\n\n".join(evidence_parts)
    return scheme_text, rule_summaries


def run_semantic_engine_local(
    document: MinerUDocument,
    project_facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """本地语义审查（不调用 LLM，仅做证据收集和关键词匹配预判）。

    这是无 Dify 时的降级模式：基于关键词匹配给出初步判定。
    有 Dify 配置时，应调用 run_semantic_engine_dify。
    """
    rules = load_semantic_rules()
    results: list[dict[str, Any]] = []
    facts = (project_facts or {}).get("facts", {})
    support_system = facts.get("support_system", {})
    system_value = support_system.get("value", "unknown")

    for rule in rules:
        result = _evaluate_semantic_local(rule, document, system_value)
        results.append(result)

    compliant = sum(1 for r in results if r["status"] == "COMPLIANT")
    violated = sum(1 for r in results if r["status"] == "VIOLATED")
    uncertain = sum(1 for r in results if r["status"] == "UNCERTAIN")
    not_app = sum(1 for r in results if r["status"] == "NOT_APPLICABLE")

    return {
        "version": "4.0.0",
        "engine_type": "semantic",
        "mode": "local_keyword_match",
        "total_rules": len(rules),
        "compliant": compliant,
        "violated": violated,
        "uncertain": uncertain,
        "not_applicable": not_app,
        "results": results,
    }


def _evaluate_semantic_local(
    rule: dict[str, Any],
    document: MinerUDocument,
    system_value: str,
) -> dict[str, Any]:
    """本地降级模式：基于关键词匹配做初步判定。"""
    keywords = rule.get("check_logic", {}).get("extraction_keywords", [])
    check_content = rule.get("check_content", "")
    if not keywords and check_content:
        keywords = re.findall(r"[\u4e00-\u9fff]{2,6}", check_content)[:5]

    # 适用性检查
    applicable_types = rule.get("applicable_types", ["universal"])
    if "universal" not in applicable_types:
        type_map = {"pankou": "disk_lock", "koujian": "coupler", "wankou": "other"}
        matched = any(type_map.get(at) == system_value for at in applicable_types)
        if not matched:
            return _build_sem_result(rule, "NOT_APPLICABLE", "支架类型不适用", [], "")

    # 关键词匹配
    evidence = build_semantic_evidence(document, rule)
    matched_count = 0
    matched_evidence: list[dict[str, Any]] = []
    for kw in keywords:
        if kw in _normalize_text(evidence):
            matched_count += 1
    # 提取匹配证据片段
    if matched_count > 0 and keywords:
        for kw in keywords[:3]:
            idx = _normalize_text(evidence).find(kw)
            if idx >= 0:
                start = max(0, idx - 30)
                end = min(len(evidence), idx + len(kw) + 50)
                matched_evidence.append({
                    "quote": evidence[start:end].strip(),
                    "page": None,
                })

    if matched_count >= max(1, len(keywords) // 2):
        status = "COMPLIANT"
        reason = f"方案中找到 {matched_count}/{len(keywords)} 个关键证据，初步判定满足要求"
    elif matched_count > 0:
        status = "UNCERTAIN"
        reason = f"方案中找到部分关键词（{matched_count}/{len(keywords)}），内容可能不充分"
    else:
        status = "UNCERTAIN"
        reason = "未找到明确的关键词匹配，需 LLM 语义判断或人工复核"

    return _build_sem_result(rule, status, reason, matched_evidence, evidence[:500])


def _build_sem_result(
    rule: dict[str, Any],
    status: str,
    reason: str,
    evidence: list[dict[str, Any]],
    raw_evidence: str,
) -> dict[str, Any]:
    code_ref = rule.get("code_ref") or {}
    return {
        "rule_id": rule.get("rule_id", ""),
        "rule_name": rule.get("rule_name", ""),
        "module": rule.get("module", ""),
        "module_name": MODULE_NAMES.get(rule.get("module", ""), ""),
        "check_type": "semantic",
        "severity": rule.get("severity", ""),
        "risk_level": rule.get("risk_level", ""),
        "status": status,
        "reason": reason,
        "code_ref": {
            "standard": code_ref.get("standard", ""),
            "original_text": code_ref.get("original_text", ""),
        },
        "remedy_suggestion": rule.get("remedy_suggestion", ""),
        "typical_violation": rule.get("typical_violation", ""),
        "manual_review": rule.get("manual_review", True),
        "evidence": evidence[:5],
        "semantic_judgment": rule.get("check_logic", {}).get("semantic_judgment", ""),
        "raw_evidence_snippet": raw_evidence,
    }


def run_semantic_engine_safe(
    document: MinerUDocument,
    project_facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """安全执行语义规则引擎。"""
    try:
        return run_semantic_engine_local(document, project_facts)
    except Exception as exc:
        logger.warning("语义规则引擎失败: %s", exc)
        return {
            "version": "4.0.0",
            "engine_type": "semantic",
            "mode": "local_keyword_match",
            "total_rules": 0,
            "compliant": 0,
            "violated": 0,
            "uncertain": 0,
            "not_applicable": 0,
            "results": [],
            "error": str(exc),
        }
