@echo off
chcp 65001 >nul
echo ========================================
echo HTFA Dashboard Startup
echo ========================================
echo.

cd /d "%~dp0"

REM 清理Python缓存文件
echo [1/4] 清理Python缓存文件...
echo [信息] 正在删除 __pycache__ 目录和 .pyc 文件...

REM 删除所有的 .pyc 和 .pyo 文件
for /r %%i in (*.pyc *.pyo) do (
    del /f /q "%%i" >nul 2>&1
)

REM 删除所有的 __pycache__ 目录
for /d /r %%i in (__pycache__) do (
    rd /s /q "%%i" >nul 2>&1
)

echo [完成] Python缓存已清理
echo.

REM 检查端口8501是否被占用
echo [2/4] 检查端口占用情况...
netstat -ano | findstr ":8501" >nul 2>&1
if %errorlevel% equ 0 (
    echo [警告] 端口8501已被占用，正在关闭占用进程...

    REM 获取占用端口的进程ID并关闭
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8501" ^| findstr "LISTENING"') do (
        echo [信息] 正在关闭进程 PID: %%a
        taskkill /F /PID %%a >nul 2>&1
    )

    REM 等待端口释放
    echo [信息] 等待端口释放...
    timeout /t 2 /nobreak >nul
    echo [完成] 端口已清理
) else (
    echo [完成] 端口8501空闲
)

echo.
echo [3/4] 配置运行环境...
REM ========================================
REM 调试模式配置
REM ========================================
REM 调试模式：跳过用户认证和权限检查（适用于开发调试）
REM 正常模式：启用完整的用户认证和权限控制（适用于生产环境）
REM
REM 设置 HTFA_DEBUG_MODE=true  -> 调试模式（默认）
REM 设置 HTFA_DEBUG_MODE=false -> 正常模式
REM ========================================

REM 设置调试模式（开发时使用true，生产时使用false）
set HTFA_DEBUG_MODE=true

echo [信息] 调试模式: %HTFA_DEBUG_MODE%
echo.
echo [4/5] 启动应用程序...
echo.
REM 自动输入空邮箱(直接回车)跳过邮箱提示
echo. | py -m streamlit run dashboard/app.py --server.port=8501

echo.
echo [5/5] 应用程序已退出
pause
