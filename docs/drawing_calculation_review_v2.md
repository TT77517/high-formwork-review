# 图文一致性与计算校核优化方案 v2

> 基于 commit `569a941` 代码实测后的修订版

## 一、已实现现状评估

其他 agent（codex）已在 commit `569a941` 中实现了原计划 90% 的内容。

### ✅ 已正确实现

| 计划项 | 状态 | 位置 |
|--------|------|------|
| 三段式解释结构 | ✅ | calculation_engine._calculation_explanation / drawing_review._review_explanation |
| 图文证据质量5级标签 | ✅ | drawing_review._evidence_quality（原文/表格/OCR/证据弱/数值冲突） |
| 立杆稳定性复算 | ✅ | calculation_rechecker._recheck_stability |
| 托撑承载力复算 | ✅ | calculation_rechecker._recheck_jack_capacity |
| 缺参数归因 | ✅ | calculation_rechecker._uncertain → uncertainty_category |
| 总控 parameter_to_rules | ✅ | orchestrator_agent._parameter_to_rules |
| 总控 drawing_evidence_quality | ✅ | orchestrator_agent._drawing_evidence_quality_summary |
| 总控 formula_recalculations 接入真实复算 | ✅ | _formula_rechecks 优先读 calculation_recheck |
| 人工复核参数聚合 | ✅ | app.js._missingParamGroupsFromQueue |
| 前端三段式展示 | ✅ | app.js.reviewExplanationHtml（计算/图文/语义详情） |
| 前端复算标签+输入表 | ✅ | app.js.calcRecheckTagHtml / calcRecheckHtml |
| 前端图文质量标签 | ✅ | app.js.drawingQualityTagHtml |
| uncertainty_analysis 四类归因 | ✅ | uncertainty_analysis.py |

### 🔴 发现的Bug

#### Bug 1: 长细比复算参数提取错误（P0 严重）

```
输入: "λ=l0/i=2250/15.9=141.5≤150"
期望: lambda = 2250 / 15.9 = 141.5
实际: lambda = 2250 / 2250 = 1.0   ← 完全错误
```

根因：`_find_number_after_labels` 用 `\bi\b` 匹配回转半径 i，但 `λ=l0/i=2250` 中 NFKC 归一化后 `i` 成为独立词被命中，取到 2250。`_parse_fraction_after_lambda` 正则要求 `λ` 和数字间不能有 `l0/i`，匹配失败。

影响：所有 `λ=l0/i=A/B=结果≤限值` 格式的长细比验算都算出 1.0，应 ISSUE 变 PASS。

#### Bug 2: 测试断言不严格

当前测试只检查 `computed_value < allowed_value` 和 `'2250' in substituted_expression`，不检查计算值是否等于 141.5。Bug 被测试放行。

### 🟡 需改进

1. **参数提取正则间距太窄**：fallback pattern 间距 12 字符，真实计算书 "稳定系数 φ = 0.45" 有空格可能匹配不到
2. **复算覆盖面窄**：仅 6 条规则，真实样例 18 条 UNCERTAIN 中复算可能只覆盖 3 条
3. **旧任务无新字段**：现有任务数据 predates 新代码，需重新上传验证
4. **φ 查表依赖未处理**：仅处理计算书显式给出 φ 的情况（v1 正确行为，v2 可扩展）

## 二、修复实施计划

### Phase 1: 修复长细比复算 Bug（P0）

修改 `calculation_rechecker.py`：

1. 修复 `_parse_fraction_after_lambda`：允许 `λ` 后跟 `l0/i=` 再跟分数 `A/B`
2. 修复 `_find_number_after_labels` 对 `i` 的匹配：不用 `\bi\b`，改用 `i=` 或 `回转半径` 精确匹配
3. 增加 explicit_lambda 提取：从 `=数字≤` 模式直接提取最终计算值
4. 修复测试断言：`assert result['computed_value'] == 141.5`

### Phase 2: 参数提取正则增强（P1）

1. fallback 间距 12→25
2. strip 空格逻辑
3. 支持全角等号 `＝` 和冒号赋值

### Phase 3: 真实样例验证

重新上传 PDF 到 `http://127.0.0.1:8002/`，检查 calculation/drawing/orchestrator JSON 新字段，浏览器验证展示。

## 三、结论

原计划 90% 已实现，架构合理。主要修复长细比复算 Bug + 加强测试断言 + 正则鲁棒性，修复后达到计划目标。
