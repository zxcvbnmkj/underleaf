#!/usr/bin/env bash
# 本地开发连接服务器上的 MySQL 和 Redis：通过 SSH 隧道转发到本机，服务器端口不对外开放。
#   bash scripts/tunnel.sh         建立隧道（后台运行，已建立时跳过）
#   bash scripts/tunnel.sh stop    关闭隧道
# 之后 .env 中用 127.0.0.1:3306 / 127.0.0.1:6379 访问。
set -euo pipefail

SERVER="${UNDERLEAF_SERVER:-ubuntu@124.223.10.25}"
FORWARDS=(-L 3306:127.0.0.1:3306 -L 6379:127.0.0.1:6379)
PATTERN="ssh .*-L 3306:127.0.0.1:3306 .*${SERVER}"

if [ "${1:-}" = "stop" ]; then
  pkill -f "$PATTERN" && echo "隧道已关闭" || echo "隧道未运行"
  exit 0
fi

if pgrep -f "$PATTERN" >/dev/null; then
  echo "隧道已在运行"
  exit 0
fi

ssh -f -N \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  "${FORWARDS[@]}" "$SERVER"
echo "隧道已建立：MySQL → 127.0.0.1:3306，Redis → 127.0.0.1:6379"
