@echo off
setlocal

echo ========================================
echo HTFA Dashboard Startup
echo ========================================
echo.

cd /d "%~dp0.."
if errorlevel 1 (
    echo [ERROR] Cannot open the project directory.
    goto :failed
)

if not exist "runtime\python.exe" (
    echo [INFO] Bundled runtime was not found. Building it now...
    where python >nul 2>nul
    if not errorlevel 1 (
        python -B scripts\htfa.py setup-runtime
    ) else (
        where py >nul 2>nul
        if not errorlevel 1 (
            py -3 -B scripts\htfa.py setup-runtime
        ) else (
            echo [ERROR] No system Python was found for the first runtime build.
            echo [HINT] Install Python 3 and run this file again.
            goto :failed
        )
    )
    if errorlevel 1 goto :failed
)

echo.
echo Clearing __pycache__ so the latest code always loads...
for /d /r ".\runtime" %%D in (__pycache__) do ( if exist "%%D" rmdir /s /q "%%D" )
for /d /r ".\dashboard" %%D in (__pycache__) do ( if exist "%%D" rmdir /s /q "%%D" )
if exist ".\__pycache__" rmdir /s /q ".\__pycache__"
echo.

if not defined HTFA_DEBUG_MODE set "HTFA_DEBUG_MODE=true"
echo [INFO] Debug mode: %HTFA_DEBUG_MODE%
echo [INFO] Checking Ts main before launch; offline mode uses the local version.
echo.
"runtime\python.exe" -B scripts\htfa.py start --server.port=8501 %*
set "HTFA_START_CODE=%ERRORLEVEL%"

echo.
echo Cleaning any remaining HTFA backend process tree...
"runtime\python.exe" -B scripts\htfa.py stop --port=8501 --wait-seconds=5
set "HTFA_STOP_CODE=%ERRORLEVEL%"

if not "%HTFA_START_CODE%"=="0" (
    echo.
    echo [ERROR] HTFA exited with an error.
    goto :failed
)
if not "%HTFA_STOP_CODE%"=="0" (
    echo.
    echo [ERROR] HTFA backend cleanup failed.
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
