#!/usr/bin/env bash
# Local runner. Usage:
#   ./run_api.sh dev    # single-worker, auto-reload
#   ./run_api.sh prod   # two workers, no reload
set -euo pipefail

MODE="${1:-dev}"
PORT="${PORT:-8000}"

case "$MODE" in
  dev)
    exec uvicorn api.main:app --host 0.0.0.0 --port "$PORT" --reload
    ;;
  prod)
    exec uvicorn api.main:app --host 0.0.0.0 --port "$PORT" --workers 2 --timeout-keep-alive 300
    ;;
  *)
    echo "Usage: $0 [dev|prod]" >&2
    exit 1
    ;;
esac
