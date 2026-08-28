# PROGRESS.md — 项目进度看板 & Agent 交接日志

> **这是多 Agent 协作的中枢文件。每次签到/签退必须更新此文件。**

## 📊 当前状态总览

- **项目版本**：v4.0（规则引擎 + 规则库 CRUD + AntD Pro 风格 UI）
- **最近提交**：`0b123b7` fix: Dify Workflow 执行失败时透传底层错误信息
- **分支**：main（远程 origin/main）
- **最后更新**：2026-08-23

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
- [x] 上下文连续性协议（避免上下文过载）：scripts/context_handoff.sh / .ps1 一键生成 .context/handoff.md（分支/最近提交/未提交改动/当前阻塞/待完成未完成项/可选本轮要点+启动提示词）；make handoff 目标；AGENTS.md 增入口协议"续接检查"步与"上下文连续性协议"小节；.context/ 入 .gitignore（support_system 覆盖，422/409 校验），_process_job 抽 _run_review_stages 复用，mineru_cache 公开 document_from_dict；重跑写 human_overrides.json、facts 标 human_override、清理非完整性复核记录、重建 precheck summary 与报告
- [x] Web 端总控审查 Agent 工作台（2026-08-25）：任务概览改为"上传解析→Agent识别工程特征→Agent制定审查计划→完整性审查工具→规范审查Agent→计算校核工具→图文一致性工具→人工复核→报告生成"；四类审查能力以 Agent 工具卡呈现；规范语义审查默认切到 agent 模式并在页面显示；时间线按业务调度顺序展示；关键测试与浏览器验证通过
- [x] 后端总控 Agent 统一落盘对象（2026-08-25）：新增 `app/orchestrator_agent.py`，生成 `orchestrator_agent.json`（统一 `dispatch_plan` / `tool_observations` / 参数候选池 / 参数冲突人工确认 / 文档解析修正重跑上下文 / 3-5 条公式复算摘要 / 图文一致性 Agent 追证联动状态）；新增 `GET /api/jobs/{id}/orchestrator`，前端任务概览改读统一总控观测；证据召回补目录降权与章节二次追证；Router 修正 `conflict` 状态参数分流为 HUMAN_REQUIRED
- [x] 无法判定归因展示（2026-08-25）：新增 `uncertainty_analysis.py`，把完整性/确定性/语义/计算的 UNCERTAIN 归为真缺内容、缺参数、证据不足、规则过宽四类；总控 `orchestrator_agent.json` 增 `uncertainty_analysis`；规范语义审查页“无法判定来源”升级为四类归因卡片，展示数量、建议动作和代表规则；老任务缺总控产物时保留原粗粒度兜底
- [x] 浏览器批注收敛（2026-08-25）：审查记录时间线改为默认折叠；规范语义审查页移除整块“无法判定归因”面板，归因改为每条 UNCERTAIN 规则的标签和详情抽屉说明（真缺内容/缺参数/证据不足/规则过宽），减少页面占用
- [x] 图文一致性与计算校核解释闭环（2026-08-25）：新增确定性 `calculation_rechecker`，首批支持长细比、立杆稳定性、可调托撑承载力真实复算；计算结果输出代入式/输入来源/复算状态/三段式解释；图文一致性结果增加原文/表格/OCR/证据弱/数值冲突质量标签与三段式解释；总控 Agent 增 `parameter_to_rules`、`formula_recalculations` 复算明细和 `drawing_evidence_quality`；前端规则/计算/图文详情与人工复核参数重跑区内联展示
- [x] 计算参数依赖与图纸几何反哺（2026-08-26，claude）：①`calculation_dependencies.py` 扩展至 26 个参数/60+ 条规则（覆盖侧压力 2.8/2.19、面板 3.1-3.3、次/主楞 3.4-3.7、地基 3.19、抗倾覆 3.20/3.25、扣件式立杆 3.26/3.27），新增 `parameters_for_formula_id` 与 `dependencies_by_formula` 反向聚合；②`parameter_definitions.py` 增 23 个计算输入参数（γc/t0/H/坍落度/β/β1/β2/面板宽/楞梁截面/楞梁间距/N/A/fa/γ0/MR/MT/Wk/μz），unit=mm² 修正 base_plate_area；③`parameter_extractor.py` 新增 `symbolic_numeric` 抽取模式（处理 γc=24、\gamma_c LaTeX 残片、fa=120kPa、γ0=1.0），归一化提取到 `app/text_utils.py`；④`app/drawing_geometry.py` 新增图纸几何/构造参数抽取（11 类参数：立杆纵/横距/步距/扫地杆/托撑悬臂/丝杆外露/垫板/剪刀撑间隔/面板厚/次主楞间距）与正文 ProjectFacts 交叉比对（MATCH/CONFLICT/SUPPLEMENT 三态），drawing 页判定修正（_is_drawing_page 增加 page_type 判定 + 关键词命中门槛）；⑤28 个测试全绿（22 新增 + 6 审查回归保护）

## 🔲 待完成

- [x] 修复"规范审查方式暂不可用"——后端 REVIEW_MODES 未同步新模式名（已验证修复完整）
- [x] MinerU 缓存验证（同 PDF 二次上传不调 MinerU / 改名同内容命中 / 同名不同内容不命中 / 缓存损坏自动失效）
- [x] 规范语义审查 Agent 架构设计（完成设计文档，待实施）
- [x] **比赛 Agent 化改造**（方案：`docs/agent_architecture_v3_1.md`；**Phase 0-7 全部完成** 2026-08-24）：V3 受控混合式架构全量落地--Planner（LLM计划+本地降级）/Router（route_hint+启发式四分流）/确定性内核/Dify批式/Guardrailed ReAct Agent（EV ID证据制+Budget+三级降级）/人工闭环；263测试全绿；Phase 3 Benchmark：Recovery 5/9(56%)+Citation 100%；Phase 7 E2E：全流程456.9s（Planner LLM生成5重点/9 Agent规则发现2新VIOLATED 6.18防护用品+6.29应急物资/审计35次LLM）；前端三区域（计划卡/路径标签/Trace抽屉）+review-plan API
  - ⚠️ **遗留外部问题**：E2E 中 Dify 批式通道 5 批全部失败（[Tongyi] Incorrect model credentials--Dify 控制台里配的通义模型凭证失效，疑与百炼账号充值/换key有关），已按设计逐批降级本地关键词（任务不中断）但批式质量受损；需用户在 Dify 控制台更新模型凭证后重跑验证
- [ ] 更多规范规则的补充与完善（85条空关键词已补全，剩余待持续优化）
- [ ] 测试覆盖补充
- [x] 修复剩余 3 个存量测试失败（2026-08-21：test_web 文案断言更新为现行五模式、compliance→smart、DR-01→DR-90 编号迁移；全套件转绿 156 passed）
- [x] Web UI 页面改进（P0，识别驱动重构 9 个提交：规范注册表/适用规范展示/章节聚合/待确认状态/统一复核工作台/重跑闭环）
- [x] 审查结果页体验增强：五处分页（10/20/50）+统计卡点击联动筛选、计算校核页改公式验算/参数一致性双卡片组（双侧对比+证据页跳转）、图文卡片展示正文值vs图纸标注值、drawing_review 交叉比对结果补正文 text_evidence；浏览器冒烟通过
- [x] 证据图像/表格展示：API 出口层按 block_id 动态补 image_path+table_html（老任务免重跑生效）；计算/语义引擎证据补 block 定位（page 不再为 None）；前端证据缩略图+灯箱（表格真渲染/图像大图/打开所在页/查看原图/404降级）；MinerU 缓存携带 raw 图像资源（命中时还原）；重跑 demo 验证全链路
- [x] 语义审查 Agent 代码侧实施（系统侧全就绪，待 Dify Workflow 建台联调）：app/services/semantic_dify.py（适用性门禁本地判定不进 LLM / 本地证据提取分批 / Dify Workflow 调用 / 结果校验 / 批次级缓存 / 单批失败降级本地关键词）；SEMANTIC_REVIEW_MODE=local|dify 开关（默认 local，行为不变）；DIFY_SEMANTIC_API_KEY 配置（回退 DIFY_API_KEY）；web+CLI 双接线；5 个测试；Workflow 建台规格：docs/semantic_review_workflow_spec.md；Dify Cloud 连通性已验证（完整性 workflow key 有效）
- [x] Dify"规范语义审查"Workflow 建台完成并接入（2026-08-22）：用户输入→LLM（低温+JSON 输出）→结束（result_json）；curl 冒烟测试通过（T-1 COMPLIANT、证据逐字引用、1.8s/564 tokens）；DIFY_SEMANTIC_API_KEY + SEMANTIC_REVIEW_MODE=dify 已写入 .env（本地，不入 git）；162 测试全绿
- [x] 完整性 Dify 复核体验改进（2026-08-23）：①复核阶段状态实时更新（"Dify 完整性语义复核进行中 x/N"，不再看似卡死）；②批次串行改并发（DIFY_COMPLETENESS_CONCURRENCY 默认 3，信号量+锁，错误语义不变：任一批失败仍带部分记录落盘后抛出）；实测用户任务 5 条复核串行约 14 分钟（53~109s/条，单条 12K tokens），并发后预计 4 分钟级。复核质量抽查：施工计划→MISSING(缺设备计划，带页码证据)、验收要求/应急措施 UNCERTAIN→PASS。169 测试全绿（测试假函数签名同步）；新任务 bfcbbcfe 全缓存命中验证无回归
- [x] 扣件式语义规则补录+体系匹配修正（2026-08-23）：修正 8 条体系专属规则 applicable_types 错标 universal（4.24/5.1/5.3/5.6/5.7/5.18→koujian，5.4/5.5→pankou），消除盘扣方案被扣件规格误审（此前联调 5.1 对盘扣方案 VIOLATED 即此误报）；从审查规则提取表补录 3 条扣件式语义规则（4.34 扫地杆≤200mm、4.35 螺杆外伸≤300mm、4.36 搭设高度≤30m，含与盘扣限值差异注释）。语义规则 84→87：盘扣方案执行 78 条/扣件 83 条/未识别 74 条通用。另：WEB_ENABLE_DIFY=true 已开启（完整性 on_demand 复核）。169 测试全绿（新增门禁回归）
- [x] 工程基础信息展示优化（2026-08-23，6bea5e1）：只展示已识别信息（参数表/卡片过滤未识别项）+适用规范按 法规/政策/国标/行标 分组
- [x] 工程基础信息页改版（2026-08-23，Part C）：qualification 增 key_parameters（11 项关键参数：识别结果+来源页+驱动的下游审查环节），前端增"关键参数识别"表（已识别绿/需复核橙/未识别灰），报告"工程基础信息"章增关键参数小节；实测样例风险属性由 unknown 转 over_scale_dangerous（高度13.88m≥8m 判定打通），10/11 参数确认。168 测试全绿（新增 1 回归）
- [x] 参数识别修复（2026-08-23，Part B）：①support_height/framework_height 删硬编码多值判 uncertain、接线已有 max_numeric（样例 214 页实测 8.05/5.87/13.62→确认 13.88m）；②total_load/concentrated_line_load 加单位护栏（正文抽取无兼容荷载单位即放弃，不再把"间距800mm/系数1"当荷载）+ 归一化支持 kN/m 单位族 + max_numeric（线荷载实测确认 20.0kN/m）；③support_span 补别名（跨度/梁跨/板跨/计算跨度等）+计算书章节（实测确认 48m 待人工核）。样例中"施工总荷载"仅现于规范条文引用、方案未写设计值 → 诚实报 missing。167 测试全绿（新增 4 回归）
- [x] 适用规范派生重构（2026-08-23，Part A）：standards.json 增 tier 分层（core=rule/ 文件夹 10 本审查主力：2法规+5通用+3技术；其余 8 本降 reference）；适用规范改从"体系门禁后适用规则引用的规范"反推（仅核心层、带规则数、降序），识别→匹配语义落地；前端 chips 带规则条数、规则库规范筛选按核心/参考分组；163 测试全绿。进行中：参数识别修复（Part B）、工程基础信息页改版（Part C）
- [x] 全量联调通过（2026-08-23，job 2d6b084f）：214 页样例、84 条规则 **11 批全部走 Dify LLM、0 降级**，约 3 分钟；结果 33 COMPLIANT / 14 VIOLATED / 37 UNCERTAIN（本地基线 30/0/54——LLM 新发现 14 条实质违规：γ₀ 取值、施工荷载取值、立杆接长方式、钢管壁厚等，均带逐字证据引用）；置信度 high 47 / medium 21 / low 16；报告正常生成。联调踩坑记录：①模型账号欠费（阿里云百炼 400）→ 换供应商；②思考型模型单批推理 >2 分钟触发 Dify 网关 504 → 换与完整性审查一致的快速模型后单批 ~19s；③批次缓存指纹含证据全文，历史缓存对旧证据版本不命中属预期

## 🚧 当前阻塞

（无）

## 📌 下一步建议

1. **浏览新版工程基础信息页**（任务 `c6902ceb`）：确认关键参数速览、适用规范（10 本核心带规则数）、风险属性（已转"超规模危大"）展示效果
2. **复核 14 条语义审查 VIOLATED 判定**：任务 `2d6b084f`/`c6902ceb`，人工确认误报率，必要时调优提示词或规则证据召回
3. **搭设跨度 48m 人工核实**：参数表召回值，疑似取到非结构跨度字段，确认后考虑收紧 support_span 召回/合理性界
4. 规则库 standard_id 落盘（目前为运行时归一化附加）；语义审查批次并行化评估

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
- [2026-08-27 11:14] codex 签退 — 完成了：优化规则库新增规则按钮，改为结构化分区表单，补规范依据、关键词、阈值、适用支架、人工复核与状态字段；后端新增/编辑接口同步结构化字段；下一步建议：增加批量导入规则入口，并按审查方式做动态字段显隐
- [2026-08-27 11:45] codex 签退 — 完成了：执行规则库批量导入与动态新增表单、扩充参数一致性和图文一致性检查项、增强总控 Agent 审查计划解释；下一步建议：补规则批量导入模板下载与参数/图文新增项专项回归测试

- [2026-08-21 18:20] claude 签到 — 开始处理：修复 3 个存量测试失败（test_web 过期断言 2 + DR-01→DR-90 编号迁移）

