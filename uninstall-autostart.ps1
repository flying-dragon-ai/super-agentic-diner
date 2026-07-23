<#
.SYNOPSIS
  卸载自启计划任务，并停止其可能正在运行的保活进程。
  仅移除计划任务与保活 watchdog；不会停止后端服务（如需一并停止请先运行 stop-public.ps1）。

.PARAMETER TaskName
  计划任务名，默认 CafePublicTunnel（需与 install-autostart.ps1 一致）。

.EXAMPLE
  .\uninstall-autostart.ps1
#>
[CmdletBinding()]
param([string]$TaskName = 'CafePublicTunnel')

$ErrorActionPreference = 'Continue'

# 1. 停止正在运行的任务实例（会杀掉 keep-public.ps1 进程）
try {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Write-Host "已停止计划任务 '$TaskName' 的运行实例" -ForegroundColor Green
} catch {
    Write-Host "计划任务 '$TaskName' 不存在，跳过停止" -ForegroundColor Yellow
}

# 2. 兜底：清理可能残留的 keep-public 后台进程
Get-CimInstance Win32_Process -Filter "Name='powershell.exe' OR Name='pwsh.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like '*keep-public.ps1*' } |
    ForEach-Object {
        try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop; Write-Host "清理残留保活进程 PID=$($_.ProcessId)" -ForegroundColor Green }
        catch {}
    }

# 3. 注销计划任务
try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
    Write-Host "已注销计划任务 '$TaskName'" -ForegroundColor Green
} catch {
    Write-Host "计划任务 '$TaskName' 不存在或已注销" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "卸载完成。后端服务仍在运行，如需停止请运行: .\stop-public.ps1" -ForegroundColor Cyan
