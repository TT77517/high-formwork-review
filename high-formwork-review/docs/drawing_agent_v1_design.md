# 图文一致性 Agent 下一阶段方案（Task 7+）

> **作者**：claude
> **日期**：2026-08-27
> **状态**：草案，待用户确认
> **适用范围**：高支模专项施工方案智能审查系统
> **承接**：`drawing_agent.py`（Task 0-6.3 已落地，13 个测试全绿，636 行）

## 1. 背景与现状

### 1.1 已有能力（Task 0-6.3 已完成）

| Task | 能力 | 行数 | 测试 |
|------|------|------|------|
| 0 | 基线审计（339/339 passed） | 0 | 0 |
| 1 | 公开 Tool wrapper + OCR 单页抽取 | +84 | +1 |
| 2 | 数据模型（Task/Evidence/State） | +72 | +1 |
| 3 | 候选核验任务生成器 | +143 | +1 |
| 4 | `DrawingConsistencyAgent` V1 有限状态循环 | +135 | +3 |
| 5A | OCR_PAGE 按需追证 | +145 | +4 |
| 5B | INSPECT_IMAGE + VLM 兜底 | +116 | +4 |
| 5C | 真实 Vision Provider Adapter（Qwen-VL） | +217（独立模块） | +6 |
| 6 | SEARCH_TEXT 双向追证 | +97 | +4 |
| 6.1 | value-anchor 语义修正 | +54 | 0（复用） |
| 6.2 | alias-local value binding | +62 | 0（复用） |
| 6.3 | before-alias 边界修正 | +24 | 0（复用） |
| **合计** | **636 行核心 + 217 行 vision + 13 测试** | | **13** |

### 1.2 未完成事项

1. **未接入业务流**——`build_drawing_review`（`drawing_review.py:177`）仍跑老 `_cross_check_param` 链路；Agent 模块孤岛
2. **无 scope 字段**——`DrawingReviewTask.scope` 硬写 `{}`，未与支撑体系（koujian/pankou/wankou）联动
3. **无结果聚合**——Agent 多状态输出与 drawing_review 结果 schema 未对齐
4. **无前端可视化**——`actions_taken`/`finish_reason` 落不进详情抽屉
5. **无 OCR/VLM 缓存**——同任务重跑 27s 重复开销
6. **无端到端 benchmark**——仅 13 个单测覆盖，未跑真实任务验证恢复率

## 2. 目标

把 `DrawingConsistencyAgent` 从「孤岛模块」升级为「可灰度的业务内核」，并在真实样例上验证 OCR/VLM 分级追证能否把旧 `REVIEW` 转为 `PASS/ISSUE` 而不增加误报。

**关键指标**（与 Task 0-6.3 单测互补）：

| 指标 | 目标 | 测量方式 |
|------|------|----------|
| Recovery Rate | 旧 REVIEW/UNCERTAIN → PASS/ISSUE ≥ 30% | 真实样例对照 |
| False Issue Rate | 旧 PASS → ISSUE ≤ 5% | 真实样例对照 |
| Avg Trace Length | ≤ 4 actions/任务 | benchmark 统计 |
| Avg Total Time | 10 参数 ≤ 30s（无 VLM）/ ≤ 90s（含 VLM） | benchmark 统计 |
| VLM Fallback Hit Rate | OCR 全部 miss 且 VLM 命中 ≥ 20% | benchmark 统计 |
| 缓存加速比 | 同任务重跑 OCR/VLM 调用 = 0 | 二次跑样本 |

## 3. 方案分阶段（Task 7-12）

### 3.1 Task 7：业务接线 + Feature Flag（核心，0.5 天）

**新增**：`build_drawing_review_v2(parsed_document, project_facts, *, job_dir, agent_enabled=False)`

**开关**：
- env `DRAWING_AGENT_ENABLED` 默认 `false`（保守）
- `false` → 直接转调旧 `build_drawing_review`（结果 100% 等同）
- `true` → 走 Agent 全量

**入参**：
- `parsed_document` / `project_facts` / `job_dir` 与旧版一致
- `agent_enabled` 来自 env 解析；调用方不传

**Agent 入参构造**（核心改造点）：
- `recall_tool = drawing_review.recall_drawing_pages`（Task 1 公开）
- `check_tool = drawing_review.cross_check_param`（Task 1 公开）
- `ocr_tool = drawing_review.ocr_drawing_page`（Task 1 公开）
- `vision_tool = drawing_vision.inspect_drawing_page`（Task 5C 公开）
- `search_text_tool = drawing_review.search_text_evidence`（Task 6 公开）
- `tasks = build_drawing_review_tasks(facts, DRAWING_PARAM_REGISTRY)`（Task 3）
- 旧 `DRAWING_CROSS_CHECK_PARAMS` 自动复用为 registry

