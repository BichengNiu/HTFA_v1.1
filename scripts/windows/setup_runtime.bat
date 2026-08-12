@echo off
setlocal

cd /d "%~dp0..\.."
if errorlevel 1 (
    echo [ERROR] Cannot open the project directory.
    exit /b 1
)

echo Building the unified HTFA runtime...
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\bootstrap_runtime.ps1
if errorlevel 1 (
    echo [ERROR] Runtime setup failed. The previous runtime was preserved.
    exit /b 1
)

echo [OK] Unified HTFA runtime is ready.
exit /b 0
