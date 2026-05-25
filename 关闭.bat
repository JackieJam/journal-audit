@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo 正在停止序时账审计分析平台...
echo.

set FOUND=0

:: 遍历 8505 ~ 8520，逐个检查并终止
for /l %%P in (8505,1,8520) do (
    set PID=
    for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":%%P "') do (
        if "!PID!"=="" set PID=%%a
    )
    if not "!PID!"=="" (
        echo 端口 %%P — 终止进程 PID: !PID!
        taskkill /PID !PID! /F >nul 2>&1
        set FOUND=1
    )
)

if !FOUND! equ 0 (
    echo 没有找到运行中的服务（端口 8505 ~ 8520）
)

timeout /t 2 /nobreak >nul

:: 二次确认
set REMAIN=0
for /l %%P in (8505,1,8520) do (
    netstat -ano 2>nul | findstr ":%%P " >nul && set REMAIN=1
)

if !REMAIN! equ 0 (
    echo 服务已停止。
) else (
    echo 警告：部分进程可能未完全停止，请手动检查。
)

echo.
pause
exit /b 0