**回退路径**：
- Agent 单个 Task 异常 → 记 trace error → 该 Task 降级为旧 `cross_check_param` 输出
- Agent 全程异常 → 整体回退旧 `build_drawing_review` 完整结果
- 不修改 `main.py:98` / `web.py:1367` 调用点

**测试**：2 个
- `test_build_drawing_review_v2_disabled_matches_v1`（关闭 = 旧基线，逐字段对照）
- `test_build_drawing_review_v2_enabled_returns_compatible_shape`（开启 = Agent 输出 shape 与 v1 兼容）

**行数预算**：~80 行（`drawing_review.py` +50 / `tests` +30）

### 3.2 Task 8：scope 字段扩展（体系门禁，0.3 天）

**改造点**：
- `DrawingReviewTask.scope` 允许承载 `{"support_system": "koujian"}` 等
- registry 项可声明 `applies_to_systems: ["koujian", "universal"]`（默认 `["universal"]`）
- `build_drawing_review_tasks` 在生成 Task 时按 `project_facts["facts"]["support_system"]` 预过滤
- 加 helper `scope_matches(task, support_system)` 单测覆盖

**行数预算**：~40 行（`drawing_agent.py` +25 / `tests` +15）

### 3.3 Task 9：结果聚合（Agent → drawing_review，0.5 天）

**新增**：`aggregate_agent_states(states, registry) -> list[dict]`

**输出 schema**（与旧 `_cross_check_param` 100% 兼容）：
```python
{
    "rule_id": "DR-01",                   # 由 fact_id 派生
    "name": "步距",
    "status": "PASS" | "ISSUE" | "REVIEW",
    "value": "1500",                      # 正文值
    "drawing_value": "1500",              # 图纸值（VLM 抽取）
    "evidence": [...],                    # 含 OCR/VLM/text/source 标签
    "agent_trace": {                      # 新增字段，Agent 独有
        "finish_reason": "ocr_evidence_found",
        "actions_taken": [...],
        "ocr_pages": 1,
        "vlm_calls": 0,
        "iterations": 2,
    }
}
```

**关键决策**：
- status 判定沿用 `_build_cross_result` 逻辑（value 一致=PASS，否则=ISSUE/REVIEW）
- VLM 抽出的 value 若与正文不一致 → ISSUE
- VLM 未调用 / 调用失败 → 沿用旧 REVIEW 口径（不编造）
- DR-90 召回卡按聚合后的 drawing_evidence 重建

**行数预算**：~120 行（`drawing_agent.py` +90 / `tests` +30）

### 3.4 Task 10：前端轨迹展示（0.5 天）

**改造点**：
- `templates/drawing_review.html` + `static/js/app.js`
- 每个 cross-check 卡片底部新增「Agent 查证轨迹」折叠区
- 渲染 `finish_reason` / `actions_taken` 时间线（search→check→ocr→vlm→search_text）
- 显示实际 OCR 页数 / VLM 次数 / 总迭代次数
- DR-90 召回卡保持兼容

**测试**：2 个
- `test_web_returns_agent_trace_field`（API 出口含 `agent_trace`）
- `test_web_omits_agent_trace_when_disabled`（关闭时不返回）

**行数预算**：~150 行（template +30 / js +100 / tests +20）

### 3.5 Task 11：OCR/VLM 缓存（0.3 天）

**新增**：
- `cache_ocr_page(job_dir, page_hash, ocr_text)` / `cache_vlm_page(job_dir, page_hash, result)`
- 写入 `job_dir/drawing_agent_cache.json`（与 `mineru_cache` 同模式）
- Agent 启动时一次性预热所有候选页

**Key 维度**：`(job_id, physical_page, ocr_engine_version)` / `(job_id, physical_page, vlm_model)`

**行数预算**：~50 行（`drawing_review.py` +30 / `tests` +20）

### 3.6 Task 12：真实样例 Benchmark（0.5 天）

**样例选择**（已有真实任务）：
- 小（< 50 页）：`12a62f8b`（214 页 → 选 50 页子集）
- 中（50-150 页）：`2d6b084f`（84 条规则 Dify 验证）
- 大（> 200 页）：`bfcbbcfe`（缓存命中验证）

