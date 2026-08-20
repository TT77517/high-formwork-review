# CLAUDE.md

本文件供 Claude / Claude Code 使用。

## ⚠️ 开始工作前（强制）

**不读以下文件就开始写代码 = 浪费额度 + 可能重复造轮子。**

1. `AGENTS.md` — 协作约定与入口协议（**必读**）
2. `PROGRESS.md` — 当前进度看板与交接日志（**必读，看上一个 agent 做到哪了**）
3. `CODEX_CONTEXT.md` — 技术架构与阶段划分（必读）
4. `high-formwork-review/README.md` — 详细技术文档

## 📌 核心协议

- **签到** — `make checkin AGENT=claude TASK="任务描述"`
- **干活** — 小步 commit，commit message 用 `feat:/fix:/docs:` 前缀
- **签退** — `make checkout AGENT=claude DONE="完成描述" NEXT="下一步建议"`
- **提交前** — `make test` 跑测试

## 🔒 Enforcement

- **pre-commit hook**：改了 .py 但没更新 PROGRESS.md → 提交被拒
- **commit-msg hook**：commit message 不规范 → 提交被拒
- 安装 hooks：`make hooks`（新 clone 后需执行一次）

详见 `AGENTS.md`。
