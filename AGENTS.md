# AGENTS.md — 本项目的 AI Agent 协作入口

> **所有 AI Agent（dewuclaw / dewucode / codex / claude / 其他）在开始工作前必须读此文件。**
>
> **新来的 agent 先读 `ONBOARDING.md`**，里面有完整的环境搭建步骤（本机 macOS 和 Windows 两种场景）。

## 📋 项目一句话

高支模专项施工方案智能审查系统——上传 PDF → 解析 → 规则审查 → 输出报告。

## 🚪 入口协议（每次会话必做）

> **这不是建议，是硬性要求。pre-commit hook 会拦截不遵守的提交。**

1. **续接检查** — 若 `.context/handoff.md` 存在（上一对话生成的交接包），先读它，按其中"待完成"续接工作；不存在则跳过
2. **读本文件** — 了解项目约定
3. **读 `PROGRESS.md`** — 了解当前进度和下一任务（**最重要的文件**）
4. **读 `CODEX_CONTEXT.md`** — 了解技术架构和阶段划分
5. **读 `high-formwork-review/README.md`** — 了解详细技术文档
6. **签到** — 运行 `make checkin AGENT=<你的名字> TASK="<任务>"` 或手动在 `PROGRESS.md` 底部 Handoff Log 追加：
   ```
   - [YYYY-MM-DD HH:MM] <agent名称> 签到 — 开始处理：<任务描述>
   ```
   > **Windows**：`powershell -File scripts\agent-protocol.ps1 checkin <名字> "<任务>"`

## 🚪 离场协议（结束工作前必做）

> **pre-commit hook 会检查：改了 .py 代码但没更新 PROGRESS.md → 拒绝提交。**

1. **更新 `PROGRESS.md`** — 把你完成的任务状态改掉，追加新发现的任务
2. **签退** — 运行 `make checkout AGENT=<你的名字> DONE="<完成描述>" NEXT="<下一步建议>"` 或手动追加：
   ```
   - [YYYY-MM-DD HH:MM] <agent名称> 签退 — 完成了：<任务描述>；下一步建议：<...>
   ```
   > **Windows**：`powershell -File scripts\agent-protocol.ps1 checkout <名字> "<完成>" "下一步"`
3. **跑测试** — `make test`（Windows: `cd high-formwork-review && python -m pytest -v`）
4. **提交** — git add + commit + push，commit message 以 `feat:` / `fix:` / `docs:` 等前缀开头
   （commit-msg hook 会拦截不规范 message）
5. 如果有未解决问题，在 PROGRESS.md 的"当前阻塞"区写清楚

## 📁 关键文件指引

| 文件 | 用途 |
|------|------|
| `ONBOARDING.md` | **新 agent 上手指南**（环境搭建+首次操作，本机/Windows 双场景） |
| `AGENTS.md`（本文件） | 协作约定，所有 agent 必读 |
| `PROGRESS.md` | 当前进度看板 + 交接日志（**最频繁更新**） |
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

## 🔄 上下文连续性协议（避免上下文过载）

> 对话窗口上下文接近上限时，模型能力下降、token 费费增多。本协议让新对话无缝续接上一对话。

### 触发时机

- **Agent 自监测（首选）**：agent 在工作过程中调用 `get_goal` 查看剩余 token 预算，低于阈值（建议剩余预算 < 20%）时，主动触发生成交接包并提示用户开新对话。
- **手动触发**：你随时可运行 `make handoff`（Windows: `powershell -File scripts\context_handoff.ps1`）生成交接包。

### 交接包内容（`.context/handoff.md`，自动生成）

`scripts/context_handoff.sh` / `scripts/context_handoff.ps1` 会自动提取：
- 当前分支 + 最近 8 条提交
- 未提交改动（`git status`）
- `PROGRESS.md` 的"当前阻塞"小节
- `PROGRESS.md` 的"待完成"小节（仅未完成项 `- [ ]`）
- 可选的"本轮要点"（运行前写入 `.context/handoff_note.md`，合并后自动清空）
- 一段可直接粘贴到新对话的"启动提示词"

### 使用流程

1. 上下文接近上限 → 运行 `make handoff`（或 agent 自动触发）
2. 开新对话，粘贴 `.context/handoff.md` 末尾的启动提示词（或让新对话直接读该文件）
3. 新对话按入口协议第 1 步读 `.context/handoff.md`，从"待完成"续接
4. `.context/` 已在 `.gitignore`，是本地再生工件，不入 git

> **注**："自动开启新对话窗口"由宿主工具（DewuCode / Codex CLI）完成，项目侧只能生成交接包 + 协议；开窗口这一步需用户/宿主触发。

## 🔒 自动化 Enforcement 机制

以下机制确保协议不只是"建议"，而是被强制执行：

### 1. Git Hooks（硬拦截）

| Hook | 位置 | 作用 |
|------|------|------|
| `pre-commit` | `.githooks/pre-commit` | 改了 `.py` 代码但 PROGRESS.md 没更新 → **拒绝提交** |
| `commit-msg` | `.githooks/commit-msg` | commit message 不符合 `<type>: <desc>` → **拒绝提交** |

**安装方式**（新 clone 后需执行一次）：
```bash
make hooks
# 或手动
git config core.hooksPath .githooks
```

**跳过检查**（仅限格式化等无关紧要的改动）：
```bash
git commit --no-verify -m "style: ..."
```

### 2. 辅助脚本（降低遗忘率）

| 操作 | macOS | Windows |
|------|-------|---------|
| 签到 | `make checkin AGENT=xxx TASK="..."` | `powershell -File scripts\agent-protocol.ps1 checkin xxx "..."` |
| 签退 | `make checkout AGENT=xxx DONE="..." NEXT="..."` | `powershell -File scripts\agent-protocol.ps1 checkout xxx "..." "..."` |
| 测试 | `make test` | `cd high-formwork-review && python -m pytest -v` |
| 安装hooks | `make hooks` | `git config core.hooksPath .githooks` |

### 3. 约定文件覆盖

不同 AI 工具认不同的入口文件，本项目同时部署了：

| 文件 | 工具 | 自动读取 |
|------|------|---------|
| `AGENTS.md` | dewuclaw | ✅ 系统注入 |
| `CLAUDE.md` | Claude Code | ✅ 自动读 |
| `.cursorrules` | Cursor | ✅ 自动读 |
| `CODEX_CONTEXT.md` | Codex / dewucode | 需在工具配置中指定 |

**如果你用的工具不在以上列表** — 在 AGENTS.md 入口协议顶部加一行指向本文件即可。
