@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title Crossroads Agent Cafe

if "%PORT%"=="" set "PORT=8000"
if "%HOST%"=="" set "HOST=127.0.0.1"
if "%A2A_DISCOVERY_HTTP_PORT%"=="" set "A2A_DISCOVERY_HTTP_PORT=%PORT%"

echo ============================================
echo   Crossroads Agent Cafe - Local Launcher
echo ============================================
echo.

echo [1/6] Preparing Python runtime...
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_CMD=%CD%\.venv\Scripts\python.exe"
    echo Using existing .venv.
) else (
    set "BASE_PYTHON="
    py -3.13 --version >nul 2>nul && set "BASE_PYTHON=py -3.13"
    if not defined BASE_PYTHON ( py -3.12 --version >nul 2>nul && set "BASE_PYTHON=py -3.12" )
    if not defined BASE_PYTHON ( py -3.11 --version >nul 2>nul && set "BASE_PYTHON=py -3.11" )
    if not defined BASE_PYTHON ( py -3.10 --version >nul 2>nul && set "BASE_PYTHON=py -3.10" )
    if not defined BASE_PYTHON ( where py >nul 2>nul && set "BASE_PYTHON=py -3" )
    if not defined BASE_PYTHON ( where python >nul 2>nul && set "BASE_PYTHON=python" )
    if "!BASE_PYTHON!"=="" (
        echo [ERROR] Python 3.10+ was not found in PATH.
        goto fail
    )
    !BASE_PYTHON! -c "import sys; sys.exit(0 if sys.version_info[:2] ^>= (3,10) else 1)" >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] This project requires Python 3.10 or newer.
        goto fail
    )
    !BASE_PYTHON! -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create .venv.
        goto fail
    )
    set "PYTHON_CMD=%CD%\.venv\Scripts\python.exe"
)
echo.

echo [2/6] Checking configuration...
if exist ".env" (
    echo Using .env.
) else (
    echo No .env found; using safe local defaults ^(SQLite + fakeredis^).
)
set "_CONFIG_FILE=%TEMP%\coffee_runtime_config_%RANDOM%.txt"
"%PYTHON_CMD%" -c "from app.config import settings; print('APP_DB_MODE=' + settings.db_mode); print('APP_USE_FAKEREDIS=' + str(settings.use_fakeredis).lower())" > "%_CONFIG_FILE%"
if errorlevel 1 (
    del "%_CONFIG_FILE%" >nul 2>nul
    echo [ERROR] Configuration validation failed.
    goto fail
)
for /f "usebackq tokens=1,2 delims==" %%a in ("%_CONFIG_FILE%") do set "%%a=%%b"
del "%_CONFIG_FILE%" >nul 2>nul
echo   DB_MODE=!APP_DB_MODE!
echo   MEMORY_BACKEND=!APP_USE_FAKEREDIS!
echo.

echo [3/6] Installing Python dependencies...
set "PIP_MIRROR=-i https://pypi.tuna.tsinghua.edu.cn/simple --default-timeout=30"
"%PYTHON_CMD%" -m pip install -r requirements.txt %PIP_MIRROR%
if errorlevel 1 (
    echo [WARN] Mirror install failed; retrying the default package source...
    "%PYTHON_CMD%" -m pip install -r requirements.txt
)
if errorlevel 1 (
    echo [ERROR] Failed to install requirements.
    goto fail
)
echo.

echo [4/6] Checking configured backends...
if /I "!APP_DB_MODE!"=="mysql" (
    "%PYTHON_CMD%" -c "from sqlalchemy import text; from app.db.database import engine; c=engine.connect(); row=c.execute(text('SELECT DATABASE(), 1')).one(); print('MySQL OK: database=' + str(row[0])); c.close()"
    if errorlevel 1 (
        echo [ERROR] MySQL connection failed. Check MYSQL_* values.
        goto fail
    )
) else (
    echo SQLite selected; no external database probe required.
)
if /I "!APP_USE_FAKEREDIS!"=="false" (
    "%PYTHON_CMD%" -c "import redis; from app.config import settings; c=redis.Redis.from_url(settings.redis_url, socket_connect_timeout=5, socket_timeout=5); c.ping(); print('Redis OK')"
    if errorlevel 1 (
        echo [ERROR] Redis connection failed. Check REDIS_* values.
        goto fail
    )
) else (
    echo fakeredis selected; no external Redis probe required.
)
echo.

echo [5/6] Running canonical schema migration...
"%PYTHON_CMD%" scripts\migrate_order_sources.py
if errorlevel 1 (
    echo [ERROR] Database migration failed.
    goto fail
)
echo.

echo [6/6] Checking port %PORT%...
set "PORT_PID="
for /f "tokens=5" %%p in ('netstat -aon ^| findstr /R /C:":%PORT% .*LISTENING"') do set "PORT_PID=%%p"
if defined PORT_PID (
    echo [ERROR] Port %PORT% is already in use by PID !PORT_PID!.
    echo Stop that process explicitly or choose another PORT. No process was terminated.
    goto fail
)

echo Starting server: http://%HOST%:%PORT%
if "%HOST%"=="127.0.0.1" echo [INFO] LAN clients cannot connect while HOST=127.0.0.1. Set HOST=0.0.0.0 to enable LAN access.
echo Press Ctrl+C to stop.
echo.
if /I not "%OPEN_BROWSER%"=="0" start "" "http://localhost:%PORT%/3d/login"
"%PYTHON_CMD%" -m uvicorn app.main:app --host %HOST% --port %PORT% --reload --ws-max-size 16384
goto end

:fail
echo.
echo Startup failed.

:end
echo.
echo Press any key to close...
pause >nul
endlocal
