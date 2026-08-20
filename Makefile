# Makefile — AI Agent 协作辅助命令
#
# 所有 agent 都可以用 make 来执行协议步骤，降低"忘记"概率。
# 不依赖 make 也可以手动执行 scripts/agent-protocol.sh。

.PHONY: checkin checkout test lint hooks

# 签到：make checkin AGENT=dewucode TASK="修复xxx"
checkin:
	@./scripts/agent-protocol.sh checkin "$(AGENT)" "$(TASK)"

# 签退：make checkout AGENT=dewucode DONE="修复了xxx" NEXT="下一步建议"
checkout:
	@./scripts/agent-protocol.sh checkout "$(AGENT)" "$(DONE)" "$(NEXT)"

# 跑测试
test:
	cd high-formwork-review && python -m pytest -v

# 安装 git hooks（如果 .githooks 没生效）
hooks:
	git config core.hooksPath .githooks
	@echo "✅ git hooks 已设置到 .githooks"
