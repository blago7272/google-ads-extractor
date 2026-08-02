"""Telegram notification bot for Google Ads reporting.

Two modes of operation:
1. Daily push: `python -m app.telegram_bot push` — sends health summaries to all
   subscribed users based on their scope (admin sees all, viewer sees own clients).
2. Interactive: `python -m app.telegram_bot serve` — listens for commands via polling.

Commands:
  /start     — register and confirm connectivity
  /status    — today's health summary (scoped to user's access)
  /detail <account_id> — high-severity alerts only (default)
  /detail <account_id> all — all alerts including medium
  /freshness — data freshness status per account
  /help      — list available commands
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from google.cloud import bigquery

from app.settings import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
if not BOT_TOKEN:
    # Re-load .env if not already loaded
    from pathlib import Path
    from dotenv import load_dotenv
    _root = Path(__file__).resolve().parent.parent
    for _p in [_root / ".env", Path.cwd() / ".env"]:
        if _p.is_file():
            load_dotenv(_p)
            break
    BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")


TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


# ---------------------------------------------------------------------------
# Data layer — reuses the same BigQuery project/datasets as the web app
# ---------------------------------------------------------------------------

@dataclass
class UserAccess:
    email: str
    role: str  # admin | viewer
    telegram_chat_id: int
    allowed_clients: list[str]
    allowed_accounts: dict[str, list[str]]  # client_id -> [account_ids]


def _bq_client() -> bigquery.Client:
    s = get_settings()
    return bigquery.Client(project=s.project_id)


def _run_query(sql: str, params: list | None = None) -> list[dict[str, Any]]:
    client = _bq_client()
    job_config = bigquery.QueryJobConfig()
    if params:
        job_config.query_parameters = params
    rows = client.query(sql, job_config=job_config).result()
    result = []
    for row in rows:
        result.append({k: v for k, v in dict(row).items()})
    return result


def get_telegram_users() -> list[UserAccess]:
    """Load all users with a telegram_chat_id from cfg_app_users.

    Always reads from the prod cfg dataset since cfg_app_users is a
    manually managed table that only exists in prod.
    """
    s = get_settings()
    cfg_dataset = os.getenv("TELEGRAM_CFG_DATASET", "gads_reporting_cfg")
    sql = f"""
        SELECT email, client_id, account_id, role, telegram_chat_id
        FROM `{s.project_id}.{cfg_dataset}.cfg_app_users`
        WHERE is_active = TRUE AND telegram_chat_id IS NOT NULL
        ORDER BY email
    """
    rows = _run_query(sql)

    # Group by (email) to merge multi-row access grants per user.
    # Same chat_id can appear for multiple emails (e.g. admin + viewer test).
    users: dict[str, UserAccess] = {}
    for row in rows:
        chat_id = int(row["telegram_chat_id"])
        email = row["email"]
        if email not in users:
            users[email] = UserAccess(
                email=row["email"],
                role=row["role"],
                telegram_chat_id=chat_id,
                allowed_clients=[],
                allowed_accounts={},
            )
        u = users[email]
        # Escalate to admin if any row is admin
        if row["role"] == "admin":
            u.role = "admin"
        cid = row["client_id"]
        aid = row["account_id"]
        if cid not in u.allowed_clients and cid != "__all__":
            u.allowed_clients.append(cid)
        if cid not in u.allowed_accounts:
            u.allowed_accounts[cid] = []
        if aid and aid != "__all__" and aid not in u.allowed_accounts[cid]:
            u.allowed_accounts[cid].append(aid)
    return list(users.values())


def get_freshness(client_id: str | None = None) -> list[dict]:
    s = get_settings()
    where = ""
    params = []
    if client_id and client_id != "__all__":
        where = "WHERE client_id = @client_id"
        params = [bigquery.ScalarQueryParameter("client_id", "STRING", client_id)]
    sql = f"""
        SELECT client_id, account_id, account_name, last_data_date,
               hours_since_last_data, freshness_status
        FROM `{s.project_id}.{s.mart_dataset}.mart_data_freshness`
        {where}
        ORDER BY client_id, account_name
    """
    return _run_query(sql, params or None)


def get_alerts_summary(client_id: str | None = None, days: int = 1) -> list[dict]:
    s = get_settings()
    date_from = (date.today() - timedelta(days=days)).isoformat()
    where_parts = ["report_date >= @date_from"]
    params = [bigquery.ScalarQueryParameter("date_from", "DATE", date_from)]
    if client_id and client_id != "__all__":
        where_parts.append("client_id = @client_id")
        params.append(bigquery.ScalarQueryParameter("client_id", "STRING", client_id))
    where = "WHERE " + " AND ".join(where_parts)
    sql = f"""
        SELECT client_id, account_id, account_name, alert_type, severity,
               alert_message, report_date
        FROM `{s.project_id}.{s.mart_dataset}.mart_ads_alerts`
        {where}
        ORDER BY report_date DESC, severity, alert_type
    """
    return _run_query(sql, params)


def get_account_detail(account_id: str) -> dict | None:
    """Get latest metrics for a specific account."""
    s = get_settings()
    sql = f"""
        SELECT client_id, account_id, account_name, currency, report_date,
               cost_eur, clicks, impressions, conversions, conversion_value_eur,
               ctr, cpc_eur, cpa_eur, roas
        FROM `{s.project_id}.{s.mart_dataset}.mart_ads_overview_daily`
        WHERE account_id = @account_id
        ORDER BY report_date DESC
        LIMIT 7
    """
    params = [bigquery.ScalarQueryParameter("account_id", "STRING", account_id)]
    rows = _run_query(sql, params)
    if not rows:
        return None
    return {"latest": rows[0], "last_7_days": rows}


# ---------------------------------------------------------------------------
# Message formatting
# ---------------------------------------------------------------------------

def _fmt_number(val: Any) -> str:
    if val is None:
        return "—"
    if isinstance(val, float):
        if val >= 1000:
            return f"{val:,.0f}"
        return f"{val:,.2f}"
    return str(val)


def _freshness_emoji(status: str) -> str:
    return {"ok": "✅", "stale": "🟡", "error": "🔴", "backfilling": "🔄"}.get(status, "❓")


def format_daily_summary(
    freshness: list[dict],
    alerts: list[dict],
    user_email: str | None = None,
    show_all: bool = False,
) -> str:
    today = date.today().isoformat()
    total = len(freshness)
    ok_count = sum(1 for f in freshness if f["freshness_status"] == "ok")
    stale_count = sum(1 for f in freshness if f["freshness_status"] == "stale")
    error_count = sum(1 for f in freshness if f["freshness_status"] == "error")
    backfill_count = sum(1 for f in freshness if f["freshness_status"] == "backfilling")

    # Filter: by default show only problem accounts (🔴, 🟡, 🔄)
    if show_all:
        display_freshness = freshness
        filter_label = "all accounts"
    else:
        display_freshness = [f for f in freshness if f["freshness_status"] != "ok"]
        filter_label = "issues only"

    lines = [
        f"📊 *Google Ads Health Report — {today}*",
    ]
    if user_email:
        lines.append(f"Profile: {_escape_md(user_email)}")

    parts = [f"{total} total", f"{ok_count} ✅"]
    if stale_count:
        parts.append(f"{stale_count} 🟡")
    if error_count:
        parts.append(f"{error_count} 🔴")
    if backfill_count:
        parts.append(f"{backfill_count} 🔄")

    lines.extend([
        "",
        f"Accounts: {', '.join(parts)}",
        f"Filter: {filter_label}",
        "",
    ])

    # Freshness per account (filtered)
    if display_freshness:
        for f in display_freshness:
            emoji = _freshness_emoji(f["freshness_status"])
            acct_alerts = [a for a in alerts if a["account_id"] == f["account_id"]]
            alert_note = f", {len(acct_alerts)} alerts" if acct_alerts else ""
            date_label = "awaiting backfill" if f["freshness_status"] == "backfilling" else f"data to {f['last_data_date']}"
            safe_name = _escape_md(str(f['account_name']))
            acct_id = f['account_id']
            lines.append(
                f"  {emoji} *{safe_name}* `{acct_id}` — "
                f"{date_label}{alert_note}"
            )
    else:
        lines.append("  ✅ All accounts healthy")

    # Alert summary by type
    if alerts:
        lines.append("")
        lines.append("*Alerts by type:*")
        type_counts: dict[str, int] = {}
        for a in alerts:
            type_counts[a["alert_type"]] = type_counts.get(a["alert_type"], 0) + 1
        for atype, count in sorted(type_counts.items()):
            lines.append(f"  • {atype}: {count}")
    else:
        lines.append("")
        lines.append("✅ No alerts today")

    lines.append("")
    if show_all:
        lines.append("Reply /status for issues only or /detail <account\\_id> for details")
    else:
        lines.append("Reply /status all for full list or /detail <account\\_id> for details")

    return "\n".join(lines)


def format_freshness(freshness: list[dict]) -> str:
    lines = ["📡 *Data Freshness Status*", ""]
    for f in freshness:
        emoji = _freshness_emoji(f["freshness_status"])
        if f["freshness_status"] == "backfilling":
            detail = "awaiting backfill"
        else:
            detail = f"Last data: {f['last_data_date']} ({f['hours_since_last_data']}h ago)"
        safe_name = _escape_md(str(f['account_name']))
        acct_id = f['account_id']
        lines.append(
            f"  {emoji} *{safe_name}* `{acct_id}`\n"
            f"     {detail}"
        )
    return "\n".join(lines)


ALERTS_PAGE_SIZE = 20


def format_detail(
    account_id: str,
    detail: dict | None,
    alerts: list[dict],
    page: int = 0,
    severity: str = "high",
) -> tuple[str, dict | None]:
    """Return (message_text, reply_markup_or_None).

    severity: 'high' (🔴 only), 'all' (🔴 + 🟡)
    """
    if detail is None:
        return f"❌ No data found for account `{account_id}`", None

    latest = detail["latest"]
    all_acct_alerts = [a for a in alerts if a["account_id"] == account_id]

    # Apply severity filter
    if severity == "high":
        acct_alerts = [a for a in all_acct_alerts if a["severity"] == "high"]
        filter_label = "🔴 high only"
        other_count = len(all_acct_alerts) - len(acct_alerts)
    else:
        acct_alerts = all_acct_alerts
        filter_label = "all severities"
        other_count = 0

    # First page always includes the metrics header
    if page == 0:
        lines = [
            f"🔍 *Account Detail: {latest['account_name']}*",
            f"Date: {latest['report_date']}",
            "",
            f"  💰 Spend: €{_fmt_number(latest.get('cost_eur'))}",
            f"  👆 Clicks: {_fmt_number(latest.get('clicks'))}",
            f"  👁 Impressions: {_fmt_number(latest.get('impressions'))}",
            f"  🎯 Conversions: {_fmt_number(latest.get('conversions'))}",
            f"  📈 ROAS: {_fmt_number(latest.get('roas'))}",
            f"  💵 CPA: €{_fmt_number(latest.get('cpa_eur'))}",
        ]
    else:
        lines = [
            f"🔍 *{latest['account_name']} — Alerts (page {page + 1})*",
        ]

    # Paginate alerts
    start = page * ALERTS_PAGE_SIZE
    end = start + ALERTS_PAGE_SIZE
    page_alerts = acct_alerts[start:end]
    remaining = len(acct_alerts) - end

    if acct_alerts:
        lines.append("")
        if page == 0:
            lines.append(f"*Recent alerts ({len(acct_alerts)} shown, filter: {filter_label}):*")
            if severity == "high" and other_count > 0:
                lines.append(f"_{other_count} medium alerts hidden — use /detail {account_id} all to see_")
        for a in page_alerts:
            sev_emoji = "🔴" if a["severity"] == "high" else "🟡"
            safe_msg = _escape_md(str(a['alert_message']))
            lines.append(f"  {sev_emoji} {safe_msg}")

        # Build inline keyboard for pagination
        reply_markup = None
        if remaining > 0:
            lines.append(f"\n_{remaining} more alerts available_")
            reply_markup = {
                "inline_keyboard": [[{
                    "text": f"📋 Show next {min(remaining, ALERTS_PAGE_SIZE)} alerts",
                    "callback_data": f"detail:{account_id}:{page + 1}:{severity}",
                }]]
            }
        return "\n".join(lines), reply_markup
    else:
        lines.append("")
        if severity == "high" and other_count > 0:
            lines.append(f"✅ No high\\-severity alerts \\({other_count} medium hidden\\)")
            lines.append(f"Use /detail {account_id} all to see all")
        else:
            lines.append("✅ No recent alerts")
        return "\n".join(lines), None


HELP_TEXT = """🤖 *GAds Notifier — Commands*

