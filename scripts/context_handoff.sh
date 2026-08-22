#!/usr/bin/env bash
#
# context_handoff.sh — 上下文交接包生成器
#
# 当一轮对话的上下文接近上限时，运行本脚本自动生成 .context/handoff.md，
# 其中包含：当前分支、最近提交、未提交改动、PROGRESS.md 当前阻塞与待完成事项，
# 以及一段可直接粘进新对话的"启动提示词"。新对话读该文件即可无缝续接。
#
# 用法（macOS）：
#   ./scripts/context_handoff.sh            # 自动生成交接包
#   make handoff                           # 等价快捷方式
#
# 可选：在运行前把本轮对话特有的临时发现写入 .context/handoff_note.md，
# 脚本会把它合并进 handoff.md 的"本轮要点"小节（合并后自动清空 note 文件）。
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CTX_DIR="$ROOT/.context"
HANDOFF="$CTX_DIR/handoff.md"
NOTE="$CTX_DIR/handoff_note.md"
PROGRESS="$ROOT/PROGRESS.md"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M')

mkdir -p "$CTX_DIR"

# --- git 状态 ---
BRANCH=$(cd "$ROOT" && git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
LAST_COMMIT=$(cd "$ROOT" && git log -1 --format='%h %s' 2>/dev/null || echo "unknown")
RECENT_LOG=$(cd "$ROOT" && git log -8 --format='- %h %s (%cr)' 2>/dev/null || echo "（无 git 历史）")
STATUS=$(cd "$ROOT" && git status --short 2>/dev/null || echo "（无法读取 git 状态）")

# --- PROGRESS.md 关键小节提取 ---
extract_section() {
  local file="$1" header="$2"
  if [ ! -f "$file" ]; then echo "（未找到 $file）"; return; fi
  # 打印从 header 行到下一个同级或更高级 ## 标题之间的内容
  awk -v hdr="$header" '
    $0 ~ "^##+ .*" hdr { flag=1; print; next }
    flag && /^##[^#]/ && $0 !~ hdr { exit }
    flag { print }
  ' "$file" | head -40
}

BLOCKERS=$(extract_section "$PROGRESS" "当前阻塞")
# 待完成只保留未完成项（- [ ]），让交接包紧凑
RAW_TODO=$(extract_section "$PROGRESS" "待完成")
TODO=$(printf '%s\n' "$RAW_TODO" | awk 'NR==1{print; next} /^- \[ \]/{print}')

# --- 本轮要点（可选 note 文件）---
NOTES=""
if [ -f "$NOTE" ] && [ -s "$NOTE" ]; then
  NOTES=$(cat "$NOTE")
fi

# --- 组装 handoff.md ---
{
  echo "# 上下文交接包（handoff）"
  echo ""
  echo "> 生成时间：$TIMESTAMP ｜ 分支：\`$BRANCH\` ｜ 最近提交：\`$LAST_COMMIT\`"
  echo "> 本文件由 \`scripts/context_handoff.sh\` 自动生成，供下一轮对话读取以续接工作。"
  echo ""
  echo "## 最近提交"
  echo ""
  echo "$RECENT_LOG"
  echo ""
  echo "## 未提交改动"
  echo '```'
  echo "$STATUS"
  echo '```'
  echo ""
  echo "## 当前阻塞"
  echo ""
  echo "$BLOCKERS"
  echo ""
  echo "## 待完成"
  echo ""
  echo "$TODO"
  if [ -n "$NOTES" ]; then
    echo ""
    echo "## 本轮要点（上一对话补充）"
    echo ""
    echo "$NOTES"
  fi
  echo ""
  echo "---"
  echo "## 新对话启动提示词（复制下方内容粘贴到新对话即可续接）"
  echo ""
  echo '```'
  echo "我是接续上一轮对话继续工作。请按入口协议操作："
  echo "1. 读 AGENTS.md（协作约定）"
  echo "2. 读 .context/handoff.md（上一对话生成的交接包，即本文件）"
  echo "3. 读 PROGRESS.md 与 CODEX_CONTEXT.md"
  echo "4. 签到：make checkin AGENT=<你的名字> TASK=\"续接：<从待完成中选一项>\""
  echo "然后从上方\"待完成\"列表继续。"
  echo '```'
} > "$HANDOFF"

# 合并完 note 后清空
if [ -f "$NOTE" ]; then
  : > "$NOTE"
fi

echo "✅ 交接包已生成：$HANDOFF"
echo "📝 开新对话后，让新对话读取 .context/handoff.md 即可续接。"
echo "   或直接把文件末尾的\"启动提示词\"复制粘贴到新对话。"
