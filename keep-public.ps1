<#
.SYNOPSIS
  公网隧道保活 watchdog。持续监控 serveo.net 隧道，断开自动重建并打印新地址。
  仅保活隧道，不碰后端进程（后端交给 uvicorn --reload 自愈）。
  所有状态同时写入 .tunnel-keepalive.log，方便计划任务后台运行时追溯地址变更。

.PARAMETER Interval
  检测间隔秒数，默认 60。

.PARAMETER Bootstrap
  开关。启动时若后端服务未运行，自动调用 start-public.ps1 拉起后端 + 隧道。

.EXAMPLE
  .\keep-public.ps1                  # 仅保活
  .\keep-public.ps1 -Bootstrap       # 启动时若没跑则自动拉起
  .\keep-public.ps1 -Interval 30     # 每 30 秒检测一次
#>
[CmdletBinding()]
param(
    [int]$Interval = 60,
    [switch]$Bootstrap
)

$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$PidFile = Join-Path $Root '.tunnel-pids.json'
$StartScript = Join-Path $Root 'start-public.ps1'
$KeepLog = Join-Path $Root '.tunnel-keepalive.log'

function Write-Ts($m, $color = 'Cyan') {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $m"
    Write-Host $line -ForegroundColor $color
    try { Add-Content -Path $KeepLog -Value $line -Encoding UTF8 -ErrorAction SilentlyContinue } catch {}
}

# 重建隧道：返回含 Pid/Url/Log 的对象
function New-PublicTunnel {
    param([int]$Port)
    $tunnelLog = Join-Path $env:TEMP "cafe-tunnel-$Port.log"
    Remove-Item $tunnelLog, "$tunnelLog.err" -ErrorAction SilentlyContinue

    # 关键：回连目标必须用 127.0.0.1（localhost 会被解析为 IPv6 ::1 导致 502）
    $tp = Start-Process -FilePath 'ssh' `
        -ArgumentList @('-o', 'StrictHostKeyChecking=accept-new', '-o', 'ServerAliveInterval=30', '-R', "80:127.0.0.1:$Port", 'serveo.net') `
        -WindowStyle Hidden `
        -RedirectStandardOutput $tunnelLog -RedirectStandardError "$tunnelLog.err" -PassThru

    $url = $null
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Milliseconds 750
        if (Test-Path $tunnelLog) {
            $m = Get-Content $tunnelLog -ErrorAction SilentlyContinue |
                Select-String -Pattern 'https://[a-z0-9.-]+serveousercontent\.com' |
                Select-Object -First 1
            if ($m) { $url = $m.Matches[0].Value; break }
        }
    }
    return [pscustomobject]@{ Pid = $tp.Id; Url = $url; Log = $tunnelLog }
}

# ---------- 首次启动：可选拉起 ----------
if ($Bootstrap) {
    $svcUp = $false
    try {
        $r = Invoke-WebRequest 'http://127.0.0.1:8000/status' -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200) { $svcUp = $true }
    } catch {}
    if (-not $svcUp -and (Test-Path $StartScript)) {
        Write-Ts '后端未运行，启动 start-public.ps1 ...' 'Yellow'
        & $StartScript
    }
}

Write-Ts "公网隧道保活已启动（检测间隔 ${Interval}s）。按 Ctrl+C 停止。" 'Green'

# ---------- 主保活循环 ----------
while ($true) {
    $info = $null
    if (Test-Path $PidFile) {
        try { $info = Get-Content $PidFile -Raw | ConvertFrom-Json } catch {}
    }

    if (-not $info) {
        Write-Ts '未找到 .tunnel-pids.json，跳过本轮（请先运行 start-public.ps1）' 'Yellow'
        Start-Sleep -Seconds $Interval
        continue
    }

    $port = if ($info.port) { [int]$info.port } else { 8000 }
    $tunAlive = $false
    $urlOk = $false

    # 1. 隧道进程是否存活
    if ($info.tunnel_pid -and ($info.tunnel_pid -is [int]) -and ($info.tunnel_pid -gt 0)) {
        try { $null = Get-Process -Id $info.tunnel_pid -ErrorAction Stop; $tunAlive = $true } catch {}
    }

    # 2. 公网地址是否可达
    if ($info.public_url) {
        try {
            $r = Invoke-WebRequest ($info.public_url + '/status') -UseBasicParsing -TimeoutSec 10
            if ($r.StatusCode -eq 200) { $urlOk = $true }
        } catch {}
    }

    if ($tunAlive -and $urlOk) {
        Write-Ts "隧道正常 | $($info.public_url)" 'DarkGray'
    } else {
        Write-Ts "隧道异常（进程存活=$tunAlive 地址可达=$urlOk），重建中..." 'Yellow'

        # 停掉旧隧道进程
        if ($info.tunnel_pid -and ($info.tunnel_pid -is [int])) {
            try { Stop-Process -Id $info.tunnel_pid -Force -ErrorAction Stop } catch {}
        }
        # 兜底清理残留 serveo ssh
        Get-CimInstance Win32_Process -Filter "Name='ssh.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -like '*serveo.net*' } |
            ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop } catch {} }

        $result = New-PublicTunnel -Port $port
        if ($result.Url) {
            $info.tunnel_pid = $result.Pid
            $info.tunnel_log = $result.Log
            $info.public_url = $result.Url
            $info | ConvertTo-Json | Set-Content -Path $PidFile -Encoding UTF8
            Write-Ts "隧道已重建，新地址 $($result.Url)" 'Green'
        } else {
            Write-Ts '重建失败，下一轮重试' 'Red'
        }
    }

    Start-Sleep -Seconds $Interval
}
