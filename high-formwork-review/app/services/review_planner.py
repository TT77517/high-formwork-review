"""Review Planner：Plan-only 审查计划生成（V3.1 Phase 6，§5 修订版）。

无 Replan。Planner 只设置审查重点/优先级/Agent 目标/人工确认项，
无权关闭任何强制检查（MANDATORY_CHECKS 白名单常驻）。

两种实现，自动降级：
- LLM：单次调用生成 focus_areas（失败自动降级，不中断）
- 本地统计：零 LLM，从 qualification/facts/规则统计推导（保底）

输出 review_plan.json 落 job 目录（前端"Agent 审查计划"区域数据源）。
"""

from __future__ import annotations

import json
import re
from typing import Any

from .agent_router import FACT_NAME_ALIASES, conflicting_fact_keys
from .llm_chat_client import LLMChatClient, LLMChatError

PLANNER_PROMPT_VERSION = "planner-v1"

# 强制检查白名单：Planner 无权关闭（V3.1 §5）
MANDATORY_CHECKS = [
    "文档解析", "完整性审查", "工程基本信息", "ProjectFacts",
    "适用性门禁", "关键规则", "必要计算校核", "结果校验",
]

SYSTEM_NAME_MAP = {
    "disk_lock": "承插型盘扣式",
    "koujian": "扣件式",
    "pankou": "盘扣式",
    "unknown": "未识别",
}


def _facts_summary(facts: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key, entry in facts.items():
        if not isinstance(entry, dict):
            continue
        summary[key] = {
            "status": entry.get("status"),
            "value": entry.get("value"),
        }
    return summary


# ---------------------------------------------------------------------------
# 本地统计生成（零 LLM 保底）
# ---------------------------------------------------------------------------

def build_review_plan_local(
    qualification: dict[str, Any],
    facts: dict[str, Any],
    rule_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """从工程特征本地推导审查计划（LLM 失败时的保底，也用于对比）。"""
    facts = facts or {}
    support_system = str(qualification.get("support_system") or "unknown")
    system_label = SYSTEM_NAME_MAP.get(support_system, support_system)
    focus_areas: list[dict[str, Any]] = [
        {
            "area": f"{system_label}支撑体系构造要求",
            "priority": "HIGH",
            "reason": f"识别为{system_label}支撑体系，体系专属规则优先执行",
        }
    ]
    risk = qualification.get("risk_classification") or {}
    if risk and str(risk).lower() not in ("unknown", "none", ""):
        focus_areas.append({
            "area": "危大工程风险条款核查",
            "priority": "HIGH",
            "reason": f"风险分级：{risk}",
        })

    agent_targets: list[dict[str, Any]] = []
    for key, entry in facts.items():
        if isinstance(entry, dict) and str(entry.get("status")) == "missing":
            agent_targets.append({
                "target": key,
                "reason": "关键参数未识别，Agent 查证阶段重点检索",
            })

    human_confirmations: list[dict[str, Any]] = []
    for key in conflicting_fact_keys(facts):
        aliases = FACT_NAME_ALIASES.get(key, [key])
        human_confirmations.append({
            "fact": key,
            "reason": f"{aliases[0]}存在多个候选值，需人工确认后重跑",
        })
    if support_system == "unknown":
        human_confirmations.insert(0, {
            "fact": "support_system",
            "reason": "支撑体系未识别，体系专属规则暂挂 PENDING，确认后重跑",
        })

    return {
        "plan_id": "PLAN-LOCAL",
        "generated_by": "local_stats",
        "prompt_version": PLANNER_PROMPT_VERSION,
        "mandatory_checks": list(MANDATORY_CHECKS),
        "focus_areas": focus_areas,
        "agent_targets": agent_targets[:8],
        "human_confirmations": human_confirmations,
        "rule_stats": rule_stats or {},
    }


# ---------------------------------------------------------------------------
# LLM 生成（失败降级本地）
# ---------------------------------------------------------------------------

_PLANNER_SYSTEM_PROMPT = """你是高支模专项施工方案审查的项目经理。根据工程特征生成审查计划。

职责边界：只设置审查重点、优先级、Agent 查证目标与人工确认项。
你无权关闭任何强制检查，不得建议跳过安全检查或修改规范要求。
输出严格 JSON（无其他文字）：
{
  "focus_areas": [{"area": "...", "priority": "HIGH|MEDIUM", "reason": "..."}],
  "agent_targets": [{"target": "...", "reason": "..."}],
  "human_confirmations": [{"fact": "...", "reason": "..."}]
}
最多各 5 项。"""


def build_review_plan(
    qualification: dict[str, Any],
    facts: dict[str, Any],
    *,
    client: LLMChatClient | None = None,
    rule_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """生成审查计划：LLM 优先，任何失败降级本地统计（任务不中断）。"""
    plan = build_review_plan_local(qualification, facts, rule_stats)
    try:
        chat_client = client or LLMChatClient.from_env()
        context = {
            "project_type": qualification.get("project_type"),
            "support_system": qualification.get("support_system"),
            "support_system_label": qualification.get("support_system_label"),
            "risk_classification": qualification.get("risk_classification"),
            "facts": _facts_summary(facts or {}),
            "rule_stats": rule_stats or {},
        }
        response = chat_client.chat_sync(
            [
                {"role": "system", "content": _PLANNER_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
            ],
            temperature=0.2,
        )
        parsed = _parse_plan_json(response.content)
        if parsed is not None:
            plan.update({
                "plan_id": "PLAN-LLM",
                "generated_by": "llm",
                "focus_areas": parsed.get("focus_areas", plan["focus_areas"])[:5],
                "agent_targets": parsed.get("agent_targets", plan["agent_targets"])[:5],
                "human_confirmations": parsed.get(
                    "human_confirmations", plan["human_confirmations"]
                )[:5],
            })
    except (LLMChatError, OSError, ValueError):
        pass  # 降级本地，静默（generated_by 已标 local_stats）
    return plan


def _parse_plan_json(content: str) -> dict[str, Any] | None:
    """解析 LLM 输出的计划 JSON（容错代码围栏）；结构不合法返回 None。"""
    if not content:
        return None
    text = re.sub(r"^```(json)?|```$", "", content.strip(), flags=re.MULTILINE).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    valid_priorities = {"HIGH", "MEDIUM", "LOW"}
    focus_areas = [
        {"area": str(item.get("area", ""))[:60], "priority": priority, "reason": str(item.get("reason", ""))[:120]}
        for item in (data.get("focus_areas") or [])
        if isinstance(item, dict) and item.get("area")
        for priority in [str(item.get("priority", "MEDIUM")).upper()]
        if priority in valid_priorities
    ]
    agent_targets = [
        {"target": str(item.get("target", ""))[:40], "reason": str(item.get("reason", ""))[:120]}
        for item in (data.get("agent_targets") or [])
        if isinstance(item, dict) and item.get("target")
    ]
    human_confirmations = [
        {"fact": str(item.get("fact", ""))[:40], "reason": str(item.get("reason", ""))[:120]}
        for item in (data.get("human_confirmations") or [])
        if isinstance(item, dict) and item.get("fact")
    ]
    return {
        "focus_areas": focus_areas,
        "agent_targets": agent_targets,
        "human_confirmations": human_confirmations,
    }
