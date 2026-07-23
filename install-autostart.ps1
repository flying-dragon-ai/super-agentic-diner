<#
.SYNOPSIS
  注册 Windows 计划任务：当前用户登录时自动运行 keep-public.ps1（含 -Bootstrap，会自动拉起后端+隧道并保活）。
  需要以管理员身份运行（注册 AtLogOn Highest 任务）。

.PARAMETER TaskName
  计划任务名，默认 CafePublicTunnel。

.EXAMPLE
  .\install-autostart.ps1
#>
[CmdletBinding()]
param([string]$TaskName = 'CafePublicTunnel')

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$keepScript = Join-Path $Root 'keep-public.ps1'

if (-not (Test-Path $keepScript)) {
    Write-Host "[X] 未找到 keep-public.ps1" -ForegroundColor Red
    exit 1
}

# 检查管理员权限（注册 Highest 级任务需要）
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "[!] 当前非管理员。Highest 级计划任务需要管理员权限，将以 Limited 级注册。" -ForegroundColor Yellow
    Write-Host "    若隧道/服务因权限不足失败，请用管理员身份重开 PowerShell 再运行本脚本。" -ForegroundColor Yellow
    $runLevel = 'Limited'
} else {
    $runLevel = 'Highest'
}

$arg = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$keepScript`" -Bootstrap"
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arg
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -RunLevel $runLevel -LogonType Interactive
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit ([timespan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Description 'Crossroads Agent Cafe 公网隧道保活（start-public + keep-public）' -Force | Out-Null

Write-Host ""
Write-Host "================================ 自启已注册 ================================" -ForegroundColor Green
Write-Host " 计划任务 : $TaskName"
Write-Host " 触发     : 用户 $env:USERNAME 登录时"
Write-Host " 动作     : 后台运行 keep-public.ps1 -Bootstrap（自动拉起服务+隧道并持续保活）"
Write-Host " 运行级别 : $runLevel"
Write-Host "---------------------------------------------------------------------------"
Write-Host " 立即测试 : Start-ScheduledTask -TaskName $TaskName"
Write-Host " 卸载     : .\uninstall-autostart.ps1"
Write-Host " 手动停止 : .\stop-public.ps1"
Write-Host "===========================================================================" -ForegroundColor Green
