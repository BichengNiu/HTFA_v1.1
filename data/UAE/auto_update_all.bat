@echo off
rem 自动运行：更新 DuckDB + 合并回 阿联酋.xlsx（供“任务计划程序”定时调用，详见 数据说明.md 第 6 节）
rem 用法: 直接把本 .bat 填进“任务计划程序”的“程序或脚本”即可（幂等，可重复运行）。
cd /d "%~dp0..\.."
if errorlevel 1 goto :failed
if not exist "runtime\python.exe" (
    echo [ERROR] runtime\python.exe not found. Run scripts\start.bat first.
    goto :failed
)

echo [1/2] update_data.py --skip-download
"runtime\python.exe" -B -c "import sys; sys.path.insert(0, r'%CD%'); from htfa.jobs.uae_data.update_data import main; sys.argv[0] = 'update_data.py'; raise SystemExit(main())" --skip-download
if errorlevel 1 goto :failed

echo [prep] close hidden Excel automation only
"runtime\python.exe" -B -c "import sys; sys.path.insert(0, r'%CD%'); from htfa.jobs.uae_data._excel_helpers import cleanup_excel_automation; cleanup_excel_automation()"
if errorlevel 1 goto :failed

echo [2/2] merge_workbook.py
"runtime\python.exe" -B -c "import sys; sys.path.insert(0, r'%CD%'); from htfa.jobs.uae_data.merge_workbook import main; sys.argv[0] = 'merge_workbook.py'; raise SystemExit(main())"
if errorlevel 1 goto :failed

:success
set "UPDATE_EXIT=0"
goto :cleanup

:failed
set "UPDATE_EXIT=1"

:cleanup
echo [cleanup] remove temporary files and caches
powershell -NoProfile -ExecutionPolicy Bypass -File "tooling\scripts\clean_temps.ps1"
if errorlevel 1 (
    echo [WARN] temporary-file cleanup failed.
    set "UPDATE_EXIT=1"
)

if "%UPDATE_EXIT%"=="0" (
    echo [OK] auto update finished.
    exit /b 0
)
echo [ERROR] auto update aborted.
exit /b 1