- [2026-08-21 18:23] claude 签退 — 完成了：修复 3 个存量测试失败（54f1f1a）：test_web 文案断言更新为现行五模式、compliance→smart、DR-01→DR-90 编号迁移；全套件转绿 156 passed/1 skipped/0 failed；下一步建议：按 docs/semantic_agent_design.md 实施语义审查 Agent（复用 PENDING_CONFIRMATION/重跑闭环）；规则库 standard_id 落盘

- [2026-08-21 18:31] claude 签到 — 开始处理：审查结果页证据图片展示：API出口层按block_id补image_path + 前端缩略图/灯箱 + 计算引擎公式验算证据补定位

- [2026-08-21 18:52] claude 签退 — 完成了：证据图像/表格展示全链路：API出口层按block_id补image_path+table_html、计算/语义引擎证据补block定位、前端缩略图+灯箱（表格真渲染）、MinerU缓存携带raw图像；157测试全绿+浏览器冒烟通过+重跑demo验证；下一步建议：配置MINERU_API_TOKEN后重解析补图像jpg；随后按设计文档实施语义审查Agent

- [2026-08-21 19:39] claude 签到 — 开始处理：MinerU重解析样例验证图像证据（token已配置，922图落盘）

- [2026-08-21 19:41] claude 签退 — 完成了：MinerU重解析完成：token配置+922图落盘新任务12a62f8b+缓存携raw生效+抽屉图像200验证；表格证据真渲染+图像通道全部就绪；下一步建议：NEXT=语义审查Agent实施（docs/semantic_agent_design.md）；规则库standard_id落盘

- [2026-08-22 21:59] claude 签到 — 开始处理：语义审查Agent实施：Dify集成（设计规格文档+代码实现+降级机制）

- [2026-08-22 22:12] claude 签退 — 完成了：语义审查Agent代码侧完成（9d634c8）：semantic_dify.py全链路+降级+5测试+建台规格文档，162测试全绿，默认local模式行为不变；下一步建议：在Dify按spec建规范语义审查Workflow→填DIFY_SEMANTIC_API_KEY+SEMANTIC_REVIEW_MODE=dify→上传样例联调

- [2026-08-22 22:30] claude 签到 — 开始处理：引导用户在 Dify 控制台按 docs/semantic_review_workflow_spec.md 逐步创建"规范语义审查"Workflow（一步一步交互指导）

- [2026-08-22 23:05] claude 签退 — 完成了：Dify"规范语义审查"Workflow 建台全程引导（用户输入4变量→LLM低温JSON输出→结束节点result_json）；纠正 rule_json→rules_json 命名后 curl 冒烟测试通过（T-1 COMPLIANT/证据逐字引用/1.8s）；DIFY_SEMANTIC_API_KEY+SEMANTIC_REVIEW_MODE=dify 写入本地 .env，162 测试全绿；下一步建议：上传样例 PDF 全量联调（84条规则分批/缓存/降级验证）

- [2026-08-22 23:15] claude 签到 — 开始处理：语义审查 Dify 全量联调（样例 PDF 上传，84 条规则分批调用/缓存/降级验证）

- [2026-08-23 00:30] claude 签退 — 完成了：语义审查 Dify 全量联调通过（job 2d6b084f）：84 条规则 11 批全走 LLM、0 降级、约 3 分钟；33 COMPLIANT/14 VIOLATED/37 UNCERTAIN，14 条实质违规均带逐字证据；期间排掉三个坑（百炼欠费 400→换供应商、思考型模型网关 504→换快速模型、旧缓存指纹不命中属预期）；下一步建议：人工复核 14 条 VIOLATED 误报率；规则库 standard_id 落盘；批次并行化评估

- [2026-08-23 01:20] claude 签到 — 开始处理：工程基础信息改版（识别修复+关键信息速览）与适用规范派生重构（核心层=rule/文件夹 10 本规范）

- [2026-08-23 02:40] claude 签退 — 完成了：工程基础信息+适用规范三部分改版全部落地（174f0f5/4e6d8e0/8b06f8b）：①注册表分层+适用规范从适用规则反推（10 本核心带规则数）；②参数识别修复（高度13.88m/跨度48m/线荷载20kN/m 确认，总荷载因方案未写诚实报 missing）；③关键参数速览表（11 项+来源页+驱动环节），风险属性 unknown→over_scale_dangerous；168 测试全绿，新任务 c6902ceb 已生成可供 Web 查看；下一步建议：用户浏览确认页面效果；人工复核 14 条语义 VIOLATED；搭设跨度 48m 取值待人工核实是否应为结构跨度

- [2026-08-23 03:30] claude 签到 — 开始处理：展示优化（只展示已识别+规范分组）+ 完整性 Dify 开启 + 扣件式语义规则补录与体系匹配修正

- [2026-08-23 04:10] claude 签退 — 完成了：①展示优化 6bea5e1（只展示已识别、规范按类别分组）；②WEB_ENABLE_DIFY=true 开启完整性 on_demand 复核；③修正 8 条体系规则错标（消除 5.1 对盘扣方案的误报根因）+ 补录 3 条扣件式语义规则（4.34/4.35/4.36），语义规则 84→87，门禁生效（盘扣78/扣件83/未识别74）；169 测试全绿；下一步建议：重传样例验证新门禁下的语义结果与完整性 Dify 复核；人工复核语义 VIOLATED

- [2026-08-23 05:00] claude 补充提交 — 完整性 Dify 复核改进：进度实时更新（x/N）+ 批次并发（默认 3）；用户样例 5 条复核串行 14 分钟→预计 4 分钟级；复核缓存命中验证无回归（任务 bfcbbcfe）

- [2026-08-23 05:30] claude 补充提交 — 完整性审查表展示口径说明（475fcce）：本地 PASS 但部分要素匹配送复核的行加标注；未送复核的行 Dify 列展示跳过原因；Dify 结论 chip 加颜色释义（绿=合规/橙=无法核验/红=缺失）

- [2026-08-23 06:20] claude 签到 — 开始处理：工程类型英文转中文展示 + 完整性审查表说明文字排版优化

- [2026-08-23 06:35] claude 签退 — 完成了：①工程类型 concrete_formwork_support→"混凝土模板支撑（高支模）"（前端 PTYPE_CN + 报告 _project_type_label 两处）；②完整性表排版重做：说明从裸 br/small 改为 .cell-note 块（chip+备注 flex 成组、行高一致、td 顶对齐）、表头下新增图例条（三色圆点+口径说明常显，颜色释义不再只靠悬停）；浏览器验证+169 测试全绿。下一步建议：用户浏览器确认效果；语义 VIOLATED 人工复核

- [2026-08-23 03:01] codex 签到 — 开始处理：实现上下文连续性协议（上下文达上限自动交接续接）
- [2026-08-23 03:01] codex 签退 — 完成了：上下文连续性协议三件套（交接脚本 bash+ps1、make handoff、AGENTS.md 协议）；下一步建议：agent 自监测 get_goal 预算低于 20% 时自动跑 make handoff 并提示开新对话

- [2026-08-23 07:00] dewucode 签到 — 开始处理：完整性审查表格样式优化（Dify列三态/一致性列红色/说明文字）+ 规范语义审查"无法判定"根因修复（85条规则补关键词+回退逻辑优化）+ 清理旧triangular_mapping文件 + 规则库管理界面增加规范版本校验
- [2026-08-23 07:30] dewucode 签退 — 完成了：①完整性审查表Dify列改为三态（已复核/未复核/复核失败），一致性列不一致显示红色加粗，表格上方说明改为规则+Dify流程解释；②语义引擎回退逻辑优化（空关键词不再盲目提取，改为从规则名提取核心名词）；③为85条空关键词规则补充extraction_keywords（v4.0源+config双写，164条全覆盖）；④删除9个旧triangular_mapping_*.json文件（含JGJ231-2010旧版引用，不被代码使用）；⑤规则库管理界面新增"规范版本校验"按钮+弹窗（GET /api/rules/version-validation，检测同规范多版本冲突）；169测试全绿。下一步建议：用户浏览器确认效果；语义VIOLATED人工复核；搭设跨度48m取值待人工核实

- [2026-08-23 08:04] claude 签到 — 开始处理：继承审查页与校验规则优化：修复 Dify 两条工作流问题 + 思考图文校验与计算校核实现方法

- [2026-08-23 08:37] claude 签退 — 完成了：修复两条 Dify 工作流问题+图文校验三处误报根因：①.env 加载 cwd 依赖根因修复（dify_config/dify_client/mineru_client/web 四处 bare load_dotenv() 改显式项目根路径，从任意目录启动服务两条工作流不再静默失效）；②时间线 Dify 复核口径改读 dify_call_audit（API 实调数/缓存命中数/失败数，缓存命中不再显示成实调）；③语义 Dify 证据页码定位（_locate_llm_quote 滑窗匹配把 LLM 引用回填 block_id/页码，32 条无定位规则受益）；④图文校验修复三个误报根因（规范条文过滤+关键词完整表述+多值匹配），实测样例 3 个假 ISSUE 全部转 PASS；⑤产出图文校验与计算校核实现方法文档（docs/drawing_calculation_method.md：现状/已修/三级演进路线）；下一步建议：①重传样例验证新图文校验与时间线口径（老任务数据不会自动更新）；②按文档第一级扩展 consistency_review 参数集（计算书输入vs正文比对）；③语义 VIOLATED 人工复核（11条）

- [2026-08-23 09:47] claude 签退 — 完成了：图文一致性模块扩展+RapidOCR轻量OCR通道：①参数从5扩到8条（新增丝杆外露长度/高宽比/扫地杆高度，每条对应三方映射表规范原文：JGJ231 6.1.6/6.1.4/GB51210 8.3.2），fact未识别自动跳过不编造；②RapidOCR onnx通道（DRAWING_OCR_ENABLED开关，惰性初始化，未安装静默降级），只对文本稀疏(<200字符)含图页触发，29页识别成功；③review发现并修复4个P1：≤/不大于条文过滤逃逸、高宽比无单位gap误抓、OCR来源标注按捕获组位置判定、rglob全任务树搜索改job_dir直连；④高宽比无量纲处理（不做×1000归一、1%容差、结论不带mm）；⑤新增8个测试，180全绿；真实任务E2E验证无回归；下一步建议：①重传样例验证OCR通道在Web全流程效果（含扩展参数在其他方案样本上的表现）；②高宽比/丝杆外露fact识别率提升（当前样本未识别导致跳过）；③OCR结果缓存（同一任务重跑27s可省）

- [2026-08-23 16:34] claude 签退 — 完成了：图文校验证据可视化修复：drawing_evidence 补 image_path（图纸页取首个 image block）或 table_html（参数表页取含关键词的表格 block），前端抽屉用 evThumb 渲染缩略图（图/表格真渲染+灯箱）+ OCR 来源 chip；真实任务重跑验证落盘数据 img/table 齐备；下一步建议：①浏览器确认图文抽屉图片/表格渲染效果；②DR-02 p46 证据质量（';3' 条款编号被当数值）属提取启发式旧问题，后续单独修

- [2026-08-23 17:15] claude 签退 — 完成了：图文校验误抓修复（条款编号/页码/图号/跨字段）：①gap 收紧（不跨句读标点和换行，≤30字符），挡掉条款编号';3'、跨行页码'方案\n7'、图号'示意图如下:\n(10'；②条文叙述 marker 补充（超过/应为/宜为/符合规范/符合要求/按规范），挡掉'当架体高度超过4'类引用；③纵距/横距加 exclude_terms（附加/根数/是否相等），消除'纵距内附加…根数 0'跨字段误抓（横距此前会抓到纵距的值造成假PASS）；④移除关键词 break——遍历全部别名（纵距+纵向间距）；⑤review 发现并修复：顿号不挡（保住'纵距、横距(mm) 900×900'组合标注）、别名重叠按捕获组终点去重、_page_text 双拼按(page,value,quote)去重（众数按标注处数计）；⑥新增7个回归测试，187全绿；真实任务重跑验证 DR-01~05 证据全部为真实图纸/参数表标注；下一步建议：①浏览器确认图文抽屉效果（证据数值已全部干净）；②OCR 结果缓存（同任务重跑27s可省）；③其余参数（壁厚/立杆间距合理性界）可按同模式扩展

- [2026-08-23 22:43] claude 签退 — 完成了：三项用户反馈处理：①图文证据点击无反应修复——evThumb 改为图片+表格双渲染（此前 table_html 优先级覆盖 image_path，用户看不到图片），app.js 加 mtime cache-busting（浏览器旧缓存是交互失灵的另一根因）；②人工复核支持参数修正——rerun overrides 从仅 support_system 扩展到 14 个数值参数（高度/步距/悬臂/间距/高宽比等），前端人工复核页新增'参数修正'折叠面板（显示当前识别值+修正输入+一键重跑），E2E 验证修正步距1.8→重跑→DR-01 正确转 ISSUE；③新增3个rerun测试，190全绿；下一步建议：①用户浏览器硬刷新验证图文证据图片+表格双渲染和参数修正面板；②语义UNCERTAIN 46条的人工复核（LLM判定需抽检误报率）；③参数修正面板与支撑体系确认的交互合并

- [2026-08-23 23:03] claude 签退 — 完成了：任务时间线重构：①新增 stage_timings.json——_run_review_stages 各阶段（参数识别/基础信息/规则引擎/规范语义审查/计算校核/实质性/参数一致性/图文校验）真实 started_at+duration_ms 计时，_process_job 前段（MinerU/完整性审查）同样计时并合并落盘；②时间线读取真实计时展示——每阶段显示开始时间+耗时（如'规范语义审查（3.3s）'），不再全部挤在最后 updated_at；③补全此前缺失的阶段事件——规范语义审查/计算校核/图文校验等首次在时间线可见；④重跑场景——run_context 标记 rerun，时间线显示'人工复核重跑开始'+新阶段计时，不重复展示首次审查的 MinerU/Dify 历史事件；⑤Dify 复核事件带真实耗时（1m55s）；老任务无计时文件时优雅回退。190测试全绿；下一步建议：①用户浏览器验证新时间线（重新上传新PDF看完整阶段时间线效果最佳）；②首次上传链路的语义审查进度实时展示（当前只有批次并发进度）

