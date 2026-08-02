# Telegram Notification Service Contract (Candidate)

Status: implemented, pending team ratification

Parent contract: `docs/reporting_contract.md`

## Purpose

Deliver automated health summaries and interactive reporting queries to agency
staff and client viewers via a private Telegram bot, complementing the web
reporting interface.

## Bot Identity

- Name: GAds--Notifier
- Username: `@GAdsNotifierBot`
- Visibility: publicly findable, but only responds to registered users

## User Management

User access is managed through the `cfg_app_users` table in BigQuery:

| Column | Purpose |
|--------|---------|
| email | User identity (matches web app auth) |
| client_id | Scoping key (`__all__` for admins) |
| account_id | Account-level scoping (`__all__` for full client access) |
| role | `admin` or `viewer` |
| telegram_chat_id | Telegram user ID for bot messaging |

A single table controls both web app access and Telegram access. Users without
a `telegram_chat_id` receive web access only. Users with a `telegram_chat_id`
who are not in the table receive a polite rejection when messaging the bot.

## Daily Push Notification

Schedule:

- 08:00 Sofia time (Europe/Sofia), daily

Recipients:

- all users in `cfg_app_users` with a non-null `telegram_chat_id`

Content:

- account health summary scoped to the user's access level
- per-account freshness status with three-tier indicators
- alert counts by type
- profile email shown for user identification

Freshness indicators:

| Icon | Status | Condition |
|------|--------|-----------|
| ✅ | ok | Data within 36 hours |
| 🟡 | stale | Data 36-168 hours old |
| 🔴 | error | Data older than 168 hours |
| 🔄 | backfilling | No data yet (awaiting backfill) |

## Interactive Commands

| Command | Access | Description |
|---------|--------|-------------|
| `/start` | all | Welcome message and registration check |
| `/status` | registered | Today's health summary (all accounts in scope) |
| `/freshness` | registered | Data freshness per account |
| `/detail <account_id>` | registered | High-severity alerts only (default) |
| `/detail <account_id> all` | registered | All alerts including medium severity |
| `/help` | registered | Command list |
| `/inactive` | admin | List inactive accounts |
| `/activate <account_id>` | admin | Activate an account in cfg_accounts |
| `/deactivate <account_id>` | admin | Deactivate an account in cfg_accounts |

## Alert Severity And Filtering

The `/detail` command defaults to showing only high-severity (🔴) alerts.
Medium-severity (🟡) alerts are hidden by default but the count is shown with
instructions to use `/detail <id> all` to reveal them.

Alert pagination:

- 20 alerts per page
- inline keyboard button for "show next 20"
- severity filter preserved across pages

## Access Scoping

- Admin users see all accounts across all clients
- Viewer users see only accounts matching their `client_id` and `account_id` grants
- When a Telegram chat ID maps to multiple user rows, the highest-privilege role is used
- The daily push sends one message per unique chat ID, scoped to that user's access

## Security

- The bot token is stored in `.env` (not in code, not committed)
- No data is exposed in the bot's public profile
- The bot cannot proactively message users who haven't sent `/start`
- Unregistered users receive only a generic rejection with a contact email
- All BigQuery queries use parameterized inputs

## Dependencies

- `mart_data_freshness` for freshness status
- `mart_ads_alerts` for alert data
- `mart_ads_overview_daily` for account metrics in `/detail`
- `cfg_app_users` for user access and Telegram chat IDs
- `cfg_accounts` for account metadata and `/activate`/`/deactivate`

## Open Items

- Production deployment: bot currently runs locally; needs a Cloud Run service
  or always-on Cloud Run instance for the polling loop
- Webhook mode: switching from polling to webhook would allow serverless
  deployment but requires a stable HTTPS endpoint
- Additional commands: consider `/compare`, `/trend`, or scheduled custom reports
- Group chat support: currently private messages only; group chat could be
  added if teams want shared channels
