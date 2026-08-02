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

当前已完成D/E：

- on_demand实际只请求selected_rule_ids
- full模式保持全量
- selected_count=0时跳过Dify
- 单规则证据上限8000字符
- 最多3个完整证据片段
- Dify部分规则返回校验已适配
- 提交：998edde

下一阶段完成标准

至少满足：

同一PDF第二次上传不调用MinerU；
改文件名但内容相同仍命中；
同名但内容不同不命中；
缓存损坏自动失效；
parser版本变化自动失效；
每个新job仍有自己的 mineru_document.json；
本地完整性审查仍重新执行；
测试全部通过；
单独Git提交。
本阶段禁止事项：

- 不修改MinerU底层解析；
- 不改变10条完整性规则业务含义；
- 不开发规范语义审查Agent；
- 不引入React、Vue、Redis、Celery、数据库等新技术栈；
- 不输出最终“合格/不合格”结论；
- 不大规模重构项目目录。
