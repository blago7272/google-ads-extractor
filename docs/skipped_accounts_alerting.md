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

1. **Takes the stale accounts** from the `raw_freshness_gate` step's results: the one
   freshness rule (`docs/operations_design.md`, Account Freshness), the same verdicts
   `stg_account_freshness` reads. The alert set is therefore exactly what the marts
   exclude (`mart_skipped_accounts`); the alert has no rule of its own.
2. **Diffs** that set against the previous release's, read from
   `<cfg_dataset>.ops_account_freshness`. The gate step appends every account's
   verdict there (day-partitioned, written with a load job so it costs nothing and
   avoids the streaming buffer). It replaced `ops_skipped_accounts_state`, which is
   no longer written; the first run after the switch reads it once instead of
   starting a new baseline.
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

With no prior state in either table, the first run reports
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

`scripts/create_monitoring_alert_policies.sh` creates these policies (plus one on any
failed execution of the job) with an email notification channel. `--check` (the default)
only prints them; `--apply --email ADDRESS` creates them, or updates them in place by
display name. The "still excluded" policy is opt-in (`--include-still-excluded`): it
matches every run while any account is excluded, which today means every day.

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
| Lag threshold | `raw_freshness_max_allowed_lag_days` in `dbt_project.yml`; `RAW_FRESHNESS_MAX_ALLOWED_LAG_DAYS` overrides it (dbt too); `--max-allowed-lag-days` for one run | `3` |
| Report timezone | `report_timezone` in `dbt_project.yml` | `Europe/Sofia` |
| State table dataset | `CFG_DATASET` / `--cfg-dataset` | `gads_reporting_cfg` |
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | unset (step is inert) |

The threshold and timezone have one definition shared by the orchestrator and dbt,
so the alert set cannot drift from `mart_skipped_accounts`.

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
