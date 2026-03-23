from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return asdict(value)
    return str(value)


def emit_log(event: str, level: str = "INFO", **fields: Any) -> None:
    payload = {
        "event": event,
        "severity": level,
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    payload.update(fields)
    print(json.dumps(payload, default=_json_default, sort_keys=True), flush=True)