- [2026-08-24 00:20] claude 签退 — 完成了：进度条细分到全部审查阶段：①STAGE_PROGRESS 从4档(0/30/60/80/100)扩展到14档——审查管线各阶段（参数识别58/基础信息60/规则引擎63/语义审查72/计算校核78/实质性81/一致性83/图文校验88/Dify复核92）独立进度，修复进度条在80%长期停滞的盲区（审查占总耗时大头却全部压在80→100区间）；②_update_status 增 progress/status_value 参数——中间阶段推进进度但保持顶层任务状态（不干扰轮询的完成判定），进度单调不减（rerun基线90）；③_timed 完成时自动推进进度；④Dify复核批次进度插值（92→99按批次线性）；⑤前端 STAGE_NAMES 补全部阶段中文名。E2E验证：新任务进度72%→83%→100%逐阶段推进，时间线完整。190全绿；下一步建议：①用户浏览器验证新进度条效果（重新上传PDF观察各阶段推进）；②Dify复核与其他引擎并行执行评估（省1-2分钟）

- [2026-08-24 11:43] claude 签到 — 开始处理：比赛 Agent 化改造方案文档：现状 workflow 差距分析 + Tier A/B 设计 + 演示脚本

- [2026-08-24 11:46] claude 签退 — 完成了：比赛Agent化改造方案文档（docs/agent_upgrade_design.md）：现状workflow差距分析（LLM无规划/工具/迭代三能力）+资产映射 + Tier A语义审查工具循环设计（5工具/max_rounds=3/轨迹缓存/三级降级）+ Tier B轻量规划Agent（LLM出计划/白名单校验）+演示脚本与答辩话术 + 3.5天实施计划与风险对策；下一步建议：用户确认方案三个决策点（TierB是否首期/LLM选型/前端轨迹粒度）后按A1起步实施semantic_agent.py

- [2026-08-24 11:57] codex 签到 — 开始处理：回答比赛 Agent 化改造策略问题

- [2026-08-24 16:22] claude 签到 — 开始处理：V3.1 修订版架构设计文档：合并双通道决策（agent直连LLM tool-calling+Dify批式保留）与review修改意见

- [2026-08-24 16:24] claude 签退 — 完成了：V3.1 实施版架构设计文档（docs/agent_architecture_v3_1.md）：合并 V3+review 8 处修订（①调用通道定为代码侧直连LLM原生tool-calling、Dify仅批式 ②按规则rerun裁掉 ③Router本地路由表+启发式零LLM ④Replan砍掉 ⑤去重语义定义 ⑥缓存维度确认 ⑦get_page护栏 ⑧编号统一）+ llm_chat_client规格/env配置 + Phase 0-7六天计划；agent_upgrade_design.md标注已取代；下一步建议：Phase 0：选定 function calling 模型（qwen-plus/deepseek-chat/glm），配 LLM_AGENT_* env，3条规则手工跑通 tool-calling 循环验证稳定性

- [2026-08-24 16:28] claude 签到 — 开始处理：Phase 0 能力验证：选定 function calling 模型、配置 LLM_AGENT_* env、3条规则手工跑通 tool-calling 循环

- [2026-08-24 16:46] claude 签退 — 完成了：Phase 0 能力验证通过：模型选定 qwen-plus（qwen3.5-ocr 不支持tool calling已排除/qwen3-max参数格式脏）；3条规则跑通tool-calling循环，Recovery实证（2.11 批式UNCERTAIN->Agent 2轮COMPLIANT，γQ=1.5 P125）；4个设计发现（强制交卷必须/Evidence ID必要性实证/检索截断/page校验）；验证脚本+记录文档落盘；190测试全绿；下一步建议：Phase 1 Evidence Layer（0.5天）：Evidence Object/ID/Registry/Validator + 检索质量改进（命中block行级截取+表格感知召回，解5.1阳性对照失败根因）

- [2026-08-24 16:58] claude 签到 — 开始处理：额度恢复验证 + LLM模型自动降级切换机制（免费额度耗尽自动换下一模型）

- [2026-08-24 17:06] claude 签退 — 完成了：①充值后6模型全部恢复；②模型链自动轮转机制落地（LLM_AGENT_MODEL逗号分隔优先级链，Arrearage/限流/额度/模型不存在触发切换+粘性+审计，bogus模型轮转测试通过）；③qwen3.8-max质量复验优于qwen-plus（阳性对照5.1转VIOLATED且P11证据校验通过、2.11参数表+公式交叉验证、单轮并行多工具）；链序：5免费模型优先+qwen-plus垫底；190测试全绿；下一步建议：Phase 1 Evidence Layer（0.5天）：Evidence Object/ID/Registry/Validator + 检索质量改进（命中block行级截取+表格感知召回）

- [2026-08-24 17:10] claude 签到 — 开始处理：Phase 1 Evidence Layer：Evidence Object/ID/Registry/Validator + 检索质量改进（行级截取+表格感知召回）

- [2026-08-24 17:18] claude 签退 — 完成了：Phase 1 Evidence Layer 完成：①agent_guardrails.py--EvidenceObject/Registry（登记去重/EV-P{n}-B{xxx}编号/落盘加载）+validate_finish（状态枚举/页码范围[解Phase0发现4]/证据ID真实存在/VIOLATED必带证据[解发现2]）+normalize_for_match/display_normalize双归一化；②agent_tools.py--LaTeX归一化检索（despaced偏移映射，'Φ48'直接命中P13计算书表格Φ48×3，解发现3根因）+关键词中心窗口（±100/140字符不再头部截断）+search/get_page/get_table/get_context四工具全登记EV ID；③27个测试，全套件217 passed；真实文档E2E：finish引用真实EV ID校验通过；下一步建议：Phase 2 Agent Loop（1天）：llm_chat_client.py生产版（继承模型链轮转）+semantic_agent.py ReAct循环（接agent_tools四工具+Budget+强制交卷+finish只准引用EV ID）

- [2026-08-24 17:27] claude 签到 — 开始处理：Phase 2 Agent Loop：llm_chat_client.py生产版（模型链轮转）+ semantic_agent.py ReAct循环（四工具+Budget+强制交卷+EV ID finish）

- [2026-08-24 17:42] claude 签退 — 完成了：Phase 2 Agent Loop 完成：①llm_chat_client.py生产版（模型链轮转+重试+审计+from_env）；②semantic_agent.py ReAct循环（Budget：3轮/5次工具/search≤2/读页≤3/去重第3次强制交卷/预算尽强制finish；finish过validate_finish失败回喂修正一次；轨迹缓存key=规则+文档指纹+prompt/tool版本+模型链）；③SEMANTIC_REVIEW_MODE扩展agent档+run_semantic_stage三级降级接线；④17新测试全绿234；⑤E2E真实LLM：2.7批式UNCERTAIN->COMPLIANT（4步查证挖出Q3k=2kN/m²，Recovery升级）、2.11六处γQ=1.5全带EV ID、5.1查询方向波动记为Phase 3观测项；⑥get_context/get_table支持EV ID定位；下一步建议：Phase 3 真实规则批量测试（0.5天）：选5-10条批式UNCERTAIN疑难规则跑Agent，统计Recovery Rate/Fallback Rate/Citation Validity/平均tool calls，产出benchmark对比数据

- [2026-08-24 17:43] claude 签到 — 开始处理：Phase 3 真实规则批量测试：批式疑难规则跑Agent，统计Recovery Rate/Citation Validity/tool calls，产出benchmark

- [2026-08-24 17:51] claude 签退 — 完成了：Phase 3 Benchmark 完成：10条批式疑难规则真实LLM跑Agent（脚本可复跑）：Recovery 5/9=56%（1.10 VIOLATED含封面审核栏空白+签字XXX占位符真实证据链、1.18/2.1/2.7/2.11 COMPLIANT均带EV ID）；Citation Validity 100%（结构性保证）；平均4.3工具调用/48s规则；4条诚实放弃（文档真缺证据不硬编）；0降级0轮转；产出benchmark文档+明细JSON；关键发现：①5.1检索方向波动（Phase4 route_hint解法）②全量agent耗时~70min印证Router分流必要性③强制交卷9/10为常态且质量稳定；下一步建议：Phase 4 Router（0.5天）：规则库route_hint字段+本地启发式四分流（LOCAL/LLM/AGENT/HUMAN）+route_decisions.json落盘+首轮检索注入extraction_keywords作查询种子（解5.1波动）

- [2026-08-24 17:55] claude 签到 — 开始处理：Phase 4 Router：route_hint+本地启发式四分流+route_decisions+agent首轮证据种子（解5.1检索波动）

- [2026-08-24 18:02] claude 签退 — 完成了：Phase 4 Router 完成：①agent_router.py两层路由（route_hint静态指定+启发式：HUMAN=关键参数冲突别名关联/LLM=召回≥2块/AGENT=召回不足）零LLM；②run_semantic_review_agent升级混合分流（四通道各司其职+各自降级，envelope带route_stats/route_decisions）；③首轮证据种子（extraction_keywords出发前自动召回进首条消息，解Phase3的5.1检索波动）；④14测试全绿248；⑤真实文档干跑：78条入路由→86%批式/12%Agent/3%人工，全量~70min→~10min；⑥1.16真实LLM验证：种子首轮生效、诚实UNCERTAIN带真实证据；下一步建议：Phase 5 Guardrails收尾（1天）：trace落盘job目录（agent_trace/route_decisions写_run_review_stages）+dify_call_audit增agent维度统计+预算类配置env化+注入防护回归测试补全

- [2026-08-24 18:04] claude 签到 — 开始处理：Phase 5-7 连续执行：Guardrails收尾（trace落盘/审计/注入防护）→ Planner（Plan-only）→ 前端三区域+E2E

- [2026-08-24 18:23] claude 签退 — 完成了：Phase 5-7 全部完成：⑤Guardrails收尾（agent_trace/route_decisions/agent_call_audit三工件经web落盘job目录+Budget env化AGENT_MAX_*+注入防护测试）+review_planner.py（LLM计划生成+本地统计降级+Mandatory Checks白名单+JSON解析容错，10测试）；⑥前端三区域（agentPlanCard计划卡/规则路径标签ROUTE_CN/抽屉Agent查证轨迹区块）+GET /api/jobs/{id}/review-plan；⑦全量E2E 456.9s真实LLM：Planner LLM生成5项审查重点（高架风险/托撑/剪刀撑/荷载/论证）、9条Agent规则新发现2 VIOLATED（6.18个人防护conf0.78/6.29应急物资conf0.9）、审计35LLM/33工具/54证据；Dify批式通道凭证失效被三级降级兜住（外部问题已记录）；263测试全绿；下一步建议：用户操作：Dify控制台更新通义模型凭证（[Tongyi] Incorrect model credentials）后重跑E2E验证批式通道；然后浏览器验证前端三区域效果；可选：.env改SEMANTIC_REVIEW_MODE=agent让新任务默认走agent模式

- [2026-08-25 10:48] codex 签到 — 开始处理：续接：修复 fact_conflict_detector 空 facts KeyError

- [2026-08-25 13:51] codex 签退 — 完成了：Web端总控审查Agent工作台：总览页流程、四类工具卡、规范Agent启用提示、时间线业务顺序和回归测试；下一步建议：上传样例PDF跑agent模式，验证review_plan/route_decisions/agent_trace落盘并优化详情抽屉演示效果

- [2026-08-25 13:58] codex 补充 — 按用户浏览器批注将规范语义审查页的"总控 Agent 审查计划"从长标签列表改为 AI总结建议格式：一句话建议 + 三条行动建议（先抓最高风险/让Agent深挖证据/人工确认后闭环）+ 统计 + 默认折叠原始计划明细；新增静态资源回归测试，真实任务 `7d3963fc` 浏览器验证通过

- [2026-08-25 14:18] codex 补充 — 修复新上传任务明细空白：文档解析存在"未分类（封面/目录等）"章节时缺少 `_direct` 明细数组，导致前端 `renderDocument` 抛错并中断后续规范/图文/计算渲染；已为章节聚合补齐默认明细数组并给模块渲染加独立保护。真实任务 `fd0e0a44` 验证恢复：文档解析 209 行、规范语义首屏 10 行（总 87）、图文 7 行、计算公式首屏 10 行（总 32）、参数一致性 4 行

- [2026-08-25 14:26] codex 补充 — 按用户浏览器批注收敛任务概览页信息层级：移除面板内重复"任务概览"标题，"总控审查 Agent"说明改为"Agent 调度结果"状态摘要，9 节点流程压缩为 4 阶段（解析取证/识别与计划/工具审查/复核报告），四类工具细节保留在下方卡片；窄屏工具卡改两列展示。浏览器验证任务 `fd0e0a44` 概览区高度 930→697，重复信息减少

- [2026-08-25 14:42] codex 补充 — 处理用户第二轮浏览器批注：①概览页规范/计算卡片改为与下方统计同口径（规范 72/115，计算 14/36），路由与公式/参数拆分降为辅助信息；②工程基础信息改为三等分横排摘要，尽量一行展示；③文档解析页新增"解析复核链路"提示与"只看需复核页/进入人工复核"入口；④规范页新增"无法判定来源"摘要，拆分确定性证据缺失/语义证据不足/LLM批式降级，解释 30+ 无法判定的成因。浏览器验证任务 `fd0e0a44` 数据对齐；前端语法检查与 3 条 Web 测试通过

- [2026-08-25 14:58] codex 补充 — 处理用户第三轮浏览器批注：①任务概览去掉下方重复统计卡和优先事项，只保留总控 Agent 调度结果；②总控 Agent 审查计划从规范语义审查页迁回任务概览页，规范页只保留规范统计/无法判定来源/规则明细；③文档解析复核链路调整为在章节/页详情抽屉内直接记录解析修正说明，并提供关键参数修正后重跑审查入口，复用现有 decisions 与 rerun API。浏览器验证：`agentPlanCard` 父节点为 `tab-overview`，`tab-semantic` 不再包含计划卡，概览重复统计区不存在；前端语法检查与 3 条 Web 测试通过

- [2026-08-25 15:05] codex 补充 — 处理用户第四轮浏览器批注：任务概览视觉顺序调整为先显示"总控 Agent 审查计划"、后显示"Agent 调度结果"；工程基础信息三张摘要卡统一值字号为 18px、固定高度 112px，优先单行展示，减少工程类型/支撑体系高度不一致。前端语法检查与 2 条 Web 测试通过，浏览器验证计划卡已排在调度结果前

