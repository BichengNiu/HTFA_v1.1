@echo off
setlocal

echo ========================================
echo HTFA Backend Shutdown
echo ========================================
echo.

cd /d "%~dp0.."
if errorlevel 1 (
    echo [ERROR] Cannot open the project directory.
    goto :failed
)

if not exist "runtime\python.exe" (
    echo [ERROR] Bundled runtime was not found.
    goto :failed
)

"runtime\python.exe" -B scripts\htfa.py stop --port=8501
if errorlevel 1 (
    echo.
    echo [ERROR] HTFA backend cleanup failed.
    goto :failed
)

echo.
echo [OK] HTFA backend process tree has been terminated and verified.
pause
exit /b 0

:failed
echo.
echo Shutdown failed. Review the error above, then press any key to close.
pause >nul
exit /b 1
