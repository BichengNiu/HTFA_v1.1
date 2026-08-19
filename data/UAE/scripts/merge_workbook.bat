@echo off
rem Merge DuckDB data into data\阿联酋.xlsx sheets.
rem Close the workbook in Excel before running.
rem Usage: merge_workbook.bat [--source cbuae,gfs]
cd /d "%~dp0..\..\.."
if errorlevel 1 goto :failed
if not exist "runtime\python.exe" (
    echo [ERROR] Bundled runtime\python.exe was not found.
    echo [HINT] Run scripts\windows\setup_runtime.bat first.
    goto :failed
)
"runtime\python.exe" -u "data\UAE\scripts\merge_workbook.py" %*
if errorlevel 1 (
    echo.
    echo [ERROR] At least one source failed to merge. Review the messages above.
    pause
    exit /b 1
)
echo.
echo [OK] Workbook data\阿联酋.xlsx updated.
pause
exit /b 0

:failed
echo [ERROR] merge_workbook.bat aborted.
pause
exit /b 1