- [2026-08-25 15:35] codex 签到 — 开始处理：接续Agent化改造：总控对象、工具调度、证据追证、人工确认与前端闭环
- [2026-08-25 16:05] codex 签退 — 完成了：后端总控 Agent 统一对象落地（orchestrator_agent.json + /api/jobs/{id}/orchestrator），四类审查工具观测、参数候选池/冲突确认、文档解析修正重跑上下文、公式复算摘要、图文追证联动与前端概览接入；证据召回新增目录降权+章节二次追证，Router 支持 conflict 状态；下一步建议：用真实样例新上传跑 agent 模式，浏览器验证 orchestrator_agent.json 与概览展示，并继续扩展计算公式复算覆盖面
- [2026-08-25 18:24] codex 签到 — 开始处理：人工复核与结果解释优化：优先实现无法判定归因展示
- [2026-08-25 18:33] codex 签退 — 完成了：无法判定归因展示（后端 uncertainty_analysis 四类归因 + 总控 JSON 接入 + 规范页四类卡片展示）；下一步建议：继续做人工复核页“缺失参数 → 关联规则 → 填值重跑”和规范详情页三段式解释
- [2026-08-25 19:08] codex 补充 — 按浏览器批注调整：审查记录时间线默认折叠；移除规范页整块归因面板，改为规则行/详情抽屉中的归因标签。相关测试与浏览器刷新验证通过
- [2026-08-25 17:07] codex 补充 — 验证用户新上传样例：服务进程已启动且新任务 `81e48fcb...` 已创建，实际数据根为 `/Users/admin/high-formwork-data/web/jobs`；任务已生成 `review_plan.json`，但长耗时语义 Agent 阶段开始后状态仍停留在规则引擎完成，导致 Web 端看起来无明细/未推进。本轮修正 `_run_review_stages` 阶段状态：进入每个工具/Agent 阶段即写入进行中状态，完成后再写完成状态，并按当前 `status.stage` 上报失败阶段；下一步建议：重启本地服务后重新上传样例，确认页面显示“规范审查 Agent 进行中”并等待 `orchestrator_agent.json` 完整落盘
- [2026-08-25 17:21] codex 补充 — 重启服务后重传样例 `f956cee0...`，确认前端/API 已正确显示“总控 Agent 制定审查计划进行中”与“规范审查 Agent（规则/Dify/自主查证分流）进行中”；同时发现 Planner LLM 耗时约 80s 才放行，演示体验偏慢。本轮给 `review_planner` 增加轻量调用预算：默认 20s、0 重试、仅首个模型，失败立即降级本地统计计划，避免总控计划阻塞四类工具调度；下一步建议：重启服务后再传样例，确认 Planner 最长等待受控，然后继续优化语义证据召回与参数缺失分流
- [2026-08-25 17:25] codex 补充 — 针对样例 `81e48fcb...` 的 UNCERTAIN 明细抽样，发现 6.30/6.32/6.33/6.35 等规则虽被 Router 判为 LLM_READY，但证据主要来自目录页或少量片段，批式 LLM 无法闭环。本轮优化 `agent_router` 证据质量门槛：LLM_READY 不再只看总命中数，必须至少 2 个非目录正文 block；若目录命中多但正文有效证据不足，自动升级为 AGENT_REQUIRED 深挖正文。新增目录重命中回归测试；下一步建议：重启服务后再跑样例，重点观察应急/保障/监测类规则的路由是否从 LLM_READY 转 Agent，并继续把“关键参数缺失”分流到人工确认/参数修正
- [2026-08-25 17:42] codex 补充 — 继续处理“规则依赖参数提取，方案没写或解析没抓到就无法判定”：`agent_router` 新增 missing_fact_keys 与关键参数别名扩展，只有 ProjectFacts 明确给出 status=missing 或 value 为空时才触发，规则文本命中对应别名则路由 HUMAN_REQUIRED，进入人工确认/参数修正重跑链路；真实样例离线验证识别出顶托悬臂长度、扫地杆高度缺失，并将扫地杆相关 4.4/4.21/4.29/4.34 分流人工确认。测试覆盖缺失、缺字段不误判、确认值不误判；下一步建议：前端人工复核页把 HUMAN_REQUIRED 的参数项聚合成“需补参数”清单，并把 6.30 等正文命中足够但 LLM 仍引用目录的问题转向证据片段排序/摘要优化
- [2026-08-25 17:54] codex 补充 — 闭环修复：语义 Agent 的 HUMAN_REQUIRED 路由项不再只停留在语义表格，已进入 `review_results.human_review_queue` 与 `orchestrator_agent.human_confirmation`；前端总控 AI 总结优先读取总控人工确认结果，避免显示“人工确认 0 项”。真实样例新任务 `ae556025...` 验证：路由统计 LOCAL 0 / LLM 66 / Agent 9 / 人工 3；人工复核队列 19 项，其中规范语义 4 项（3 条扫地杆参数缺失 + 1 条监测频率 Agent 查证违规）；总控人工确认 9 项。下一步建议：继续优化证据片段排序/摘要，让 LLM_READY 规则少引用目录和碎片证据，并把参数修正面板按“缺失参数→关联规则→重跑影响范围”聚合展示
- [2026-08-25 18:07] codex 补充 — 执行下一步优化：①语义证据召回新增正文优先/目录降权/表格段落加权/关键词中心窗口，并在标题命中时自动补同小节后续正文，Dify 批式 evidence_text 与 quote 回填 blocks 共用同一套排序；真实样例抽查 6.30/6.32/6.33/6.35 已优先正文/表格，6.9 不再只给“监测频率”标题，而带出同小节正文；②人工复核参数修正面板新增“需补参数→影响规则→重跑影响范围”聚合，样例显示“扫地杆中心线高度影响 3 条规则”。测试：新增证据质量回归，48 条聚焦测试通过，compileall 与 app.js 语法检查通过；下一步建议：重传样例跑完整新证据版本，抽检 LLM_READY 规则的 UNCERTAIN 是否减少，并进一步做 evidence score/route_decisions 可视化

- [2026-08-25 18:24] codex 签到 — 开始处理：人工复核与结果解释优化：优先实现无法判定归因展示

- [2026-08-25 19:22] codex 签到 — 开始处理：图文一致性与计算校核优化闭环
- [2026-08-25 19:39] codex 签退 — 完成了：图文一致性与计算校核解释闭环：公式真实复算、图文证据质量标签、总控参数关联、前端详情与人工复核展示；下一步建议：用真实样例任务重跑后人工抽查 3 条复算公式和图文冲突标签

- [2026-08-26 11:15] codex 签到 — 开始处理：探索计算板块公式校核与参数验算规则关系
- [2026-08-26 11:16] codex 签退 — 完成了：梳理计算板块公式校核与参数一致性校核的实现关系；下一步建议：如需优化，可把参数一致性命名调整为“计算输入一致性”，减少与公式验算规则混淆

- [2026-08-26 11:24] codex 签到 — 开始处理：优化计算规则与计算书证据召回
- [2026-08-26 11:30] codex 签退 — 完成了：补齐计算规则公式字段、修正盘扣式计算规则命名、优化计算书章节证据召回并补回归测试；下一步建议：继续把荷载组合、侧压力、地基承载力、抗倾覆等从存在性预审升级为真实复算
- [2026-08-26 11:46] codex 签退 — 完成了：计算校核 Agent 化第一版，新增 calculation_agent 证据追踪，5 条规则接入 agent_evidence 路由，calculation_results 输出 Agent trace，前端计算详情展示追证轨迹；下一步建议：继续补荷载组合、侧压力、地基、抗倾覆真实复算器

- [2026-08-26 11:47] codex 签到 — 开始处理：继续计算校核Agent化：补真实复算器
- [2026-08-26 11:51] codex 签退 — 完成了：补充荷载组合、地基承载力、抗倾覆三类真实复算器，指定5条Agent规则保留trace且可由确定性复算给出判定；下一步建议：继续补侧压力与面板/楞梁抗弯挠度复算
- [2026-08-26 15:49] codex 签退 — 完成了：按已抽取的JGJ130/JGJ162条文继续优化计算规则，明确结构计算规则适用体系边界（universal/pankou/koujian/wankou），修正扣件式/盘扣式/碗扣式规则门禁，新增扣件式立杆计算长度与立杆稳定性规则，并补体系门禁与扣件式稳定复算回归测试；下一步建议：对桌面jisuan中扫描/乱码规范先做OCR，再补GB55001/GB55023上位规范系数覆盖、盘扣/碗扣托撑承载力和侧压力/面板楞梁真实复算
- [2026-08-26 16:29] codex 签退 — 完成了：新增规范PDF转Markdown脚本并从桌面jisuan生成rule/source_md索引与7个MD中间文件；确认JGJ130/JGJ162可直接规则提取，GB55001/GB55023/GB50666/JGJ166/盘扣标准需OCR；尝试安装ocrmac本机OCR依赖成功但Vision识别在当前环境返回空结果，暂不据此生成正文；下一步建议：用外部OCR或可用OCR环境补齐5本规范正文MD后，再继续提取上位规范与盘扣/碗扣专属计算规则
- [2026-08-26 17:32] codex 签退 — 完成了：接收用户整理后的source_md规范，新增规范来源索引并标注GB50666文件名错位/JGJ166缺失；按GB55023和盘扣标准修正首批规则：2.4施工荷载口径改为2.5/4.0，3.17扣件托撑收窄为koujian，新增3.17p盘扣托撑100/140kN，3.20抗倾覆收窄为pankou；补盘扣托撑复算与体系门禁测试；下一步建议：继续从GB55001/GB55023/GB50666/盘扣标准提取上位规范覆盖规则和侧压力、面板/楞梁真实复算
- [2026-08-26 17:38] codex 签退 — 完成了：继续从整理后规范提取计算规则，纠正GB50666侧压力0.28β公式、保留JGJ162侧压力0.22β1β2公式、新增Q3附加水平荷载规则，并接入侧压力确定性复算与回归测试；下一步建议：继续按适用体系提取GB55001/GB55023/GB50666/JGJ162/盘扣标准剩余计算规则，优先补面板/楞梁抗弯挠度与风荷载真实复算；JGJ166仍需补充可读MD
- [2026-08-26 17:57] codex 签退 — 完成了：继续细化规则适用条件，为2.4/2.8/2.19/2.24、3.1~3.7、3.20/3.22补充结构化applicability_conditions，并让确定性/语义/计算三类引擎结果输出适用条件；同步修正规则库index统计并新增索引一致性测试；下一步建议：基于这些条件字段继续做自动触发判定，例如按泵管/泵送/外露隐蔽/梁板墙柱事实自动筛选或降级人工确认
- [2026-08-26 18:03] codex 签退 — 完成了：实现规则适用条件自动判定第一版，新增condition_evaluator并接入计算引擎/计算Agent；2.19可自动选择GB50666侧压力0.28β公式或γcH分支，2.4/2.18可识别水平泵管/移动设备工况，2.24可识别泵送/Q3/2%条件，3.20可追踪浇筑前/浇筑时抗倾覆工况，3.22可按B型40kN/Z型65kN判断顶层步距缩小触发；下一步建议：把condition_evaluation接入前端详情和人工复核队列，并继续扩展梁/板/墙柱、外露/隐蔽的自动事实抽取
- [2026-08-26 18:06] codex 签退 — 完成了：根据代码审查修正条件细化问题，删除2.1/2.2误挂的applicability_conditions，收紧GB50666侧压力条件判定为V与坍落度均明确后才选择0.28β或γcH分支，并补错挂/缺V回归测试；下一步建议：继续修正3.22 B/Z型局部窗口解析，避免同段规范阈值说明影响实际型号判定
- [2026-08-26 18:14] codex 签退 — 完成了：计算条件判定前端展示与人工复核闭环：review_results 汇总 calculation condition_evaluation，计算页展示条件标签/条件明细，人工复核队列新增计算条件来源并可跳转计算详情；补充队列回归测试；下一步建议：做参数校核到计算校核的数据联动，建立参数-计算规则依赖表，把4个已校核参数映射到受影响公式规则，人工修正后标注影响范围并重跑；随后做图文几何/构造参数抽取反哺参数校核
- [2026-08-26 18:14] codex 补充 — 完成了：参数校核到计算校核的数据联动第一版：新增 calculation_dependencies 参数-公式规则依赖表，4个既有参数校核项输出 calculation_impacts，参数详情抽屉展示“影响公式验算”，总控 parameter_to_rules 可从计算 rule_id/formula_id 反向关联参数；下一步建议：扩展侧压力、面板/梁楞、地基、抗倾覆所需参数提取，再进入图文几何/构造参数抽取反哺参数校核

- [2026-08-26 19:15] claude 签到 — 开始处理：扩展侧压力/面板梁楞/地基/抗倾覆参数提取+图文几何构造参数抽取反哺参数校核

- [2026-08-26 20:03] claude 签退 — 完成了：完成计算参数依赖扩展+图纸几何反哺：calculation_dependencies扩至26参数60+规则；23个新计算输入参数入parameter_definitions；symbolic_numeric抽取模式(γc/t0/fa/γ0)新增；drawing_geometry模块新建立杆纵横距/扫地杆/垫板/剪刀撑等11类参数抽取+正文交叉比对；28测试全绿；下一步建议：跑全套件验证不回归

- [2026-08-27 10:09] codex 签到 — 开始处理：读取近期agent更改内容
- [2026-08-27 10:11] codex 签退 — 完成了：读取并梳理近期 agent 提交与当前未提交改动；下一步建议：先确认当前未提交规则库/条件评估改动归属与测试状态，再决定是否继续收敛或提交
- [2026-08-27 10:22] codex 签退 — 完成了：按 review comment 收紧 3.22 顶层步距缩小措施追证，避免仅出现“顶层步距”即误判措施存在，并补回归测试；下一步建议：提交后继续扩展 3.22 局部窗口解析和更多条件判定测试
- [2026-08-27 10:46] codex 签退 — 完成了：按浏览器批注优化审查详情展示：首页去除任务信息四格、总控建议隐藏英文参数名、完整性流程说明更新、四类详情抽屉同步折叠判定理由/证据并将 Agent 轨迹中文化，计算详情新增审查逻辑摘要；下一步建议：继续抽查真实任务中语义/计算/图文详情的信息层级，必要时把公式符号旁补中文释义

- [2026-08-27 11:09] codex 签到 — 开始处理：优化规则库新增规则按钮

- [2026-08-27 11:28] codex 签到 — 开始处理：执行规则库新增优化、参数图文一致性扩充、Agent计划解释增强

- [2026-08-27 11:53] claude 签到 — 开始处理：调查：已扩展参数校验规则+图文规则，但 web 页面无变化

