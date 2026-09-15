@echo off
setlocal

cd /d "%~dp0"
if errorlevel 1 goto :failed

if /I "%~1"=="stop" goto :stop
if /I "%~1"=="setup-runtime" goto :setup_runtime

echo ========================================
echo HTFA Dashboard Startup
echo ========================================
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%CD%\htfa.ps1" -Command Start %*
if errorlevel 1 goto :failed
exit /b 0

:stop
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%CD%\htfa.ps1" -Command Stop
if errorlevel 1 goto :failed
exit /b 0

:setup_runtime
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%CD%\htfa.ps1" -Command SetupRuntime
if errorlevel 1 goto :failed
exit /b 0

:failed
echo.
echo HTFA command failed. Review the error above, then press any key to close.
pause >nul
exit /b 1
