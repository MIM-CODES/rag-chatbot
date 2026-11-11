#!/usr/bin/env bash
# اجرای سرویس: نصب وابستگی‌ها در صورت نیاز و بالا آوردن uvicorn
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT_DIR="$(pwd)"
BACKEND_DIR="$ROOT_DIR/backend"

if [ ! -x "$BACKEND_DIR/.venv/bin/python" ]; then
  echo "ساخت محیط مجازی…"
  python3 -m venv "$BACKEND_DIR/.venv"
fi

if ! "$BACKEND_DIR/.venv/bin/python" -c "import fastapi, chromadb" >/dev/null 2>&1; then
  echo "نصب وابستگی‌ها…"
  "$BACKEND_DIR/.venv/bin/python" -m pip install -q -r "$BACKEND_DIR/requirements.txt"
fi

APP_HOST="${APP_HOST:-127.0.0.1}"
APP_PORT="${APP_PORT:-8000}"

echo "سرویس روی http://$APP_HOST:$APP_PORT در حال اجراست"
exec "$BACKEND_DIR/.venv/bin/python" -m uvicorn app.main:app \
  --app-dir "$BACKEND_DIR" \
  --host "$APP_HOST" \
  --port "$APP_PORT"
