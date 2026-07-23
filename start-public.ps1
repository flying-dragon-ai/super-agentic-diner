<#
.SYNOPSIS
  一键启动 Crossroads Agent Cafe 后端 + serveo.net 公网隧道，并打印公网访问地址。
  基于系统自带 ssh.exe，无需安装任何额外软件。

.PARAMETER Port
  后端端口，默认 8000。

.PARAMETER Lan
  开关。后端绑定 0.0.0.0，允许同 WiFi 局域网设备直连（默认仅 127.0.0.1，仍不影响公网隧道）。

.PARAMETER NoBackend
  开关。若后端已在外部运行，仅建隧道，不启动/重启后端。

.EXAMPLE
  .\start-public.ps1            # 启动后端 + 公网隧道
  .\start-public.ps1 -Lan       # 额外开放局域网访问
  .\start-public.ps1 -NoBackend # 后端已在跑，只建隧道

.NOTES
  - 公网地址是 serveo.net 分配的临时随机域名，隧道 SSH 进程存活期间一直有效，断开重连会换新地址。
  - 首次浏览器访问 serveo 域名会有一个警告页，点击继续即可。
  - 停止：.\stop-public.ps1
#>
[CmdletBinding()]
param(
    [int]$Port = 8000,
    [switch]$Lan,
    [switch]$NoBackend
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$BackendHost = if ($Lan) { '0.0.0.0' } else { '127.0.0.1' }
$Python      = Join-Path $Root '.venv\Scripts\python.exe'
$StatusUrl   = "http://127.0.0.1:$Port/status"
$PidFile     = Join-Path $Root '.tunnel-pids.json'

function Write-Step($m) { Write-Host "[$(Get-Date -Format HH:mm:ss)] $m" -ForegroundColor Cyan }
function Write-Ok($m)   { Write-Host "  [OK] $m" -ForegroundColor Green }
function Write-Warn2($m){ Write-Host "  [!]  $m" -ForegroundColor Yellow }
function Write-Err2($m) { Write-Host "  [X]  $m" -ForegroundColor Red }

# ---------------- 0. 前置检查 ----------------
Write-Step "检查运行环境"
if (-not (Test-Path $Python)) {
    Write-Err2 "未找到 $Python；请先运行 start.bat 创建 .venv"
    exit 1
}
if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
    Write-Err2 "未找到 ssh.exe；请在 [设置] 启用 Windows OpenSSH 客户端"
    exit 1
}
Write-Ok "python 与 ssh 就绪"

# ---------------- 1. 后端 ----------------
$backendReady = $false
try {
    $r = Invoke-WebRequest $StatusUrl -UseBasicParsing -TimeoutSec 3
    if ($r.StatusCode -eq 200) { $backendReady = $true }
} catch {}

$backendPid = 0

if ($NoBackend) {
    if ($backendReady) {
        Write-Step "复用已在运行的后端 (-NoBackend)"
    } else {
        Write-Err2 "指定了 -NoBackend，但 127.0.0.1:$Port 未检测到服务"
        exit 1
    }
} elseif ($backendReady) {
    Write-Step "检测到后端已在 127.0.0.1:$Port 运行，复用（如需重启请先运行 .\stop-public.ps1）"
} else {
    Write-Step "启动后端 uvicorn (${BackendHost}:${Port})"
    $backendLog = Join-Path $env:TEMP "cafe-backend-$Port.log"
    $p = Start-Process -FilePath $Python `
        -ArgumentList @('-m','uvicorn','app.main:app','--host',$BackendHost,'--port',$Port,'--ws-max-size','16384') `
        -WorkingDirectory $Root -WindowStyle Hidden `
        -RedirectStandardOutput $backendLog -RedirectStandardError "$backendLog.err" -PassThru
    $backendPid = $p.Id
    Write-Ok "后端 PID=$backendPid，日志 $backendLog"

    $ready = $false
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Milliseconds 750
        try {
            $r = Invoke-WebRequest $StatusUrl -UseBasicParsing -TimeoutSec 3
            if ($r.StatusCode -eq 200) { $ready = $true; break }
        } catch {}
    }
    if (-not $ready) {
        Write-Err2 "后端启动超时，请查看 $backendLog.err"
        exit 1
    }
    Write-Ok "后端就绪"
}

# ---------------- 2. SSH 公网隧道 (serveo.net) ----------------
Write-Step "建立 serveo.net 公网隧道"
$tunnelLog = Join-Path $env:TEMP "cafe-tunnel-$Port.log"
Remove-Item $tunnelLog, "$tunnelLog.err" -ErrorAction SilentlyContinue

# 关键：回连目标必须用 127.0.0.1，不能用 localhost
# （localhost 在 Windows 上会被 ssh 解析为 IPv6 ::1，而 uvicorn 仅监听 IPv4，会导致 502）
$tp = Start-Process -FilePath 'ssh' `
    -ArgumentList @('-o','StrictHostKeyChecking=accept-new','-o','ServerAliveInterval=30','-R',"80:127.0.0.1:$Port",'serveo.net') `
    -WindowStyle Hidden `
    -RedirectStandardOutput $tunnelLog -RedirectStandardError "$tunnelLog.err" -PassThru
Write-Ok "隧道 PID=$($tp.Id)"

$publicUrl = $null
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 750
    if (Test-Path $tunnelLog) {
        $m = Get-Content $tunnelLog -ErrorAction SilentlyContinue |
            Select-String -Pattern 'https://[a-z0-9.-]+serveousercontent\.com' |
            Select-Object -First 1
        if ($m) { $publicUrl = $m.Matches[0].Value; break }
    }
}
if (-not $publicUrl) {
    Write-Err2 "未能获取公网地址，请查看 $tunnelLog.err"
    Write-Warn2 "若 serveo.net 暂时不可用，可手动改用：ssh -R 80:127.0.0.1:$Port nokey@localhost.run"
    exit 1
}
Write-Ok "公网地址 $publicUrl"

# ---------------- 3. 持久化 PID ----------------
$lanIp = $null
if ($Lan) {
    $lanIp = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
        Select-Object -First 1).IPAddress
}
$pidInfo = [ordered]@{
    backend_pid = $backendPid
    tunnel_pid  = $tp.Id
    tunnel_log  = $tunnelLog
    public_url  = $publicUrl
    lan_ip      = $lanIp
    port        = $Port
    lan         = [bool]$Lan
}
$pidInfo | ConvertTo-Json | Set-Content -Path $PidFile -Encoding UTF8

# ---------------- 4. 汇总 ----------------
Write-Host ""
Write-Host "================ 公网访问已就绪 ================" -ForegroundColor Green
Write-Host " 公网   : $publicUrl" -ForegroundColor Green
Write-Host " 本机   : http://127.0.0.1:$Port"
if ($Lan -and $lanIp) {
    Write-Host " 局域网 : http://${lanIp}:${Port} （同 WiFi 设备可访问）"
}
Write-Host "------------------------------------------------"
Write-Host " 页面   : /3d  /economy  /about  /services  /skill/discovery"
Write-Host " 停止   : .\stop-public.ps1"
Write-Host "===============================================" -ForegroundColor Green
Write-Host ""
Write-Host "提示：serveo 临时地址在隧道存活期间有效；首次访问会有警告页，点继续即可。" -ForegroundColor DarkGray
