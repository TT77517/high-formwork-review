# PROGRESS.md — 项目进度看板 & Agent 交接日志

> **这是多 Agent 协作的中枢文件。每次签到/签退必须更新此文件。**

## 📊 当前状态总览

- **项目版本**：v4.0（规则引擎 + 规则库 CRUD + AntD Pro 风格 UI）
- **最近提交**：`aea8018` feat: 审查证据带图展示——表格真渲染灯箱+图像通道+缓存携图
- **分支**：main（远程 origin/main）
- **最后更新**：2026-08-21

## ✅ 已完成

- [x] PDF 上传 + MinerU 解析基础流程
- [x] 本地完整性审查（10 条规则，章节/要素/结构证据）
- [x] Dify 完整性语义复核（on_demand / full 模式）
- [x] Dify 缓存 + 调用审计
- [x] MinerU 解析结果缓存（按文件 hash）
- [x] 审查报告生成与导出
- [x] v4.0 规则引擎（32 条计算规则 + 84 条语义规则）
- [x] 规则库 CRUD（增删改查）
- [x] Web 审查模块重构（4 核心 Tab + 规则库管理）
- [x] 图文一致性校验（正文参数与图纸文本数值交叉比对）
- [x] 规范筛选 + 规则详情编辑入口
- [x] 规范注册表（config/standards.json + app/standards.py；/api/standards；规则 standard_id/standard_refs 标注与规范精确过滤）
- [x] qualification 输出 applicable_standards（按支撑体系派生，未识别仅列通用规范附 note）+ 报告适用规范行
- [x] 前端规范词汇统一：规则库规范筛选改注册表词汇、工程基础信息页适用规范 chips 点击跳转规则库筛选
- [x] qualification 接通跨度/总荷载/线荷载三参数（键名不变、requires_review 口径不变）+ 未识别时 pending_confirmation 摘要（各体系待执行专属规则数）
- [x] 引擎适用性门禁共享（system_applicability_status）：支撑体系未识别时体系专属规则记 PENDING_CONFIRMATION（待人工确认后重跑），已识别不匹配仍 NOT_APPLICABLE；report/summary/前端状态词、筛选、统计卡同步
- [x] 文档解析页章节聚合+钻取：一级章节主表（页范围/文本量/图表/partial/需复核）展开页行、Block 分布条折叠、抽屉所见即所得（表格真渲染/图片直显/原文折叠）
- [x] 文档解析页改三级钻取表（章节→小节→页），移除右侧长目录，全宽表格+操作提示
- [x] 统一人工复核队列后端：human_review_queue 增 item_key、引擎 VIOLATED 逐条（按等级排序）、体系待确认聚合项、解析风险页聚合项（带 deep-link）、qualification 队首项 actionable（确认支撑体系选项）；decisions 端点支持 item_key（旧 rule_id payload 兼容）；报告复核表改事项编号
- [x] 人工复核前端重写为统一工作台：按来源分组（识别/审查范围/规则引擎/语义/完整性/实质性/一致性/图文/文档解析）、证据跳转（页抽屉/规则详情/文档筛选）、确认支撑体系+重跑按钮（startPolling 复用）、概览卡改队列口径；浏览器冒烟通过
- [x] 重跑闭环：POST /api/jobs/{id}/rerun（support_system 覆盖，422/409 校验），_process_job 抽 _run_review_stages 复用，mineru_cache 公开 document_from_dict；重跑写 human_overrides.json、facts 标 human_override、清理非完整性复核记录、重建 precheck summary 与报告

## 🔲 待完成

