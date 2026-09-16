@echo off
rem Manual online refresh: update DuckDB, then merge into the workbook.
rem Run this batch manually from the project; no scheduled task is created or required.
cd /d "%~dp0..\.."
if errorlevel 1 goto :failed
if not exist "runtime\python.exe" (
    echo [ERROR] runtime\python.exe not found. Run htfa.bat first.
    goto :failed
)

echo [1/5] update_data.py --source baker_hughes,oil,cbuae,gfs,dubai_customs_air,comtrade_vehicles,scad,uaewps,salik,dot_t100 (official online refresh)
"runtime\python.exe" -B -c "import sys; sys.path.insert(0, r'%CD%'); from htfa.jobs.uae_data.update_data import main; sys.argv[0] = 'update_data.py'; raise SystemExit(main())" --source baker_hughes,oil,cbuae,gfs,dubai_customs_air,comtrade_vehicles,scad,uaewps,salik,dot_t100
if errorlevel 1 goto :failed

echo [2/5] update_data.py --source cloudflare_radar,comtrade,ded,dld,emirates_post,employment,eurostat_air,foreign_labour,pmi,portwatch,rta,steel,tdra (official online refresh)
"runtime\python.exe" -B -c "import sys; sys.path.insert(0, r'%CD%'); from htfa.jobs.uae_data.update_data import main; sys.argv[0] = 'update_data.py'; raise SystemExit(main())" --source cloudflare_radar,comtrade,ded,dld,emirates_post,employment,eurostat_air,foreign_labour,pmi,portwatch,rta,steel,tdra
if errorlevel 1 goto :failed

echo [3/5] update_data.py --source wam (discover and extract official WAM articles)
"runtime\python.exe" -B -c "import sys; sys.path.insert(0, r'%CD%'); from htfa.jobs.uae_data.update_data import main; sys.argv[0] = 'update_data.py'; raise SystemExit(main())" --source wam
if errorlevel 1 goto :failed

echo [prep] close hidden Excel automation only
"runtime\python.exe" -B -c "import sys; sys.path.insert(0, r'%CD%'); from htfa.jobs.uae_data._excel_helpers import cleanup_excel_automation; cleanup_excel_automation()"
if errorlevel 1 goto :failed

echo [4/5] merge_workbook.py
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
