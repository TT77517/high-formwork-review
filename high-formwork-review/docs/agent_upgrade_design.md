# 比赛 Agent 化改造方案：从 Workflow 到 Agent

> ⚠️ **本文档已被取代（2026-08-24）**：架构方案演进为 V3（受控混合式）+ V3.1（实施版，见 `docs/agent_architecture_v3_1.md`）。本文的 Tier A/B 框架已被 V3 吸收，调用通道等关键决策以 V3.1 为准。

> 状态：设计稿（未实施）。实施前需用户确认。
> 定位：在不推翻现有审查管线的前提下，补齐"LLM 自主规划 / 自主调用工具 / 自主迭代"三个 Agent 核心能力，形成可对比赛评委讲述的完整 Agent 故事。

## 1. 背景与差距

### 1.1 现状（Workflow 架构）

当前系统是一条 Python 硬编码的确定性 DAG 流水线：

```
PDF 上传 -> MinerU 解析 -> 完整性审查 -> _run_review_stages：
  参数识别 -> 工程基础信息 -> 规则引擎(本地) -> 语义审查(LLM 单次判定)
  -> 计算校核(本地) -> 实质性/一致性/图文校验 -> 报告
-> 人工复核队列 -> 参数修正 -> rerun 重跑闭环
```

语义审查（`app/services/semantic_dify.py`）的 LLM 使用方式是"固定投喂 + 单次判定"：
本地证据召回一次性打包 -> 8 条规则/批送 Dify -> 校验返回。LLM 没有工具、没有循环、对流程零控制权。

### 1.2 评审视角的差距

比赛评审认定的 Agent 三个标志能力，当前均缺失：

| 能力 | Agent 要求 | 当前实现 |
|------|-----------|---------|
| 自主规划 | LLM 决定做什么、按什么顺序 | 阶段顺序写死在 Python |
| 工具调用 | LLM 主动检索信息、调用系统能力 | 证据本地召回后一次性投喂，LLM 无法追加 |
| 自主迭代 | 证据不足时自己再查、反思、直到有结论 | 单次调用，证据不足直接 UNCERTAIN |

结论：**不是要重写，而是把现有管线"降级"为 Agent 的工具层，在其上加一层 LLM 控制权**。

### 1.3 现有资产到 Agent 概念的映射（讲故事的素材）

| 现有组件 | Agent 概念 |
|----------|-----------|
| 各审查阶段函数 | 工具（Tools） |
| job 目录 JSON 落盘 | Agent 记忆（file-based memory） |
| 证据召回器 `build_semantic_evidence` | 检索原语（供 agent 主动调用） |
| 人工复核队列 + rerun overrides | Human-in-the-loop 工具 |
| 批级缓存 / 结果校验 / 降级 | 安全护栏（工程加分项，保留并强化） |

## 2. 目标与非目标

**目标**
1. 语义审查具备工具循环（Agentic RAG）：LLM 自主决定检索什么、看哪页、何时停止
2. 增加"审查规划 Agent"：按工程特征动态生成审查计划（LLM 出计划、代码执行，可控可审计）
3. 全链路留下 agent 决策轨迹（agent_trace.json），供演示与审计
4. 现有 workflow 作为兜底路径保留，任何 agent 失败自动降级，任务永不中断
5. 可量化的比赛指标：UNCERTAIN 显著下降、自主检索命中率、人工复核闭环耗时

**非目标**
- 不引入 LangChain/LangGraph 等新框架（违背项目"不引入新技术栈"规则，且无必要）
- 不做多 Agent 辩论/投票（Tier C，除非赛项明确要求 multi-agent）
- 不改变"不输出最终合格/不合格结论"的产品边界

## 3. 总体架构

```
┌────────────────────────────────────────────────────────────┐
│                    Agent 编排层（新增）                       │
│  规划 Agent（Tier B）：qualification/facts -> 审查计划 JSON   │
│  审查 Agent（Tier A）：规则 + 工具循环 -> 判定 + 证据          │
├────────────────────────────────────────────────────────────┤
│                    工具层（现有代码包装）                     │
│  search_document(keywords)   get_page(n)   get_table(id)    │
│  get_drawing_blocks(n)       run_calculation()              │
│  request_human_confirmation()（挂复核队列）                   │
├────────────────────────────────────────────────────────────┤
│                    护栏层（强化现有）                         │
│  结果校验（rule_id/枚举/证据回填） 批级+轨迹级缓存              │
│  三级降级（agent -> 批式 LLM -> 本地关键词） 审计 agent_trace  │
└────────────────────────────────────────────────────────────┘
```

