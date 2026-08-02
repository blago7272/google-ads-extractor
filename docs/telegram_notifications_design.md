# Contract: Telegram Notification Service

Status: `CANDIDATE` — pending team review

Parent contract: `docs/reporting_contract.md`

## Purpose

Deliver scheduled health summaries and on-demand account reports to agency staff
and client contacts via a Telegram bot. This complements the web reporting
interface by providing push-based delivery without requiring users to log in.

## Goals

- Push concise daily health summaries after the scheduled dbt run
- Allow per-recipient, per-account subscription granularity
- Support interactive commands for on-demand detail retrieval
- Reuse the same mart layer and alert logic as the web app

## Notification Subscription Model

### Subscription Table

Table: `cfg_telegram_subscriptions`

Location: BigQuery dataset `gads_reporting_cfg`

Grain: one row per `telegram_user_id`, `client_id`, `account_id`

Required fields:

- `telegram_user_id` — Telegram numeric user ID (obtained when user starts the bot)
- `telegram_username` — Telegram username for display purposes (not used for auth)
- `display_name` — human-readable name for the recipient
- `client_id` — which agency client this subscription covers
- `account_id` — which specific account within that client (`__all__` for all accounts under the client)
- `role` — `admin` or `viewer` (controls what commands and data are available)
- `receives_daily_summary` — boolean, whether this user gets the daily push
- `receives_alert_push` — boolean, whether this user gets immediate alert pushes (future phase)
- `is_active` — boolean

### Subscription Granularity

A single Telegram user can have multiple subscription rows. Each row grants
visibility into one client + account combination.

Examples:

```
telegram_user_id  client_id   account_id  role    receives_daily_summary
111222333         sexwell     __all__     admin   true
111222333         matraci.bg  4848659150  admin   true
444555666         matraci.bg  4848659150  viewer  true
444555666         sexwell     1200697994  viewer  false
```

In this example:

- User 111222333 is an admin who receives daily summaries for all Sexwell
  accounts and for the specific Matraci account
- User 444555666 is a viewer who receives daily summaries for Matraci only,
  and has read access (but no push) to one Sexwell account via commands

### Access Control Rules

- A user can only query accounts they have a subscription row for
- `account_id = '__all__'` grants access to all current and future accounts
  under that client
- `role = 'admin'` can see all alert details and run all commands
- `role = 'viewer'` can see summary and detail for their subscribed accounts only
- Interactive commands enforce the same scoping as the web app

## Daily Summary Message

### Trigger

Sent after the scheduled dbt run completes successfully. Timing follows the
operations design schedule (expected ~08:00 Sofia time).

### Content Structure

```
Google Ads Health — 2026-03-30

Accounts: 2 checked, 2 OK, 0 issues

  Sexwell.bg (EUR) — OK
    208 days of data, 0 new alerts

  Matraci (EUR) — 3 alerts
    110 days of data
    1x conversion_drop (high)
    2x budget_exhausted (medium)

Data freshness: all current (T-1)
```

### Formatting Rules

- One message per recipient, covering only their subscribed accounts
- Accounts with zero alerts show a single OK line
- Accounts with alerts show a count per alert type and severity
- Data freshness status is appended at the bottom
- Message must remain under Telegram's 4096 character limit
- If the message exceeds the limit (many accounts), split into multiple messages

### Data Sources

| Data Point | Source |
|------------|--------|
| Alert counts by type and severity | `mart_ads_alerts` |
| Data freshness per account | `mart_data_freshness` (when implemented) or `max(report_date)` from `mart_ads_overview_daily` |
| Account metadata | `cfg_accounts` |
| dbt test results | dbt run artifacts (`run_results.json`) |

## Interactive Commands

### Command Reference

| Command | Access | Response |
|---------|--------|----------|
| `/start` | Any | Register with the bot, display welcome and instructions |
| `/status` | All subscribed | Today's summary for subscribed accounts |
| `/detail <account_id>` | Subscribed to that account | Full alert list, top metrics, freshness for that account |
| `/freshness` | All subscribed | Data freshness table for subscribed accounts |
| `/alerts <account_id>` | Subscribed to that account | Last 7 days of alerts for that account |
| `/help` | Any | List available commands |

### `/detail` Response Structure