/status — Today's health summary (all accounts)
/freshness — Data freshness per account
/detail <account\\_id> — Metrics \\+ 🔴 high alerts only
/detail <account\\_id> all — Metrics \\+ all alerts
/inactive — List all inactive accounts
/activate <account\\_id> — Re-enable an account (admin)
/deactivate <account\\_id> — Disable an account (admin)
/help — Show this message

Daily summaries are sent automatically each morning.
"""


# ---------------------------------------------------------------------------
# Telegram API helpers (using urllib — no extra dependency)
# ---------------------------------------------------------------------------

import json
import urllib.request
import urllib.error


def _tg_request(method: str, data: dict | None = None) -> dict:
    url = f"{TELEGRAM_API}/{method}"
    if data:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode(),
            headers={"Content-Type": "application/json"},
        )
    else:
        req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        log.error("Telegram API error %s %s: %s", method, e.code, body)
        return {"ok": False, "description": body}


def send_message(
    chat_id: int,
    text: str,
    parse_mode: str = "Markdown",
    reply_markup: dict | None = None,
) -> dict:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return _tg_request("sendMessage", payload)


def answer_callback_query(callback_query_id: str) -> dict:
    return _tg_request("answerCallbackQuery", {"callback_query_id": callback_query_id})


def get_updates(offset: int | None = None) -> list[dict]:
    params: dict[str, Any] = {
        "timeout": 30,
        "allowed_updates": ["message", "callback_query"],
    }
    if offset is not None:
        params["offset"] = offset
    result = _tg_request("getUpdates", params)
    return result.get("result", [])


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def _scope_filter(user: UserAccess) -> str | None:
    """Return client_id filter or None for admins (all clients)."""
    if user.role == "admin":
        return None
    if user.allowed_clients:
        return user.allowed_clients[0]  # primary client
    return None


def _find_user_by_chat_id(chat_id: int, users: list[UserAccess]) -> UserAccess | None:
    """Find the user with the broadest access for a given chat_id.

    When the same chat_id is used by multiple profiles (e.g. admin + viewer
    for testing), the admin profile wins for interactive commands.
    """
    matches = [u for u in users if u.telegram_chat_id == chat_id]
    if not matches:
        return None
    # Prefer admin over viewer
    for m in matches:
        if m.role == "admin":
            return m
    return matches[0]


def _escape_md(text: str) -> str:
    """Escape special characters for Telegram Markdown (v1)."""
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, f"\\{ch}")
    return text


def handle_start(chat_id: int, user: UserAccess | None) -> str:
    if user is None:
        return (
            "👋 Welcome! Your Telegram account is not yet linked to the "
            "reporting system.\n\nPlease contact blago@idconsult.bg to "
            "request access."
        )
    email_escaped = _escape_md(user.email)
    return (
        f"👋 Welcome, *{email_escaped}*!\n\n"
        f"Role: *{user.role}*\n"
        f"You'll receive daily health summaries here.\n\n"
        f"Use /help to see available commands."
    )


def handle_status(user: UserAccess) -> str:
    client_filter = _scope_filter(user)
    freshness = get_freshness(client_filter)
    alerts = get_alerts_summary(client_filter, days=1)
    return format_daily_summary(freshness, alerts, user_email=user.email, show_all=True)


def handle_freshness(user: UserAccess) -> str:
    client_filter = _scope_filter(user)
    freshness = get_freshness(client_filter)
    return format_freshness(freshness)


def handle_detail(
    user: UserAccess, account_id: str, page: int = 0, severity: str = "high"
) -> tuple[str, dict | None]:
    """Return (message_text, reply_markup_or_None).

    severity: 'high' (default, 🔴 only), 'all' (🔴 + 🟡)
    """
    # Check access
    if user.role != "admin":
        allowed_ids = []
        for aids in user.allowed_accounts.values():
            allowed_ids.extend(aids)
        if account_id not in allowed_ids:
            return f"🚫 You don't have access to account `{account_id}`", None

    detail = get_account_detail(account_id)
    alerts = get_alerts_summary(days=7)
    return format_detail(account_id, detail, alerts, page=page, severity=severity)


def handle_activate(user: UserAccess, account_id: str) -> str:
    """Activate an account (admin only). Updates BQ directly."""
    if user.role != "admin":
        return "🚫 Only admins can activate accounts."
    return _toggle_account(account_id, active=True)


def handle_deactivate(user: UserAccess, account_id: str) -> str:
    """Deactivate an account (admin only). Updates BQ directly."""
    if user.role != "admin":
        return "🚫 Only admins can deactivate accounts."
    return _toggle_account(account_id, active=False)


def _toggle_account(account_id: str, active: bool) -> str:
    """Toggle is_active in the BQ cfg_accounts table."""
    s = get_settings()
    cfg_dataset = s.cfg_dataset
    action = "activated" if active else "deactivated"
    try:
        # Check account exists
        check_sql = f"""
            SELECT account_id, account_name, is_active
            FROM `{s.project_id}.{cfg_dataset}.cfg_accounts`
            WHERE cast(account_id AS STRING) = @account_id
        """
        params = [bigquery.ScalarQueryParameter("account_id", "STRING", account_id)]
        rows = _run_query(check_sql, params)
        if not rows:
            return f"❌ Account `{account_id}` not found in cfg\\_accounts."

        current = rows[0]
        current_active = current.get("is_active", False)
        name = _escape_md(str(current.get("account_name", account_id)))

        if current_active == active:
            status = "already active" if active else "already inactive"
            return f"ℹ️ *{name}* is {status}."

        # Update
        update_sql = f"""
            UPDATE `{s.project_id}.{cfg_dataset}.cfg_accounts`
            SET is_active = @active
            WHERE cast(account_id AS STRING) = @account_id
        """
        client = _bq_client()
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("active", "BOOL", active),
                bigquery.ScalarQueryParameter("account_id", "STRING", account_id),
            ]
        )
        client.query(update_sql, job_config=job_config).result()

        emoji = "✅" if active else "⏸️"
        return (
            f"{emoji} *{name}* has been {action}.\n\n"
            f"Note: This takes effect immediately for the bot and web app. "
            f"Run `dbt run` to rebuild marts with the updated account list."
        )
    except Exception as e:
        log.exception("Error toggling account %s", account_id)
        return f"❌ Error: {_escape_md(str(e))}"


def handle_inactive(user: UserAccess) -> str:
    """List all inactive accounts (admin only)."""
    if user.role != "admin":
        return "🚫 Only admins can view inactive accounts."
    s = get_settings()
    sql = f"""
        SELECT cast(account_id AS STRING) AS account_id, account_name, client_id
        FROM `{s.project_id}.{s.cfg_dataset}.cfg_accounts`
        WHERE is_active = FALSE
        ORDER BY client_id, account_name
    """
    rows = _run_query(sql)
    if not rows:
        return "✅ All accounts are active."

    lines = [f"⏸️ *Inactive accounts ({len(rows)}):*", ""]
    for r in rows:
        name = _escape_md(str(r["account_name"]))
        lines.append(f"  • `{r['account_id']}` — {name} ({r['client_id']})")
    lines.append("")
    lines.append("Use /activate <account\\_id> to re-enable.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Push mode — send daily summary to all subscribed users
# ---------------------------------------------------------------------------

def push_daily_summary():
    """Send scoped daily summaries to all users with a telegram_chat_id."""
    users = get_telegram_users()
    if not users:
        log.warning("No users with telegram_chat_id found")
        return

    # Deduplicate by chat_id — if same person has admin + viewer rows,
    # send the admin (broader) view only once.
    seen_chat_ids: set[int] = set()
    deduped_users = []
    # Sort so admins come first (broader scope wins)
    for user in sorted(users, key=lambda u: (0 if u.role == "admin" else 1)):
        if user.telegram_chat_id not in seen_chat_ids:
            seen_chat_ids.add(user.telegram_chat_id)
            deduped_users.append(user)
    users = deduped_users

    log.info("Sending daily summary to %d users", len(users))

    for user in users:
        try:
            client_filter = _scope_filter(user)
            freshness = get_freshness(client_filter)
            alerts = get_alerts_summary(client_filter, days=1)

            if not freshness:
                log.warning("No freshness data for user %s (filter=%s)", user.email, client_filter)
                continue

            message = format_daily_summary(freshness, alerts)
            result = send_message(user.telegram_chat_id, message)

            if result.get("ok"):
                log.info("✅ Sent to %s (chat_id=%d)", user.email, user.telegram_chat_id)
            else:
                log.error(
                    "❌ Failed to send to %s: %s",
                    user.email,
                    result.get("description", "unknown error"),
                )
        except Exception:
            log.exception("Error sending to %s", user.email)


# ---------------------------------------------------------------------------
# Serve mode — long-polling command listener
# ---------------------------------------------------------------------------

def _flush_pending_updates() -> int | None:
    """Consume all pending updates so we don't replay old messages on startup."""
    result = _tg_request("getUpdates", {"offset": -1, "timeout": 0})
    updates = result.get("result", [])
    if updates:
        latest = updates[-1]["update_id"]
        log.info("Flushed pending updates up to %d", latest)
        return latest + 1
    return None