- [x] 修复"规范审查方式暂不可用"——后端 REVIEW_MODES 未同步新模式名（已验证修复完整）
- [x] MinerU 缓存验证（同 PDF 二次上传不调 MinerU / 改名同内容命中 / 同名不同内容不命中 / 缓存损坏自动失效）
- [x] 规范语义审查 Agent 架构设计（完成设计文档，待实施）
- [ ] 更多规范规则的补充与完善
- [ ] 测试覆盖补充
- [x] 修复剩余 3 个存量测试失败（2026-08-21：test_web 文案断言更新为现行五模式、compliance→smart、DR-01→DR-90 编号迁移；全套件转绿 156 passed）
- [x] Web UI 页面改进（P0，识别驱动重构 9 个提交：规范注册表/适用规范展示/章节聚合/待确认状态/统一复核工作台/重跑闭环）
- [x] 审查结果页体验增强：五处分页（10/20/50）+统计卡点击联动筛选、计算校核页改公式验算/参数一致性双卡片组（双侧对比+证据页跳转）、图文卡片展示正文值vs图纸标注值、drawing_review 交叉比对结果补正文 text_evidence；浏览器冒烟通过
- [x] 证据图像/表格展示：API 出口层按 block_id 动态补 image_path+table_html（老任务免重跑生效）；计算/语义引擎证据补 block 定位（page 不再为 None）；前端证据缩略图+灯箱（表格真渲染/图像大图/打开所在页/查看原图/404降级）；MinerU 缓存携带 raw 图像资源（命中时还原）；重跑 demo 验证全链路
- [x] 语义审查 Agent 代码侧实施（系统侧全就绪，待 Dify Workflow 建台联调）：app/services/semantic_dify.py（适用性门禁本地判定不进 LLM / 本地证据提取分批 / Dify Workflow 调用 / 结果校验 / 批次级缓存 / 单批失败降级本地关键词）；SEMANTIC_REVIEW_MODE=local|dify 开关（默认 local，行为不变）；DIFY_SEMANTIC_API_KEY 配置（回退 DIFY_API_KEY）；web+CLI 双接线；5 个测试；Workflow 建台规格：docs/semantic_review_workflow_spec.md；Dify Cloud 连通性已验证（完整性 workflow key 有效）

## 🚧 当前阻塞

（无）

## 📌 下一步建议

1. **在 Dify 控制台创建"规范语义审查"Workflow**（规格：`high-formwork-review/docs/semantic_review_workflow_spec.md`，含验收自测命令）→ 拿到新 app key 填 `DIFY_SEMANTIC_API_KEY`、设 `SEMANTIC_REVIEW_MODE=dify`，上传样例联调
2. 规则库 standard_id 落盘（目前为运行时归一化附加），便于离线统计与清洗"住建部令[2018]31号"等疑似误写

> ✅ 已完成（2026-08-21）：MINERU_API_TOKEN 已配置（.env，gitignore），样例已重解析——922 张图像落盘新任务 `12a62f8b`（mineru_api/raw），缓存条目开始携带 raw 资源，文档解析抽屉/证据图像通道浏览器验证 200。旧任务 `129b4a90` 无图（解析早于 token），重跑不触发重解析，如需图像可重新上传。

## ⚠️ 已知测试问题（2026-08-21 claude 诊断，a20b549 基线）

> ✅ 全部解决（2026-08-21 claude）：①py3.9 收集错误 3 处已修复；②test_web 两个过期断言已更新（文案改现行五模式、compliance→smart）；③DR-01 召回测试按其编号迁移改为 DR-90（召回类条目从 DR-01 移至 DR-90，功能本身一直正常）。当前基线：**157 passed / 1 skipped / 0 failed**。

> 更新（2026-08-21 claude）：py3.9 收集错误 3 处已修复（test_dify_cache/test_review 加 `from __future__ import annotations`、test_dify 去 `zip(..., strict=True)`），全量测试解锁为 140 passed / 3 failed / 1 skipped；剩余失败即下文第 2、3 两项。

`cd high-formwork-review && .venv/bin/python -m pytest` 结果：**4 failed, 99 passed, 1 skipped, 2 collection errors**（Desktop 与 dewuclaw 两份副本结果完全一致，确认为存量问题）：