```
Matraci (EUR) — 4848659150
Period: 2026-03-01 to 2026-03-29

Key metrics (last 30 days):
  Spend: €1,245.67
  Clicks: 3,421
  Conversions: 89
  ROAS: 4.2x

Active alerts (3):
  [HIGH] Conversions dropped from 12 to 3 (2026-03-29)
  [MED] Campaign "Search - Generic" likely exhausted budget (2026-03-28)
  [MED] Campaign "Search - Brand" likely exhausted budget (2026-03-28)

Data: current (last date: 2026-03-29)
```

### `/freshness` Response Structure

```
Data Freshness — 2026-03-30

  Sexwell.bg (EUR)    last: 2026-03-29  OK
  Matraci (EUR)       last: 2026-03-29  OK
```

### Error Responses

| Scenario | Response |
|----------|----------|
| Unknown user (no subscription rows) | "You are not registered. Contact your account manager." |
| Account not in user's subscriptions | "You do not have access to this account." |
| Invalid account ID | "Account not found. Use /status to see your accounts." |
| No data available | "No reporting data is available yet for this account." |

## Registration Flow

### Option A — Manual Registration (Phase 1)

1. User messages `/start` to the bot
2. Bot responds with their Telegram user ID and instructions:
   "Your Telegram ID is 111222333. Share this with your account manager to
   activate notifications."
3. Admin adds a row to `cfg_telegram_subscriptions` in BigQuery
4. On next `/start` or `/status`, the user sees their subscribed accounts

### Option B — Self-Service Registration (Future)

1. User messages `/register <email>`
2. Bot looks up the email in `cfg_app_users`
3. If found, creates matching subscription rows in `cfg_telegram_subscriptions`
4. User is immediately active

### Recommendation

Start with Option A. Manual registration is sufficient for agency-managed
recipients and avoids building an email verification flow.

## Bot Infrastructure

### Deployment

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Bot server | Cloud Run (always-on, min 1 instance) | Handle webhook callbacks for commands |
| Daily push | Cloud Scheduler + Cloud Run Job | Trigger summary generation and sending |
| Bot framework | `python-telegram-bot` library | Telegram Bot API interaction |
| Data access | BigQuery Python client | Read marts and config tables |

### Telegram Bot Setup

- Create bot via BotFather (`@BotFather` on Telegram)
- Set bot commands via BotFather for command auto-complete
- Use webhook mode (not polling) for production
- Bot token stored as a Secret Manager secret, not in code or `.env`

### Configuration

Environment variables:

- `TELEGRAM_BOT_TOKEN` — from BotFather
- `TELEGRAM_WEBHOOK_URL` — Cloud Run service URL + `/webhook`
- `REPORTING_PROJECT_ID` — BigQuery project
- `REPORTING_MART_DATASET` — mart dataset name
- `REPORTING_CFG_DATASET` — config dataset name

## Security

- Telegram user IDs are numeric and cannot be spoofed within the Telegram API
- The bot only responds to users with active subscription rows
- No sensitive data (passwords, tokens, PII) is sent in messages
- Bot token must be stored in Secret Manager, not in environment variables
  or source code
- The webhook endpoint should validate the Telegram secret token header

## Phasing

### Phase 1 — Daily Summary + Basic Commands

- Manual subscription management via BigQuery
- Daily push summary after dbt run
- `/start`, `/status`, `/detail`, `/freshness`, `/help` commands
- Deployment on Cloud Run

### Phase 2 — Enhanced Interaction

- `/alerts` command with date range filtering
- Alert-level push notifications (`receives_alert_push` flag)
- Self-service registration via `/register`
- Command to request a specific report page screenshot

### Phase 3 — Bi-Directional

- Acknowledge alerts via inline buttons
- Snooze specific alert types
- Subscribe/unsubscribe from specific accounts via commands

## Open Questions For The Team

- Should the daily summary be sent once per day or configurable per recipient
  (e.g., some users want morning + evening)?
- Should viewers see numeric spend values or only alert counts?
- Is the Telegram bot token managed by the agency or per-client?
- Should the bot support group chats (e.g., a shared agency channel) or only
  direct messages?
- What is the bot's display name and profile picture?

## Dependencies

- `mart_ads_alerts` — must exist and be current (already implemented)
- `mart_data_freshness` — should be implemented before or alongside this feature
- Scheduled dbt runs — the daily push depends on a reliable build schedule
- `cfg_telegram_subscriptions` — new config table

## Related Documents

- `docs/reporting_contract.md` — parent contract
- `docs/operations_design.md` — scheduling and pipeline design
- `docs/auth_design.md` — access control patterns
- `docs/contract_review_infra_and_ops.md` — infrastructure review
