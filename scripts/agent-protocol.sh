#!/usr/bin/env bash
#
# agent-protocol.sh — AI Agent 签到/签退辅助脚本
#
# 用法：
#   ./scripts/agent-protocol.sh checkin  <agent名> <任务描述>
#   ./scripts/agent-protocol.sh checkout <agent名> <完成描述> [下一步建议]
#
set -euo pipefail

PROGRESS_FILE="$(dirname "$0")/../PROGRESS.md"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M')

ACTION="${1:-}"
AGENT="${2:-}"
DESC="${3:-}"

if [ -z "$ACTION" ] || [ -z "$AGENT" ] || [ -z "$DESC" ]; then
  echo "用法："
  echo "  $0 checkin  <agent名> <任务描述>"
  echo "  $0 checkout <agent名> <完成描述> [下一步建议]"
  exit 1
fi

if [ ! -f "$PROGRESS_FILE" ]; then
  echo "❌ 找不到 PROGRESS.md，请确认你在项目根目录下运行此脚本"
  exit 1
fi

case "$ACTION" in
  checkin)
    LINE="- [$TIMESTAMP] $AGENT 签到 — 开始处理：$DESC"
    echo "" >> "$PROGRESS_FILE"
    echo "$LINE" >> "$PROGRESS_FILE"
    echo "✅ 签到成功：$LINE"
    echo "📝 请记得工作结束后运行："
    echo "   $0 checkout $AGENT \"<完成描述>\" \"<下一步建议>\""
    ;;

  checkout)
    NEXT="${4:-（无）}"
    LINE="- [$TIMESTAMP] $AGENT 签退 — 完成了：$DESC；下一步建议：$NEXT"
    echo "" >> "$PROGRESS_FILE"
    echo "$LINE" >> "$PROGRESS_FILE"
    echo "✅ 签退成功：$LINE"
    echo "📝 请记得："
    echo "   1. 更新 PROGRESS.md 的任务状态（✅/🔲）"
    echo "   2. git add + commit + push"
    ;;

  *)
    echo "❌ 未知操作：$ACTION"
    echo "   只支持 checkin 或 checkout"
    exit 1
    ;;
esac
