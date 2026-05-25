#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "正在停止序时账审计分析平台..."
echo

PORT="${STREAMLIT_PORT:-8505}"

# 查找并终止 streamlit 进程
PIDS=$(lsof -Pi ":$PORT" -sTCP:LISTEN -t 2>/dev/null || true)

if [ -z "$PIDS" ]; then
  echo "没有找到运行中的服务（端口 $PORT）"
  read -r -p "按回车关闭窗口..."
  exit 0
fi

for PID in $PIDS; do
  echo "终止进程 PID: $PID"
  kill "$PID" 2>/dev/null || true
done

# 等待进程退出
sleep 1

# 验证是否已停止
if lsof -Pi ":$PORT" -sTCP:LISTEN -t >/dev/null 2>&1; then
  echo "警告：进程可能未完全停止，尝试强制终止..."
  for PID in $PIDS; do
    kill -9 "$PID" 2>/dev/null || true
  done
fi

echo
echo "服务已停止。"
read -r -p "按回车关闭窗口..."
