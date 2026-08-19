@echo off
setlocal

echo ========================================
echo HTFA Dashboard Startup
echo ========================================
echo.

cd /d "%~dp0..\.."
if errorlevel 1 (
    echo [ERROR] Cannot open the project directory.
    goto :failed
)

echo [1/2] Preparing HTFA...
if not exist "runtime\python.exe" (
    echo [ERROR] Bundled runtime\python.exe was not found.
    echo [HINT] Run scripts\windows\setup_runtime.bat to build the unified runtime.
    goto :failed
)

set "HTFA_LAUNCHER_ACTIVE=true"

echo Checking port 8501...
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\free_port.ps1 -Port 8501 -WaitSeconds 15
if errorlevel 1 goto :failed
echo.

echo Clearing __pycache__ so the latest code always loads...
for /d /r ".\runtime" %%D in (__pycache__) do ( if exist "%%D" rmdir /s /q "%%D" )
for /d /r ".\dashboard" %%D in (__pycache__) do ( if exist "%%D" rmdir /s /q "%%D" )
if exist ".\__pycache__" rmdir /s /q ".\__pycache__"
echo.

echo [2/2] Starting HTFA...
if not defined HTFA_DEBUG_MODE set "HTFA_DEBUG_MODE=true"
echo [INFO] Debug mode: %HTFA_DEBUG_MODE%
echo [INFO] Checking Ts main before launch; offline mode uses the local version.
echo.
"runtime\python.exe" scripts\run_htfa.py --server.port=8501 %*
if errorlevel 1 (
    echo.
    echo [ERROR] HTFA exited with an error.
    goto :failed
)

echo.
echo [OK] HTFA has stopped.
pause
exit /b 0

:failed
echo.
echo Startup failed. Review the error above, then press any key to close.
pause >nul
exit /b 1
