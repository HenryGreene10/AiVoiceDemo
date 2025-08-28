#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."/src

export UVICORN_RELOAD=true
echo "Starting FastAPI locally on http://127.0.0.1:8787"
echo "Tip: use cloudflared or ngrok for HTTPS if testing from browser"
echo "  cloudflared tunnel --url http://localhost:8787"

uvicorn app:app --host 127.0.0.1 --port 8787 --reload


