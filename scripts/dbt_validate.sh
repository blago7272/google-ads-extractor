#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if [[ ! -d ".venv" ]]; then
  echo ".venv not found. Create it first with: python3.12 -m venv .venv"
  exit 1
fi

source .venv/bin/activate

dbt debug
dbt seed --full-refresh
dbt run --select path:models/staging/google_ads path:models/staging/manual
dbt run --full-refresh --select path:models/marts/reporting
dbt test