1. **Python 3.9 兼容性（收集错误 + 1 失败）**
   - `tests/test_dify_cache.py:12`、`tests/test_review.py:30`：函数签名注解用了 `dict | None` / `str | None`（PEP 604，3.10+），3.9 下 import 即报 TypeError
   - `tests/test_dify.py:351`：`zip(..., strict=True)`（3.10+ 语法）
   - 注：本机仅有 Python 3.9.6，装 `eval_type_backport` 无效（它只对 `get_type_hints` 生效）
2. **测试断言过期（test_web 2 个失败）**
   - `test_home_page_shows_modular_review_modes`：断言旧文案"规范符合性审查"，当前 UI 已改为"规范语义审查"等新模式
   - `test_upload_creates_job`：传 `review_mode=compliance`，但 `app/web.py:73` 的 `REVIEW_MODES = {smart, completeness, semantic, drawing, calculation}` 已无 `compliance`（与 dewucode 2026-08-20 手工验证结论矛盾——手工验证通过的记录未同步到测试）
3. **DR-01 缺失（test_vertical_slice 1 个失败）**
   - `test_drawing_review_recalls_related_drawing_pages`：`build_drawing_review` 输出中无 `DR-01` 条目（KeyError），需查 `app/drawing_review.py` 规则配置

## 🔄 Agent 交接日志（Handoff Log）

> 格式：`[时间] agent名称 签到/签退 — 内容`

- [2026-08-20 17:30] dewuclaw 签到 — 创建 AGENTS.md / PROGRESS.md / 迁移 CODEX_CONTEXT.md，建立多 Agent 协作基础设施

- [2026-08-20 17:52] dewuclaw 签退 — 完成了：建立 enforcement 机制：git hooks + 签到签退脚本 + Makefile；下一步建议：验证 967951c 修复完整性

- [2026-08-20 18:00] dewuclaw 签到 — 开始处理：创建 ONBOARDING.md + Windows PowerShell 脚本 + 更新所有入口文件

- [2026-08-20 18:00] dewuclaw 签退 — 完成了：创建 ONBOARDING.md(双场景指南)+agent-protocol.ps1(Windows脚本)+更新AGENTS/CLAUDE/.cursorrules；下一步建议：验证967951c修复完整性+规划规范语义审查Agent

- [2026-08-20 18:11] dewucode 签到 — 开始处理：使用样例文件上传到web运行，并review出现的问题

- [2026-08-20 19:30] dewucode 签退 — 完成了：样例PDF上传测试和系统功能验证；下一步建议：修复代码结构问题和配置问题

- [2026-08-20 19:45] claude 签到 — 开始处理：合并两个 app 目录，统一代码结构

- [2026-08-20 19:50] claude 签退 — 完成了：代码结构统一，删除冗余嵌套目录；下一步建议：验证规范审查模式修复

- [2026-08-20 19:55] claude 签到 — 开始处理：验证规范审查模式修复完整性

- [2026-08-20 20:00] claude 签退 — 完成了：验证所有审查模式正常工作；下一步建议：MinerU 缓存验证

## 📋 代码结构合并记录（2026-08-20 19:45）

### 合并操作
1. 从嵌套目录 `high-formwork-review/high-formwork-review/app/` 复制更新的文件到主目录 `high-formwork-review/app/`
2. 已复制的文件：
   - `main.py` - 添加规则引擎和报告生成器的导入和调用
   - `parameter_definitions.py` - 添加 v4.0 确定性规则扩展参数
3. 待删除：冗余的嵌套目录 `high-formwork-review/high-formwork-review/`
4. 已删除：使用 `git rm -r` 删除嵌套目录，统一代码结构

## 📋 测试报告（2026-08-20 19:30）

### 测试环境
- 样例文件：`rule/04_方案样本/高支模方案.pdf`（214页）
- 审查模式：智能预审（smart）
- 任务ID：`1c7fadda5ab94690bf86fcdf4578b86d`

