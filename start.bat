@echo off
REM FSAR unified launcher.
REM Always rebuilds the frontend so latest .tsx/.ts changes are picked up.
REM Python backend (uvicorn) does not auto-reload - re-run this script to
REM apply backend changes; the script kills the old backend window first.

setlocal
cd /d "%~dp0"

set LOG=%~dp0frontend-build.log

REM 1. Ensure node_modules exists.
if not exist "frontend\node_modules" (
    echo [FSAR] Installing frontend deps...
    call npm --prefix frontend install
    if errorlevel 1 (
        echo [FSAR] npm install failed.
        pause
        exit /b 1
    )
)

REM 2. Always rebuild frontend - Vite incremental keeps this fast (1-5s).
echo [FSAR] Building frontend (log: %LOG%)...
call npm --prefix frontend run build > "%LOG%" 2>&1
set RC=%errorlevel%
if not "%RC%"=="0" (
    echo.
    echo [FSAR] BUILD FAILED with exit code %RC%. Full log:
    echo ---------------------------------------------------------------
    type "%LOG%"
    echo ---------------------------------------------------------------
    echo.
    pause
    exit /b 1
)

REM 3. Kill any previous FSAR Backend window so port :8765 isn't held by an
REM    old process running stale Python code (uvicorn has no --reload).
taskkill /FI "WINDOWTITLE eq FSAR Backend*" /T /F >nul 2>&1

REM 4. Start backend (which serves the GUI at the same origin).
start "FSAR Backend" cmd /k "python -m src.server.ws_server"

REM 5. Open browser after a short delay.
timeout /t 3 /nobreak >nul
start "" "http://127.0.0.1:8765"

echo.
echo [FSAR] Backend + GUI on http://127.0.0.1:8765
echo [FSAR] Edit code and re-run this script to pick up changes.
echo.
pause