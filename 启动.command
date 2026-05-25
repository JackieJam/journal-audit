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

echo "正在同步依赖..."
uv sync --quiet

echo "浏览器访问地址：http://127.0.0.1:${PORT}"
echo "按 Ctrl+C 停止服务"
echo

set +e
uv run streamlit run app.py \
  --server.address 127.0.0.1 \
  --server.port "$PORT"
status=$?
set -e

if [[ "$status" -ne 0 ]]; then
  echo
  echo "服务启动失败，退出码：$status"
  echo "请把上面的错误信息发给 Claude 继续排查。"
  echo
  read -r -p "按回车关闭窗口..."
  exit "$status"
fi

echo
echo "服务已退出。"
read -r -p "按回车关闭窗口..."