- [2026-08-27 14:30] claude 签到 — 开始处理：图文一致性 Agent 分阶段开发方案 Task 0 基线审计

- [2026-08-27 14:45] claude 签退 — 完成了：图文一致性 Agent 化 Task 0 基线审计（339/339 passed，零代码改动）+ Task 1 公开 Tool wrapper + OCR 单页抽取（DRAWING_PARAM_REGISTRY 同对象别名 + 6 个 PUBLIC_WRAPPER + _ocr_single_page 抽取，净 +84 行，diff 全部归 REGISTRY_ALIAS/PUBLIC_WRAPPER/OCR_HELPER_EXTRACTION 三类，340/340 passed 新增 1 测试）；下一步建议：用户确认 Task 1 验收后进入 Task 2（Task/Evidence/State 数据模型）

- [2026-08-27 15:00] claude 签退 — 完成了：Task 2 数据模型层（app/drawing_agent.py：DrawingReviewTask/Evidence/DrawingAgentState 三个 dataclass 共 72 行 + tests/test_drawing_agent.py 92 行 1 个测试）；不接 Tool / 不接 build_drawing_review / 不实现 Agent；341/341 passed（基线 340 +1）；下一步建议：等用户确认后进入 Task 3（去掉 ProjectFacts 缺失即沉默）

- [2026-08-27 15:24] claude 签到 — 开始处理：Task 3: 候选核验任务生成器

- [2026-08-27 15:40] claude 签退 — 完成了：Task 3 候选核验任务生成器（app/drawing_agent.py +143 行：build_drawing_review_tasks + _task_from_registry_entry；tests/test_drawing_agent.py +1 测试覆盖 6 case；registry 17 项全唯一，missing fact 仍生成 Task source=critical_fact；342/342 passed；test_drawing_cross_check_skips_unidentified_params 旧行为保留 PASS；drawing_agent.py 143 行 超 120 期望 23 行 但在 145 硬上限内）；下一步建议：等用户确认后进入 Task 4（Drawing Agent V1 有限状态循环）

- [2026-08-27 15:32] claude 签到 — 开始处理：Task 4: DrawingConsistencyAgent V1

- [2026-08-27 15:55] claude 签退 — 完成了：Task 4 DrawingConsistencyAgent V1（app/drawing_agent.py +135 行：DrawingConsistencyAgent + MAX_ITERATIONS=3 + 3 Action 常量；tests +3 测试 happy_path/missing_text_value/empty_candidates；真实 Tool 注入兼容；345/345 passed；旧 missing-fact 测试 PASS；drawing_agent.py 278 行超 250 期望 28 行 但在 290 硬上限内）；下一步建议：等用户确认后进入 Task 5（OCR/VLM 分级追证）

- [2026-08-27 15:37] claude 签到 — 开始处理：Task 5A: Evidence 正式化 + OCR_PAGE 按需追证

- [2026-08-27 16:10] claude 签退 — 完成了：Task 5A Evidence 正式化 + OCR_PAGE 按需追证（drawing_review.py +6 行 ocr_drawing_page public wrapper；drawing_agent.py +145 行：OCR_PAGE Action + MAX_OCR_PAGES=2 + ocr_tool 依赖注入 + TextEvidence 自动初始化 + 2 内部 helper _resolve_candidate_page / _extract_ocr_evidence；tests +4 新测试 text_evidence_init/ocr_evidence_found/skips_to_second_page/ocr_unavailable，更新 1 旧 missing 测试断言为 OCR_PAGE 路径；349/349 passed；OCR 回归 4/4；drawing_agent.py 423 行（超 390 期望 33 行 但在 440 硬上限内）；下一步建议：等用户确认后进入 Task 5B（VLM 视觉理解）或 Task 6（双向追证）

- [2026-08-27 15:48] claude 签到 — 开始处理：Task 5B: INSPECT_IMAGE + VLM 结构化证据兜底

- [2026-08-27 16:20] claude 签退 — 完成了：Task 5B INSPECT_IMAGE + VLM 结构化证据兜底（drawing_agent.py +116 行：INSPECT_IMAGE Action + MAX_ITERATIONS=4 + MAX_VLM_CALLS=1 + vision_tool 依赖注入 + OCR 命中后不再自动 FINISH + _ocr_phase_done 判定 + _execute_inspect + _extract_vision_evidence；tests +4 新测试 ocr_evidence_triggers_vlm/ocr_miss_falls_back_to_vlm/vision_unavailable_preserves_ocr_evidence/vision_found_false_no_evidence，更新 2 旧测试 finish_reason 为 vision_unavailable；353/353 passed；OCR 回归 4/4；drawing_agent.py 539 行（超 510 期望 29 行 在 560 硬上限内）；tests 623 行（≤650 期望）；下一步建议：等用户确认后进入 Task 5C（真实 VLM Provider Adapter）或 Task 6（Drawing → Text 双向追证）

- [2026-08-27 16:05] claude 签到 — 开始处理：Task 5C: 真实 Vision Provider Adapter

- [2026-08-27 16:30] claude 签退 — 完成了：Task 5C 真实 Vision Provider Adapter（app/drawing_vision.py 217 行 + tests 199 行：复用项目 LLMChatClient + 引入 VLM_MODEL env 调 Qwen-VL/Aliyun DashScope，inspect_drawing_page → 6 字段 contract；drawing_review.py +19 行 resolve_drawing_image_path public wrapper；drawing_agent.py 0 行修改；6 个测试全过：normalizes_full_contract/drops_extra_fields/found_false_no_fabrication/image_missing_no_client_call/malformed_response_does_not_crash/agent_construction_compat；359/359 passed；agent 13/13 回归 OK）；下一步建议：等用户确认后进入 Task 6（Drawing → Text 双向追证）

- [2026-08-27 16:21] claude 签到 — 开始处理：Task 6: SEARCH_TEXT + Drawing→Text 双向追证

- [2026-08-27 16:40] claude 签退 — 完成了：Task 6 SEARCH_TEXT 双向追证（drawing_review.py +~100 行 search_text_evidence public + 3 内部 helper；drawing_agent.py +97 行：MAX_ITERATIONS=5/MAX_TEXT_SEARCHES=1/SEARCH_TEXT Action/search_text_tool 注入/_after_drawing_phase 决策点/INSPECT_IMAGE 与 OCR 不再自动 _finish 让 SEARCH_TEXT 介入；tests +4 test_drawing_text_search + 3 test_drawing_agent；drawing_vision.py 0 行；所有禁止文件 0 行；PROJECT_FACTS_WRITEBACK NO / TASK_VALUE_MUTATION NO；366/366 passed；drawing_agent.py 636 行（≤710 硬上限）；下一步建议：等用户确认后进入 Task 7

- [2026-08-27 16:39] claude 签到 — 开始处理：Task 6.1: 修正 SEARCH_TEXT value-anchor 语义

- [2026-08-27 16:50] claude 签退 — 完成了：Task 6.1 SEARCH_TEXT value-anchor 修正（drawing_review.py 净 +54 行：_scan_page_for_text_evidence 不再硬过滤 target + 新增 _extract_text_value 按 snippet 实际提取 + _values_match 最小相等比较 + 保留 _value_appears_in_text 作低层 helper；test Case 2 从 [] 改为保留 candidate value=160 matched=False；drawing_agent.py 0 行；drawing_vision.py 0 行；所有禁止文件 0 行；366/366 passed；drawing_review.py 1160 行 ≤70 硬上限）；下一步建议：等用户确认后进入 Task 7

- [2026-08-27 16:45] claude 签到 — 开始处理：Task 6.2: alias-local value binding fix

- [2026-08-27 17:00] claude 签退 — 完成了：Task 6.2 alias-local value binding（drawing_review.py 净 +62 行：_extract_value_and_unit_near_alias 以 alias 位置为中心 + _find_value_in_windows after/before 窗口优先级 + _find_scalar_in + _find_2d_in + _find_unit_near_value unit 绑定到 value 邻近 20 字；test Case 1 覆盖 A "高度5m，托撑插入长度150mm" + B "层高5.4m，立杆间距900×900mm" + value != 5/5.4 关键回归断言；Case 2 覆盖 C "高度5m，托撑插入长度160mm" + value != 5 断言；drawing_agent.py 0 行；drawing_vision.py 0 行；所有禁止文件 0 行；366/366 passed；drawing_review.py 1222 行 ≤70 硬上限）；下一步建议：等用户确认后进入 Task 7

- [2026-08-27 16:54] claude 签到 — 开始处理：Task 6.3: 边界核验 + before-alias fix

- [2026-08-27 17:10] claude 签退 — 完成了：Task 6.3 before-alias selection fix（drawing_review.py 净 +24 行：_find_scalar_in / _find_2d_in 新增 prefer_last 参数；after-window 仍取第一个（最接近 alias 起点），before-window 取最后一个（最接近 alias 终点）；两个 Case 合并进 Case 2 测试：层高5m，150mm为可调托撑插入长度设计值 → value=150 + value != 5；层高5.4m，900×900mm为梁底立杆间距 → value=[900,900] + value != 5.4；drawing_agent.py 0 行；drawing_vision.py 0 行；所有禁止文件 0 行；366/366 passed；test_drawing_text_search.py 仍 4 个 pytest 函数；drawing_review.py 1246 行）；下一步建议：Task 6 正式封版，等用户确认

- [2026-08-27 14:30] claude 签到 — 开始处理：图文一致性 Agent 分阶段开发方案设计

- [2026-08-27 15:24] claude 签到 — 开始处理：Task 3: 候选核验任务生成器

- [2026-08-27 15:32] claude 签到 — 开始处理：Task 4: DrawingConsistencyAgent V1

- [2026-08-27 15:37] claude 签到 — 开始处理：Task 5A: Evidence 正式化 + OCR_PAGE 按需追证

- [2026-08-27 15:48] claude 签到 — 开始处理：Task 5B: INSPECT_IMAGE + VLM 结构化证据兜底

- [2026-08-27 16:05] claude 签到 — 开始处理：Task 5C: 真实 Vision Provider Adapter

- [2026-08-27 16:21] claude 签到 — 开始处理：Task 6: SEARCH_TEXT + Drawing→Text 双向追证

- [2026-08-27 16:39] claude 签到 — 开始处理：Task 6.1: 修正 SEARCH_TEXT value-anchor 语义

- [2026-08-27 16:45] claude 签到 — 开始处理：Task 6.2: alias-local value binding fix

- [2026-08-27 16:54] claude 签到 — 开始处理：Task 6.3: 边界核验 + before-alias fix

- [2026-08-27 17:00] claude 签到 — 开始处理：续接：设计图文一致性 Agent 下一阶段方案（Task 7+）

- [2026-08-27 17:01] claude 签退 — 完成了：完成图文一致性 Agent Task 7+ 设计文档：docs/drawing_agent_v1_design.md 起草完成（9 章 1.5k 字），含 6 个 Task（业务接线/scope/结果聚合/前端展示/缓存/真实样例 benchmark）、2.6 天时间表、5 个决策点；TaskCreate 已落 7 个跟踪项，依赖图已建（7→8→9→{10,11}→12）；等待用户确认 5 个决策点（Task 7 是否立即启动 / scope 优先级 / benchmark 样例 / VLM 模型 / 灰度节奏）；下一步建议：用户确认 5 个决策点后从 Task 7（build_drawing_review_v2 业务接线 + feature flag）启动；如需调整 Task 切分或优先级请指示

- [2026-08-27 17:06] claude 签到 — 开始处理：Task 7A 实施：Evidence Scope 提取 + Scope 对齐（drawing_scope.py + 5 测试 + Agent 最小 enrichment）

- [2026-08-27 17:11] claude 签退 — 完成了：Task 7A 完成（36e9fc9）：drawing_scope.py 175 行（4 函数 + 3 常量）+ test_drawing_scope.py 144 行（5 测试）。Agent 4 处 Evidence scope 改 resolve_evidence_scope（+2 行）；test_drawing_agent.py 改 3 个 fake + 3 行断言（无新 pytest）。drawing_review.py / drawing_vision.py / web.py / main.py / orchestrator_agent.py / report_generator.py / project_facts.py / requirements.txt / rules/* delta=0。371 passed / 1 skipped / 0 failed（+5 tests 全绿）；下一步建议：等用户确认 Task 7A → 进入 Task 7B（value 比较 + 一致性状态 CONSISTENT/CONFLICT/TEXT_ONLY/DRAWING_ONLY/UNCERTAIN/NOT_FOUND）

- [2026-08-27 17:30] claude 签到 — 开始处理：Task 7B/7B.1/7C/7C.1/8A/8A.1 串行实施

- [2026-08-27 18:00] claude 签退 — 完成了：Task 7B→8A.1 全套封版（6 commits，388 passed/1 skipped/0 failed）：
  - f74aaa7  Task 7B  drawing_compare.py 271 行 + 8 个测试
  - 95aacd2  Task 7B.1  multi-pair 聚合修正（len(pairs)>1 一律 UNCERTAIN）
  - 4086989  Task 7C  _check_result_to_drawing_evidence（CHECK_PARAM → 结构化 Evidence）
  - d40e7dd  Task 7C.1  CHECK_PARAM provenance（multi-match 唯一性 + unit=None）
  - 57551f9  Task 8A  build_agent_drawing_review（Integration Preview，5 个端到端测试）
  - 4797f3a  Task 8A.1  test 收敛（390→277 行）+ **registry scope passthrough** 1 行补全
  设计文档 docs/drawing_agent_v1_design.md 更新"已完成"清单 1.3 节（含 registry scope
  passthrough 数据通道补全说明，不属于业务行为变更）。下一步建议：等用户确认 → 进入
  Task 8B（真实方案全量 Agent 回归）；registry scope passthrough 已在 Task 8 体系门禁
  之前就绪，Task 8 实施时无需重做这部分数据通道。

- [2026-08-27 18:30] claude 签退 — 完成了：Task 8B 真实方案 Agent 全量回归（OBSERVE-ONLY，production 0 delta）：用项目既有 job `146dc530dd964a30a2d4f29410738e4d`（214 页高支模方案 PDF，30 个 ProjectFacts，17 个 registry task，5 个 legacy drawing_review 项）跑完整 `build_agent_drawing_review`，回归脚本写到 `tmp/drawing_agent_regression/`（3 个 artifact：agent_result.json / task_audit.json / legacy_comparison.json，不进 git）。总耗时 4.7s，full suite 388/1/0 不变。

  真实结果（不修代码，只记录）：
  - 状态分布：CONSISTENT=0, CONFLICT=0, TEXT_ONLY=3, DRAWING_ONLY=0, UNCERTAIN=1, NOT_FOUND=13
  - DECISIVE=0/17=0% （非 accuracy，是 deterministic decision coverage）
  - 工具调用：SEARCH_DRAWING=17, CHECK_PARAM=4, OCR_PAGE=11, INSPECT_IMAGE=7, SEARCH_TEXT=0
  - OCR/VLM 实际跑了 7 task；VLM 配置了 credential，但 Agent 实际触发了 7 次 INSPECT_IMAGE
  - NOT_FOUND 13 中：5 task `no_candidate_pages`（6/13 实际），8 task `ocr_no_evidence`；TEXT_ONLY 3 是因为 legacy `_cross_check_param` 找不到图纸标注
  - UNCERTAIN 1（horizontal_spacing scope_unknown）：drawing Evidence 来自 CHECK_PARAM legacy，text+drawing scope 都空 → 走 scope_unknown 分支（注意：CHECK_PARAM 路径 drawing unit=None 是 Task 7C.1 provenance 故意设的，unit_incomplete 没在本次 17 task 触发因为 scope 不 compatible）
  - legacy vs agent：4 个有 legacy 数据的 fact 中 3 个 legacy 状态/agent 状态完全错位（legacy 看到 ISSUE/PASS 但 drawing 来自 `_cross_check_param` 后真实 RepositoryFacts 与图纸标注差 1-2 个数量级，看起来 legacy cross_check 用了 body_value=m 误抓 4.0=4000mm 当 drawing；agent CHECK_PARAM 路径上 unit=mm 收不到 unit 但 alias-local 推断没找到证据 → TEXT_ONLY）

  P0 阻断（13/17 tasks = 76%）：Drawing Recall 缺陷——critical_fact 任务在 214 页方案里 6 个连候选页都没有（base_jack_*/free_end/top_level/main_beam/monitoring），另 7 个 OCR 触发后找不到 alias 命中。
  P1（4/17）：Unit Provenance（Task 7C.1 故意设 unit=None）。
  P2（1/17）：Scope Inference（horizontal_spacing）。

  推荐下一任务（仅一项）：Drawing Recall Enhancement——让 OCR/VLM 在 alias hit 之前先做 raw page scanning，提升 recall。
  不要为 unit_incomplete 妥协 comparator 规则；不要把 task.unit 填回 DrawingEvidence。

  design doc 不需要新版本：已用 Section 1.3 已完成清单记录当前封版基线。
  下一步建议：等用户确认 P0 路径；不进入 Task 8C。

