# context_handoff.ps1 — 上下文交接包生成器（Windows）
#
# 当一轮对话的上下文接近上限时，运行本脚本自动生成 .context\handoff.md，
# 新对话读该文件即可无缝续接上一轮工作。
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File scripts\context_handoff.ps1
#
# 可选：运行前把本轮临时发现写入 .context\handoff_note.md，脚本会合并进 handoff.md。
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$CtxDir = Join-Path $Root ".context"
$Handoff = Join-Path $CtxDir "handoff.md"
$Note = Join-Path $CtxDir "handoff_note.md"
$Progress = Join-Path $Root "PROGRESS.md"
$Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm"

if (-not (Test-Path $CtxDir)) { New-Item -ItemType Directory -Path $CtxDir | Out-Null }

# git 状态
$Branch = (git -C $Root rev-parse --abbrev-ref HEAD 2>$null); if (-not $Branch) { $Branch = "unknown" }
$LastCommit = (git -C $Root log -1 --format='%h %s' 2>$null); if (-not $LastCommit) { $LastCommit = "unknown" }
$RecentLog = (git -C $Root log -8 --format='- %h %s (%cr)' 2>$null); if (-not $RecentLog) { $RecentLog = "（无 git 历史）" }
$Status = (git -C $Root status --short 2>$null); if (-not $Status) { $Status = "（无法读取 git 状态）" }

function Extract-Section($file, $header) {
    if (-not (Test-Path $file)) { return "（未找到 $file）" }
    $lines = Get-Content $file
    $capture = $false
    $result = @()
    foreach ($l in $lines) {
        if ($l -match "^#+\s.*$header") { $capture = $true; $result += $l; continue }
        if ($capture -and $l -match "^##[^#]" -and $l -notmatch $header) { break }
        if ($capture) { $result += $l }
    }
    if ($result.Count -eq 0) { return "（未找到小节：$header）" }
    return ($result -join "`n")
}
$Blockers = Extract-Section $Progress "当前阻塞"
$Todo = Extract-Section $Progress "待完成"
$Notes = ""
if ((Test-Path $Note) -and (Get-Item $Note).Length -gt 0) { $Notes = Get-Content $Note -Raw }

$body = @"
# 上下文交接包（handoff）

> 生成时间：$Timestamp ｜ 分支：``$Branch`` ｜ 最近提交：``$LastCommit``
> 本文件由 scripts\context_handoff.ps1 自动生成，供下一轮对话读取以续接工作。

## 最近提交

$RecentLog

## 未提交改动

`````
$Status
`````

## 当前阻塞

$Blockers

## 待完成

$Todo
"@
if ($Notes) { $body += "`n`n## 本轮要点（上一对话补充）`n`n$Notes" }
$body += @"

---
## 新对话启动提示词（复制下方内容粘贴到新对话即可续接）

`````
我是接续上一轮对话继续工作。请按入口协议操作：
1. 读 AGENTS.md（协作约定）
2. 读 .context\handoff.md（上一对话生成的交接包，即本文件）
3. 读 PROGRESS.md 与 CODEX_CONTEXT.md
4. 签到：powershell -File scripts\agent-protocol.ps1 checkin <你的名字> "续接：<从待完成中选一项>"
然后从上方"待完成"列表继续。
`````
"@
Set-Content -Path $Handoff -Value $body -Encoding UTF8
if (Test-Path $Note) { Set-Content -Path $Note -Value "" -Encoding UTF8 }
Write-Host "✅ 交接包已生成：$Handoff" -ForegroundColor Green
Write-Host "📝 开新对话后，让新对话读取 .context\handoff.md 即可续接。" -ForegroundColor Green
