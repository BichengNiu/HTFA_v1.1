@echo off
setlocal

echo ========================================
echo HTFA Dashboard Startup
echo ========================================
echo.

cd /d "%~dp0"
if errorlevel 1 (
    echo [ERROR] Cannot open the project directory.
    goto :failed
)

echo [1/5] Checking the project virtual environment...
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Project virtual environment .venv was not found.
    echo [HINT] Run: py -3.14 -m venv .venv
    echo [HINT] Then run: .venv\Scripts\python.exe -m pip install -r requirements.txt
    goto :failed
)

for /f "delims=" %%V in ('".venv\Scripts\python.exe" --version 2^>^&1') do set "HTFA_PYTHON_VERSION=%%V"
echo [OK] Using %HTFA_PYTHON_VERSION%

".venv\Scripts\python.exe" -c "from pathlib import Path; import sysconfig, Ts; module_file = getattr(Ts, '__file__', None); raise SystemExit(0 if module_file and Path(module_file).resolve().is_relative_to(Path(sysconfig.get_path('purelib')).resolve()) else 1)" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing Ts into the project virtual environment...
    ".venv\Scripts\python.exe" scripts\install_ts.py
    if errorlevel 1 (
        echo [ERROR] Ts installation failed.
        goto :failed
    )
)
echo [OK] Ts is installed in the project virtual environment.
echo.

set "HTFA_LAUNCHER_ACTIVE=true"

echo [2/5] Clearing Python caches...
call :clean_python_cache dashboard
call :clean_python_cache scripts
call :clean_python_cache Ts
call :clean_python_cache tests
if exist "__pycache__" rd /s /q "__pycache__" >nul 2>&1
echo [OK] Python caches cleared.
echo.

echo [3/5] Checking port 8501...
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\free_port.ps1 -Port 8501 -WaitSeconds 15
if errorlevel 1 goto :failed
echo.

echo [4/5] Configuring the runtime environment...
set "HTFA_DEBUG_MODE=true"
echo [INFO] Debug mode: %HTFA_DEBUG_MODE%
echo.

echo [5/5] Starting HTFA...
echo.
".venv\Scripts\python.exe" scripts\run_htfa.py --server.port=8501 %*
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
