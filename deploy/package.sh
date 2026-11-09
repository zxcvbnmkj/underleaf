#!/usr/bin/env bash
# 在流水线构建机上执行：把部署需要的文件收集到 release/ 目录，由「构建物上传」打包上传。
# 前置条件：已执行 pnpm build，frontend/dist 已生成。
#
# release/
# ├── backend/        后端代码和运维脚本 scripts/（不含 tests、.venv、.env）
# ├── frontend/dist/  前端打包产物，由 Nginx 直接托管
# └── deploy/         deploy.sh、restart.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/release"

[ -f "$ROOT/frontend/dist/index.html" ] || { echo "frontend/dist 不存在，请先执行 pnpm build"; exit 1; }

rm -rf "$OUT"
mkdir -p "$OUT/backend" "$OUT/frontend"

cp -r "$ROOT/frontend/dist" "$OUT/frontend/dist"
cp -r "$ROOT/backend/app" "$ROOT/backend/migrations" "$ROOT/backend/scripts" "$OUT/backend/"
cp "$ROOT/backend/alembic.ini" "$ROOT/backend/pyproject.toml" "$ROOT/backend/pdm.lock" \
   "$ROOT/backend/pdm.toml" "$OUT/backend/"
cp -r "$ROOT/deploy" "$OUT/deploy"
rm -f "$OUT/deploy/package.sh"

# 记录版本信息，部署后可以在服务器上查看当前运行的是哪次提交
{
  echo "commit=${CI_COMMIT_ID:-$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || echo unknown)}"
  echo "built_at=$(date '+%Y-%m-%d %H:%M:%S')"
} > "$OUT/VERSION"

find "$OUT" -name '__pycache__' -type d -prune -exec rm -rf {} +
echo "打包完成：$(du -sh "$OUT" | cut -f1)"
