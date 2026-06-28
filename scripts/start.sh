#!/usr/bin/env bash
# Crossroads Agent Café — Linux 生产启动脚本
# 对应 start.bat 的 6 步逻辑，去除 Windows/本地开发专属行为：
#   - 去掉 --reload / --reload-dir app（生产不热重载）
#   - 绑 0.0.0.0（非 127.0.0.1，允许外部访问；前置 nginx 时可改回 127.0.0.1）
#   - 去掉清华 pip 镜像（服务器按需自配 ~/.pip/pip.conf）
#   - 去掉自动开浏览器
# 单 worker：/ws/visualization 在线 presence 状态在进程内，多 worker 会割裂。
set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"

PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"
WORKERS="${WORKERS:-1}"

echo "============================================"
echo "  Crossroads Agent Café - Linux Launcher"
echo "============================================"
echo

# [1/5] Python runtime
if [ -x ".venv/bin/python" ]; then
  PYTHON_CMD="$PROJECT_DIR/.venv/bin/python"
  echo "[1/5] Using existing .venv"
else
  BASE_PYTHON="${PYTHON:-}"
  if [ -z "$BASE_PYTHON" ]; then
    for c in python3 python; do
      if command -v "$c" >/dev/null 2>&1; then BASE_PYTHON="$c"; break; fi
    done
  fi
  if [ -z "$BASE_PYTHON" ]; then
    echo "[ERROR] Python 3.10+ not found. Install python3 and re-run." >&2
    exit 1
  fi
  echo "[1/5] Creating .venv with $BASE_PYTHON ..."
  "$BASE_PYTHON" -m venv .venv
  PYTHON_CMD="$PROJECT_DIR/.venv/bin/python"
fi
echo

# [2/5] .env check
if [ ! -f ".env" ]; then
  echo "[ERROR] .env not found. Copy .env.example to .env and fill MYSQL_*/REDIS_*/LLM_*." >&2
  exit 1
fi
MISSING_ENV=""
for K in MYSQL_HOST MYSQL_PORT MYSQL_USER MYSQL_PASSWORD MYSQL_DATABASE REDIS_HOST REDIS_PORT; do
  if ! grep -qE "^[[:space:]]*$K[[:space:]]*=" .env; then
    MISSING_ENV="$MISSING_ENV $K"
  fi
done
if [ -n "$MISSING_ENV" ]; then
  echo "[ERROR] Missing required .env keys:$MISSING_ENV" >&2
  exit 1
fi
echo "[2/5] .env OK"
if [ "${WORKERS}" != "1" ]; then
  "$PYTHON_CMD" - <<'PY'
from app.config import settings
import sys

if settings.use_fakeredis:
    print(
        "[ERROR] WORKERS>1 requires USE_FAKEREDIS=false so Redis Pub/Sub can "
        "synchronize /ws/visualization events across workers.",
        file=sys.stderr,
    )
    sys.exit(1)
PY
fi
echo

# [3/5] Install dependencies
echo "[3/5] Installing Python dependencies ..."
"$PYTHON_CMD" -m pip install --upgrade pip
"$PYTHON_CMD" -m pip install -r requirements.txt
echo

# [4/5] Connectivity check
echo "[4/5] Checking MySQL and Redis connectivity ..."
"$PYTHON_CMD" -c "from sqlalchemy import text; from app.db.database import engine; conn = engine.connect(); row = conn.execute(text('SELECT DATABASE(), 1')).one(); print('MySQL OK: database=' + str(row[0])); conn.close()"
"$PYTHON_CMD" -c "import redis; from app.config import settings; client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=5, socket_timeout=5); client.ping(); print('Redis OK')"
echo

# [5/5] Schema init + migrate
echo "[5/5] Initializing and migrating MySQL schema ..."
"$PYTHON_CMD" scripts/init_db.py
"$PYTHON_CMD" scripts/migrate_order_sources.py
echo

# Start (exec 让 uvicorn 接管 PID，便于 systemd 直接管理)
echo "Starting server: http://${HOST}:${PORT}  (workers=${WORKERS})"
echo "Press Ctrl+C to stop."
echo
exec "$PYTHON_CMD" -m uvicorn app.main:app --host "$HOST" --port "$PORT" --workers "$WORKERS"
