#!/usr/bin/env bash
# ANTAR - set up and run the backend on http://127.0.0.1:8000
set -euo pipefail
cd "$(dirname "$0")/backend"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements-dev.txt
fi
( sleep 2; command -v xdg-open >/dev/null && xdg-open http://127.0.0.1:8000 || true ) &
exec .venv/bin/python -m uvicorn antar.api:app --reload --port 8000 --host "${ANTAR_HOST:-127.0.0.1}"
