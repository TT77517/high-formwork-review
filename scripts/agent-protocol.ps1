# agent-protocol.ps1 — Windows PowerShell 签到/签退脚本
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File scripts\agent-protocol.ps1 checkin  <agent名> <任务描述>
#   powershell -ExecutionPolicy Bypass -File scripts\agent-protocol.ps1 checkout <agent名> <完成描述> [下一步建议]
#
param(
    [Parameter(Mandatory=$true, Position=0)]
    [ValidateSet("checkin", "checkout")]
    [string]$Action,

    [Parameter(Mandatory=$true, Position=1)]
    [string]$Agent,

    [Parameter(Mandatory=$true, Position=2)]
    [string]$Desc,

    [Parameter(Position=3)]
    [string]$Next = "（无）"
)

$ErrorActionPreference = "Stop"
$ProgressFile = Join-Path $PSScriptRoot "..\PROGRESS.md"
$ProgressFile = Resolve-Path $ProgressFile -ErrorAction SilentlyContinue

if (-not $ProgressFile) {
    # 尝试从当前目录找
    $ProgressFile = "PROGRESS.md"
    if (-not (Test-Path $ProgressFile)) {
        Write-Host "❌ 找不到 PROGRESS.md，请确认你在项目根目录下运行此脚本" -ForegroundColor Red
        exit 1
    }
} else {
    $ProgressFile = $ProgressFile.Path
}

$Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm"

switch ($Action) {
    "checkin" {
        $Line = "- [$Timestamp] $Agent 签到 — 开始处理：$Desc"
        Add-Content -Path $ProgressFile -Value "`n$Line"
        Write-Host "✅ 签到成功：$Line" -ForegroundColor Green
        Write-Host "📝 工作结束后记得签退："
        Write-Host "   powershell -File scripts\agent-protocol.ps1 checkout $Agent `"<完成描述>`" `"下一步`""
    }
    "checkout" {
        $Line = "- [$Timestamp] $Agent 签退 — 完成了：$Desc；下一步建议：$Next"
        Add-Content -Path $ProgressFile -Value "`n$Line"
        Write-Host "✅ 签退成功：$Line" -ForegroundColor Green
        Write-Host "📝 请记得："
        Write-Host "   1. 更新 PROGRESS.md 的任务状态（✅/🔲）"
        Write-Host "   2. git add + commit + push"
    }
}