## 4. Tier A：Agentic 语义审查（核心，必做）

### 4.1 工具集定义

| 工具 | 入参 | 返回 | 底层实现 |
|------|------|------|---------|
| `search_document` | keywords: list[str] | 命中章节摘要（≤5 段，含 block_id/页码） | 复用 `_find_relevant_sections` |
| `get_page` | page: int | 该页全部 block 文本（≤4000 字符） | MinerUDocument 遍历 |
| `get_table` | block_id: str | 表格 HTML/结构化行 | 现有 table block 直读 |
| `get_drawing_blocks` | page: int | 图纸页文本 + OCR 结果 | 复用 RapidOCR 通道 |
| `finish` | status, reason, evidence_quote, confidence | 结束循环，产出判定 | - |

规则上下文（规则条文、规范原文、semantic_judgment）随系统提示一次性给足，不占工具。

### 4.2 工具循环（代码侧实现，LLM function calling）

```python
# app/services/semantic_agent.py（新增）
def review_rule_with_agent(rule, document, tools, client, *, max_rounds=3):
    messages = [system_prompt(rule), user_prompt(rule)]
    trace = []
    for round in range(max_rounds):
        resp = client.chat(messages, tools=TOOL_SPECS)   # 复用/扩展现有 DifyClient
        if resp.tool_call == "finish":
            return validate_and_build(resp, rule, trace)  # 复用现有校验器
        result = tools.dispatch(resp.tool_call)           # 本地执行工具
        messages.append(tool_result(result))
        trace.append({"round": round, "tool": resp.tool_call, "args": resp.args})
    return uncertain_result(rule, trace)                  # 轮次耗尽，诚实放弃
```

关键决策：
- **max_rounds=3**：最多 3 轮工具调用。足够体现"迭代"，成本可控（单规则最多 4 次 LLM 调用）
- **单规则单循环，规则间并发**：与现有批式不同，agent 模式按规则粒度跑，复用 `asyncio.Semaphore` 并发模式（默认 3）
- **证据回填**：`finish` 的 evidence_quote 仍走 `_locate_llm_quote` 滑窗匹配回填 block/页码，但 agent 模式下引用天然来自工具返回的原文，命中率会更高
- **每条规则一个 agent_trace**：轮次、调用过哪些工具、看过哪些页，全部落盘

### 4.3 与现有架构的集成

- `SEMANTIC_REVIEW_MODE` 扩展为 `agent | dify | local`（现有配置解析加一档，默认不变）
- `run_semantic_stage` 分发：agent 模式 -> 逐规则 agent 循环；失败降级链：**agent -> 批式 Dify -> 本地关键词**（现有两级降级原样保留）
- 适用性门禁不变（PENDING_CONFIRMATION / NOT_APPLICABLE 仍本地判定，不进 LLM）

### 4.4 缓存策略

批式缓存的 key 是"证据包 hash"，agent 模式没有固定证据包。改为**轨迹缓存**：
`cache_key = sha256(规则定义 + 文档指纹 + prompt_version + model)`，命中时直接返回上次的最终判定与轨迹。轨迹里的工具调用不重放（结果确定性由文档指纹保证）。

### 4.5 预期收益与度量

| 指标 | 基线（批式，job 2d6b084f） | agent 模式预期 | 采集方式 |
|------|---------------------------|---------------|---------|
| UNCERTAIN 数 | 37/84 | 目标 <20 | 同文档对比跑 |
| 证据带页码定位率 | 32 条受益于滑窗回填 | 接近 100% | trace 统计 |
| 单规则成本 | ~1 次调用 | 1~4 次调用 | dify_call_audit |
| 总耗时 | ~3 分钟（11 批） | 预计 5~8 分钟（并发 3） | stage_timings |

同一样例双模式对比跑一次，就是比赛 PPT 的核心数据页。

## 5. Tier B：审查规划 Agent（轻量版）

### 5.1 设计

不让 LLM 直接执行流程（不可控），而是**LLM 生成计划、代码执行计划**：

```
输入：project_qualification + project_facts + 规则库统计
输出：审查计划 JSON（白名单校验后执行）
{
  "stages": [
    {"stage": "semantic_engine", "params": {"applicable_types": "pankou"}},
    {"stage": "drawing_review", "params": {}, "reason": "图文参数已识别 8 项"},
    {"stage": "calculation_engine", "skip": false},
    ...
  ],
  "escalations": [
    {"item": "support_span=48m 超合理界", "action": "request_human_confirmation"}
  ]
}
```

