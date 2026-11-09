#!/usr/bin/env bash
# 在服务器上执行（由流水线「主机部署」调用）：
#   bash deploy.sh /home/ubuntu/servers/underleaf/underleaf-package.tgz
#
# 目录结构：
#   /home/ubuntu/servers/underleaf/
#   ├── releases/<时间>/   每次部署解压出的版本，保留最近 5 个
#   ├── current -> releases/<时间>   当前运行的版本（Nginx 和后端都从这里读）
#   └── shared/            跨版本共享：.env、venv、日志、pid
#
# 流程：解压 → 链接共享配置 → 安装依赖 → 数据库迁移 → 切换 current → 重启 → 健康检查
# 健康检查失败时自动切回上一个版本。
set -euo pipefail

PACKAGE="${1:?用法: deploy.sh <制品 tgz 路径>}"
BASE="${UNDERLEAF_BASE:-/home/ubuntu/servers/underleaf}"
SHARED="$BASE/shared"
KEEP=5

export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"

log() { echo "[deploy] $*"; }

[ -f "$SHARED/.env" ] || { log "缺少 $SHARED/.env，请先按 docs/pipeline.md 完成服务器准备"; exit 1; }
[ -x "$SHARED/venv/bin/python" ] || { log "缺少虚拟环境 $SHARED/venv，请先按 docs/pipeline.md 完成服务器准备"; exit 1; }

# ---------- 1. 解压到新版本目录 ----------
RELEASE="$BASE/releases/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$RELEASE"
tar xzf "$PACKAGE" -C "$RELEASE"
# 兼容制品中带 release/ 这一层目录的情况
if [ -d "$RELEASE/release" ]; then
  shopt -s dotglob
  mv "$RELEASE/release"/* "$RELEASE/"
  rmdir "$RELEASE/release"
fi
rm -f "$PACKAGE"
log "解压到 ${RELEASE}（$(cat "$RELEASE/VERSION" 2>/dev/null | tr '\n' ' ')）"

# ---------- 2. 链接共享配置和虚拟环境 ----------
ln -sfn "$SHARED/.env" "$RELEASE/backend/.env"
echo "$SHARED/venv/bin/python" > "$RELEASE/backend/.pdm-python"

# ---------- 3. 安装依赖 / 数据库迁移（失败则中止，线上旧版本不受影响） ----------
cd "$RELEASE/backend"
log "安装依赖"
pdm sync --prod --no-self --clean
log "数据库迁移"
pdm run alembic upgrade head

# ---------- 4. 切换版本并重启 ----------
PREVIOUS="$(readlink "$BASE/current" 2>/dev/null || true)"
switch_to() {
  ln -sfn "$1" "$BASE/current.tmp"
  mv -T "$BASE/current.tmp" "$BASE/current"   # 原子替换软链接
}
switch_to "$RELEASE"
bash "$BASE/current/deploy/restart.sh" restart

# ---------- 5. 健康检查，失败自动回滚 ----------
PORT="$(grep -E '^PORT=' "$SHARED/.env" | cut -d= -f2 | tr -d ' "\r' || true)"
PORT="${PORT:-8100}"
wait_healthy() {
  for _ in $(seq 1 30); do
    curl -fsS "http://127.0.0.1:$PORT/api/v1/health" >/dev/null 2>&1 && return 0
    sleep 2
  done
  return 1
}

if wait_healthy; then
  log "健康检查通过，部署完成：${RELEASE}"
  # 只保留最近 $KEEP 个版本
  ls -1dt "$BASE"/releases/*/ | tail -n +$((KEEP + 1)) | xargs -r rm -rf
  exit 0
fi

log "健康检查失败，最近日志："
tail -n 50 "$SHARED/logs/underleaf.log" || true
if [ -n "$PREVIOUS" ] && [ -d "$PREVIOUS" ]; then
  log "回滚到 ${PREVIOUS}"
  switch_to "$PREVIOUS"
  bash "$BASE/current/deploy/restart.sh" restart
  if wait_healthy; then log "回滚成功，线上仍为旧版本"; else log "回滚后仍无法启动，请登录服务器排查"; fi
else
  log "没有可回滚的旧版本"
fi
exit 1
