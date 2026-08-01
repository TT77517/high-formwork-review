# 项目上下文

项目名称：
高支模专项施工方案智能审查系统

当前主流程：
PDF上传
→ MinerU解析
→ 本地完整性审查
→ Dify完整性语义复核
→ 人工确认

当前完整性审查关系：

- 本地完整性审查：检查章节、基本要素和结构证据；
- Dify完整性语义复核：处理同义表达、跨章节证据和本地疑难项；
- 规范语义审查：后续独立阶段，本次尚未开发。

当前已完成阶段：

A. DIFY_COMPLETENESS_MODE
B. CompletenessResult置信度和语义复核字段
C. completeness_review_selector及dify_selection.json

当前默认模式：

DIFY_COMPLETENESS_MODE=on_demand

下一阶段：

D. 复用现有dify_scheme证据提取，缩小单规则证据包
E. 让on_demand真正只调用selected_rule_ids
F. 后续再考虑缓存、日志和comparison扩展

本阶段禁止事项：

- 不修改MinerU底层解析；
- 不改变10条完整性规则业务含义；
- 不开发规范语义审查Agent；
- 不引入React、Vue、Redis、Celery、数据库等新技术栈；
- 不输出最终“合格/不合格”结论；
- 不大规模重构项目目录。
