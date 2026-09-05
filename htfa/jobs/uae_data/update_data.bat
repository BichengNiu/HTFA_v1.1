@echo off
rem Fetch, clean and load all data sources into data\UAE\uae.duckdb.
rem Usage: update_data.bat [--source cbuae,gfs] [--skip-download] [--force]
cd /d "%~dp0..\..\.."
if errorlevel 1 goto :failed
if not exist "runtime\python.exe" (
    echo [ERROR] Bundled runtime\python.exe was not found.
    echo [HINT] Run scripts\start.bat first.
    goto :failed
)
"runtime\python.exe" -m htfa.jobs.uae_data.update_data %*
if errorlevel 1 (
    echo.
    echo [ERROR] At least one source failed. Review the messages above.
    pause
    exit /b 1
)
echo.
echo [OK] All requested sources updated in data\uae.duckdb.
pause
exit /b 0

:failed
echo [ERROR] update_data.bat aborted.
pause
exit /b 1
