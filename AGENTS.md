# AGENTS.md — 本项目的 AI Agent 协作入口

> **所有 AI Agent（dewuclaw / dewucode / codex / claude / 其他）在开始工作前必须读此文件。**

## 📋 项目一句话

高支模专项施工方案智能审查系统——上传 PDF → 解析 → 规则审查 → 输出报告。

## 🚪 入口协议（每次会话必做）

1. **读本文件** — 了解项目约定
2. **读 `PROGRESS.md`** — 了解当前进度和下一任务
3. **读 `CODEX_CONTEXT.md`** — 了解技术架构和阶段划分
4. **读 `high-formwork-review/README.md`** — 了解详细技术文档
5. **签到** — 在 `PROGRESS.md` 底部 Handoff Log 追加一行：
   ```
   - [YYYY-MM-DD HH:MM] <agent名称> 签到 — 开始处理：<任务描述>
   ```

## 🚪 离场协议（结束工作前必做）

1. **更新 `PROGRESS.md`** — 把你完成的任务状态改掉，追加新发现的任务
2. **签退** — 在 `PROGRESS.md` 底部 Handoff Log 追加：
   ```
   - [YYYY-MM-DD HH:MM] <agent名称> 签退 — 完成了：<任务描述>；下一步建议：<...>
   ```
3. **提交** — git add + commit + push，commit message 以 `feat:` / `fix:` / `docs:` 等前缀开头
4. 如果有未解决问题，在 PROGRESS.md 的"当前阻塞"区写清楚

## 📁 关键文件指引

| 文件 | 用途 |
|------|------|
| `AGENTS.md`（本文件） | 协作约定，所有 agent 必读 |
| `PROGRESS.md` | 当前进度看板 + 交接日志 |
| `CODEX_CONTEXT.md` | 技术架构 + 阶段划分 + 禁止事项 |
| `high-formwork-review/README.md` | 详细技术文档 |
| `high-formwork-review/app/` | 后端核心代码 |
| `high-formwork-review/rule/` | 规则库与规范文件 |
| `high-formwork-review/tests/` | 测试代码 |
| `high-formwork-review/config/` | 配置文件 |

## 🔧 技术栈

- Python + Flask 后端（无前端框架，Jinja2 模板 + 原生 JS）
- MinerU 做 PDF 解析
- Dify 做语义复核（可选）
- 无数据库，文件缓存

## 📐 开发规则

1. **不引入新技术栈** — 不加 React/Vue/Redis/Celery/数据库（除非用户明确要求）
2. **不改 MinerU 底层解析逻辑**
3. **不改变 10 条完整性规则的业务含义**
4. **不输出最终"合格/不合格"结论** — 只做审查提示
5. **Git 提交规范** — `feat:` / `fix:` / `docs:` / `chore:` 前缀
6. **先读后写** — 修改前先读文件原内容
7. **小步提交** — 一个功能一个 commit，别攒大包
8. **跑测试** — 提交前 `cd high-formwork-review && python -m pytest`

## 🤝 多 Agent 协作约定

- **同一时间只有一个 agent 在写代码** — 避免冲突
- 如果你是被叫来接手的，先读 Handoff Log 看上一个 agent 做到哪了
- 签到时注明你用的是哪个工具（dewuclaw / dewucode / codex / claude）
- 如果发现架构问题或需要重构，先在 PROGRESS.md 记录讨论，不要直接大改
- **所有 agent 的产出都走 git** — 不依赖任何 agent 的私有记忆
