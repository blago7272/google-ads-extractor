# Skipped-account alerting

## Why this exists

The raw freshness gate is deliberately non-blocking: when an account's raw data
goes stale, the selective-freshness models exclude it from every mart and the
release continues for everyone else. The gap was that nothing *announced* the
exclusion. `Onesleep RS` (5304022952) stopped ingesting on 2026-06-15 and was
missing from reporting for 47 days before anyone noticed.

`orchestration/skipped_accounts_alert.py` runs as the `skipped_accounts_alert`
step, immediately after `raw_freshness_gate` and before any dbt build, so a
regression is announced within seconds of the release starting rather than after
an hour of building.

## What it does

1. **Classifies** every active account using the same rule as
   `stg_account_freshness` — `date_diff(current_date(report_timezone),
   last_raw_date) > max_allowed_lag_days` — so the alert set is identical to
   `mart_skipped_accounts` rather than drifting from it.
2. **Diffs** that set against the previous release's set, stored in
   `<cfg_dataset>.ops_skipped_accounts_state` (day-partitioned, written with a
   load job so it costs nothing and avoids the streaming buffer).
3. **Emits** structured logs:

   | Event | Severity | Meaning |
   |---|---|---|
   | `skipped_accounts_alert` | `ERROR` | One or more accounts **newly** dropped out — this is the one to page on. |
   | `skipped_accounts_still_excluded` | `WARNING` | Standing list of everything currently excluded. Re-emitted every run, so a long outage never goes quiet. |
   | `skipped_accounts_recovered` | `INFO` | Accounts that rejoined the marts. |
   | `skipped_accounts_summary` | `INFO` | Counts for dashboards. |
   | `skipped_accounts_baseline_initialized` | `INFO` | First run only — see below. |

4. **Optionally posts to Telegram** when both `TELEGRAM_BOT_TOKEN` and
   `TELEGRAM_CHAT_ID` are set.

### First run is a baseline

With no prior state, the first run records the current set and reports
`is_baseline: true` without firing `skipped_accounts_alert`. Deploying this does
not page for the five accounts that were already stale; the next run diffs
against that baseline normally.

### Alerting never fails the release

Every failure path — a missing state table, a BigQuery error, a dead Telegram
token — is logged and swallowed. A broken notifier must not break a working data
pipeline. Look for `skipped_accounts_alert_failed` or
`skipped_accounts_telegram_failed` if alerts go quiet.

## Wiring up notifications

### Telegram (recommended — the token is already deployed)

The Cloud Run job already mounts `TELEGRAM_BOT_TOKEN` from the
`telegram-bot-token` secret. Only the chat id is missing:

```bash
gcloud run jobs update reporting-release-orchestrator \
  --project gads-export-all --region europe-west1 \
  --update-env-vars TELEGRAM_CHAT_ID=<chat_id>
```

Until then the step logs `skipped_accounts_telegram_skipped` and relies on logs
alone.

### Cloud Logging alert policy

For paging independent of Telegram, alert on the log filter:

```
resource.type="cloud_run_job"
resource.labels.job_name="reporting-release-orchestrator"
jsonPayload.event="skipped_accounts_alert"
severity="ERROR"
```

A second, lower-urgency policy on `jsonPayload.event="skipped_accounts_still_excluded"`
catches the case where an account has been excluded for a long time and the
original alert was missed or acknowledged.

## Configuration

| Setting | Source | Default |
|---|---|---|
| Lag threshold | `RAW_FRESHNESS_MAX_ALLOWED_LAG_DAYS` / `--max-allowed-lag-days` | `3` in prod |
| Report timezone | `DBT_REPORT_TIMEZONE` / `--report-timezone` | `Europe/Sofia` |
| State table dataset | `CFG_DATASET` / `--cfg-dataset` | `gads_reporting_cfg` |
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | unset (step is inert) |

The report timezone must match the dbt `report_timezone` var, otherwise the
alert set can drift from `mart_skipped_accounts` by a day.

## Currently excluded (as of 2026-08-01)

| Account | ID | Last raw date | Lag |
|---|---|---|---|
| Balkan eCommerce Summit | 4532197439 | 2026-04-25 | 98d |
| Tiger Technology | 5861433372 | 2026-06-03 | 59d |
| Toprentacar - RO | 4151214925 | 2026-06-08 | 54d |
| Abrites | 4225655970 | 2026-06-08 | 54d |
| Onesleep RS | 5304022952 | 2026-06-15 | 47d |

These are ingestion-side failures — the Google Ads Data Transfer has stopped
delivering rows for them. Alerting surfaces the symptom; fixing it means
re-authorising or removing the accounts upstream.