- [2026-08-27 19:00] claude 签退 — 完成了：Task 8B.2 失败尸检（OBSERVE-ONLY，0 production delta）：
  逐个对 13 个 critical_fact DrawingEvidence acquisition failure 做 alias/synonym 在 214 页全文档搜索 + 候选页 OCR/VLM 链路审计。
  核心修正 Task 8B.1 错误的 P0（"Drawing Recall"）：
  
  真实 primary root cause 分布（13 task 总和）：
  - OCR_RECOGNITION_MISS: 7（Group B；recall 找到 1-8 候选页，但 OCR 在 image block 上无法 re-detect alias text；VLM found=False 是 downstream consequence 而非 primary）
  - TARGET_NOT_PRESENT: 5（base_jack_insertion/free_end/base_jack_screw_ext/top_level_to_jack/main_beam——5 个参数连"插入"/"自由端"/"底座外伸"等 3-4 个工程同义表达在 214 页都搜不到；这些是规范条文要求/施工组织设计参数，不是图纸标注目标）
  - ALIAS_RECALL_MISS: 1（monitoring_point_spacing：target "监测点" 在 p41 出现 6 次，但 registry "监测点间距/观测点间距" 不在文本里）
  
  真实 P0 = TARGET_NOT_PRESENT (5/13 = 38.5%)，不是 recall/OCR/VLM。
  按 §四十八 决策规则：最大类是 TARGET_NOT_PRESENT 时不做 recall enhancement；
  重新评估 registry applicability → Drawing Review Task Applicability / Registry Governance。
  
  Coverage（diagnostic, NOT accuracy）：
  - DRAWING_TARGET_EXISTENCE_RATE: 8/13 = 61.5%
  - PAGE_RECALL_RATE_ON_EXISTING_TARGETS: 7/8 = 87.5% (excluding ALIAS_RECALL_MISS) / 0/8 if strictly
  - EVIDENCE_EXTRACTION_RATE_ON_CORRECT_PAGES: 0/8 (OCR layer 全部失败)
  
  推荐下一任务：Drawing Review Task Applicability / Registry Governance（仅 1 项推荐）
  Backlog P1: OCR_RECOGNITION_MISS (7) — Drawing OCR Evidence Extraction Enhancement
  Backlog P2: ALIAS_RECALL_MISS (1) — Registry Alias Audit
  
  full suite 388/1/0 不变；artifacts 在 tmp/drawing_agent_regression/root_cause_audit.json（.gitignored）。
  不实施推荐任务；不进入 Task 8C；等待用户确认 P0 路径。

- [2026-08-27 19:30] claude 签退 — 完成了：Task 8B.2.2 MinerU Image Asset Provenance & Resolution Audit
  （OBSERVE-ONLY，0 production delta）：
  审计 146dc job 的 7 个 Group B 任务 image asset 失败真实根因。
  
  关键发现：原 7 task "OCR_RECOGNITION_MISS" 实际是 PARSED_DOCUMENT_LOSS 根因的
  downstream 表现（image file 完全没在 job_dir）。
  
  证据链：
  1. mineru_document.json 引用 193 个 image_path（相对路径 part-001/raw 或 part-002/raw）
  2. Resolver 尝试 job_dir/mineru_api/raw/<rel> 和 job_dir/mineru_api/<rel> → 都不存在
  3. job_dir 0 image files；project data/ 0 真实图（.pytest_tmp 9 个是 test fixture）
  4. 全项目按 basename rglob → 0 matches
  5. MinerU cache (data/cache/mineru/) 2 个 keys 用 PDF-hash，不包含此 job
  6. asset_prefix pattern (mineru_cache.py:313) 显示 image_path 设计为 asset_prefix + block.image_path
  7. mineru_cache.py:424 有 'shutil.copytree(raw_source_dir, cache_dir/"raw")' 但只走 cache flow
  8. CLI/web flow (146dc 走的路径) 没有 co-save raw image assets
  9. Original PDF EXISTS at job_dir/source.pdf (4.7MB, 214 pages) → 提供 PDF page render fallback 路线
  
  根因：JOB_ARTIFACT_COPY_LOSS（pipeline 保存 mineru_document.json 但未 co-save raw image assets）
  
  REAL_TOOL_INVOCATIONS 重新计数（纠正 Task 8B 错数）：
  - INSPECT_IMAGE_ACTIONS: 7（Agent action count）
  - VISION_ADAPTER_INVOCATIONS: 7（function calls）
  - REAL_PROVIDER_REQUESTS: 0（实际 VLM API call；image missing → short-circuit _empty_contract()）
  - OCR_PAGE_ACTIONS: 7
  - OCR_ADAPTER_INVOCATIONS: 7
  - REAL_OCR_ENGINE_CALLS: 0（同理，image missing → continue）
  
  Applicability 降级：之前 4 个 NOT_APPLICABLE 因 image asset 完全 unavailable
  暂不能证明 drawing image 一定没目标。改为 UNRESOLVED_DUE_TO_IMAGE_ASSETS。
  仅 base_jack_screw_extension 保持 TARGET_NOT_FOUND_AFTER_AVAILABLE_AUDIT。
  
  推荐下一任务：MinerU Job Artifact Persistence Fix
  修复：CLI/web parse flow 应 co-save raw image assets 到 job_dir/mineru_api/raw/
  （或保存 image_path 为绝对路径，或 resolver 先查 cache）。
  Backup: PDF physical-page rendering fallback（PDF 存在 214 页）。
  
  full suite 388/1/0 不变。artifacts 在 tmp/drawing_agent_regression/（.gitignored）。
  不实施推荐任务；不进入 Task 8C；等待用户确认 P0 路径。

- [2026-08-27 20:00] claude 签退 — 完成了：Task 8B.3 MinerU Job Artifact Persistence Fix
  （修复 Task 8B.2.2 鉴定的 JOB_ARTIFACT_COPY_LOSS 真实根因）：
  
  app/mineru_cache.py 新增 _ensure_job_local_raw_assets helper（59 行）：
  - parse_pdf_with_cache 末尾在 cache-hit 和 non-cache 两条路径都调用
  - 优先从 cross-job cache_dir/raw/ copytree
  - 退路：MinerU natural output raw_output_dir/<part>/raw/ 重组到
    raw_output_dir/raw/<part>/raw/（保持现有 resolver 第一个查找路径命中）
  - 任何 OSError 静默 swallow；返回 image count
  - 不抛、不修改 drawing_review.py 现有 resolver
  
  tests/test_mineru_cache.py +4 个 pytest 函数：
  - test_ensure_job_local_raw_assets_copies_from_cache
  - test_ensure_job_local_raw_assets_noop_when_already_present
  - test_ensure_job_local_raw_assets_falls_back_to_mineru_output
  - test_ensure_job_local_raw_assets_returns_zero_when_nothing_available
  
  修复影响范围：未来新 job 走此 pipeline 时 raw image assets 自动 co-save。
  146dc 历史 job 因为 cache 也是空、原始 raw output 也已丢失，需要在 Task 8B.4
  重新 re-MinerU 解析才能恢复。
  
  full suite 392 passed / 1 skipped / 0 failed（+4 tests，0 回归）。
  不实施 Task 8B.4 / 8C / 8D；等待用户确认。

- [2026-08-27 19:38] claude 签到 — 开始处理：Task 8B.4: re-MinerU 真实方案 + 重建可信 Drawing Agent baseline

- [2026-08-27 20:00] claude 签退 — 完成了：Task 8B.4 OBSERVE-ONLY 重建（0 production delta，0 pytest delta）：

  **A. 基础设施恢复（Cache 命中 1.6s）**
  - 真实 parse flow `parse_pdf_with_cache` 重跑：cache_hit=True（key `0f1f8b56...`），自动触发 `_ensure_job_local_raw_assets` → `data/web/jobs/146dc.../mineru_api/raw/` 落盘 922 jpg
  - Asset Gate：143/143 image_path resolvable（0 missing），5 个随机 sample 全部存在（12-78KB），job 自包含（source.pdf/mineru_document.json/mineru_api/raw/project_facts.json 齐全）

  **B. Tool Smoke（VLM 真实能力首次被观察到）**
  - OCR：RapidOCR onnx 引擎加载，page 21 真实读图，识别 "立杆/水平杆/对接扣件/≥500/0593" 21 字
  - VLM：qwen-vl-plus 真实 provider request，page 21 找到 value=500mm/evidence "≥500"/confidence 1.0
  - 旧 8B 的 VLM 0 调用问题根因是 image asset 丢失（Task 8B.2.2 已鉴定的 JOB_ARTIFACT_COPY_LOSS）

  **C. 17-task Agent 真实 baseline（6.41s）**
  - 状态分布：CONSISTENT=0 / CONFLICT=0 / TEXT_ONLY=3 / DRAWING_ONLY=0 / UNCERTAIN=1 / NOT_FOUND=13
  - 与旧 8B 完全相同（0/0/3/0/1/13）—— **status counts 没变，但 wire 状态变了**
  - Tool：SEARCH_DRAWING=17 / CHECK_PARAM=4 / OCR_PAGE=11（3 真返文）/ INSPECT_IMAGE=7（7 真发 provider，0 found）/ SEARCH_TEXT=0
  - Evidence coverage：TEXT=4/17, DRAWING=1/17, BOTH=1/17, NO=13/17（与旧 8B 相同；唯一的 drawing_evidence 来自 legacy_check horizontal_spacing）
  - Decision coverage：0/17=0%（deterministic, 非 accuracy）

  **D. 真实新 P0 = OCR/VLM recognition miss（不再 TARGET_NOT_PRESENT）**
  - 7 NOT_FOUND = ocr_no_evidence（OCR 在候选页上没 re-detect alias text）
  - 6 NOT_FOUND = no_candidate_pages（base_jack_*/free_end/top_level/main_beam/monitoring 在 214 页都没命中 alias；任务 8B.2 鉴定的 TARGET_NOT_PRESENT 仍存在但降到 P1）
  - 1 NOT_FOUND = base_jack_screw_extension（alias "外伸"/"底座外伸" 等同义表达在 214 页完全缺失）
  - 1 UNCERTAIN = horizontal_spacing（scope_unknown，legacy_check 给的 drawing unit=None 是 Task 7C.1 provenance 故意）
  - VLM smoke 在 page 21 找到了 500mm 但 agent 在同一页调 INSPECT_IMAGE 返回 found=False：提示 prompt 形态差异显著影响 VLM 表现

  **E. Reverse Chase 0 触发**：VLM/OCR 都没拿到 drawing value，SEARCH_TEXT 失去 anchor
  **F. Production code delta = 0**（新增 tmp/drawing_agent_regression_8b4/run_8b4.py，.gitignored）
  **G. Tests**：前 392/1/0 → 后 392/1/0（无变化）

  artifacts（均 tmp/.gitignored，不入 git）：
  `OLD_STATE.json / parse_info.json / asset_audit.json / job_self_contained.json / ocr_smoke.json / vision_smoke.json / agent_result.json / task_audit.json / tool_call_stats.json / legacy_comparison.json / final_report.json`

  推荐下一任务（仅 1 项）：**Drawing OCR Evidence Extraction Enhancement**（VLM smoke 已证明能力可达 page-21 → 500mm；agent 7 次 INSPECT_IMAGE 0 found 表明 prompt 形态需要适配）
  Backlog P1：Drawing Recall Enhancement（6/13 = no_candidate_pages，alias 召回问题）
  Backlog P2：Registry Alias Audit（monitoring_point_spacing）

  不实施推荐任务；不进入 Task 8C；不修改 Registry/Agent/Comparator；不补 alias/scope/unit；等待用户确认 P0 路径。

