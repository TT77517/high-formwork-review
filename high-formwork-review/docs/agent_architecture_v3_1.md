# 高支模专项方案智能审查 Agent 架构设计 V3.1（实施版）

> 状态：已确认，待实施
> 前置文档：V3 架构设计（受控混合式工程审查 Agent，2026-08-24）+ review 修改意见
> 本文档是**实施权威版**：V3 中与本文冲突的部分以本文为准，未提及的部分沿用 V3。
> 取代 `docs/agent_upgrade_design.md`（早期方案，其 Tier A/B 框架已被 V3 吸收）。

## 0. 修订记录（V3 -> V3.1）

| # | V3 原设计 | V3.1 修订 | 原因 |
|---|----------|----------|------|
| 1 | §10/§22 `llm.call(messages, tools=...)` 调用通道未定 | **明确：代码侧直连 LLM API（OpenAI 兼容协议 + 原生 function calling）**；Dify 仅保留批式通道 | Dify Workflow 无 tool calling；Dify Agent 应用需把本地检索暴露成 HTTP 工具（双跳延迟+鉴权面），且 Budget/去重/Evidence ID 护栏无法在循环内拦截。铁律已放开（2026-08-24），可引入新客户端依赖 |
| 2 | §16 "只 rerun 受影响规则" | **裁掉，第一期维持全量 rerun**（现有 `_rerun_review_stages` 全阶段重跑不动）；按规则增量 rerun 移入"可选 Phase 8"（需先建参数->规则依赖图） | 现有 rerun 无规则粒度索引与依赖图；比赛叙事不依赖它 |
| 3 | §6 Router 每规则 LLM 生成 route | **改为规则路由表 + 本地启发式**：规则库加 `route_hint` 字段（默认 LLM_READY），本地按"Fact 命中/证据召回量/冲突检测"判 LOCAL_READY 与 AGENT_REQUIRED/HUMAN_REQUIRED；LLM 不参与路由 | 87 条规则逐条 LLM 路由 = 87 次额外调用，比省下的还多；本地路由可测、可解释、稳定 |
| 4 | §15 Planner Replan 最多 1 次 | **第一期砍掉 Replan**，只保留 Plan + 执行统计观察（时间线展示）；Replan 移入"可选 Phase 9" | 单次同步管线中触发条件难以真实出现；避免答辩被问"何时真的触发过" |
| 5 | §11 `max_duplicate_calls=1` 语义未定义 | **定义死**：相同 `(tool, args)` 二次调用直接返回缓存结果并计入轮次；第三次重复强制 `finish(UNCERTAIN, reason=DUPLICATE_CALL)` | Budget 最容易被绕过的口子 |
| 6 | §20 缓存 key 含 tool_version | **确认维度**：`rule_definition + document_fingerprint + prompt_version + tool_version + model`；`tool_version` 必须落到常量并在工具返回格式变更时手动递增 | 批式缓存踩过"旧证据版本不命中"坑（PROGRESS.md 2026-08-23 记录），维度必须显式 |
| 7 | §8 Tool 5 get_page "不作为默认工具" | **加护栏**：get_page 进白名单但执行前先查 `max_pages_read`（默认 3），超限返回拒绝提示而非执行 | 页级兜底是 token 消耗大户 |
| 8 | §18 示例规则编号 `HF-JGJT231-6.2.5-03` | **统一用现有规则库编号体系**（`4.34`、`DR-01` 风格） | 落地时两套编号会造成规则库 CRUD 与报告错乱 |

## 1. 总体架构（双通道）

```
                ┌─────────────────────────────┐
                │      Review Planner         │  Plan（无 Replan）
                └──────────────┬──────────────┘
                               ▼
                ┌─────────────────────────────┐
                │      Deterministic Core     │  现有管线不动
                │  解析/完整性/Facts/规则/计算   │
                └──────────────┬──────────────┘
                               ▼
                ┌─────────────────────────────┐
                │      Semantic Router        │  本地路由表+启发式
                │  LOCAL / LLM / AGENT / HUMAN│
                └──────┬────────┬───────┬─────┘
                       ▼        │       ▼
            ┌──────────────┐    │  ┌──────────────────┐
            │ LOCAL_READY  │    │  │  AGENT_REQUIRED  │
            │ 本地规则引擎   │    │  │  Evidence Agent  │
            ├──────────────┤    │  │  代码侧 ReAct     │
            │ LLM_READY    │◄───┘  │  直连 LLM API     │
            │ Dify 批式工作流│ 降级  │  原生 tool calling │
            └──────┬───────┘      └────────┬─────────┘
                   │                       │
                   └───────────┬───────────┘
                               ▼
                ┌─────────────────────────────┐
                │      Result Validator       │
                │  Evidence ID / Schema 校验   │
                └──────────────┬──────────────┘
                   自动结果 │ 人工复核 -> overrides -> 全量 rerun
```

**通道职责划分**：

