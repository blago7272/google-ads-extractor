"""Send a plain-text message to the ops Telegram chat.

The ops chat is `TELEGRAM_CHAT_ID` and the bot is `TELEGRAM_BOT_TOKEN`, the same
pair the skipped-accounts alert uses. Standard library only, so the release
entry point can import this even when a third-party import in the orchestrator
itself is what broke.

Never raises: a notifier must not turn a warning into a failed release, or mask
the error it is reporting.
"""

from __future__ import annotations

import json
import os
import urllib.request

from orchestration.logging_utils import emit_log

# Telegram rejects messages over 4096 characters.
MAX_MESSAGE_CHARS = 4000


def send_ops_message(text: str, *, event: str = "ops_telegram") -> bool:
    """Post `text` to the ops chat. Returns True if Telegram accepted it."""

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        emit_log(f"{event}_skipped", reason="TELEGRAM_BOT_TOKEN and/or TELEGRAM_CHAT_ID not set")
        return False

    if len(text) > MAX_MESSAGE_CHARS:
        text = text[: MAX_MESSAGE_CHARS - 1] + "…"

    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps(
            {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read()
    except Exception as exc:  # noqa: BLE001 - see module docstring
        emit_log(
            f"{event}_failed",
            level="ERROR",
            error_type=type(exc).__name__,
            # The URL carries the bot token; never log the exception's request details.
            error_message=str(exc).replace(token, "<token>"),
        )
        return False

    emit_log(f"{event}_sent", chat_id=chat_id)
    return True