### 功能验证结果

| 模块 | 状态 | 结果 |
|------|------|------|
| PDF上传 + MinerU解析 | ✅ 正常 | 使用缓存，解析耗时约10秒 |
| 完整性审查 | ✅ 正常 | 10/10 PASS |
| 确定性规则引擎 | ✅ 正常 | 28条规则：11合规, 6违规, 11无法判定 |
| 语义规则引擎 | ✅ 正常 | 84条规则：30合规, 0违规, 54无法判定 |
| 计算规则引擎 | ✅ 正常 | 32条规则：18合规, 0违规, 14无法判定 |
| 参数一致性检查 | ✅ 正常 | 4项：2 PASS, 2 REVIEW |
| 图文一致性校验 | ✅ 正常 | 5项：1 PASS, 3 ISSUE, 1 REVIEW |

### 发现的问题

#### 1. 代码结构问题（严重）
存在两个嵌套的 app 目录，导致功能缺失：
- **主目录**：`high-formwork-review/app/`（缺少关键文件）
- **嵌套目录**：`high-formwork-review/high-formwork-review/app/`（包含完整代码）

缺失文件需要手动复制：
- `rule_engine.py` - 确定性规则引擎
- `semantic_engine.py` - 语义规则引擎
- `calculation_engine.py` - 计算规则引擎
- `report_generator.py` - 报告生成器
- `config/rule_library_v4/` - v4.0规则库配置

#### 2. 配置问题
- MinerU API Token 未配置（`.env` 中为空）
- 需要手动复制 MinerU 缓存目录到 `data/cache/mineru/`

#### 3. 依赖问题
- Python 3.9 需要安装 `eval_type_backport` 包支持新语法

#### 4. 审查结果问题
- 语义规则引擎：54/84 条规则状态为 UNCERTAIN，需要人工复核
- 图文一致性校验：发现 3 项 ISSUE（步距、可调托撑悬臂长度等参数不一致）

### 建议修复
1. 合并两个 app 目录，统一代码结构
2. 补充 `.env.example` 中的配置说明
3. 在 `requirements.txt` 中添加 `eval_type_backport` 依赖
4. 优化语义规则引擎的关键词匹配逻辑，减少 UNCERTAIN 结果

## ✅ 规范审查模式验证报告（2026-08-20 20:00）

### 测试环境
- 样例文件：`rule/04_方案样本/高支模方案.pdf`（214页）
- 测试模式：semantic、calculation、drawing
- 任务ID：
  - semantic: `d690953d020e4721ada18e1098b0a062`
  - calculation: `46921c37346f43f488510214c761b037`
  - drawing: `a3d9416baf744a1888b2d851b4771ad5`

### 验证结果

| 审查模式 | 上传状态 | 处理状态 | 审查结果 |
|---------|---------|---------|---------|
| semantic | ✅ 正常 | ✅ completed (100%) | 84条规则：30合规, 0违规, 54无法判定 |
| calculation | ✅ 正常 | ✅ completed (100%) | 32条规则：18合规, 0违规, 14无法判定 |
| drawing | ✅ 正常 | ✅ completed (100%) | 0条（未找到相关数据） |

### 结论
✅ **规范审查模式修复完整**
- 所有审查模式（smart、completeness、semantic、calculation、drawing）都能正常接受和处理
- 后端 REVIEW_MODES 定义与前端 MODES 定义一致
- 不再出现"规范审查方式暂不可用"错误

### 下一步建议
1. MinerU 缓存验证
2. 规范语义审查 Agent 架构规划

- [2026-08-21 10:30] claude 签到 — 开始处理：Desktop 副本同步至 a20b549 + 基线测试验证；发现并诊断 6 个存量测试失败（详见"已知测试问题"），准备进入 P0 Web UI 改进

