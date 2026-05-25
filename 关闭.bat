@echo off
chcp 65001 >nul
setlocal

echo 正在停止序时账审计分析平台...
echo.

if "%STREAMLIT_PORT%"=="" set STREAMLIT_PORT=8505

:: 查找监听端口的进程 PID
set PID=
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%STREAMLIT_PORT% " 2^>nul') do (
    if "!PID!"=="" set PID=%%a
)

if "%PID%"=="" (
    echo 没有找到运行中的服务（端口 %STREAMLIT_PORT%）
    pause
    exit /b 0
)

echo 终止进程 PID: %PID%
taskkill /PID %PID% /F >nul 2>&1

timeout /t 2 /nobreak >nul

:: 验证是否已停止
netstat -ano 2>nul | findstr ":%STREAMLIT_PORT% " >nul
if !errorlevel! equ 0 (
    echo 警告：进程可能未完全停止。
) else (
    echo 服务已停止。
)

echo.
pause
exit /b 0
