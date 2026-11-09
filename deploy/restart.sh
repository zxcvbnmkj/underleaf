#!/usr/bin/env bash
# 后端进程管理（参考 taskNote 的 restart.sh，去掉了多环境）：
#   bash restart.sh {start|stop|restart|status|logs}
#
# 端口、worker 数从 shared/.env 中的 PORT、WORKERS 读取，默认 8100、2。
# 只监听 127.0.0.1，由 Nginx 对外提供服务。
set -euo pipefail

APP_NAME="underleaf"
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"          # 版本目录（通常经由 current 软链接）
BASE="${UNDERLEAF_BASE:-/home/ubuntu/servers/underleaf}"
SHARED="$BASE/shared"
ENV_FILE="$SHARED/.env"

read_env() { grep -E "^$1=" "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2 | tr -d ' "\r' || true; }
PORT="$(read_env PORT)"; PORT="${PORT:-8100}"
WORKERS="$(read_env WORKERS)"; WORKERS="${WORKERS:-2}"

PID_FILE="$SHARED/$APP_NAME.pid"
LOG_DIR="$SHARED/logs"
LOG_FILE="$LOG_DIR/$APP_NAME.log"
mkdir -p "$LOG_DIR"

get_pid() {
  if [ -f "$PID_FILE" ]; then
    local pid
    pid="$(cat "$PID_FILE")"
    if kill -0 "$pid" 2>/dev/null; then echo "$pid"; return; fi
    rm -f "$PID_FILE"
  fi
  # pid 文件丢失时，按命令行查找
  pgrep -f "uvicorn app.main:app --host 127.0.0.1 --port $PORT" | head -1 || true
}

stop_service() {
  local pid
  pid="$(get_pid)"
  if [ -z "$pid" ]; then echo "[$APP_NAME] 未在运行"; return; fi
  echo "[$APP_NAME] 停止 (PID: $pid)..."
  kill "$pid" 2>/dev/null || true
  for _ in $(seq 1 15); do
    kill -0 "$pid" 2>/dev/null || { rm -f "$PID_FILE"; echo "[$APP_NAME] 已停止"; return; }
    sleep 1
  done
  echo "[$APP_NAME] 超时，强制结束"
  pkill -9 -f "uvicorn app.main:app --host 127.0.0.1 --port $PORT" || true
  rm -f "$PID_FILE"
}

start_service() {
  if [ -n "$(get_pid)" ]; then echo "[$APP_NAME] 已在运行 (PID: $(get_pid))"; return; fi
  cd "$APP_DIR/backend"
  # 直接用 venv 中的 uvicorn 启动，记录的 PID 就是 uvicorn 主进程，停止时会一并结束 worker
  nohup "$SHARED/venv/bin/uvicorn" app.main:app --host 127.0.0.1 --port "$PORT" \
    --workers "$WORKERS" --proxy-headers --forwarded-allow-ips 127.0.0.1 \
    >> "$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"
  echo "[$APP_NAME] 已启动 (PID: $!, 端口: $PORT, worker: $WORKERS, 日志: $LOG_FILE)"
}

case "${1:-restart}" in
  start) start_service ;;
  stop) stop_service ;;
  restart) stop_service; start_service ;;
  status)
    pid="$(get_pid)"
    if [ -n "$pid" ]; then echo "[$APP_NAME] 运行中 (PID: $pid, 端口: $PORT)"; else echo "[$APP_NAME] 未在运行"; fi
    cat "$APP_DIR/VERSION" 2>/dev/null || true
    ;;
  logs) tail -f "$LOG_FILE" ;;
  *) echo "用法: $0 {start|stop|restart|status|logs}"; exit 1 ;;
esac
