@echo off
rem Manual online refresh: fetch all sources, load DuckDB, and merge Excel.
rem Run this batch manually; it does not create or require a scheduled task.
cd /d "%~dp0..\.."
if errorlevel 1 goto :failed
if not exist "runtime\python.exe" (
    echo [ERROR] runtime\python.exe not found. Run htfa.bat first.
    goto :failed
)

set "UPDATE_EXIT=0"
echo [1/2] update all UAE sources and merge their workbook sheets
"runtime\python.exe" -B -m htfa.jobs.uae_data.update_data
if errorlevel 1 set "UPDATE_EXIT=1"
goto :cleanup

:failed
set "UPDATE_EXIT=1"

:cleanup
echo [2/2] remove temporary files and caches
powershell -NoProfile -ExecutionPolicy Bypass -File "tooling\scripts\clean_temps.ps1"
if errorlevel 1 (
    echo [WARN] temporary-file cleanup failed.
    set "UPDATE_EXIT=1"
)

if "%UPDATE_EXIT%"=="0" (
    echo [OK] auto update finished.
    exit /b 0
)
echo [ERROR] auto update finished with failures.
exit /b 1
