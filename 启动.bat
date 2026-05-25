@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo 启动序时账审计分析平台...
echo 项目目录：%~dp0
echo.

:: 检查 uv 是否可用
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo 未检测到 uv，请先安装后再启动。
    echo 安装说明：https://docs.astral.sh/uv/getting-started/installation/
    echo.
    pause
    exit /b 1
)

:: 默认端口
if "%STREAMLIT_PORT%"=="" set STREAMLIT_PORT=8505

:: 检查端口是否被占用
netstat -ano 2>nul | findstr ":%STREAMLIT_PORT% " >nul
if !errorlevel! equ 0 (
    echo 端口 %STREAMLIT_PORT% 已被占用，可能服务已在运行。
    echo 访问地址：http://127.0.0.1:%STREAMLIT_PORT%
    echo.
    pause
    exit /b 0
)

echo 正在同步依赖...

set SYNC_OK=0

:: 第一次尝试：正常同步
uv sync --quiet 2>%TEMP%\uv-sync-err.log
if !errorlevel! equ 0 (
    set SYNC_OK=1
) else (
    :: 检查是否为缓存权限错误
    findstr /C:"Operation not permitted" /C:"Permission denied" "%TEMP%\uv-sync-err.log" >nul 2>&1
    if !errorlevel! equ 0 (
        echo 检测到 uv 缓存权限问题，尝试清除缓存后重试...
        rd /s /q "%USERPROFILE%\.cache\uv\sdists-v*" 2>nul
        rd /s /q "%USERPROFILE%\.cache\uv\archive-v*" 2>nul
        uv sync --quiet 2>%TEMP%\uv-sync-err.log
        if !errorlevel! equ 0 set SYNC_OK=1
    )
)

:: 如果仍失败，尝试 --no-cache
if !SYNC_OK! equ 0 (
    echo 尝试无缓存模式同步...
    uv sync --no-cache --quiet 2>%TEMP%\uv-sync-err.log
    if !errorlevel! equ 0 set SYNC_OK=1
)

if !SYNC_OK! equ 0 (
    echo.
    echo 依赖同步失败。错误信息：
    type "%TEMP%\uv-sync-err.log" 2>nul
    echo.
    echo 手动修复建议：
    echo   1. 删除 %%USERPROFILE%%\.cache\uv\ 清除 uv 缓存后重试
    echo   2. 运行 uv sync --no-cache 跳过缓存直接安装
    echo   3. 确认本机 Python 版本 ^>= 3.11
    echo.
    pause
    exit /b 1
)

echo 浏览器访问地址：http://127.0.0.1:%STREAMLIT_PORT%
echo 按 Ctrl+C 停止服务
echo.

uv run streamlit run app.py --server.address 127.0.0.1 --server.port %STREAMLIT_PORT%

:: 清理临时文件
del "%TEMP%\uv-sync-err.log" 2>nul

echo.
echo 服务已退出。
pause
