# 项目上下文（CODEX_CONTEXT.md）

> **最后更新**：2026-08-20
> **维护方式**：每次有重大阶段进展时更新此文件。日常进度看 `PROGRESS.md`。

## 项目名称

高支模专项施工方案智能审查系统

## 当前主流程

```
PDF上传
→ MinerU解析（带文件 hash 缓存）
→ 本地完整性审查（10条规则）
→ Dify完整性语义复核（on_demand / full 模式，可选）
→ 规则引擎审查（84条语义规则 + 32条计算规则）
→ 图文一致性校验（正文参数与图纸文本数值交叉比对）
→ 审查报告生成与导出
→ 人工确认
```

## 当前项目版本：v4.0

主要模块（`high-formwork-review/app/` 下）：

| 模块 | 文件 | 状态 |
|------|------|------|
| PDF 解析 | `mineru_client.py`, `mineru_parser.py`, `mineru_cache.py` | ✅ 含缓存 |
| 完整性审查 | `completeness_review.py` | ✅ 10条规则 |
| Dify 语义复核 | `dify_scheme.py`, `dify_cache.py`, `dify_config.py`, `completeness_review_selector.py` | ✅ on_demand/full |
| 语义规则引擎 | `rule_engine.py`（语义部分） | ✅ 84条 |
| 计算规则引擎 | `rule_engine.py`（计算部分） | ✅ 32条 |
| 图文一致性校验 | `drawing_review.py` | ✅ 正文参数与图纸交叉比对 |
| 实质性审查 | `substantive_review.py` | ✅ |
| 事实冲突检测 | `fact_conflict_detector.py` | ✅ |
| 参数提取与归一化 | `parameter_extractor.py`, `parameter_normalizer.py`, `parameter_definitions.py` | ✅ |
| 项目信息提取 | `project_facts.py`, `project_qualification.py` | ✅ |
| 审查报告 | `review_summary.py`, `review_comparison.py` | ✅ |
| Web 界面 | `web.py` + `templates/` + `static/` | ✅ 4核心Tab+规则库CRUD |

## 历史阶段记录

### 阶段 A-E：Dify 完整性审查集成（已完成）

- A. DIFY_COMPLETENESS_MODE 机制
- B. CompletenessResult 置信度和语义复核字段
- C. completeness_review_selector 及 dify_selection.json
- D. on_demand 模式（仅请求 selected_rule_ids）/ full 模式 / selected_count=0 跳过 Dify
- E. 单规则证据上限8000字符 / 最多3个证据片段 / Dify 部分规则返回校验
- 提交：`998edde`

### 阶段 F：MinerU 解析缓存（已完成）

- 按文件 hash 缓存解析结果
- 提交：`0826c75`

### 阶段 G：v4.0 规则引擎 + 规则库 CRUD（已完成）

- 32 条计算规则（公式验算项目存在性检查）
- 84 条语义规则（本地关键词匹配模式）
- 规则库增删改查
- AntD Pro 风格 UI
- Web 审查模块重构为 4 核心 Tab
- 提交：`ac0a983` → `e0750ec`

### 阶段 H：图文一致性校验（已完成）

- 正文参数与图纸文本数值交叉比对
- 单位统一处理
- 提交：`e13bee8` → `fe79b6c`

### 阶段 I：Bug 修复（部分完成）

- `967951c` — 后端 REVIEW_MODES 未同步新模式名（可能不完整，待验证）
- `fe79b6c` — 确定性规则引擎 section_path 报错 + 图文交叉验证单位统一

## 尚未开发的阶段

- **规范语义审查 Agent** — 独立阶段，当前仅有本地关键词匹配，无深度语义理解
- **MinerU 缓存验证用例** — 需验证：同名不同内容不命中 / 缓存损坏自动失效等
- **测试覆盖补充**

## 开发禁止事项

1. 不修改 MinerU 底层解析逻辑
2. 不改变 10 条完整性规则的业务含义
3. 不引入 React / Vue / Redis / Celery / 数据库等新技术栈（除非用户明确要求）
4. 不输出最终"合格/不合格"结论——只做审查提示
5. 不大规模重构项目目录
6. 先读后写，小步提交，提交前跑测试
