@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo 启动序时账审计分析平台...
echo 项目目录：%~dp0
echo.

:: ── 检查 uv 是否可用，若未安装则提示自动安装 ──
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo 未检测到 uv 包管理器。
    echo.
    echo uv 是 Python 包管理器，用于安装本项目的依赖。
    echo 安装说明：https://docs.astral.sh/uv/getting-started/installation/
    echo.
    choice /C YN /M "是否自动安装 uv（需要管理员权限）"
    if !errorlevel! equ 2 (
        echo 已取消安装。请手动安装 uv 后重新启动本脚本。
        pause
        exit /b 1
    )
    echo 正在安装 uv...
    powershell -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    if !errorlevel! neq 0 (
        echo uv 安装失败，请手动安装。
        echo 安装说明：https://docs.astral.sh/uv/getting-started/installation/
        pause
        exit /b 1
    )
    :: 刷新 PATH
    call :refresh_env
    where uv >nul 2>&1
    if !errorlevel! neq 0 (
        echo uv 已安装但未加入 PATH。请重新打开命令窗口后重试。
        pause
        exit /b 1
    )
    echo uv 安装成功。
    echo.
)

:: ── 自动寻找可用端口（从 8505 开始，最多尝试到 8520）──
set PORT=8505
if not "%STREAMLIT_PORT%"=="" set PORT=%STREAMLIT_PORT%
set _ORIGINAL_PORT=%PORT%

:find_port
netstat -ano 2>nul | findstr ":%PORT% " >nul
if !errorlevel! neq 0 goto port_found
if !PORT! geq 8520 goto no_port
set /a PORT+=1
goto find_port

:no_port
echo 端口 %_ORIGINAL_PORT% ~ 8520 全部被占用，请释放端口后重试。
pause
exit /b 1

:port_found
if not "%_ORIGINAL_PORT%"=="%PORT%" (
    echo 端口 %_ORIGINAL_PORT% 已被占用，自动切换到 %PORT%
    echo.
)
set STREAMLIT_PORT=%PORT%

:: ── 同步依赖（显示进度，不用 --quiet）──
echo 正在同步依赖（首次运行需下载，可能需要几分钟）...

set SYNC_OK=0

:: 第一次尝试：正常同步，显示进度
uv sync --link-mode=copy
if !errorlevel! equ 0 (
    set SYNC_OK=1
) else (
    echo.
    echo 同步失败，尝试清除缓存后重试...
    rd /s /q "%USERPROFILE%\.cache\uv\sdists-v*" 2>nul
    rd /s /q "%USERPROFILE%\.cache\uv\archive-v*" 2>nul
    uv sync --link-mode=copy
    if !errorlevel! equ 0 set SYNC_OK=1
)

:: 如果仍失败，尝试 --no-cache
if !SYNC_OK! equ 0 (
    echo.
    echo 尝试无缓存模式同步（将重新下载所有包）...
    uv sync --link-mode=copy --no-cache
    if !errorlevel! equ 0 set SYNC_OK=1
)

if !SYNC_OK! equ 0 (
    echo.
    echo ============================================================
    echo 依赖同步失败。
    echo.
    echo 手动修复建议：
    echo   1. 删除 %%USERPROFILE%%\.cache\uv\ 清除 uv 缓存后重试
    echo   2. 运行 uv sync --no-cache 跳过缓存直接安装
    echo   3. 确认本机 Python 版本 ^>= 3.11
    echo   4. 检查网络连接是否正常（需要访问 PyPI）
    echo ============================================================
    echo.
    pause
    exit /b 1
)

echo.
echo 依赖就绪。
echo.
echo 浏览器访问地址：http://127.0.0.1:!PORT!
echo 按 Ctrl+C 停止服务
echo.

uv run streamlit run app.py --server.address 127.0.0.1 --server.port !PORT! --server.headless true

echo.
echo 服务已退出。
pause
exit /b 0

:: ── 刷新环境变量 ──
:refresh_env
for /f "tokens=2*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v PATH 2^>nul') do set "SysPath=%%b"
for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v PATH 2^>nul') do set "UserPath=%%b"
set "PATH=%SysPath%;%UserPath%;%PATH%"
goto :eof