### 5.2 护栏

- **阶段白名单**：计划中的 stage 必须在白名单内，未知阶段直接拒绝、回退默认全量计划
- **计划 diff 展示**：agent 计划 vs 默认计划的差异落盘并展示在时间线（评委可见"agent 在思考"）
- 单次 LLM 调用（非循环），失败回退默认计划，风险极低

### 5.3 讲故事的价值

Tier A 回答"agent 会自己查证据"，Tier B 回答"agent 会自己安排审查重点"——识别出盘扣体系就聚焦盘扣规则、缺关键参数就先挂人工确认。这两点合起来是完整的"规划 + 执行 + 工具"Agent 叙事。

## 6. 比赛叙事与演示脚本

### 6.1 一句话定位

"面向高支模专项方案的审查 Agent：规划自主、检索自主、判定可溯、人工兜底。"

### 6.2 演示流程（约 5 分钟）

1. **上传 PDF** -> 时间线展示 agent 生成的审查计划（与默认计划 diff 高亮）
2. **语义审查阶段** -> 实时展示某条规则的 agent 轨迹：`search_document("扫地杆 高度")` -> `get_page(46)` -> `finish(VIOLATED, 引用原文)`（前端加轨迹抽屉，复用证据灯箱组件）
3. **结果页** -> 双模式对比数据：UNCERTAIN 37 -> N，VIOLATED 均带 agent 自主检索到的页码证据
4. **人工复核闭环** -> 修正步距 -> rerun -> 结果翻转（现有能力，强调 human-in-the-loop 是 Agent 架构的一部分）
5. **工程护栏页**（备讲）-> 三级降级链、轨迹级缓存、校验器拦截幻觉的次数统计

### 6.3 架构话术要点

- 工具层 = 保留的确定性引擎（规则/计算/图文比对不过 LLM，成本与可复现性优势）
- 护栏层 = LLM 输出必须过校验、证据必须回填真实 block、失败三级降级
- 对照常见 ReAct agent：我们不是"LLM 自由循环"，而是"受控自主"——每轮工具有白名单、轮次有上限、结论有校验——这正是工程化落地 agent 与 demo agent 的区别（把约束讲成卖点）

## 7. 实施计划

| 阶段 | 内容 | 预估 | 交付物 |
|------|------|------|--------|
| A1 | `semantic_agent.py` 工具循环 + 5 个工具 + DifyClient function calling 扩展 | 1 天 | agent 模式可跑单规则 |
| A2 | 校验/降级/轨迹缓存接线 + `agent` 模式开关 + 轨迹落盘 | 0.5 天 | E2E 双模式对比数据 |
| B1 | 规划 agent + 计划白名单校验 + 默认计划回退 | 0.5 天 | 计划 diff 落盘 |
| B2 | 前端：agent 轨迹抽屉 + 时间线计划展示 | 1 天 | 演示界面 |
| 测试 | 单测（工具分发/循环终止/降级链）+ 现有 190 测试回归 | 0.5 天 | 全绿 |

总计约 3.5 天。每阶段独立可交付、独立可回退（模式开关默认不变，现有行为零风险）。

## 8. 风险与对策

| 风险 | 对策 |
|------|------|
| 单规则多轮调用导致耗时/成本上升 | 并发 3 + 轨迹缓存 + max_rounds=3 硬上限 |
| LLM 滥用工具（反复查无关页） | 工具返回带截断、轮次上限、trace 审计暴露 |
| function calling 依赖模型能力 | 工具 spec 用最简 JSON schema；若模型不支持，降级批式（现有链路兜底） |
| 降级链过深难排查 | agent_trace.json 记录降级原因；dify_call_audit 增加 agent 维度统计 |
| 比赛答辩被问"为什么不用 LangGraph" | 答：编排确定性需求 + 零依赖 + 可测试性；文档第 6.3 节话术 |

## 9. 决策待确认项

1. Tier B 是否进第一期（建议进，轻量且演示价值高）
2. agent 模式的 LLM 供应商：沿用当前 Dify 工作流背后的快速模型，还是需要 function calling 原生支持更好的模型（涉及账号/成本）
3. 前端轨迹展示做到抽屉级还是时间线级（抽屉级 1 天，时间线级再 +0.5 天）
