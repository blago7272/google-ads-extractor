#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if [[ ! -d ".venv" ]]; then
  echo ".venv not found. Create it first with: python3.12 -m venv .venv"
  exit 1
fi

source .venv/bin/activate

python -m unittest discover -s tests/unit -v
python scripts/raw_freshness_check.py --help >/dev/null
python scripts/release_orchestrator.py --help >/dev/null