- [2026-08-27 20:25] claude 签退 — 完成了：Task 8B.4.1 Vision Smoke vs Agent Run Parity Audit（OBSERVE-ONLY，0 production delta，0 new pytest）：

  **关键发现 — 7 Vision false 中 5/7 实际是 page 没图，2/7 才是 task 接地问题**
  - 4 case `TARGET_NOT_IN_SELECTED_IMAGE`（support_height p3 / sweeper p18×2 / panel_thickness p50 / panel_stringer_spacing p18，页面 0 image block，agent 仍走 INSPECT_IMAGE → `_empty_contract`，无 provider 请求）
  - 1 case `IMAGE_SELECTION_MISS`（height_to_width_ratio p20，与 smoke 不同图）
  - 2 case `TASK_GROUNDING_MISMATCH`（head_jack_insertion / head_jack_screw_exposed_length p21，**SAME image as smoke 哈希校验通过**，agent 仍 found=False）

  **Parity Replay（4 calls，预算内）** — page 21 同图同 provider 同模型：
  - 1A: head_jack_insertion_length + agent task → found=False
  - 1B: 同图 + smoke-style task → **found=True, value=500, "≥500"** ✓
  - 2A: head_jack_screw_exposed_length + agent task → found=False
  - 2B: 同图 + smoke-style task → **found=True, value=500, "≥500"** ✓
  → VLM 能力可达；prompt aliases 视觉语义 gap 是真因（agent aliases 缺 "可调托撑" 这个图像真实术语）

  **OCR P0 重判：NO** — RapidOCR 引擎工作正常（3/3 real calls 返文），OCR 不是瓶颈。3/3 evidence_created=0 是 alias 匹配 gap。

  **更正 8B.4 tool_stats**：4 case 实际未发 provider 请求（image 缺失 short-circuit），真 REAL_PROVIDER_REQUESTS=3（非 7）。

  **Root Cause Distribution (sum=7)**：TARGET_NOT_IN_SELECTED_IMAGE=4 / IMAGE_SELECTION_MISS=1 / TASK_GROUNDING_MISMATCH=2 / VLM_NONDETERMINISM=0 / TRUE_VLM_RECOGNITION_MISS=0

  **NEXT_TASK 改为：Drawing Image Selection Enhancement**（5/7 = 71% 是 page-level recall 选错页；不是 VLM/OCR）
  - Backlog P1: Drawing Task Grounding Enhancement（2/7 同图 prompt 适配）
  - Backlog P2: Drawing Alias Recall Enhancement（OCR 返文但 0 evidence）

  artifacts：`vision_parity_audit.json` / `vision_parity_summary.md` / `parity_replay.json`（tmp/.gitignored，不入 git）。
  full suite 392/1/0 不变；不实施推荐任务；不进入 Task 8C；等待用户确认 P0 路径。

- [2026-08-27 19:55] claude 签到 — 开始处理：Task 8B.4.1: Vision Smoke vs Agent Run Parity Audit (OBSERVE-ONLY)

- [2026-08-27 20:02] claude 签到 — 开始处理：Task 8B.5: Drawing Vision Candidate & Image Selection Enhancement

- [2026-08-27 20:45] claude 签退 — 完成了：Task 8B.5 Image Applicability Gate（最小生产改动 + 5+1 regression）：

  **Production 改动**（2 files）：
  - `app/drawing_vision.py`：新增 `has_usable_drawing_image()` / `select_relevant_drawing_image()`；`inspect_drawing_page` 加 `image_path` kwarg（Agent 预选图）
  - `app/drawing_agent.py`：`_execute_inspect` 加 usable image gate；候选穷尽无图 → `finish_reason='no_usable_image'`，不调 vision_tool、不增 vlm_calls
  - 多 image 排序（deterministic）：alias hit desc / file size desc / block_index asc

  **5 regression tests**（tests/test_drawing_agent.py）：
  1. candidate A no-image / B has image → only B called, vision_calls=[88]
  2. all no-image → 0 vision calls, finish_reason='no_usable_image'
  3. multi-image with alias hit → 选 B（alias 命中），单次调用
  4. multi-image no alias hit → 选 a.jpg (block_index=0)，两次运行一致
  5. image_path 设但文件缺失 → unusable，vision 跳过该 block

  **1 保护 test**（page 21 grounding）：验证 Task 8B.4.1 鉴定的 grounding 失败 case 仍 found=False（防止本 Task 误用 alias/prompt 改 PASS）

  **Tests**：前 392/1/0 → 后 **398/1/0**（+6 全部新增/更新）
  **Budgets**：MAX_ITERATIONS/MAX_OCR_PAGES/MAX_VLM_CALLS/MAX_TEXT_SEARCHES 0 delta
  **PRODUCTION_CODE_CHANGE: YES**（仅 drawing_vision.py + drawing_agent.py）
  **VISION_PROMPT/ALIAS/REGISTRY/OCR/COMPARATOR/SCOPE/UNIT/BUDGET/WEB/ORCHESTRATOR_CHANGE: NO**

  **已知剩余问题（按 8B.4.1 P1 保留）**：
  - TASK_GROUNDING_MISMATCH：head_jack_insertion_length / head_jack_screw_exposed_length 在 page 21 同图 VLM 仍 found=False（smoke-style aliases 含「可调托撑」可达 500mm；本 Task 不改 prompt/alias）

  **生产 diff 略超 100 行**（drawing_vision +89 + drawing_agent +67 = ~156，跨 2 文件自然超出；但 2 files 限制内）
  **测试 diff 略超 150 行**（test_drawing_agent +323 / test_drawing_integration +47；既有测试 fake page 无 image block，新增 production 行为后必须给测试 page 补 image，helper 改动是必然开销）
  推荐下一任务：Task 8B.5.1（真实回归验证 7 Vision cases 在新 gate 下行为变化）
  不实施推荐任务；不进入 Task 8C；等待用户确认。

- [2026-08-27 20:46] claude 签退 — Task 8B.5 Image Applicability Gate 已 commit。

- [2026-08-27 20:15] claude 签到 — 开始处理：Task 8B.5a: Diff Governance Cleanup (no behavior change)

- [2026-08-27 22:25] codex 签到 — 开始处理：读取最近的更改

- [2026-08-27 22:26] codex 签退 — 完成了：读取最近提交与未提交 diff，整理变更摘要；下一步建议：如需继续，可审查未提交的 drawing_vision 重构与 Tool 别名测试后再决定是否提交

- [2026-08-27 22:34] codex 签到 — 开始处理：Task 8B.5a: Diff Governance Cleanup

- [2026-08-27 22:35] codex 签退 — 完成了：Task 8B.5a Diff Governance Cleanup（不改变生产行为）：`drawing_vision.py` 合并可用图片 resolver/iteration 单一路径；`test_drawing_agent.py` 将 8B.5 的 no-image/later-valid/multi-image/missing-file/deterministic/page21/statistics 语义压缩为参数化矩阵；移除半途遗留的非本任务 vertical_slice 公共别名测试。Diff 治理结果：production 67/38 + 72/4，净新增 97（<=120）；tests 170/15 + 35/12，净新增 178（<=180）。Focused `32 passed`；Full `398 passed / 1 skipped / 0 failed`（1 LibreSSL warning）。下一步建议：Task 8B.5.1 — Real Regression After Image Gate

- [2026-08-27 22:58] codex 签退 — 完成了：Task 8B.5.1 Real Regression After Image Gate（OBSERVE-ONLY，0 production/test change）：复用真实 job `146dc530dd964a30a2d4f29410738e4d`，asset gate `193/193 resolvable, missing=0`，registry=17，budgets=5/2/1/1。
  - 真实 17-task：状态分布由 8B.4 `0/0/3/0/1/13` → `0/0/3/0/2/12`（CONSISTENT/CONFLICT/TEXT_ONLY/DRAWING_ONLY/UNCERTAIN/NOT_FOUND）。
  - Vision routing：INSPECT_IMAGE actions 7→12；vision_tool invocations 7→6；real provider requests corrected 3→6；no-image fake false 4→0；VLM true/false/invalid=1/5/0。
  - Gate 真实效果：PASS。4 个旧 no-image case 中 3 个跳过无图候选后到达后续 usable image，1 个 `panel_stringer_spacing` 正确结束 `no_usable_image`；跳过 no-image candidates 总数=6。
  - Page21 grounding：`head_jack_insertion_length` / `head_jack_screw_exposed_length` 仍同图 provider called 且 found=false，符合 8B.5 未改 grounding 的预期。
  - Evidence：TextEvidence tasks=5；DrawingEvidence tasks=2；Both-side=2；No-evidence=12；sources: legacy_check=1 task/1 ev，vision=1 task/1 ev，ocr=0。
  - OCR：actions/adapter/real/nonempty=11/11/10/3，OCR text nonempty tasks=3，但 OCR drawing evidence tasks=0；Reverse chase=1 action/1 hit/0 miss。
  - Comparator：COMPARABLE_PAIR_0=17，decisive=0/17（diagnostic deterministic coverage, not accuracy）；UNCERTAIN reason: scope_unknown=2；finish reasons: check_completed=4, text_evidence_found=1, ocr_no_evidence=5, no_candidate_pages=6, no_usable_image=1。
  - Artifacts（tmp ignored，不提交）：`tmp/drawing_agent_regression_8b5_1/{agent_result.json,task_audit.json,tool_call_stats.json,regression_comparison.json}`；结束 full suite `398 passed / 1 skipped / 0 failed`。下一步建议：Task 8B.6 — Drawing Candidate Recall / Alias Enhancement

- [2026-08-27 23:09] codex 签到 — 开始处理：Task 8B.5.2: CHECK_PARAM Registry Config Wiring Fix

- [2026-08-27 23:10] codex 签退 — 完成了：Task 8B.5.2 CHECK_PARAM Registry Config Wiring Fix：修复 `build_agent_drawing_review` integration boundary 的 fact_id-only config gap，用传入 registry 建局部 `fact_id -> registry entry` 绑定并在 injected check_tool 前 copy-merge（runtime 覆盖 registry；missing lookup fallback 原 config；不 mutation；无 global state）。
  - 变更范围：production 仅 `app/drawing_integration.py`（24/2，净 +22）；test 仅 `tests/test_drawing_integration.py`（94/0，新增 4 regression）。`drawing_agent.py` / `cross_check_param` / `DrawingReviewTask` / Registry 内容 0 delta。
  - 新测覆盖：完整 registry config + custom_marker 透传、registry 不被修改、DI contract 与 DrawingEvidence conversion 保留、direct path 与旧 workaround path parity。
  - Focused `tests/test_drawing_integration.py`: 9 passed；Full suite: 402 passed / 1 skipped / 0 failed（1 LibreSSL warning）。
  - 真实 4-task CHECK_PARAM smoke（job `146dc530dd964a30a2d4f29410738e4d`）：direct production path + `cross_check_param`，无 instrumentation wrapper，CHECK_PARAM actions=4，INSPECT_IMAGE/VLM=0，vs 8B.5.1 workaround baseline parity PASS。
  - 保留问题未修：6 no_candidate_pages、`panel_stringer_spacing` no_usable_image、page21 grounding mismatch、scope_unknown x2。下一步建议：Task 8B.6 — Drawing Candidate Recall / Alias Enhancement

- [2026-08-27 23:19] codex 签到 — 开始处理：Task 8B.6: Drawing Candidate Recall Fallback Enhancement

- [2026-08-27 23:31] codex 签退 — 完成了：Task 8B.6 Drawing Candidate Recall Fallback Enhancement：
  - Production：`DrawingReviewTask` 新增 `recall_terms` 默认空列表；registry task builder copy metadata；`SEARCH_DRAWING` 改为 aliases primary miss 后才用 recall_terms fallback，同一个 action/iteration 内记录 `recall_mode`、`primary_candidate_count`、`fallback_candidate_count`，保留 `candidate_count`。
  - Registry：仅新增 3 个 recall_terms：`top_level_to_jack_distance=["顶层水平杆"]`、`main_beam_spacing=["主梁间距"]`、`monitoring_point_spacing=["监测点"]`；未改 aliases/fact_id/unit/scope。
  - Tests：新增 bounded fallback、primary-hit 不 fallback、empty recall terms 不 fallback、observation 字段、recall_terms 不进入 OCR/Vision/search_text aliases、builder copy 覆盖；focused `tests/test_drawing_agent.py` = 33 passed。
  - Full suite：408 passed / 1 skipped / 0 failed（1 LibreSSL warning）。
  - 6-task deterministic recall smoke：旧 6 个 no_candidate 中 3 个仍无安全 recall_terms；3 个 fallback 得到候选页（top-level 6、main-beam 4、monitoring 2）。
  - 6-task real regression：NEW_NO_CANDIDATE=3，FALLBACK_CANDIDATE=3，NO_USABLE_IMAGE=1，VISION_REACHED=2，DRAWING_EVIDENCE=0；未运行 Task 8C。
  - 下一步建议：Task 8B.7 — Drawing Task Grounding Enhancement

- [2026-08-27 23:30] codex 签到 — 开始处理：Task 8B.6.1: Post-Recall Vision Grounding Audit

- [2026-08-27 23:39] codex 签退 — 完成了：Task 8B.6.1 Post-Recall Vision Grounding Audit（observe-only，0 production/test change）：审计 4 个 selected-image case。
  - 新 fallback false：`top_level_to_jack_distance` 选中 page21 `db5...jpg`，图中无目标“顶层水平杆至托撑/调节螺杆伸出长度”与目标值，`RECALL_TERM` 只在页面文本中；重归类为 candidate/image issue，不证明 grounding。
  - 新 fallback false：`monitoring_point_spacing` page41 无 usable image 后进入 page214 `a462...jpg`，selected image 有监测布置视觉元素但无清晰“监测点间距”或目标值，`RECALL_TERM` 来自页面标题/文本；重归类为 image/readability issue，不证明 grounding。
  - 已证明 golden：`head_jack_insertion_length` / `head_jack_screw_exposed_length` 复用 8B.4.1 parity replay，同 page21 同图同 provider/model：agent task false，smoke-style grounded terminology true，正式保留为 task grounding issue。
  - Full suite：408 passed / 1 skipped / 0 failed（1 LibreSSL warning）。下一步建议：Task 8B.7 — Drawing Task Grounding Enhancement（仅针对已证明 golden terminology gap）。

- [2026-08-27 23:39] codex 签到 — 开始处理：Task 8B.7: Drawing Task Grounding Enhancement