def serve_polling():
    """Run the bot in long-polling mode, handling commands interactively.

    Also pushes a daily summary at DAILY_PUSH_HOUR (Sofia time).
    """
    import zoneinfo

    DAILY_PUSH_HOUR = 8  # 08:00 Sofia time
    SOFIA_TZ = zoneinfo.ZoneInfo("Europe/Sofia")

    log.info("Starting Telegram bot in polling mode...")
    log.info("Daily push scheduled at %02d:00 Sofia time", DAILY_PUSH_HOUR)
    users = get_telegram_users()
    log.info("Loaded %d users with Telegram access", len(users))

    # Track last push date so we only push once per day
    last_push_date: date | None = None

    # Skip any messages that arrived while the bot was offline
    offset = _flush_pending_updates()
    while True:
        # --- Check if daily push is due ---
        from datetime import datetime as _dt
        now_sofia = _dt.now(SOFIA_TZ)
        today_sofia = now_sofia.date()
        if (
            now_sofia.hour >= DAILY_PUSH_HOUR
            and last_push_date != today_sofia
        ):
            log.info("Triggering daily push for %s", today_sofia)
            try:
                push_daily_summary()
                last_push_date = today_sofia
                log.info("Daily push completed for %s", today_sofia)
            except Exception:
                log.exception("Daily push failed, will retry next poll cycle")
        try:
            updates = get_updates(offset)
            for update in updates:
                offset = update["update_id"] + 1

                # Handle callback queries (inline button presses)
                callback = update.get("callback_query")
                if callback:
                    cb_chat_id = callback["message"]["chat"]["id"]
                    cb_data = callback.get("data", "")
                    cb_user = _find_user_by_chat_id(cb_chat_id, users)
                    answer_callback_query(callback["id"])

                    if cb_user and cb_data.startswith("detail:"):
                        parts = cb_data.split(":")
                        if len(parts) >= 3:
                            acc_id = parts[1]
                            page = int(parts[2])
                            sev = parts[3] if len(parts) > 3 else "high"
                            text_out, markup = handle_detail(cb_user, acc_id, page=page, severity=sev)
                            send_message(cb_chat_id, text_out, reply_markup=markup)
                    continue

                msg = update.get("message")
                if not msg or "text" not in msg:
                    continue

                chat_id = msg["chat"]["id"]
                text = msg["text"].strip()
                user = _find_user_by_chat_id(chat_id, users)

                log.info(
                    "Message from chat_id=%d user=%s: %s",
                    chat_id,
                    user.email if user else "unknown",
                    text,
                )

                if text.startswith("/start"):
                    response = handle_start(chat_id, user)
                    send_message(chat_id, response)
                    # Reload users in case a new user was just added
                    users = get_telegram_users()
                    continue

                if user is None:
                    send_message(
                        chat_id,
                        "🚫 Your Telegram account is not linked to the reporting system.\n"
                        "Please contact blago@idconsult.bg to request access.",
                    )
                    continue

                reply_markup = None
                if text.startswith("/status"):
                    response = handle_status(user)
                elif text.startswith("/freshness"):
                    response = handle_freshness(user)
                elif text.startswith("/detail"):
                    parts = text.split()
                    if len(parts) < 2:
                        response = "Usage: /detail <account\\_id> \\[all\\]\n\nExample: /detail 1200697994\nExample: /detail 1200697994 all"
                    else:
                        acct_id = parts[1].strip()
                        sev = "all" if len(parts) > 2 and parts[2].strip().lower() == "all" else "high"
                        response, reply_markup = handle_detail(user, acct_id, severity=sev)
                elif text.startswith("/activate"):
                    parts = text.split(maxsplit=1)
                    if len(parts) < 2:
                        response = "Usage: /activate <account\\_id>"
                    else:
                        response = handle_activate(user, parts[1].strip())
                elif text.startswith("/deactivate"):
                    parts = text.split(maxsplit=1)
                    if len(parts) < 2:
                        response = "Usage: /deactivate <account\\_id>"
                    else:
                        response = handle_deactivate(user, parts[1].strip())
                elif text.startswith("/inactive"):
                    response = handle_inactive(user)
                elif text.startswith("/help"):
                    response = HELP_TEXT
                else:
                    response = "Unknown command. Use /help to see available commands."

                send_message(chat_id, response, reply_markup=reply_markup)

        except KeyboardInterrupt:
            log.info("Shutting down bot...")
            break
        except Exception:
            log.exception("Error in polling loop, retrying in 5s...")
            import time
            time.sleep(5)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m app.telegram_bot [push|serve]")
        sys.exit(1)

    mode = sys.argv[1]
    if mode == "push":
        push_daily_summary()
    elif mode == "serve":
        serve_polling()
    else:
        print(f"Unknown mode: {mode}. Use 'push' or 'serve'.")
        sys.exit(1)
