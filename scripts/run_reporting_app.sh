#!/usr/bin/env bash
set -euo pipefail

if [[ -d ".venv" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

host="${REPORTING_APP_HOST:-127.0.0.1}"
port="${REPORTING_APP_PORT:-8000}"

exec uvicorn app.main:app --host "$host" --port "$port" --reload
