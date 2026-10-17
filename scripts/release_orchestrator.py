#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from orchestration.release_orchestrator import main  # noqa: E402
except Exception as exc:  # noqa: BLE001
    # A broken import (missing dependency, bad deploy) fails before main() can
    # report anything. ops_telegram is standard-library only, so it still loads.
    from orchestration.ops_telegram import report_release_failed  # noqa: E402

    report_release_failed(step="import", error_type=type(exc).__name__, error_message=str(exc))
    raise


if __name__ == "__main__":
    raise SystemExit(main())