- [2026-08-27 23:47] codex 签退 — 完成了：Task 8B.7 pre-implementation applicability audit，结论 BLOCKED_BY_APPLICABILITY（observe-only，0 production/test change）：
  - page21 selected image hash `c8cef8cd60a4345c...` 与 golden artifact 一致；图中可见术语为“立杆 / 水平杆 / 对接扣件 / ≥500”，未见“可调托撑/托撑/顶托/插入立杆/丝杆外露”等可将 `≥500` 安全归因到 head-jack 的视觉术语。
  - `head_jack_insertion_length`：visible value=≥500，但 term→fact relation=UNCLEAR/NO；不能把 smoke-style recognition success 当作插入长度 attribution。
  - `head_jack_screw_exposed_length`：visible value=≥500，但图中无外露长度语义，且 page text 对丝杆外露约束为 400mm；APPLICABLE=NO，禁止通过 vision_terms 强行转 true。
  - 因两条 proven case 均未达到 APPLICABLE=YES，本 Task 未新增 `vision_terms`、未改 prompt、未跑新 provider smoke，避免 false-positive grounding。
  - Full suite：408 passed / 1 skipped / 0 failed（1 LibreSSL warning）。下一步建议：Task 8B.7a — Correct Golden Grounding Set / Image Attribution Audit。

- [2026-08-27 23:44] codex 签到 — 开始处理：Task 8B.7a: Correct Golden Grounding Set / Image Attribution Audit

- [2026-08-27 23:56] codex 签退 — 完成了：Task 8B.7a Correct Golden Grounding Set / Image Attribution Audit（observe-only，0 production/test/registry/prompt change）：
  - 历史术语纠偏：page21 两 case 从 `PROVEN_TASK_GROUNDING` 改称 `RECOGNITION_PARITY_WITH_UNPROVEN_ATTRIBUTION`；page21 role 固定为 `RECOGNITION_REFERENCE_ONLY`。
  - 审计 8 个候选：`support_height`、`height_to_width_ratio`、`sweeper_centerline_height_above_base_plate`、`head_jack_insertion_length`、`head_jack_screw_exposed_length`、`top_level_to_jack_distance`、`panel_thickness`、`monitoring_point_spacing`。
  - SAFE_GOLDEN_COUNT=1：`support_height` page22 图中 `H≤8m` 可安全归属于搭设/支架高度；但当前 agent found=true/value=null，属于 value extraction miss，不是 grounding found=false。
  - GROUNDING_CANDIDATE_COUNT=0：没有满足 candidate+selected image correct+parameter/value visible+attribution safe+provider called+found=false 的 case。
  - Negative controls：page21 insertion/exposed 均 attribution unsafe；top_level target_not_in_image；monitoring value_not_readable。
  - Artifacts（tmp ignored）：`tmp/drawing_grounding_golden_audit_8b7a/{golden_candidate_audit.json,golden_set.json,audit_summary.md}`；NEW_PROVIDER_REQUESTS=0。
  - Tests before/after：408 passed / 1 skipped / 0 failed（1 LibreSSL warning）。下一步建议：Task 8B.7b — Drawing Vision Value Extraction Audit for Safe Golden。

- [2026-08-27 23:56] codex 签到 — 开始处理：Task 8B.7b: Drawing Vision Value Extraction Audit for Safe Golden

- [2026-08-28 00:07] codex 签退 — 完成了：Task 8B.7b Drawing Vision Value Extraction Audit for Safe Golden（observe-only，0 production/test/registry/prompt change）：
  - Hash parity PASS：support_height page22 selected image `01b354...f79b.jpg` sha `f7b746a6acdbc121`。
  - 真实 production provider 1 次请求：raw safe fields = found=true/value=null/unit=m/evidence_text=`Hs/m`；parser/inspect 均原样保留，adapter 未丢值。
  - Layer trace：DrawingEvidence 已创建但 value=null；action observation 只记录 found/has_value=false；Comparator 仅支持 scalar/2D，不支持 inequality/range/constraint。
  - 深审计纠偏：`support_height` fact 是实际支撑架搭设高度/多区域最大值；page22 `H≤8m` 是约束/分类图示，不是 actual scalar drawing value。
  - SAFE_GOLDEN_RETAINED=NO，TASK8B7B_STATUS=COMPLETED_GOLDEN_DOWNGRADED；把 `H≤8m` 简化为 value=8 不具备语义安全性。
  - Root cause：PRIMARY=`VALUE_SCHEMA_CANNOT_REPRESENT_CONSTRAINT`，SECONDARY=`VLM_DID_NOT_READ_VALUE`；不建议做普通 Vision extraction prompt fix。
  - Artifacts（tmp ignored）：`tmp/drawing_value_extraction_audit_8b7b/{support_height_trace.json,value_contract_audit.json,audit_summary.md}`。
  - Tests before/after：408 passed / 1 skipped / 0 failed（1 LibreSSL warning）。下一步建议：No Vision-value implementation；回到真实 evidence acquisition / attribution blocker。

- [2026-08-28 00:16] workbuddy 签到 — 开始处理：Task 8B.8 — Drawing Evidence Acquisition Finalization（17-task 全量 Evidence Classification，observe-only 优先）

- [2026-08-28 10:02] codex 签到 — 开始处理：读取最近更改并续接 workbudy 中断修复

- [2026-08-28 10:03] codex 签退 — 完成了：读取最近更改：workbuddy 仅有 Task 8B.8 签到、无未提交代码；修复 fact_conflict_detector 空定义/空候选 KeyError 边界并补回归测试；下一步建议：继续 Task 8B.8 的 17-task 全量 Evidence Classification observe-only 审计

- [2026-08-28 10:06] codex 签到 — 开始处理：Task 8B.8: Drawing Evidence Acquisition Finalization

- [2026-08-28 10:20] codex 签退 — 完成了：Task 8B.8 Drawing Evidence Acquisition Finalization（17-task production evidence classification，observe-only；0 production/test/registry/prompt change）：
  - Pure production `build_agent_drawing_review(...)` 真实跑完 JOB `146dc530dd964a30a2d4f29410738e4d`，TASKS=17；asset gate：890/890 file image paths resolvable，32 directory placeholders ignored。
  - Status distribution：CONSISTENT=0 / CONFLICT=0 / TEXT_ONLY=3 / DRAWING_ONLY=0 / UNCERTAIN=2 / NOT_FOUND=12。
  - Evidence class distribution：ACTUAL_DRAWING_VALUE=0 / DRAWING_CONSTRAINT=1 / TEXT_TABLE_ONLY=3 / NO_CANDIDATE=3 / NO_USABLE_IMAGE=2 / VALUE_NOT_VISIBLE=2 / ATTRIBUTION_UNCLEAR=3 / COMPARISON_BLOCKED=1 / NO_RELEVANT_EVIDENCE=2（sum=17）。
  - Raw DrawingEvidence coverage=2/17（`horizontal_spacing`, `support_height`）；Actual Drawing Value coverage=1/17（`horizontal_spacing`）；Comparator eligible=0/17。
  - Critical corrections：`support_height` = DRAWING_CONSTRAINT（`H≤8m` 不当作 `H=8m`）；page21 head-jack = ATTRIBUTION_UNCLEAR；`horizontal_spacing` actual value blocked by scope_unknown；`main_beam_spacing`/`panel_stringer_spacing` = NO_USABLE_IMAGE；`monitoring_point_spacing` = VALUE_NOT_VISIBLE。
  - FINAL_FIX_REQUIRED=NO：没有满足小范围高收益低风险的 production bug；Prompt/Recall/Scope/Comparator/constraint semantics 均进 backlog，不在 8B.8 实施。
  - Artifacts（tmp ignored）：`tmp/drawing_evidence_finalization_8b8/{task_evidence_matrix.json,evidence_classification.json,coverage_summary.json,audit_summary.md}`。
  - Tests before/after：409 passed / 1 skipped / 0 failed（1 LibreSSL warning）。NEXT_TASK：Task 8B.9 — Final 17-Task Production Regression；8B.9 后结束 8B。

- [2026-08-28 10:19] codex 签到 — 开始处理：Task 8B.9: Final 17-Task Production Regression & 8B Sign-Off

- [2026-08-28 10:32] codex 签退 — 完成了：Task 8B.9 Final 17-Task Production Regression & 8B Sign-Off（observe-only；Task 8B CLOSED）：
  - Pure production `build_agent_drawing_review(...)` 跑完 JOB `146dc530dd964a30a2d4f29410738e4d`，REGISTRY_COUNT=17，TOTAL_TASKS=17；无 workaround/retry/手工换图。
  - Asset gate PASS：890/890 real file image paths resolvable；32 directory placeholders ignored；missing real images=0；budgets=5/2/1/1。
  - Tool stats：SEARCH_DRAWING actions=17，primary recall=17，fallback recall=3，fallback recalled tasks=3；OCR actions/adapter/engine/nonempty=17/17/7/5，OCR evidence tasks=0；INSPECT_IMAGE actions=19，vision tool/provider=8/8，VLM true/false/invalid=1/7/0；SEARCH_TEXT actions/hits/misses=1/1/0；no-usable actions/tasks=11/2，no fake VLM false。
  - Status distribution stable：CONSISTENT=0 / CONFLICT=0 / TEXT_ONLY=3 / DRAWING_ONLY=0 / UNCERTAIN=2 / NOT_FOUND=12（sum=17）。
  - Evidence classes stable：ACTUAL_DRAWING_VALUE=0 / DRAWING_CONSTRAINT=1 / TEXT_TABLE_ONLY=3 / NO_CANDIDATE=3 / NO_USABLE_IMAGE=2 / VALUE_NOT_VISIBLE=2 / ATTRIBUTION_UNCLEAR=3 / COMPARISON_BLOCKED=1 / NO_RELEVANT_EVIDENCE=2（sum=17）。
  - Coverage：raw DrawingEvidence=2/17 (`horizontal_spacing`, `support_height`)；actual drawing value=1/17 (`horizontal_spacing`)；comparator eligible=0/17；decision coverage=0/17 diagnostic only。
  - Critical sign-off：`support_height` keeps `H≤8m` as DRAWING_CONSTRAINT, not `H=8m`; page21 head-jack no proven grounding label; `horizontal_spacing` actual value safely blocked by scope_unknown; `main_beam_spacing` no usable image; `monitoring_point_spacing` value not visible。
  - READY_FOR_ORCHESTRATOR_INTEGRATION=YES：contract stable, deterministic comparator retained, unsafe/constraint/attribution/no-image cases safely degrade with status/reason/class for orchestrator consumption。
  - Artifacts（tmp ignored）：`tmp/drawing_agent_final_regression_8b9/{final_agent_result.json,final_task_matrix.json,final_tool_stats.json,final_signoff.json}`；tests before/after：409 passed / 1 skipped / 0 failed。
  - NO_NEW_8B_FEATURE_TASKS=YES；NEXT：Task 8C — Orchestrator Integration。

- [2026-08-28 10:26] codex 签到 — 开始处理：Task 8C: Drawing Consistency Agent to Orchestrator Integration

- [2026-08-28 10:42] codex 签退 — 完成了：Task 8C Drawing Consistency Agent → Orchestrator Integration（消费层集成；未改 Drawing Agent/vision/compare/scope/registry/alias/recall/web UI）：
  - Orchestrator 新增可选 `agent_drawing_review` 域对象，稳定消费 Task 8B `build_agent_drawing_review(...)` 结果；legacy `drawing_review.json` PASS/ISSUE/REVIEW 摘要保持兼容。
  - 六态原样保留：CONSISTENT / CONFLICT / TEXT_ONLY / DRAWING_ONLY / UNCERTAIN / NOT_FOUND；summary count deterministic，empty result 安全返回 0 计数。
  - Domain policy 固定为 `domain_status_authoritative_no_orchestrator_rejudge`；总控不重新判定图文一致性，也不把图文一致性当规则合规结论。
  - Constraint safety：`support_height` 的 `H≤8m` 仍不 scalarize 成 `H=8m`；Orchestrator 只传递已有 `drawing_value`。
  - Web pipeline 仅在 `agent_drawing_review.json` 已存在时读取并传入；不会触发 Drawing Agent/OCR/Vision 重跑。
  - Focused tests：`tests/test_drawing_integration.py tests/test_orchestrator_agent.py tests/test_web.py` = 53 passed。
  - 8B.9 artifact smoke：JOB `146dc530dd964a30a2d4f29410738e4d` received=17，status_counts=0/0/3/0/2/12，extra Vision/OCR=0。
  - Full suite：413 passed / 1 skipped / 0 failed（1 LibreSSL warning）。
  - NEXT_TASK：Task 8D — Drawing Review Frontend / Report Integration。

- [2026-08-28 10:36] codex 签到 — 开始处理：Task 8D: Drawing Review Frontend / Report Integration

- [2026-08-28 10:50] codex 签退 — 完成了：Task 8D Drawing Review Frontend / Report Integration（presentation-only；未改 Drawing Agent/vision/compare/scope/registry/recall/OCR）：
  - Frontend：图文一致性 tab 优先消费 `orchestrator_agent.json.agent_drawing_review`，支持六态 CONSISTENT/CONFLICT/TEXT_ONLY/DRAWING_ONLY/UNCERTAIN/NOT_FOUND。
  - 展示语义：machine status/reason 保留，中文 label/reason 独立映射；UNCERTAIN 不显示为冲突，NOT_FOUND 不显示为不合格。
  - Summary：直接消费 backend deterministic `total_tasks/status_counts`；旧 job 缺失或空 agent domain 时安全回落 legacy `drawing_review`。
  - Detail：展示文本/图纸侧实际值、单位、scope alignment、reason、可用 evidence 与页码；null value 显示为“未提取到可比较的实际值”。
  - Report：Markdown 报告接入 agent drawing summary 与非一致项列表；不重新判定、不 scalarize constraint。
  - Constraint safety：`support_height` 的 `drawing_value=null` 不渲染为 8m；若 backend 提供 `H≤8m` evidence，可作为图纸证据原文展示。
  - Real 146dc smoke：received=17，status_counts=0/0/3/0/2/12；`horizontal_spacing`=暂无法确定/scope_unknown；no-candidate 显示证据不足语义。
  - Tool cost：additional Drawing Agent/Vision/OCR = 0/0/0。
  - Focused tests：56 passed；Full suite：416 passed / 1 skipped / 0 failed（1 LibreSSL warning）。
  - NEXT_TASK：Task 8E — End-to-End Product Regression & Release Sign-Off。
