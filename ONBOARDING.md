# ONBOARDING.md — 新 Agent 上手指南

> **你是新来的 AI Agent。这份文件教你如何在 5 分钟内开始干活。**
> 不管你用的是 dewucode、codex、claude、cursor 还是别的工具，照着做就行。

---

## 📋 先读什么（必做，2 分钟）

按顺序读这四个文件，你就知道项目到哪了、该干啥：

| 顺序 | 文件 | 看什么 |
|------|------|--------|
| 1 | `AGENTS.md` | 协作规则：签到签退协议、禁止事项 |
| 2 | `PROGRESS.md` | 当前进度：✅已完成的 / 🔲待完成的 / 🔄交接日志 |
| 3 | `CODEX_CONTEXT.md` | 技术架构：模块清单、历史阶段 |
| 4 | `high-formwork-review/README.md` | 详细文档：代码结构、运行方式 |

**跳过这一步 = 大概率重复造轮子或破坏已有功能。**

---

## 场景一：在本机（macOS）用其他 agent

本机已经有完整环境：git 仓库、Python 3.11、git hooks 已配置。你只需要：

### 步骤 1 — 拉最新代码

```bash
cd /Users/admin/.dewuclaw/workspaces/default/coding_projects/high-formwork-review
git pull origin main
```

### 步骤 2 — 安装 git hooks（首次必做）

```bash
make hooks
```

这会把 `core.hooksPath` 指向 `.githooks`，之后你每次 `git commit` 都会检查：
- 改了 `.py` 代码但没更新 `PROGRESS.md` → **拒绝提交**
- commit message 不符合 `feat:/fix:` 规范 → **拒绝提交**

### 步骤 3 — 签到

```bash
make checkin AGENT=<你的工具名> TASK="你要做的任务"
```

例如：
```bash
make checkin AGENT=dewucode TASK="修复规范审查模式bug"
```

### 步骤 4 — 装依赖（首次必做）

```bash
cd high-formwork-review
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 步骤 5 — 跑测试确认环境正常

```bash
# 在 high-formwork-review 目录下
source .venv/bin/activate
python -m pytest -v
```

### 步骤 6 — 读 PROGRESS.md 的待完成列表，挑一个任务

### 步骤 7 — 干活，小步提交

```bash
# 改代码...
git add <文件>
git commit -m "fix: 修复了xxx问题"
```

> ⚠️ pre-commit hook 会拦截：如果你改了 .py 文件但没更新 PROGRESS.md，提交会被拒绝。
> 更新方法：编辑 PROGRESS.md，把完成任务从 🔲 改为 ✅，底部 Handoff Log 追加签退记录。

### 步骤 8 — 签退 + 推送

```bash
make checkout AGENT=<你的工具名> DONE="完成了xxx" NEXT="下一步建议xxx"
git push origin main
```

---

## 场景二：在另一台 Windows 电脑用其他 agent

Windows 没有 `make` 和 `bash`，用 PowerShell 替代。

### 步骤 1 — 安装前置软件

```powershell
# 安装 Git for Windows（含 Git Bash）
winget install Git.Git

# 安装 Python 3.11+
winget install Python.Python.3.11
```

装完后重启终端，确认：
```powershell
git --version    # 应显示 git version 2.x
python --version # 应显示 Python 3.11.x
```

### 步骤 2 — Clone 仓库

```powershell
# 选一个工作目录，比如 C:\Projects
cd C:\
mkdir Projects
cd Projects

git clone https://github.com/TT77517/high-formwork-review.git
cd high-formwork-review
```

> 如果仓库是私有的，会提示输入 GitHub 用户名和密码（用 Personal Access Token 代替密码）。

### 步骤 3 — 安装 git hooks

```powershell
# PowerShell 中设置 hooks 路径
git config core.hooksPath .githooks
```

> ⚠️ `.githooks/pre-commit` 和 `.githooks/commit-msg` 是 bash 脚本。
> Git for Windows 自带 bash 运行环境，hook 能正常工作。
> 如果你用的是纯 Windows 原生 git（不推荐），hook 可能无法执行，改用 `--no-verify` 提交然后手动检查。

### 步骤 4 — 签到

```powershell
# 用 PowerShell 脚本（见 scripts/agent-protocol.ps1）
powershell -ExecutionPolicy Bypass -File scripts\agent-protocol.ps1 checkin <你的工具名> "你要做的任务"