| 通道 | 承载 | LLM 客户端 | 状态 |
|------|------|-----------|------|
| 本地 | 规则引擎/计算校核/图文比对/门禁 | 无 | 现有，不动 |
| 批式 | LLM_READY 规则的批量语义判定 + 完整性复核 | `DifyClient.run_workflow`（现有） | 现有，不动 |
| Agent | AGENT_REQUIRED 规则的自主查证 | `llm_chat_client`（新增，直连 API） | 本方案新建 |
| 人工 | HUMAN_REQUIRED + UNCERTAIN 终态 | 无 | 现有复核队列扩展来源 |

降级链不变：**Agent(直连) -> 批式(Dify) -> 本地关键词**，两通道独立、互为兜底。

## 2. 新增 LLM Chat 客户端（`app/services/llm_chat_client.py`）

约 150 行，OpenAI 兼容协议（`/chat/completions` + `tools` 参数）：

```python
class LLMChatClient:
    """直连 LLM API 的 tool-calling 客户端，与 DifyClient 并列、职责互补。"""
    # 复用 DifyClient 的模式：from_env() 配置解析、重试+指数退避、
    # 超时（RETRYABLE_GATEWAY_STATUSES 同款处理）、DifyError 同款错误语义

    async def chat(self, messages, *, tools=None, temperature=0.1) -> ChatResponse
    # ChatResponse: content / tool_calls[{name, arguments}] / finish_reason / usage
```

配置（`.env`，回退顺序与现有 `DIFY_SEMANTIC_API_KEY` 模式一致）：

```text
LLM_AGENT_API_KEY=        # 必填（agent 模式启用时）
LLM_AGENT_BASE_URL=       # 如 https://api.deepseek.com / dashscope compatible-mode
LLM_AGENT_MODEL=          # 须支持 function calling（qwen-plus/max、deepseek-chat、glm 系列均可）
LLM_AGENT_TIMEOUT_SECONDS=60
```

选型原则：非思考型快速模型（批式通道已验证思考型模型超时风险）；供应商沿用现有可用账号，key 不入 git。

## 3. Router 设计（本地化修订版）

路由决策**零 LLM 调用**，分两层：

**第一层：规则路由表（静态）**
规则库（`config/rule_library_v4/` 语义规则）增可选字段：

```json
{
  "rule_id": "4.34",
  "route_hint": "LOCAL_READY"
  // 可选值: LOCAL_READY | LLM_READY | AGENT_REQUIRED | AUTO（默认 AUTO）
}
```

- 数值比较类规则（如 4.34 扫地杆≤200mm、4.35 螺杆外伸≤300mm）标 `LOCAL_READY`：Fact 已识别时直接本地判定（规则引擎已有该能力，Router 只是把语义阶段的这类规则分流过去，避免重复送 LLM）
- 疑难规则（历史上批式 UNCERTAIN 率高的）可标 `AGENT_REQUIRED`

**第二层：本地启发式（route_hint=AUTO 时）**

```text
Fact 冲突/多值           -> HUMAN_REQUIRED
结构化 Fact 命中且规则可数值比较 -> LOCAL_READY
初始证据召回 >= 阈值(如 2 段命中) -> LLM_READY
初始证据召回不足/跨章节关键词分散 -> AGENT_REQUIRED
```

输出（落盘 `route_decisions.json`，前端"审查路径标签"读它）：

```json
{"rule_id": "4.34", "route": "AGENT_REQUIRED",
 "reason": "INITIAL_EVIDENCE_INSUFFICIENT", "decided_by": "heuristic"}
```

## 4. Evidence Agent（`semantic_agent.py` + `agent_tools.py` + `agent_guardrails.py`）

沿用 V3 §7-§13 全部设计（工具 8 个、Evidence Registry、Evidence ID-only 引用、ReAct 循环、状态机、Result Validator、Prompt Injection 防护），仅以下修订生效：

### 4.1 循环实现（原生 function calling）

```python
async def run_evidence_agent(rule, context, client, tools, budget):
    messages = [system_prompt(rule), user_prompt(rule, context)]
    trace = []
    while budget.can_continue():
        resp = await client.chat(messages, tools=TOOL_SPECS)   # 原生 tool calling
        if resp.finish_reason == "tool_calls":
            for call in resp.tool_calls:
                action = guardrails.check(call, budget)         # 白名单/预算/去重拦截
                result = tools.dispatch(action)                 # 本地执行
                evidence_registry.register(result)              # 全部登记为 Evidence Object
                trace.append(trace_step(action, result))
                messages.append(tool_result_message(action, result))
        else:  # finish：模型给出最终判定
            return validator.validate_finish(resp, rule, evidence_registry)
    return uncertain(rule, reason="AGENT_BUDGET_EXHAUSTED", trace=trace)
```

### 4.2 Budget（V3 §11 + 修订 #5）

