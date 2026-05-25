#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "启动序时账审计分析平台..."
echo "项目目录：$ROOT"
echo

# ── 检查 uv 是否可用，若未安装则尝试自动安装 ──
if ! command -v uv >/dev/null 2>&1; then
  echo "未检测到 uv 包管理器。"
  echo
  echo "uv 是 Python 包管理器，用于安装本项目的依赖。"
  echo "安装说明：https://docs.astral.sh/uv/getting-started/installation/"
  echo
  read -r -p "是否自动安装 uv？[Y/n] " answer
  answer="${answer:-Y}"
  if [[ ! "$answer" =~ ^[Yy] ]]; then
    echo "已取消。请手动安装 uv 后重新启动本脚本。"
    read -r -p "按回车关闭窗口..."
    exit 1
  fi

  echo "正在安装 uv..."
  install_ok=false

  # 优先尝试 Homebrew（macOS 最常见）
  if command -v brew >/dev/null 2>&1; then
    echo "检测到 Homebrew，使用 brew install uv..."
    if brew install uv 2>/dev/null; then
      install_ok=true
    else
      echo "Homebrew 安装失败，尝试官方安装脚本..."
    fi
  fi

  # 官方安装脚本
  if ! $install_ok; then
    if curl -LsSf https://astral.sh/uv/install.sh 2>/dev/null | sh; then
      install_ok=true
    fi
  fi

  if ! $install_ok; then
    echo "uv 安装失败，请手动安装。"
    echo "安装说明：https://docs.astral.sh/uv/getting-started/installation/"
    read -r -p "按回车关闭窗口..."
    exit 1
  fi

  # 刷新 shell 环境（安装脚本通常会修改 ~/.bashrc / ~/.zshrc，当前 shell 可能还没加载）
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  if ! command -v uv >/dev/null 2>&1; then
    echo "uv 已安装但未在当前终端生效。请关闭此窗口，重新打开终端后再试。"
    read -r -p "按回车关闭窗口..."
    exit 1
  fi

  echo "uv 安装成功。"
  echo
fi

# ── 自动寻找可用端口（从 8505 开始，最多尝试到 8520）──
PORT="${STREAMLIT_PORT:-8505}"
ORIGINAL_PORT="$PORT"

find_free_port() {
  local p=$1
  local max=8520
  while [ "$p" -le "$max" ]; do
    if ! lsof -Pi ":$p" -sTCP:LISTEN -t >/dev/null 2>&1; then
      echo "$p"
      return 0
    fi
    p=$((p + 1))
  done
  return 1
}

FREE_PORT=$(find_free_port "$PORT")
if [ -z "$FREE_PORT" ]; then
  echo "端口 $ORIGINAL_PORT ~ 8520 全部被占用，请释放端口后重试。"
  read -r -p "按回车关闭窗口..."
  exit 1
fi

if [ "$FREE_PORT" -ne "$ORIGINAL_PORT" ]; then
  echo "端口 $ORIGINAL_PORT 已被占用，自动切换到 $FREE_PORT"
  echo
fi
PORT="$FREE_PORT"

# 同步依赖（显示进度，不用 --quiet）
echo "正在同步依赖（首次运行需下载，可能需要几分钟）..."

sync_ok=false

# 第一次尝试：正常同步，显示进度
if uv sync --link-mode=copy; then
  sync_ok=true
else
  echo
  echo "同步失败，尝试清除缓存后重试..."
  rm -rf ~/.cache/uv/sdists-v* 2>/dev/null || true
  rm -rf ~/.cache/uv/archive-v* 2>/dev/null || true
  if uv sync --link-mode=copy; then
    sync_ok=true
  fi
fi

# 如果仍失败，尝试 --no-cache
if ! $sync_ok; then
  echo
  echo "尝试无缓存模式同步（将重新下载所有包）..."
  if uv sync --link-mode=copy --no-cache; then
    sync_ok=true
  fi
fi

if ! $sync_ok; then
  echo
  echo "依赖同步失败。"
  echo
  echo "手动修复建议："
  echo "  1. 运行 rm -rf ~/.cache/uv/ 清除 uv 缓存后重试"
  echo "  2. 运行 uv sync --no-cache 跳过缓存直接安装"
  echo "  3. 确认本机 Python 版本 >= 3.11（当前：$(python3 --version 2>/dev/null || echo '未检测到')）"
  echo "  4. 检查网络连接是否正常（需要访问 PyPI）"
  echo
  read -r -p "按回车关闭窗口..."
  exit 1
fi

echo "浏览器访问地址：http://127.0.0.1:${PORT}"
echo "按 Ctrl+C 停止服务"
echo

set +e
uv run streamlit run app.py \
  --server.address 127.0.0.1 \
  --server.port "$PORT" \
  --server.headless true
status=$?
set -e

if [[ "$status" -ne 0 ]]; then
  echo
  echo "服务启动失败，退出码：$status"
  echo "请把上面的错误信息检查后重试。"
  echo
  read -r -p "按回车关闭窗口..."
  exit "$status"
fi

echo
echo "服务已退出。"
read -r -p "按回车关闭窗口..."
