# Phase 0 能力验证记录（2026-08-24）

> 对应 `agent_architecture_v3_1.md` §8 Phase 0。脚本：`scripts/phase0_tool_calling_check.py`
> 测试文档：job `2d6b084f`（214 页样例，Dify 批式基线 33 COMPLIANT / 14 VIOLATED / 37 UNCERTAIN）

## 结论：✅ 通过，模型选定 qwen-plus

| 验证项 | 结果 |
|--------|------|
| 模型选型 | `qwen-plus`（百炼 OpenAI 兼容模式，`https://dashscope.aliyuncs.com/compatible-mode/v1`） |
| function calling 稳定性 | ✅ 全部轮次 tool_calls JSON 合法、零解析失败；模型会自主细化检索关键词 |
| 多轮循环 | ✅ tool_call -> 本地执行 -> 结果回填 -> 迭代 -> finish 全链路通 |
| Agent Recovery 实证 | ✅ 规则 2.11 批式 UNCERTAIN -> Agent 2 轮 COMPLIANT（γQ=1.5 计算书 P125 等 4 处） |

## 三条规则明细

| 规则 | 批式 | Agent | 轨迹摘要 |
|------|------|-------|---------|
| 2.7 倾倒冲击荷载 | UNCERTAIN | UNCERTAIN(0.3) | 3 轮检索（含规范量纲关键词 2/4/6kN/m²）后强制交卷诚实放弃；理由含查证轨迹（page 49/60/70 仅有 G4k 侧压力） |
| 2.11 活载分项系数 | UNCERTAIN | **COMPLIANT(1.0)** | R1 检索命中 P125 参数表，R2 立即 finish；引用 γQ=1.5 满足 ≥1.5 |
| 5.1 钢管规格 | VIOLATED | UNCERTAIN(0.3) | 检索命中 P12 技术参数页但摘要截断未露出钢管行，未找到 Φ48×3（证据层质量问题，见发现 3） |

## 模型候选对比

| 模型 | tool calling | 结论 |
|------|-------------|------|
| qwen3.5-ocr | ❌ 返回 tool_calls=null + 幻觉内容 | OCR 专用模型，不适用于对话循环 |
| **qwen3.8-max** | ✅ 支持 | **模型链首选**（详见下节补充验证） |
| qwen-plus | ✅ 参数 JSON 干净 | 链尾兜底（付费账号，已充值） |
| qwen3-max | ⚠️ 可用但 arguments 内含换行（解析需容错） | 备选 |

## 补充验证（2026-08-24 充值后）：模型链 + qwen3.8-max 质量

账号充值后 6 模型全部恢复。`LLM_AGENT_MODEL` 升级为**逗号分隔优先级链**，额度耗尽自动轮转（脚本已实现并验证：欠费 Arrearage / 限流 429/Throttling / 额度耗尽 / 模型不存在 均触发切换；切换粘性 + 审计记录）：

```text
qwen3.8-max,qwen3.7-plus-2026-05-26,qwen3.8-2.4t-a95b,qwen3.8-27b,qwen3.7-max-2026-06-08,qwen-plus
```

（前 5 个有免费额度优先消耗，已充值的 qwen-plus 垫底兜底）

**qwen3.8-max 三规则复跑结果**（Phase 0 判定质量优于 qwen-plus）：

| 规则 | qwen-plus | qwen3.8-max |
|------|-----------|-------------|
| 2.7 | UNCERTAIN(0.3) | UNCERTAIN(0.75)，查证角度更全（溜槽/导管/料斗/泵送/浇筑速度） |
| 2.11 | COMPLIANT(1.0) | COMPLIANT(0.92)，参数表+计算公式交叉验证（q₂=γ₀×γL×1.5×bQ₃k） |
| 5.1 阳性对照 | ❌ UNCERTAIN（未找到证据） | ✅ **VIOLATED(0.88) 且证据校验通过**--P11 材料需要计划表"Φ48×3.0"，与批式基线判定一致、引用逐字真实 |

新发现：qwen3.8-max 会**单轮并行调用多个工具**（一轮发两组 search），查证效率更高。

**结论：模型链首选 qwen3.8-max（免费且质量更优），Phase 2 生产客户端继承链式轮转设计。**

## 四个设计发现（反哺 V3.1）

1. **预算用尽必须强制交卷**：三条规则全部用满 3 轮、无一主动 finish。Budget 实现须加"最后一轮仅提供 finish 工具"（脚本已验证该模式有效，2.7 的 UNCERTAIN 即强制交卷产出）
2. **quote 文本校验太脆，Evidence ID 必要性实证**：2.11 的证据真实存在（P125 表确有 γQ=1.5）但模型轻微改写表格措辞，滑窗匹配判"未能定位"。V3.1 的"只准引用 Evidence ID、不准自填原文"是结构性解法，Phase 1 落地
3. **检索摘要截断是真问题**：5.1 阳性对照失败根因--`search_document` 命中正确页面（P12 技术参数）但 block 预览截断没露出钢管规格行。Phase 1 证据层需做：命中 block 内行级截取、表格感知召回
4. **page 参数需校验**：2.7 的 finish 返回过 page=-1，Result Validator 须加 page∈[1,总页数] 校验

## 环境配置（已写入本地 .env，不入 git）

```text
LLM_AGENT_API_KEY=sk-***
LLM_AGENT_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_AGENT_MODEL=qwen-plus
```

## 下一步：Phase 1（Evidence Layer）

Evidence Object/ID/Registry/Validator + 检索质量改进（发现 2、3 的解法），约 0.5 天。
