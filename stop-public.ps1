<#
.SYNOPSIS
  停止由 start-public.ps1 启动的公网隧道与后端，并清理 PID 记录。
  对 backend_pid 为 0（复用的外部后端）不会停止，以免误杀。

.EXAMPLE
  .\stop-public.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Continue'
$Root    = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path $Root '.tunnel-pids.json'

if (-not (Test-Path $PidFile)) {
    Write-Host "未找到 .tunnel-pids.json，无可停止的记录。" -ForegroundColor Yellow
} else {
    $info = Get-Content $PidFile -Raw | ConvertFrom-Json
    foreach ($k in 'tunnel_pid', 'backend_pid') {
        $id = $info.$k
        if ($id -and ($id -is [int]) -and ($id -gt 0)) {
            try {
                Stop-Process -Id $id -Force -ErrorAction Stop
                Write-Host "已停止 $k = $id" -ForegroundColor Green
            } catch {
                Write-Host "$k = $id 已不在运行" -ForegroundColor Yellow
            }
        }
    }
    Remove-Item $PidFile -ErrorAction SilentlyContinue
}

# 兜底：清理任何可能残留的 serveo 隧道进程
Get-CimInstance Win32_Process -Filter "Name='ssh.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like '*serveo.net*' } |
    ForEach-Object {
        try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop; Write-Host "清理残留 serveo 隧道 PID=$($_.ProcessId)" -ForegroundColor Green }
        catch {}
    }

Write-Host "停止完成。" -ForegroundColor Green
