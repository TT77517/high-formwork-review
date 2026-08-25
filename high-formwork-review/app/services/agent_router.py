"""Semantic Router：规则四分流（V3.1 Phase 4，§3 修订版）。

路由决策零 LLM 调用，两层：
1. 规则路由表（静态）：规则库 route_hint 字段（LOCAL_READY/LLM_READY/
   AGENT_REQUIRED/HUMAN_REQUIRED），人工可逐规则指定
2. 本地启发式（route_hint 缺省/AUTO 时）：
   - HUMAN_REQUIRED：规则内容命中存在取值冲突的关键参数（多候选值待人工确认）
   - LLM_READY：关键词召回 >= 2 个 block（证据充分，批式一次判定即可）
   - AGENT_REQUIRED：召回不足（0-1 个 block，需要 Agent 自主深挖）

输出 route_decisions（落盘 job 目录，供前端"审查路径标签"与时间线展示）。
"""

from __future__ import annotations

from typing import Any

from ..models import MinerUDocument
from .agent_tools import _despaced_with_offsets, _index_blocks

VALID_ROUTES = {"LOCAL_READY", "LLM_READY", "AGENT_REQUIRED", "HUMAN_REQUIRED"}
LLM_READY_HIT_THRESHOLD = 2

# 关键参数 -> 规则文本中常见的中文别名（用于 HUMAN_REQUIRED 冲突关联）
FACT_NAME_ALIASES: dict[str, list[str]] = {
    "support_height": ["搭设高度", "支模高度", "支架高度"],
    "support_span": ["搭设跨度", "模板跨度", "结构跨度"],
    "step_height": ["步距", "步高"],
    "total_load": ["施工总荷载", "总荷载"],
    "concentrated_line_load": ["线荷载"],
}


def conflicting_fact_keys(facts: dict[str, Any] | None) -> list[str]:
    """识别存在取值冲突的关键参数（status=conflict/uncertain 且候选值 >= 2 个不同值）。"""
    facts = facts or {}
    conflicting: list[str] = []
    for key, entry in facts.items():
        if not isinstance(entry, dict):
            continue
        status = str(entry.get("status", "")).lower()
        if status not in {"uncertain", "conflict"} and not entry.get("has_conflict"):
            continue
        candidates = entry.get("candidates") or []
        values = {
            str(c.get("value")) for c in candidates if isinstance(c, dict)
        }
        values.discard("None")
        if len(values) >= 2:
            conflicting.append(key)
    return conflicting


def _keyword_hit_stats(document: MinerUDocument, keywords: list[str]) -> dict[str, int]:
    """统计命中关键词的 block 数，并拆分目录/正文证据质量。"""
    terms = [
        "".join(_despaced_with_offsets(k)[0])
        for k in keywords
        if k and _despaced_with_offsets(k)[0]
    ]
    if not terms:
        return {"total": 0, "body": 0, "toc": 0}
    total = body = toc = 0
    for _page, block, _section_path, is_toc in _index_blocks(document):
        despaced, _ = _despaced_with_offsets(block.text or "")
        if not despaced:
            continue
        if any(term in despaced for term in terms):
            total += 1
            if is_toc:
                toc += 1
            else:
                body += 1
    return {"total": total, "body": body, "toc": toc}


def route_rule(
    rule: dict[str, Any],
    document: MinerUDocument,
    facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """对单条规则做路由决策；返回 {rule_id, route, reason, decided_by}。"""
    rule_id = str(rule.get("rule_id", ""))
    hint = str(rule.get("route_hint") or "").strip().upper()
    if hint in VALID_ROUTES:
        return {
            "rule_id": rule_id,
            "route": hint,
            "reason": "规则库 route_hint 静态指定",
            "decided_by": "route_hint",
        }

    # HUMAN_REQUIRED：关键参数冲突
    conflicting = conflicting_fact_keys(facts)
    if conflicting:
        aliases: list[str] = []
        for key in conflicting:
            aliases.extend(FACT_NAME_ALIASES.get(key, []))
        text = f"{rule.get('check_content', '')} {rule.get('rule_name', '')}"
        hit_alias = next((a for a in aliases if a in text), None)
        if hit_alias:
            return {
                "rule_id": rule_id,
                "route": "HUMAN_REQUIRED",
                "reason": f"关键参数取值冲突（{hit_alias}），需人工确认后重跑",
                "decided_by": "heuristic",
            }

    keywords = rule.get("check_logic", {}).get("extraction_keywords") or [
        rule.get("rule_name", "")
    ]
    hit_stats = _keyword_hit_stats(document, [str(k) for k in keywords if k])
    hits = hit_stats["total"]
    body_hits = hit_stats["body"]
    toc_hits = hit_stats["toc"]
    if hits >= LLM_READY_HIT_THRESHOLD and body_hits < LLM_READY_HIT_THRESHOLD:
        return {
            "rule_id": rule_id,
            "route": "AGENT_REQUIRED",
            "reason": (
                f"初始证据召回 {hits} 个 block，但正文有效证据仅 {body_hits} 个"
                f"（目录 {toc_hits} 个），需 Agent 深挖正文"
            ),
            "decided_by": "heuristic",
        }
    if body_hits >= LLM_READY_HIT_THRESHOLD:
        return {
            "rule_id": rule_id,
            "route": "LLM_READY",
            "reason": f"初始证据召回 {body_hits} 个正文 block，批式一次判定即可",
            "decided_by": "heuristic",
        }
    return {
        "rule_id": rule_id,
        "route": "AGENT_REQUIRED",
        "reason": (
            f"初始证据召回不足（{hits} 个 block），需 Agent 自主查证"
            if hits
            else "初始证据召回为 0，需 Agent 自主查证"
        ),
        "decided_by": "heuristic",
    }


def route_rules(
    rules: list[dict[str, Any]],
    document: MinerUDocument,
    facts: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """批量路由；返回 {rule_id: decision}。"""
    return {
        str(rule.get("rule_id", "")): route_rule(rule, document, facts)
        for rule in rules
    }
