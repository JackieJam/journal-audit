#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "正在停止序时账审计分析平台..."
echo

START=8505
END=8520
FOUND=0

for port in $(seq $START $END); do
  PIDS=$(lsof -Pi ":$port" -sTCP:LISTEN -t 2>/dev/null || true)
  if [ -n "$PIDS" ]; then
    for pid in $PIDS; do
      echo "端口 $port — 终止进程 PID: $pid"
      kill "$pid" 2>/dev/null || true
    done
    FOUND=1
  fi
done

if [ "$FOUND" -eq 0 ]; then
  echo "没有找到运行中的服务（端口 $START ~ $END）"
fi

sleep 1

# 二次确认，残留进程强制终止
REMAIN=0
for port in $(seq $START $END); do
  PIDS=$(lsof -Pi ":$port" -sTCP:LISTEN -t 2>/dev/null || true)
  if [ -n "$PIDS" ]; then
    for pid in $PIDS; do
      echo "强制终止残留进程 PID: $pid"
      kill -9 "$pid" 2>/dev/null || true
    done
    REMAIN=1
  fi
done

if [ "$REMAIN" -eq 0 ]; then
  echo
  echo "服务已停止。"
else
  echo
  echo "警告：部分进程可能未完全停止，请手动检查。"
fi

read -r -p "按回车关闭窗口..."