# 或者手动编辑 PROGRESS.md，在底部 Handoff Log 追加一行：
# - [2026-08-20 18:00] dewucode 签到 — 开始处理：修复xxx
```

### 步骤 5 — 装依赖

```powershell
cd high-formwork-review
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 步骤 6 — 配置环境变量

```powershell
# 复制示例文件
copy .env.example .env

# 编辑 .env，填入实际的 API Token：
# MINERU_API_TOKEN=你的token
# DIFY_API_KEY=你的key（如果需要 Dify）
notepad .env
```

### 步骤 7 — 跑测试确认环境正常

```powershell
# 在 high-formwork-review 目录下
.venv\Scripts\activate
python -m pytest -v
```

### 步骤 8 — 读文件，挑任务，干活

```
1. 读 AGENTS.md → 协作规则
2. 读 PROGRESS.md → 待完成任务列表
3. 读 CODEX_CONTEXT.md → 技术架构
4. 改代码，小步 commit
```

### 步骤 9 — 签退 + 推送

```powershell
# 更新 PROGRESS.md 任务状态（手动编辑）
# 签退
powershell -ExecutionPolicy Bypass -File scripts\agent-protocol.ps1 checkout <你的工具名> "完成了xxx" "下一步建议"

git add .
git commit -m "fix: 修复了xxx问题"
git push origin main
```

---

## ⚡ 快速参考卡

### 必读文件

| 文件 | 内容 |
|------|------|
| `AGENTS.md` | 协作规则、禁止事项、enforcement 机制 |
| `PROGRESS.md` | 进度看板 + 交接日志（**最频繁更新**） |
| `CODEX_CONTEXT.md` | 技术架构、模块清单、历史阶段 |
| `ONBOARDING.md`（本文件） | 新人上手指南 |
| `high-formwork-review/README.md` | 详细技术文档 |

### 常用命令对照

| 操作 | macOS | Windows |
|------|-------|---------|
| 签到 | `make checkin AGENT=xxx TASK="..."` | `powershell -File scripts\agent-protocol.ps1 checkin xxx "..."` |
| 签退 | `make checkout AGENT=xxx DONE="..." NEXT="..."` | `powershell -File scripts\agent-protocol.ps1 checkout xxx "..." "..."` |
| 测试 | `make test` | `cd high-formwork-review && python -m pytest -v` |
| 安装hooks | `make hooks` | `git config core.hooksPath .githooks` |
| 激活venv | `source .venv/bin/activate` | `.venv\Scripts\activate` |

### Commit message 规范

```
feat: 新功能
fix: 修复bug
docs: 文档更新
chore: 杂项
refactor: 重构
test: 测试相关
```

### 违反协议的后果

| 违规行为 | 后果 |
|----------|------|
| 改了 .py 没更新 PROGRESS.md | pre-commit 拒绝提交 |
| commit message 不规范 | commit-msg 拒绝提交 |
| 没签到就开工 | 下一个 agent 不知道你做了什么 |
| 没签退就结束 | 下一个 agent 不知道进度到哪了 |

---

## ❓ 常见问题

### Q: pre-commit hook 拦截了，但我只是改了格式/注释怎么办？
A: 用 `git commit --no-verify -m "style: 格式化"` 跳过。但正式功能/修复提交不能用这个。

### Q: 我用的 AI 工具不认 AGENTS.md / CLAUDE.md / .cursorrules 怎么办？
A: 在 `AGENTS.md` 底部的约定文件覆盖表里加一行。或者你发给它的第一条消息里直接写"先读 AGENTS.md 和 PROGRESS.md"。

### Q: PROGRESS.md 怎么更新？
A: 手动用编辑器改。把你完成的任务从 `- [ ]` 改为 `- [x]`，新发现的任务加到待完成列表，底部 Handoff Log 追加签退记录。不需要精确到完美，重点是让下一个 agent 知道你做了什么。

### Q: Windows 上 hook 不工作？
A: 确认装的是 Git for Windows（不是其他 git 实现）。Git for Windows 自带 bash，hook 能正常跑。如果实在不行，手动遵守规则，用 `--no-verify` 提交后检查 PROGRESS.md 是否更新了。
