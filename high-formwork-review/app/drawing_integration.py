"""Drawing Agent Integration Preview（Task 8A）。

编排层：document + project_facts + registry
        ↓ build_drawing_review_tasks
        ↓ DrawingConsistencyAgent.run（每个 task 一次）
        ↓ compare_evidence_sets
        ↓ AgentDrawingReviewItem[]
        ↓ AgentDrawingReviewResult（items + status_counts）

不修改 legacy build_drawing_review；不接 web/main/orchestrator/report；
不写 drawing_review.json；不引入真实 Provider。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .drawing_agent import DrawingConsistencyAgent, build_drawing_review_tasks
from .drawing_compare import (
    CONSISTENT,
    CONFLICT,
    DRAWING_ONLY,
    NOT_FOUND,
    TEXT_ONLY,
    UNCERTAIN,
    compare_evidence_sets,
)


_ALL_STATUSES = (CONSISTENT, CONFLICT, TEXT_ONLY, DRAWING_ONLY, UNCERTAIN, NOT_FOUND)


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentDrawingReviewItem:
    fact_id: str
    display_name: str
    status: str
    reason: str
    scope_alignment: str
    text_value: object | None = None
    drawing_value: object | None = None
    text_unit: str | None = None
    drawing_unit: str | None = None
    text_evidence_count: int = 0
    drawing_evidence_count: int = 0
    comparable_pair_count: int = 0
    finish_reason: str | None = None
    iterations: int = 0


@dataclass(frozen=True)
class AgentDrawingReviewResult:
    items: list[AgentDrawingReviewItem]
    total_tasks: int
    status_counts: dict[str, int]
    reviewed_tasks: int


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_agent_drawing_review(
    document: Any,
    project_facts: Mapping[str, Any],
    registry: Iterable[Mapping[str, Any]],
    *,
    recall_tool: Any,
    check_tool: Any,
    ocr_tool: Any,
    search_text_tool: Any,
    vision_tool: Any = None,
    ocr_engine: Any = None,
    job_dir: Any = None,
) -> AgentDrawingReviewResult:
    """对每个 registry entry 跑 Agent + Comparator，输出稳定摘要。"""
    tasks = build_drawing_review_tasks(
        project_facts.get("facts", {}) if isinstance(project_facts, Mapping) else {},
        list(registry),
    )
    agent = DrawingConsistencyAgent(
        recall_tool=recall_tool,
        check_tool=check_tool,
        ocr_tool=ocr_tool,
        vision_tool=vision_tool,
        search_text_tool=search_text_tool,
    )
    items: list[AgentDrawingReviewItem] = []
    status_counts: dict[str, int] = {s: 0 for s in _ALL_STATUSES}
    for task in tasks:
        # 构造 config：必须含 fact_id 供 check_tool 内部使用
        config = {"fact_id": task.fact_id}
        state = agent.run(
            task=task,
            document=document,
            facts=project_facts.get("facts", {}) if isinstance(project_facts, Mapping) else {},
            config=config,
            ocr_engine=ocr_engine,
            job_dir=job_dir,
        )
        comparison = compare_evidence_sets(
            task.fact_id, state.text_evidence, state.drawing_evidence,
        )
        item = AgentDrawingReviewItem(
            fact_id=task.fact_id,
            display_name=task.display_name,
            status=comparison.status,
            reason=comparison.reason,
            scope_alignment=comparison.scope_alignment,
            text_value=comparison.text_value,
            drawing_value=comparison.drawing_value,
            text_unit=comparison.text_unit,
            drawing_unit=comparison.drawing_unit,
            text_evidence_count=comparison.text_evidence_count,
            drawing_evidence_count=comparison.drawing_evidence_count,
            comparable_pair_count=comparison.comparable_pair_count,
            finish_reason=state.finish_reason,
            iterations=state.iteration,
        )
        items.append(item)
        status_counts[comparison.status] = status_counts.get(comparison.status, 0) + 1
    return AgentDrawingReviewResult(
        items=items,
        total_tasks=len(items),
        status_counts=status_counts,
        reviewed_tasks=len(items),
    )
