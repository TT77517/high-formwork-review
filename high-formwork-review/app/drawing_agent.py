"""Drawing Agent 数据模型层（Task 2）。

本模块只承载三个纯数据模型，供后续 Agent 阶段使用：

- ``DrawingReviewTask``：单个图文核验任务（参数候选 + 已知正文值 + scope）
- ``Evidence``：单条可追溯证据（页码/来源/角色/置信度）
- ``DrawingAgentState``：单个 Task 的运行状态（证据 + 候选页 + 行动历史 + 计数）

约束（Task 2 边界）：
- 仅数据模型，不实现 Agent / 循环 / Action / Tool 调用
- 不导入 ``app.drawing_review``，避免与 ``drawing_review`` 模块形成循环依赖
- 不接入 ``build_drawing_review``，业务流仍走原 ``drawing_review`` Workflow
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping

from .drawing_scope import resolve_evidence_scope


@dataclass
class DrawingReviewTask:
    """单个图文核验任务。

    字段语义详见 Task 2 指令第四节。
    """

    fact_id: str
    display_name: str
    aliases: list[str]
    text_value: object | None = None
    unit: str | None = None
    priority: str = "medium"
    source: str = "project_fact"
    scope: dict[str, object] = field(default_factory=dict)


@dataclass
class Evidence:
    """单条可追溯证据。

    字段语义详见 Task 2 指令第六/七/八/九节。
    """

    fact_id: str
    source_type: str
    value: object | None = None
    unit: str | None = None
    page: int | None = None
    evidence_text: str | None = None
    confidence: float | None = None
    source_role: str = "unknown"
    scope: dict[str, object] = field(default_factory=dict)


@dataclass
class DrawingAgentState:
    """单个 DrawingReviewTask 的运行状态。

    字段语义详见 Task 2 指令第十/十一节。
    本轮只承载状态字段，不实现 Agent 循环 / Budget 校验。
    """

    task: DrawingReviewTask
    text_evidence: list[Evidence] = field(default_factory=list)
    drawing_evidence: list[Evidence] = field(default_factory=list)
    candidate_pages: list[dict[str, object]] = field(default_factory=list)
    actions_taken: list[dict[str, object]] = field(default_factory=list)
    iteration: int = 0
    ocr_pages: int = 0
    vlm_calls: int = 0
    finished: bool = False
    finish_reason: str | None = None


# ---------------------------------------------------------------------------
# Task 3: 候选核验任务生成器
# ---------------------------------------------------------------------------


def _task_from_registry_entry(
    config: Mapping[str, Any],
    fact: Mapping[str, Any] | None,
) -> DrawingReviewTask:
    """从 registry 单条 config + 可选 ProjectFact 构造 DrawingReviewTask。

    行为：
    - fact 不存在 / fact 非 dict / fact["value"] is None → 视为 missing：
        text_value=None, source="critical_fact"
    - fact["value"] 存在 → text_value=fact["value"], source="project_fact"
    - display_name：优先 config["name"]；缺失时退回 config["keywords"][0]
    - aliases：config["keywords"] 的浅拷贝（避免污染 registry）
    - unit：优先 fact["unit"]，否则 config.get("unit")，否则 None
    - priority 统一 "medium"（dataclass 默认值，不显式传）
    - scope 一律 {}（Task 7 单独实现）
    """
    keywords = config.get("keywords") or []
    display_name = config.get("name") or (keywords[0] if keywords else None)
    if display_name is None:
        raise ValueError(
            f"registry item 缺少 name 与 keywords: fact_id={config.get('fact_id')!r}"
        )
    aliases = list(keywords)

    fact_value: Any = None
    source = "critical_fact"
    if isinstance(fact, Mapping):
        raw = fact.get("value")
        if raw is not None:
            fact_value = raw
            source = "project_fact"

    unit: Any = None
    if isinstance(fact, Mapping) and fact.get("unit") is not None:
        unit = fact.get("unit")
    elif config.get("unit") is not None:
        unit = config.get("unit")

    return DrawingReviewTask(
        fact_id=config["fact_id"],
        display_name=display_name,
        aliases=aliases,
        text_value=fact_value,
        unit=unit,
        source=source,
        scope=dict(config.get("scope") or {}),  # 显式 scope 可选；缺省仍 {}
    )


def build_drawing_review_tasks(
    facts: Mapping[str, Any],
    registry: list[Mapping[str, Any]],
) -> list[DrawingReviewTask]:
    """按 registry 顺序，为每条当前核验参数生成一个 ``DrawingReviewTask``。

    与旧 ``_cross_check_param`` 的关键区别：ProjectFact 缺失（含 value=None）
    也会生成 Task（text_value=None, source="critical_fact"），为未来 Agent
    准备任务候选；不再因 fact 缺失而静默。

    本函数不调用任何 Task 1 Tool，不触发 OCR/VLM/LLM。
    registry 由调用方传入，本模块不内置默认注册表。
    """
    return [_task_from_registry_entry(config, facts.get(config["fact_id"])) for config in registry]


# ---------------------------------------------------------------------------
# Task 4 + 5A + 5B: DrawingConsistencyAgent 有界状态循环 + OCR/VLM 分级追证
# ---------------------------------------------------------------------------

MAX_ITERATIONS = 5
MAX_OCR_PAGES = 2
MAX_VLM_CALLS = 1
MAX_TEXT_SEARCHES = 1

SEARCH_DRAWING = "SEARCH_DRAWING"
CHECK_PARAM = "CHECK_PARAM"
FINISH = "FINISH"
OCR_PAGE = "OCR_PAGE"
INSPECT_IMAGE = "INSPECT_IMAGE"
SEARCH_TEXT = "SEARCH_TEXT"


# ---------------------------------------------------------------------------
# Task 7C: CHECK_PARAM legacy result → structured DrawingEvidence
# ---------------------------------------------------------------------------


def _check_result_to_drawing_evidence(
    task: DrawingReviewTask,
    result: Mapping[str, Any] | None,
) -> Evidence | None:
    """Convert legacy ``check_tool`` result → structured ``Evidence``.

    Structured evidence preserves the raw drawing-side fact; legacy
    PASS/ISSUE tolerance remains separate. Returns ``None`` if no usable
    drawing-side evidence exists. Does NOT inspect ``status`` to decide
    whether to emit Evidence. Does NOT mutate the input ``result``.

    Provenance 规则（Task 7C.1）：

    - 多个 drawing_evidence entry 数值匹配 drawing_value 时，仅在所有
      匹配的 (page, quote) signature 一致（同一标注重复）时才返回 Evidence；
      否则返回 None（不任意绑定第一条，避免"梁底 vs 板底"假关联）。
    - unit：legacy cross_check_param 的 drawing_evidence entry 不携带
      unit 字段（unit 仅在 quote 字符串中或由 task 隐式假设），因此
      DrawingEvidence.unit = None（显式说明非图纸自带单位，让 Comparator
      Unit Gate 报 unit_incomplete → UNCERTAIN）。
    """
    if not isinstance(result, Mapping):
        return None
    drawing_value = result.get("drawing_value")
    if drawing_value is None:
        return None
    matches: list[Mapping[str, Any]] = []
    for entry in result.get("drawing_evidence") or []:
        if isinstance(entry, Mapping) and _values_match(entry.get("value"), drawing_value):
            matches.append(entry)
    if not matches:
        return None
    # 唯一性 / 等价性检查
    if len(matches) > 1:
        sigs = {(m.get("page"), m.get("quote")) for m in matches}
        if len(sigs) > 1:
            return None  # 多个不同 page/quote 同时匹配 → 无法证明唯一来源
    chosen = matches[0]
    page = chosen.get("page")
    quote = chosen.get("quote") or ""
    if isinstance(quote, str) and len(quote) > 300:
        quote = quote[:300]
    if page is None and not quote:
        return None
    return Evidence(
        fact_id=task.fact_id,
        source_type="legacy_check",
        value=drawing_value,
        unit=None,  # FALLBACK_PARAMETER_UNIT：legacy 不携带 drawing-side unit
        page=page,
        evidence_text=quote or None,
        confidence=None,
        source_role="drawing_annotation",
        scope=resolve_evidence_scope(task.scope, quote or None, task.aliases),
    )


def _values_match(left: object, right: object) -> bool:
    """scalar / 2D list-tuple 最小相等（1e-9 容差）。"""
    if left is None or right is None:
        return False
    left_seq = isinstance(left, (list, tuple))
    right_seq = isinstance(right, (list, tuple))
    if left_seq != right_seq:
        return False
    if left_seq and (len(left) != 2 or len(right) != 2):  # type: ignore[arg-type]
        return False
    try:
        if left_seq:
            return math.isclose(float(left[0]), float(right[0]), rel_tol=0.0, abs_tol=1e-9) \
                and math.isclose(float(left[1]), float(right[1]), rel_tol=0.0, abs_tol=1e-9)  # type: ignore[index]
        return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=1e-9)
    except (TypeError, ValueError, IndexError):
        return False


class DrawingConsistencyAgent:
    """图文一致性 Agent（确定性 Policy，Task 5B 加入 VLM fallback）。

    能力：
    - 有状态：根据 ``DrawingAgentState`` 选择下一 Action
    - 工具调用：通过依赖注入传入 ``recall_tool`` / ``check_tool`` / ``ocr_tool``
      / ``vision_tool``（vision 可选，默认 None），与本模块解耦
    - 有限循环：单次 ``run`` 最多 ``MAX_ITERATIONS``（4）次 Tool Action，
      其中 OCR 调用最多 ``MAX_OCR_PAGES``（2）次，VLM 调用最多
      ``MAX_VLM_CALLS``（1）次
    - 明确停止：每次 Action 后根据 observation 设置 ``finish_reason``

    Action 共五种：
    - ``SEARCH_DRAWING`` → 调 ``recall_tool`` 召回候选图纸页
    - ``CHECK_PARAM``    → 调 ``check_tool`` 跑确定性 cross-check
    - ``OCR_PAGE``       → 调 ``ocr_tool`` 对单页 OCR 追证
    - ``INSPECT_IMAGE``  → 调 ``vision_tool`` 对单页做 VLM 结构化识别
    - ``FINISH``         → 不调 Tool，仅收尾

    注意：当前 ``CHECK_PARAM`` 仍走 Task 1 的旧 Tool（整文档检查），
    ``state.candidate_pages`` 不作为其搜索范围约束。
    """

    def __init__(
        self,
        recall_tool,
        check_tool,
        ocr_tool,
        vision_tool=None,
        search_text_tool=None,
    ) -> None:
        self.recall_tool = recall_tool
        self.check_tool = check_tool
        self.ocr_tool = ocr_tool
        self.vision_tool = vision_tool
        self.search_text_tool = search_text_tool

    def run(
        self,
        task: DrawingReviewTask,
        document: Any,
        facts: Mapping[str, Any],
        config: Mapping[str, Any],
        *,
        ocr_engine: Any = None,
        ocr_texts: Mapping[int, str] | None = None,
        job_dir: Any = None,
    ) -> DrawingAgentState:
        state = DrawingAgentState(task=task)
        # 一次性初始化 TextEvidence（按 Task 5A 第十三/十五节）
        if task.text_value is not None:
            state.text_evidence.append(
                Evidence(
                    fact_id=task.fact_id,
                    source_type="text",
                    value=task.text_value,
                    unit=task.unit,
                    source_role="design_parameter",
                    scope=resolve_evidence_scope(task.scope, None, task.aliases),
                )
            )
        # 把 ocr_engine 绑定到 state（供 decide/execute 读取，不进 actions_taken）
        state._ocr_engine = ocr_engine  # type: ignore[attr-defined]
        state._job_dir = job_dir  # type: ignore[attr-defined]
        state._ocr_texts = ocr_texts  # type: ignore[attr-defined]
        while not self.should_stop(state):
            action = self.decide_next_action(state)
            if action == FINISH:
                break
            self.execute_action(
                action, state, document, facts, config
            )
            state.iteration += 1
        if not state.finished:
            state.finished = True
            state.finish_reason = "max_iterations"
        # 清理一次性挂载的运行时字段
        for attr in ("_ocr_engine", "_job_dir", "_ocr_texts"):
            if hasattr(state, attr):
                delattr(state, attr)
        return state

    def should_stop(self, state: DrawingAgentState) -> bool:
        return state.finished or state.iteration >= MAX_ITERATIONS

    def decide_next_action(self, state: DrawingAgentState) -> str:
        actions_so_far = {item.get("action") for item in state.actions_taken}
        # Step 1: 尚未执行 SEARCH_DRAWING
        if SEARCH_DRAWING not in actions_so_far:
            return SEARCH_DRAWING
        # Step 2: 已搜索但无候选
        if not state.candidate_pages:
            self._finish(state, "no_candidate_pages")
            return FINISH
        # Step 3a: 有候选 + 有正文值 → CHECK_PARAM
        if state.task.text_value is not None:
            if CHECK_PARAM not in actions_so_far:
                return CHECK_PARAM
            self._finish(state, state.finish_reason or "check_completed")
            return FINISH
        # Step 3b: text_value=None → OCR → VLM → reverse-chase 分级路径
        ocr_engine = getattr(state, "_ocr_engine", None)
        if ocr_engine is None:
            # 无 OCR 引擎：本轮 DrawingEvidence 尚未形成 → 直接收尾
            self._finish(state, "ocr_unavailable")
            return FINISH
        # 已有 drawing value（兼容未来 OCR 直接出 value 的场景）
        for ev in state.drawing_evidence:
            if ev.value is not None:
                return self._after_drawing_phase(state, actions_so_far, "drawing_value_found")
        # OCR 阶段未结束 → 继续 OCR
        if not self._ocr_phase_done(state) and state.ocr_pages < MAX_OCR_PAGES:
            return OCR_PAGE
        # OCR 阶段结束 → 切 VLM
        if state.vlm_calls >= MAX_VLM_CALLS:
            return self._after_drawing_phase(state, actions_so_far, "ocr_no_evidence")
        if self.vision_tool is None:
            return self._after_drawing_phase(state, actions_so_far, "vision_unavailable")
        return INSPECT_IMAGE

    def _after_drawing_phase(
        self, state: DrawingAgentState, actions_so_far: set, fallback_reason: str
    ) -> str:
        """Drawing 阶段（OCR/VLM）结束后，决定 SEARCH_TEXT 还是直接 FINISH。

        - SEARCH_TEXT 未执行 + drawing_evidence 非空 + search_text_tool 可用 → SEARCH_TEXT
        - SEARCH_TEXT 未执行 + drawing_evidence 非空 + search_text_tool is None → text_search_unavailable
        - 无 drawing_evidence 或 SEARCH_TEXT 已执行 → 用 fallback_reason 收尾
        """
        if SEARCH_TEXT not in actions_so_far and state.drawing_evidence:
            if self.search_text_tool is None:
                self._finish(state, "text_search_unavailable")
            else:
                return SEARCH_TEXT
        else:
            self._finish(state, state.finish_reason or fallback_reason)
        return FINISH

    def _ocr_phase_done(self, state: DrawingAgentState) -> bool:
        """OCR 阶段是否结束（任一即结束）：
        1) 已达 OCR 预算
        2) 已生成 OCR Evidence（alias 已命中，无需再 OCR）
        3) 候选全部 OCR 完（无 untried 候选）
        """
        if state.ocr_pages >= MAX_OCR_PAGES:
            return True
        if any(ev.source_type == "ocr" for ev in state.drawing_evidence):
            return True
        done_pages = {
            item.get("page")
            for item in state.actions_taken
            if item.get("action") == OCR_PAGE
        }
        for cand in state.candidate_pages:
            if cand.get("physical_page") not in done_pages:
                return False
        return True

    def execute_action(
        self,
        action: str,
        state: DrawingAgentState,
        document: Any,
        facts: Mapping[str, Any],
        config: Mapping[str, Any],
    ) -> None:
        if action == SEARCH_DRAWING:
            result = self.recall_tool(document, state.task.aliases, limit=8)
            state.candidate_pages = list(result or [])
            state.actions_taken.append(
                {
                    "iteration": state.iteration + 1,
                    "action": SEARCH_DRAWING,
                    "observation": {"candidate_count": len(state.candidate_pages)},
                }
            )
            return
        if action == CHECK_PARAM:
            result = self.check_tool(
                document,
                facts,
                config,
                ocr_texts=getattr(state, "_ocr_texts", None),
                job_dir=getattr(state, "_job_dir", None),
            )
            observation: dict[str, Any] = {"result_is_none": result is None}
            if isinstance(result, dict) and "status" in result:
                observation["status"] = result["status"]
            state.actions_taken.append(
                {
                    "iteration": state.iteration + 1,
                    "action": CHECK_PARAM,
                    "observation": observation,
                }
            )
            # Task 7C：将 legacy check result 结构化为 DrawingEvidence。
            # 不改变 observation / finish_reason / Action / Policy。
            if isinstance(result, Mapping):
                ev = _check_result_to_drawing_evidence(state.task, result)
                if ev is not None:
                    state.drawing_evidence.append(ev)
            if result is None:
                self._finish(state, "check_returned_none")
            else:
                self._finish(state, "check_completed")
            return
        if action == OCR_PAGE:
            self._execute_ocr(action, state, document)
            return
        if action == INSPECT_IMAGE:
            self._execute_inspect(action, state, document)
            return
        if action == SEARCH_TEXT:
            self._execute_search_text(state, document)
            return
        self._finish(state, f"unknown_action:{action}")

    def _execute_inspect(
        self,
        action: str,
        state: DrawingAgentState,
        document: Any,
    ) -> None:
        """INSPECT_IMAGE 的实际执行：选页（优先 OCR Evidence 页）→ vision_tool → 构造 VLM Evidence。"""
        # 优先选已存在 OCR Evidence 的页；否则选 candidate_pages[0]
        target: Mapping[str, Any] | None = None
        for ev in state.drawing_evidence:
            if ev.source_type == "ocr" and ev.page is not None:
                target = {"physical_page": ev.page}
                break
        if target is None and state.candidate_pages:
            target = state.candidate_pages[0]
        if target is None:
            self._finish(state, "vision_no_evidence")
            return
        page = self._resolve_candidate_page(document, target)
        obs: dict[str, Any] = {"page": target.get("physical_page")}
        if page is None:
            obs["page_resolved"] = False
            state.actions_taken.append(
                {
                    "iteration": state.iteration + 1,
                    "action": INSPECT_IMAGE,
                    "page": target.get("physical_page"),
                    "observation": obs,
                }
            )
            state.vlm_calls += 1
            return
        try:
            result = self.vision_tool(page, state.task)
        except Exception:
            # Task 5B 第 33 节：允许异常向上抛
            raise
        state.vlm_calls += 1
        evidence = self._extract_vision_evidence(state.task, page, result)
        if evidence is not None:
            state.drawing_evidence.append(evidence)
            obs["found"] = True
            obs["has_value"] = evidence.value is not None
            # Task 6：不自动 _finish，让 decide_next_action 决定是否走 SEARCH_TEXT
        else:
            obs["found"] = False
            # Task 6：不自动 _finish（fallback_reason 由 _after_drawing_phase 提供）
        state.actions_taken.append(
            {
                "iteration": state.iteration + 1,
                "action": INSPECT_IMAGE,
                "page": page.physical_page,
                "observation": obs,
            }
        )

    def _extract_vision_evidence(
        self,
        task: DrawingReviewTask,
        page: Any,
        result: Any,
    ) -> Evidence | None:
        """从 vision_tool 返回构造 VLM Evidence。

        - 非 dict 或 result["found"] is False → None（视为 vision_no_evidence）
        - fact_id / source_type / source_role 由系统固定，不信模型
        - evidence_text 截断到 300 字符
        - scope 仅透传，不做判断
        """
        if not isinstance(result, dict):
            return None
        if not result.get("found"):
            return None
        unit = result.get("unit") or task.unit
        raw_text = result.get("evidence_text") or ""
        evidence_text = raw_text[:300] if isinstance(raw_text, str) else None
        explicit_scope = result.get("scope") if isinstance(result.get("scope"), dict) else {}
        return Evidence(
            fact_id=task.fact_id,
            source_type="vlm",
            value=result.get("value"),
            unit=unit,
            page=getattr(page, "physical_page", None),
            evidence_text=evidence_text,
            confidence=result.get("confidence"),
            source_role="drawing_annotation",
            scope=resolve_evidence_scope(explicit_scope, evidence_text, task.aliases),
        )

    def _execute_search_text(self, state: DrawingAgentState, document: Any) -> None:
        """SEARCH_TEXT 的实际执行：从最近一次 drawing value 作为 anchor 调 search_text_tool。"""
        # 取最近一次非空 drawing value 作为 target_value；无则 None
        target_value: Any = None
        for ev in reversed(state.drawing_evidence):
            if ev.value is not None:
                target_value = ev.value
                break
        try:
            candidates = self.search_text_tool(
                document,
                state.task.aliases,
                target_value=target_value,
                unit=state.task.unit,
            )
        except Exception:
            raise
        added_evidence = 0
        for cand in candidates or []:
            ev = self._search_text_to_evidence(state.task, cand)
            if ev is None:
                continue
            state.text_evidence.append(ev)
            added_evidence += 1
        used_anchor = target_value is not None
        state.actions_taken.append(
            {
                "iteration": state.iteration + 1,
                "action": SEARCH_TEXT,
                "observation": {
                    "candidate_count": len(candidates or []),
                    "evidence_count": added_evidence,
                    "used_value_anchor": used_anchor,
                },
            }
        )
        if added_evidence >= 1:
            self._finish(state, "text_evidence_found")
        else:
            self._finish(state, "text_no_evidence")

    def _search_text_to_evidence(
        self, task: DrawingReviewTask, cand: Mapping[str, Any]
    ) -> Evidence | None:
        """把 Tool 返回的 candidate dict 构造为 reverse TextEvidence。

        - source_role 强制 "unknown"（reverse-chase 阶段不做完整分类）
        - scope 走 resolve_evidence_scope（Task 7A）
        - evidence_text 超过 300 字符截断
        """
        evidence_text = cand.get("evidence_text")
        if not isinstance(evidence_text, str) or not evidence_text:
            return None
        if len(evidence_text) > 300:
            evidence_text = evidence_text[:300]
        page = cand.get("physical_page")
        return Evidence(
            fact_id=task.fact_id,
            source_type="text",
            value=cand.get("value"),
            unit=cand.get("unit"),
            page=page,
            evidence_text=evidence_text,
            confidence=None,
            source_role="unknown",
            scope=resolve_evidence_scope(task.scope, evidence_text, task.aliases),
        )

    def _execute_ocr(
        self,
        action: str,
        state: DrawingAgentState,
        document: Any,
    ) -> None:
        """OCR_PAGE 的实际执行：选下一页、调 ocr_tool、生成 DrawingEvidence。"""
        ocr_engine = getattr(state, "_ocr_engine", None)
        job_dir = getattr(state, "_job_dir", None)
        done_pages = {
            item.get("page")
            for item in state.actions_taken
            if item.get("action") == OCR_PAGE
        }
        target = None
        for cand in state.candidate_pages:
            if cand.get("physical_page") not in done_pages:
                target = cand
                break
        if target is None:
            self._finish(state, "ocr_no_evidence")
            return
        page = self._resolve_candidate_page(document, target)
        obs: dict[str, Any] = {"page": target.get("physical_page")}
        if page is None:
            obs["page_resolved"] = False
            state.actions_taken.append(
                {
                    "iteration": state.iteration + 1,
                    "action": OCR_PAGE,
                    "page": target.get("physical_page"),
                    "observation": obs,
                }
            )
            state.ocr_pages += 1
            return
        ocr_text = self.ocr_tool(page, ocr_engine, job_dir=job_dir)
        state.ocr_pages += 1
        obs["ocr_returned"] = ocr_text is not None
        evidence = self._extract_ocr_evidence(state.task, page, ocr_text)
        if evidence is not None:
            state.drawing_evidence.append(evidence)
            obs["evidence_created"] = True
            # Task 5B：OCR 命中后不自动 FINISH，让 decide_next_action 决定是否走 VLM
        else:
            obs["evidence_created"] = False
        state.actions_taken.append(
            {
                "iteration": state.iteration + 1,
                "action": OCR_PAGE,
                "page": page.physical_page,
                "observation": obs,
            }
        )

    def _resolve_candidate_page(self, document: Any, candidate: Mapping[str, Any]) -> Any:
        """从 recall 返回的 candidate dict 解析回 MinerUPage（按 physical_page 匹配）。

        返回 ``None`` 表示无法定位（不在 pages 列表里 / physical_page 缺失）。
        """
        target = candidate.get("physical_page")
        if target is None:
            return None
        for page in getattr(document, "pages", []) or []:
            if getattr(page, "physical_page", None) == target:
                return page
        return None

    def _extract_ocr_evidence(
        self,
        task: DrawingReviewTask,
        page: Any,
        ocr_text: str | None,
    ) -> Evidence | None:
        """OCR 文本含 task 任一 alias → 生成 DrawingEvidence。

        evidence_text 截取 alias 命中位置前后 80 字（硬上限 300）。
        本阶段不解析数值（value=None），由后续阶段补强。
        """
        if not ocr_text:
            return None
        for alias in task.aliases:
            idx = ocr_text.find(alias)
            if idx < 0:
                continue
            start = max(0, idx - 80)
            end = min(len(ocr_text), idx + len(alias) + 80)
            snippet = ocr_text[start:end]
            if len(snippet) > 300:
                snippet = snippet[:300]
            return Evidence(
                fact_id=task.fact_id,
                source_type="ocr",
                value=None,
                unit=task.unit,
                page=getattr(page, "physical_page", None),
                evidence_text=snippet,
                confidence=None,
                source_role="drawing_annotation",
                scope=resolve_evidence_scope(task.scope, snippet, task.aliases),
            )
        return None

    def _finish(self, state: DrawingAgentState, reason: str) -> None:
        state.finished = True
        state.finish_reason = reason

