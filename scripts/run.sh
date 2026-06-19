#!/bin/bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)/.."
cd "$DIR"

# Activate venv if exists
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8185}"

echo "========================================"
echo "  Media Gallery Server (Ubuntu)"
echo "========================================"
echo ""

exec uvicorn app.main:app --host "$HOST" --port "$PORT"
