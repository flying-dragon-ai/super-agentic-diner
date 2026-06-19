@echo off
cd /d "%~dp0"
title Coffee AI Boss

echo ============================================
echo   Coffee AI Boss - Launcher
echo ============================================
echo.

REM ---- Kill old server on port 8000 only (not all python) ----
echo [0/4] Stopping old server on port 8000 (if any)...
for /f "tokens=5" %%p in ('netstat -aon ^| findstr ":8000 " ^| findstr "LISTENING"') do taskkill /F /PID %%p >nul 2>nul
echo.

REM ---- Check Python ----
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] python not found in PATH.
    echo Install from: https://www.python.org/downloads/
    goto end
)
echo [1/4] Python OK

REM ---- Install deps ----
echo [2/4] Checking dependencies...
python -m pip install -r requirements.txt -q
if errorlevel 1 echo [INFO] Some deps may already be installed, continue...

REM ---- Init DB ----
echo [3/4] Initializing database...
if exist coffee.db del /q coffee.db
python scripts\init_db.py
if errorlevel 1 (
    echo [ERROR] DB init failed
    goto end
)

REM ---- Start server ----
echo [4/4] Starting server: http://localhost:8000
echo       Press Ctrl+C to stop.
echo.
timeout /t 2 >nul
start "" http://localhost:8000
python -m uvicorn app.main:app --port 8000

:end
echo.
echo Press any key to close...
pause >nul