```text
max_rounds = 3          # LLM 调用轮次（每轮可含多个 tool_call）
max_tool_calls = 5      # 工具调用总数
max_search_calls = 2    # search_document 专属
max_pages_read = 3      # get_page / get_drawing_blocks 共享计数
max_context_chars = 12000
去重：相同 (tool, args) 第 2 次返回缓存并计轮次；第 3 次强制 finish(UNCERTAIN, DUPLICATE_CALL)
```

### 4.3 缓存（修订 #6）

```text
key = sha256(rule_definition + document_fingerprint + AGENT_PROMPT_VERSION
             + AGENT_TOOL_VERSION + LLM_AGENT_MODEL)
value = {result, evidence_ids, trace}
```

`AGENT_TOOL_VERSION = "tools-v1"` 常量；任何工具返回格式变更必须递增。

### 4.4 与现有架构接线

- `SEMANTIC_REVIEW_MODE` 扩展：`local | dify | agent`（默认不变；`agent` = Router+双通道混合）
- `run_semantic_stage` 分发：agent 模式下先跑 Router，按 route 分流四路；Agent 路失败降级批式（复用 `semantic_dify.py` 现有降级），批式失败降级本地关键词
- 适用性门禁（PENDING_CONFIRMATION / NOT_APPLICABLE）在 Router 之前，本地判定，不进任何 LLM
- `agent_trace.json`、`route_decisions.json`、`evidence_registry.json` 落盘 job 目录（Memory 设计沿用 V3 §17）

## 5. Planner（简化版，`review_planner.py`）

保留 V3 §4 输入输出与 §5 Mandatory Checks（强制检查白名单，Planner 无权关闭）。

修订：
- **无 Replan**。执行后把观察统计（各 route 数量、Agent 恢复率、事实冲突数）写入 `plan_observations.json` 并展示在时间线--这是诚实的 Observe，不触发重规划
- Planner 本身允许两种实现，实施时按 Phase 6 时间盒决定：①单次 LLM 调用生成 focus_areas（V3 §4.2 原样）；②时间盒不够时降级为纯本地统计生成（零 LLM，规则/事实统计出重点，故事完整性不受损，只是少一层"LLM 规划"叙事）

## 6. 前端（V3 §23 三区域不变）

A. Agent 审查计划（读 `review_plan.json`）
B. 审查路径标签（读 `route_decisions.json`：规则引擎/LLM/Agent 查证/人工确认）
C. Agent Trace 抽屉（读 `agent_trace.json`，复用现有证据灯箱组件渲染 Evidence 对应的图/表）

## 7. Benchmark（V3 §24 不变，补充基线）

基线数据现成：job `2d6b084f`（批式：33 COMPLIANT / 14 VIOLATED / 37 UNCERTAIN，~3 分钟）。
核心指标：**Agent Recovery Rate**（原本 UNCERTAIN 且 Agent 找到新证据形成判定的比例）与 **Citation Validity**（引用 Evidence ID 100% 可解析--结构性保证）。

## 8. 实施计划（Phase 0-7，约 6 天）

| Phase | 内容 | 估算 | 交付物 |
|-------|------|------|--------|
| 0 | 能力验证：选定模型 tool calling 稳定性（3 条规则手工跑通循环） | 0.5 天 | 验证记录 + 最终模型选型 |
| 1 | Evidence Layer：Evidence Object/ID/Registry/Validator | 0.5 天 | `agent_guardrails.py` 数据层部分 |
| 2 | Agent Loop：`llm_chat_client.py` + `semantic_agent.py` + 5 个核心工具（search/get_context/get_table/get_section/finish） | 1 天 | agent 模式可跑 |
| 3 | 真实规则测试：5-10 条批式疑难规则 | 0.5 天 | Recovery 数据 |
| 4 | Router：route_hint 字段 + 本地启发式 + `route_decisions.json` | 0.5 天 | 四路分流生效 |
| 5 | Guardrails 收尾：Budget/缓存/get_page+get_drawing_blocks 工具/注入防护/Trace 落盘 | 1 天 | 全护栏生效 |
| 6 | Planner（Plan-only，含时间盒降级预案） | 0.5 天 | `review_plan.json` |
| 7 | 前端三区域 + 190 测试回归 + E2E | 1 天 | 演示就绪 |

可选（比赛时间富余才做）：Phase 8 参数->规则依赖图+按规则增量 rerun；Phase 9 Replan。

## 9. 已确认决策记录

1. **2026-08-24 铁律更新**：允许为比赛 Agent 化改造引入新技术栈（AGENTS.md/CODEX_CONTEXT.md 已改），约束：用户确认方案、小步提交可回退、不破坏确定性引擎与 190 测试
2. **双通道**：Agent 循环代码侧直连 LLM API 原生 tool calling；Dify 保留批式通道；不上 LangGraph 等框架（50 行循环足够，答辩口径"评估过，确定性需求用代码更可控可测"）
3. **V3 为主体**，本文 8 处修订生效；`agent_upgrade_design.md` 被 V3/V3.1 取代