**测试维度**：
| 维度 | 旧 baseline | Agent | 提升 |
|------|------|------|------|
| 图文项数 | 8 项 | 15 项（新增 7 项 VLM 抽取） | +87% |
| Recovery Rate | 0% | ≥ 30% | +30% |
| False Issue Rate | — | ≤ 5% | — |
| Avg Trace Length | 0 | ≤ 4 actions | — |
| Avg Total Time | ~3s | ≤ 30s | — |
| VLM Fallback Hit | 0 | ≥ 20% | — |
| 重跑加速比（同任务） | 27s | < 1s | 27× |

**产出**：
- `docs/drawing_agent_benchmark.md`（报告）
- `docs/drawing_agent_benchmark_data.json`（明细）

**行数预算**：~80 行（脚本 + 报告）

## 4. 风险与对策

| 风险 | 等级 | 对策 |
|------|------|------|
| VLM 误识（VLM 把"900"看成"600"） → 假 ISSUE | 高 | Task 7 用 `_values_match` 严格相等 + 0.1 容差；Task 12 benchmark 监控 False Issue Rate |
| VLM 抽到非目标值（如识图出"附注：500"） | 中 | Task 5C 已限定 VLM 返回 schema；本设计保持只信 `value`/`unit`/`evidence_text` |
| Agent 单 Task 异常导致整条结果缺失 | 中 | Task 7 加单 Task 降级：异常 → 走旧 `cross_check_param` |
| 性能退化（VLM 慢） | 中 | Task 11 缓存 + Task 12 benchmark 监控 Avg Total Time ≤ 90s |
| VLM 成本（每页 ¥0.01） | 中 | Task 7 默认关闭，按需开启；Task 12 benchmark 给成本估算 |
| 任务并发下缓存冲突 | 低 | 缓存按 `job_id` 隔离；不在并发层共享 |
| 旧 `build_drawing_review` 行为漂移 | 低 | Task 7 `agent_enabled=False` 路径下输出 100% 等同旧版（强测试断言） |

## 5. 不在范围内

明确不做（避免越界）：

1. **不改 MinerU 底层解析**——按项目铁律
2. **不重构 drawing_review 既有链路**——只在 _v2 旁路
3. **不动 main.py / web.py 调用点**——避免影响其他模块
4. **不做 LLM 驱动的内部 Planner**——Task 6 已是 deterministic policy；不引入 LLM 调度（与 V3.1 架构保持一致：确定性内核优先）
5. **不改 PROJECT_FACTS 写回**——Agent 只读 facts，不写（Task 6 设计已约束）
6. **不引入新数据库/Redis**——缓存走 job_dir 文件（与 mineru_cache 一致）
7. **不改报告生成器 / Web 详情抽屉主体**——只在卡片底部追加折叠面板

## 6. 时间表

| Task | 预计 | 累计 |
|------|------|------|
| 7 业务接线 | 0.5 天 | 0.5 天 |
| 8 scope 字段 | 0.3 天 | 0.8 天 |
| 9 结果聚合 | 0.5 天 | 1.3 天 |
| 10 前端展示 | 0.5 天 | 1.8 天 |
| 11 OCR/VLM 缓存 | 0.3 天 | 2.1 天 |
| 12 真实样例 benchmark | 0.5 天 | 2.6 天 |

总计 2.6 天（合 1 个完整工作周内完成）。

## 7. 决策点（待用户确认）

1. **Task 7 是否立即启动**？（推荐：是）
2. **Task 8 scope 字段优先级**？（推荐：紧跟 Task 7，0.3 天）
3. **Task 12 benchmark 样例是否指定**？（默认按 §3.6 三档）
4. **VLM 默认走哪个模型**？（推荐：复用 `LLM_AGENT_MODEL` 链 + 单独 `VLM_MODEL` env，Qwen-VL-Plus）
5. **灰度节奏**？（推荐：Task 7-9 内部 dev 自测，Task 11 完成后开 env 上传 1 个真实任务验证，Task 12 benchmark 报告通过后默认开）

## 8. 关联文档

- `agent_architecture_v3_1.md`：V3.1 总控架构（确定性内核优先原则的源头）
- `agent_upgrade_design.md`：原升级方案（已部分过时）
- `phase3_benchmark.md`：规范语义 Agent benchmark 模板（Task 12 借鉴）
- `drawing_calculation_method.md`：图文与计算校核的现状/演进文档

## 9. 签退与追踪

- 入口检查：先读 `AGENTS.md` / `PROGRESS.md` / 本文件
- 签到：每 Task 开始前 `make checkin AGENT=claude TASK="Task N: ..."`
- 签退：每 Task 完成后更新 `PROGRESS.md` + `make checkout`
- 提交：每 Task 一个小 commit，前缀 `feat:` / `fix:` / `docs:`
- 测试：每 Task 完成后 `cd high-formwork-review && python -m pytest -v`
