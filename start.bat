@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title Coffee AI Boss

if "%PORT%"=="" set "PORT=8000"

echo ============================================
echo   Coffee AI Boss - Launcher
echo ============================================
echo.

echo [0/6] Stopping old server on port %PORT% (if any)...
for /f "tokens=5" %%p in ('netstat -aon ^| findstr /R /C:":%PORT% .*LISTENING"') do (
    if not "%%p"=="0" taskkill /F /PID %%p >nul 2>nul
)
echo.

echo [1/6] Preparing Python runtime...
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_CMD=%CD%\.venv\Scripts\python.exe"
    echo Using existing .venv.
) else (
    set "BASE_PYTHON="
    rem Detect a Python 3.10+ interpreter. The app uses PEP 604 `X | None`
    rem type hints (app/config.py), so Python < 3.10 will crash at import.
    rem Prefer the `py` launcher and target a specific modern version, because
    rem the bare `python` in PATH may resolve to an older copy (e.g. 3.8).
    py -3.13 --version >nul 2>nul && set "BASE_PYTHON=py -3.13"
    if not defined BASE_PYTHON ( py -3.12 --version >nul 2>nul && set "BASE_PYTHON=py -3.12" )
    if not defined BASE_PYTHON ( py -3.11 --version >nul 2>nul && set "BASE_PYTHON=py -3.11" )
    if not defined BASE_PYTHON ( py -3.10 --version >nul 2>nul && set "BASE_PYTHON=py -3.10" )
    if not defined BASE_PYTHON (
        where py >nul 2>nul && set "BASE_PYTHON=py -3"
    )
    if not defined BASE_PYTHON (
        where python >nul 2>nul && set "BASE_PYTHON=python"
    )
    if "!BASE_PYTHON!"=="" (
        echo [ERROR] Python was not found in PATH.
        echo Install Python 3.11+ and run this launcher again.
        goto fail
    )
    rem Guard: refuse to build a venv from an interpreter older than 3.10,
    rem otherwise we silently get a broken venv that crashes at import time.
    !BASE_PYTHON! -c "import sys; sys.exit(0 if sys.version_info[:2]>=(3,10) else 1)" >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] Detected Python is too old. This project needs 3.10+.
        !BASE_PYTHON! --version
        echo Install Python 3.11+ and run this launcher again.
        goto fail
    )
    echo Using !BASE_PYTHON! to create .venv...
    !BASE_PYTHON! -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create .venv.
        goto fail
    )
    set "PYTHON_CMD=%CD%\.venv\Scripts\python.exe"
)
echo.

echo [2/6] Checking .env...
if not exist ".env" (
    echo [ERROR] .env was not found.
    if exist ".env.example" (
        echo Copy .env.example to .env and edit settings.
    )
    goto fail
)
echo .env OK.
echo.

echo [3/6] Installing Python dependencies...
set "PIP_MIRROR=-i https://pypi.tuna.tsinghua.edu.cn/simple --default-timeout=30"
"%PYTHON_CMD%" -m pip install --upgrade pip %PIP_MIRROR%
"%PYTHON_CMD%" -m pip install -r requirements.txt %PIP_MIRROR%
if errorlevel 1 (
    echo [WARN] Mirror install failed, retrying default source ^(may be slow^)...
    "%PYTHON_CMD%" -m pip install -r requirements.txt
)
if errorlevel 1 (
    echo [ERROR] Failed to install requirements.
    goto fail
)
echo.

echo [4/6] Detecting database/memory backend...
set "_MODE_FILE=%TEMP%\coffee_db_mode.txt"
"%PYTHON_CMD%" -c "from app.config import settings; print(settings.db_mode)" > "%_MODE_FILE%" 2>nul
set "DB_MODE="
set /p DB_MODE=<"%_MODE_FILE%"
del "%_MODE_FILE%" >nul 2>nul
if "!DB_MODE!"=="" set "DB_MODE=sqlite"
echo   DB_MODE = !DB_MODE!

if /I "!DB_MODE!"=="sqlite" (
    echo   Using SQLite - no MySQL/Redis connectivity check needed.
    echo.
    echo [5/6] Initializing SQLite schema...
    "%PYTHON_CMD%" scripts\init_db.py
    if errorlevel 1 (
        echo [ERROR] Database initialization failed.
        goto fail
    )
    echo.
    goto start_server
)

echo   Using MySQL - checking connectivity...
"%PYTHON_CMD%" -c "from sqlalchemy import text; from app.db.database import engine; conn = engine.connect(); row = conn.execute(text('SELECT DATABASE(), 1')).one(); print('MySQL OK: database=' + str(row[0])); conn.close()"
if errorlevel 1 (
    echo [ERROR] MySQL connection failed. Check MYSQL_* values in .env.
    goto fail
)
"%PYTHON_CMD%" -c "import redis; from app.config import settings; client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=5, socket_timeout=5); client.ping(); print('Redis OK')"
if errorlevel 1 (
    echo [ERROR] Redis connection failed. Check REDIS_* values in .env.
    goto fail
)
echo.

echo [5/6] Initializing and migrating MySQL schema...
"%PYTHON_CMD%" scripts\init_db.py
if errorlevel 1 (
    echo [ERROR] Database initialization failed.
    goto fail
)
"%PYTHON_CMD%" scripts\migrate_order_sources.py
if errorlevel 1 (
    echo [ERROR] Database migration failed.
    goto fail
)
echo.

:start_server

echo [6/6] Starting server: http://localhost:%PORT%
echo       Press Ctrl+C to stop.
echo.
timeout /t 2 >nul
if /I not "%OPEN_BROWSER%"=="0" start "" "http://localhost:%PORT%/3d/login"
"%PYTHON_CMD%" -m uvicorn app.main:app --host 127.0.0.1 --port %PORT% --reload
goto end

:fail
echo.
echo Startup failed.

:end
echo.
echo Press any key to close...
pause >nul
endlocal
