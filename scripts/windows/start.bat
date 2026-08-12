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

set "PYTHONDONTWRITEBYTECODE=1"

echo [1/4] Checking the bundled Python runtime...
if not exist "runtime\python.exe" (
    echo [ERROR] Bundled runtime\python.exe was not found.
    echo [HINT] Run scripts\windows\setup_runtime.bat to build the unified runtime.
    goto :failed
)

"runtime\python.exe" --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Bundled Python cannot start. The release may be damaged.
    goto :failed
)
for /f "delims=" %%V in ('"runtime\python.exe" --version 2^>^&1') do set "HTFA_PYTHON_VERSION=%%V"
echo [OK] Using bundled %HTFA_PYTHON_VERSION%
echo.

set "HTFA_LAUNCHER_ACTIVE=true"

echo [2/4] Clearing project Python caches...
call :clean_python_cache dashboard
call :clean_python_cache scripts
call :clean_python_cache tests
if exist "__pycache__" rd /s /q "__pycache__" >nul 2>&1
echo [OK] Python caches cleared.
echo.

echo [3/4] Checking port 8501...
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\free_port.ps1 -Port 8501 -WaitSeconds 15
if errorlevel 1 goto :failed
echo.

echo [4/4] Starting HTFA...
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

:clean_python_cache
if not exist "%~1" exit /b 0
for /r "%~1" %%F in (*.pyc) do del /f /q "%%F" >nul 2>&1
for /r "%~1" %%F in (*.pyo) do del /f /q "%%F" >nul 2>&1
for /d /r "%~1" %%D in (__pycache__) do rd /s /q "%%D" >nul 2>&1
exit /b 0

:failed
echo.
echo Startup failed. Review the error above, then press any key to close.
pause >nul
exit /b 1
