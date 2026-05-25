#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "启动序时账审计分析平台..."
echo "项目目录：$ROOT"
echo

# 检查 uv 是否可用
if ! command -v uv >/dev/null 2>&1; then
  echo "未检测到 uv，请先安装后再启动。"
  echo "安装说明：https://docs.astral.sh/uv/getting-started/installation/"
  read -r -p "按回车关闭窗口..."
  exit 1
fi

PORT="${STREAMLIT_PORT:-8505}"

# 检查端口是否被占用
if lsof -Pi ":$PORT" -sTCP:LISTEN -t >/dev/null 2>&1; then
  echo "端口 $PORT 已被占用，可能服务已在运行。"
  echo "访问地址：http://127.0.0.1:${PORT}"
  read -r -p "按回车关闭窗口..."
  exit 0
fi

# 同步依赖（带缓存降级处理）
echo "正在同步依赖..."

sync_ok=false

# 第一次尝试：正常同步
if uv sync --quiet 2>/tmp/uv-sync-err.log; then
  sync_ok=true
else
  err_msg=$(cat /tmp/uv-sync-err.log 2>/dev/null || true)
  # 如果遇到缓存权限或 .git 相关错误，清除缓存后重试
  if echo "$err_msg" | grep -qE "Operation not permitted|Permission denied|sdists-v[0-9]+/.git"; then
    echo "检测到 uv 缓存权限问题，尝试清除缓存后重试..."
    rm -rf ~/.cache/uv/sdists-v* 2>/dev/null || true
    rm -rf ~/.cache/uv/archive-v* 2>/dev/null || true
    if uv sync --quiet 2>/tmp/uv-sync-err.log; then
      sync_ok=true
    fi
  fi
fi

# 如果仍失败，尝试 --no-cache
if ! $sync_ok; then
  echo "尝试无缓存模式同步..."
  if uv sync --no-cache --quiet 2>/tmp/uv-sync-err.log; then
    sync_ok=true
  fi
fi

if ! $sync_ok; then
  echo
  echo "依赖同步失败。错误信息："
  cat /tmp/uv-sync-err.log 2>/dev/null || true
  echo
  echo "手动修复建议："
  echo "  1. 运行 rm -rf ~/.cache/uv/ 清除 uv 缓存后重试"
  echo "  2. 运行 uv sync --no-cache 跳过缓存直接安装"
  echo "  3. 确认本机 Python 版本 >= 3.11（当前：$(python3 --version 2>/dev/null || echo '未检测到')）"
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
  --server.port "$PORT"
status=$?
set -e

# 清理临时文件
rm -f /tmp/uv-sync-err.log

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