- [2026-08-21 13:24] claude 签到 — 开始处理：P0 Web UI 页面改进——现状梳理 + 与用户沟通改进方向

- [2026-08-21 13:59] claude 签到 — 开始处理：P0 Web UI 改进——针对用户 4 点反馈（工程基础信息展示/规则包按规范展示/解析明细可视化/按工程特征匹配规则/人工复核定位）梳理现状并讨论改进方案
- [2026-08-21 15:20] claude 签退 — 完成了：P0 Web UI 识别驱动重构（规范注册表+适用规范展示、qualification 三参数接线、引擎 PENDING_CONFIRMATION、文档解析章节聚合+抽屉所见即所得、统一人工复核工作台、POST /rerun 重跑闭环，10 个提交，153 测试通过/存量 3 败未触碰，浏览器冒烟通过）；下一步建议：修复剩余 3 个存量测试失败；语义审查 Agent 复用 PENDING_CONFIRMATION/重跑机制
- [2026-08-21 16:05] claude 补充提交 — 文档解析页按用户选择改三级钻取表（章节→小节→页），移除右侧长目录；浏览器验证通过
- [2026-08-21 16:40] claude 补充提交 — 钻取表增强：展开箭头+节/页计数+首章默认展开；叶子章节行点击直开内容抽屉；章节/小节行“查看内容”按钮打开整段所见即所得抽屉（≤12 页）

- [2026-08-21 17:58] claude 签到 — 开始处理：收尾未提交改动：审查结果页分页+卡片联动筛选+证据展示，验证后提交

- [2026-08-21 18:11] claude 签退 — 完成了：收尾提交 f789271：审查结果页分页+统计卡联动筛选、计算校核双卡片组、图文证据展示、drawing_review 补正文证据；重启 dev server 后浏览器冒烟全部通过；下一步建议：修复 3 个存量测试失败（test_web 过期断言 2 + DR-01 召回 1）；随后按 docs/semantic_agent_design.md 实施语义审查 Agent

- [2026-08-21 18:20] claude 签到 — 开始处理：修复 3 个存量测试失败（test_web 过期断言 2 + DR-01→DR-90 编号迁移）

- [2026-08-21 18:23] claude 签退 — 完成了：修复 3 个存量测试失败（54f1f1a）：test_web 文案断言更新为现行五模式、compliance→smart、DR-01→DR-90 编号迁移；全套件转绿 156 passed/1 skipped/0 failed；下一步建议：按 docs/semantic_agent_design.md 实施语义审查 Agent（复用 PENDING_CONFIRMATION/重跑闭环）；规则库 standard_id 落盘

- [2026-08-21 18:31] claude 签到 — 开始处理：审查结果页证据图片展示：API出口层按block_id补image_path + 前端缩略图/灯箱 + 计算引擎公式验算证据补定位

- [2026-08-21 18:52] claude 签退 — 完成了：证据图像/表格展示全链路：API出口层按block_id补image_path+table_html、计算/语义引擎证据补block定位、前端缩略图+灯箱（表格真渲染）、MinerU缓存携带raw图像；157测试全绿+浏览器冒烟通过+重跑demo验证；下一步建议：配置MINERU_API_TOKEN后重解析补图像jpg；随后按设计文档实施语义审查Agent

- [2026-08-21 19:39] claude 签到 — 开始处理：MinerU重解析样例验证图像证据（token已配置，922图落盘）

- [2026-08-21 19:41] claude 签退 — 完成了：MinerU重解析完成：token配置+922图落盘新任务12a62f8b+缓存携raw生效+抽屉图像200验证；表格证据真渲染+图像通道全部就绪；下一步建议：NEXT=语义审查Agent实施（docs/semantic_agent_design.md）；规则库standard_id落盘

- [2026-08-22 21:59] claude 签到 — 开始处理：语义审查Agent实施：Dify集成（设计规格文档+代码实现+降级机制）
