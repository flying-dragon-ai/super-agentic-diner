#!/usr/bin/env bash
# Crossroads Agent Cafe Linux launcher. SQLite/fakeredis remain valid defaults;
# external MySQL/Redis are probed only when the active configuration selects them.
set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"

PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"
WORKERS="${WORKERS:-1}"

echo "============================================"
echo "  Crossroads Agent Cafe - Linux Launcher"
echo "============================================"
echo

if [ -x ".venv/bin/python" ]; then
  PYTHON_CMD="$PROJECT_DIR/.venv/bin/python"
  echo "[1/5] Using existing .venv"
else
  BASE_PYTHON="${PYTHON:-}"
  if [ -z "$BASE_PYTHON" ]; then
    for candidate in python3 python; do
      if command -v "$candidate" >/dev/null 2>&1; then
        BASE_PYTHON="$candidate"
        break
      fi
    done
  fi
  if [ -z "$BASE_PYTHON" ]; then
    echo "[ERROR] Python 3.10+ not found." >&2
    exit 1
  fi
  "$BASE_PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 10) else 1)'
  echo "[1/5] Creating .venv with $BASE_PYTHON ..."
  "$BASE_PYTHON" -m venv .venv
  PYTHON_CMD="$PROJECT_DIR/.venv/bin/python"
fi
echo

if [ -f ".env" ]; then
  echo "[2/5] Using .env"
else
  echo "[2/5] No .env found; using safe local defaults (SQLite + fakeredis)"
fi
APP_DB_MODE="$("$PYTHON_CMD" -c 'from app.config import settings; print(settings.db_mode)')"
APP_USE_FAKEREDIS="$("$PYTHON_CMD" -c 'from app.config import settings; print(str(settings.use_fakeredis).lower())')"
echo "  DB_MODE=$APP_DB_MODE"
echo "  USE_FAKEREDIS=$APP_USE_FAKEREDIS"
if [ "$WORKERS" != "1" ] && [ "$APP_USE_FAKEREDIS" = "true" ]; then
  echo "[ERROR] WORKERS>1 requires USE_FAKEREDIS=false for shared Pub/Sub state." >&2
  exit 1
fi
echo

echo "[3/5] Installing Python dependencies ..."
"$PYTHON_CMD" -m pip install -r requirements.txt
echo

echo "[4/5] Checking configured backends ..."
if [ "$APP_DB_MODE" = "mysql" ]; then
  "$PYTHON_CMD" -c "from sqlalchemy import text; from app.db.database import engine; c=engine.connect(); row=c.execute(text('SELECT DATABASE(), 1')).one(); print('MySQL OK: database=' + str(row[0])); c.close()"
else
  echo "SQLite selected; no external database probe required."
fi
if [ "$APP_USE_FAKEREDIS" = "false" ]; then
  "$PYTHON_CMD" -c "import redis; from app.config import settings; c=redis.Redis.from_url(settings.redis_url, socket_connect_timeout=5, socket_timeout=5); c.ping(); print('Redis OK')"
else
  echo "fakeredis selected; no external Redis probe required."
fi
echo

echo "[5/5] Running canonical schema migration ..."
"$PYTHON_CMD" scripts/migrate_order_sources.py
echo

echo "Starting server: http://${HOST}:${PORT} (workers=${WORKERS})"
echo "Press Ctrl+C to stop."
exec "$PYTHON_CMD" -m uvicorn app.main:app --host "$HOST" --port "$PORT" --workers "$WORKERS" --ws-max-size 16384
