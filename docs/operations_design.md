# Operations Design

This document defines the recommended scheduling, monitoring, backfill, and operational controls for the reporting stack.

## Goals

- keep the reporting data fresh and predictable
- detect raw-import gaps early
- surface failing builds before users see stale data
- support safe backfills without ad hoc manual SQL

## Phase-1 Operating Assumptions

- reporting is primarily T-1, not real-time
- raw Google Ads imports land in `gads_raw`
- `gads_raw.p_ads_AccountStats_*` is the canonical daily raw-presence source for release gating
- Google Ads raw transfer is expected to complete by `05:00-06:00` `Europe/Sofia` for the current pilot
- the scheduled reporting release starts at `06:30`, leaving a `30-90` minute buffer after the expected raw import window
- if the raw transfer completion window shifts later for `3` consecutive operating days, move the release window rather than raising the freshness threshold
- the current pilot account runs in `Europe/Sofia`

## Daily Release Window

Recommended default release window in `Europe/Sofia` time:

### 1. Scheduler Start

- `06:30`
- trigger one `reporting-release-orchestrator` job

### 2. Orchestrated Release Sequence

The orchestrator runs these steps in order:

1. `raw_freshness_gate`: applies the freshness rule to every active account and records
   the verdicts (see Account Freshness). Never blocks: stale accounts are excluded from
   the marts instead.
2. `skipped_accounts_alert`: announces accounts that dropped out of or rejoined the marts
3. `ecb_fx_refresh`: refreshes ECB exchange rates (retries, then keeps stored rates)
4. `stage_build` and `stage_test`: only with `--include-stage` (or `--skip-prod`)
5. `prod_build`
6. `prod_test`
7. `telegram_daily_summary`

Rules:

- each step starts only after the previous step succeeds
- prod never starts from a fixed clock gap after stage
- the same container or image revision must be used from stage validation through prod release
- the release stops on the first failing step and alerts the ops chat (see Monitoring And Alerts)

Why one daily cycle first:

- the current product is an ads-only reporting layer
- daily full builds are operationally simpler
- extra intraday runs can be added later if the HTML app needs them

Why one orchestrator first:

- it removes the race between stage and prod
- it keeps `Cloud Scheduler` simple
- it creates one release log stream per operating day
- it is enough for phase 1 without introducing workflow tooling yet

## Jobs To Schedule

Required scheduled job set:

- `reporting-release-orchestrator`

Recommended manual or on-demand jobs:

- `reporting-dbt-stage-build`
- `reporting-dbt-stage-test`
- `reporting-dbt-prod-build`
- `reporting-dbt-prod-test`
- `reporting-raw-freshness-check`
- `reporting-data-freshness-refresh`

- `reporting-dbt-prod-intraday-refresh`
- `reporting-backfill-run`

## Build Policy

Stage policy:

- run inside the daily orchestrated release window
- can also run manually on merged changes or hotfix validation
- must pass before prod promotion

Prod policy:

- run only if raw freshness and stage validation succeeded
- run only from a known stage-validated revision
- prefer a single promoted artifact, not separate ad hoc builds

Failure policy:

- if raw freshness fails, stop before stage and alert immediately
- if stage fails, skip prod
- if prod build fails, alert immediately
- if prod tests fail after build, mark the release unhealthy and alert immediately

## Account Freshness

### The rule

One rule decides whether an account's data is current, everywhere it is used: the
release log, the skipped-accounts alert, which accounts the marts include, and the
user-facing `mart_data_freshness`.

```
lag_days = today in report_timezone - last raw date (max segments_date in gads_raw.p_ads_AccountStats_*)
stale    = lag_days > threshold, or no raw data at all
```

- `report_timezone` (`Europe/Sofia`) and the threshold (`raw_freshness_max_allowed_lag_days`,
  `3`) are the `vars` in `dbt_project.yml`. `orchestration/raw_freshness.py` reads that
  file, so dbt and the orchestrator cannot drift. `RAW_FRESHNESS_MAX_ALLOWED_LAG_DAYS`
  overrides the threshold for both; `--max-allowed-lag-days` overrides it for one run
  and is passed on to dbt.
- Only active accounts (`cfg_accounts.is_active = true`) are evaluated.
- A stale account is excluded from every mart; the release is not blocked. It rejoins
  the marts automatically once its raw data resumes.

### Where it is applied

1. **`raw_freshness_gate` step** (`orchestration/raw_freshness.py`): applies the rule to
   every active account, logs `raw_freshness_summary` (and `raw_freshness_gate_warning`
   listing stale accounts), and appends one row per account to
   `gads_reporting_cfg.ops_account_freshness`.
2. **`skipped_accounts_alert` step**: takes the same results, diffs the stale set against
   the previous run in `ops_account_freshness`, and announces changes
   (`docs/skipped_accounts_alerting.md`).
3. **`stg_account_freshness`** (a table): reads this run's rows from
   `ops_account_freshness` (the orchestrator passes `ACCOUNT_FRESHNESS_RUN_TS` to dbt).
   With no usable recorded run it applies the rule in SQL; `freshness_source` says which
   (`ops_account_freshness` or `computed_in_dbt`). That happens when the write failed, or
   on a manual dbt run when no run is recorded for today's report date. Every mart joins
   it and keeps only `healthy` accounts.
4. **`mart_data_freshness`** (a view): the user-facing status, below.

### `ops_account_freshness` (audit trail)

Append-only, never truncated; partitioned by day on `run_timestamp`, clustered by
`account_id`. One row per active account per release:

| Column | Meaning |
|---|---|
| `run_timestamp` | The release's execution timestamp; identifies the run |
| `report_date` | Today in `report_timezone` at run time |
| `account_id`, `client_id`, `account_name` | From `cfg_accounts` |
| `last_raw_date` | Latest raw date, NULL if none |
| `lag_days` | `report_date - last_raw_date`, NULL if no raw data |
| `status` | `healthy` (in the marts) or `stale` (excluded) |
| `max_allowed_lag_days`, `report_timezone` | The settings the verdict used |

It replaces `ops_skipped_accounts_state`, which is no longer written; the alert reads it
once, on the first run after the switch, so that run is not treated as a baseline.

### User-facing status: `mart_data_freshness`

A view over `mart_account_freshness_snapshot` (the verdicts this build's marts were built
with). `lag_days` is measured when the view is read, so if a release fails the status
keeps degrading instead of freezing at the last build.

| Status | Condition |
|---|---|
| `ok` | lag ≤ 1 day (data through yesterday) |
| `stale` | 1 < lag ≤ threshold (behind, still in the marts) |
| `error` | lag > threshold (excluded from the marts) |
| `backfilling` | no raw data at all |

`excluded_from_marts` says whether the current marts were built without the account.
Between midnight and the morning release every account shows lag 2 (`stale`) until that
day's data is built; the reporting app and the Telegram summary are read after it.

## Monitoring And Alerts

Recommended alert channels:

- email for build failures
- Slack for operational alerts if a team channel exists

Trigger conditions:

- stage build failure
- prod build failure
- prod test failure
- freshness status moves to `error`
- account row counts drop abnormally versus recent baseline

Minimum alert payload:

- environment
- job name
- failing step
- commit or image revision
- affected accounts if known
- expected last date and observed last raw date for freshness failures
- link to logs

### What is implemented

- **Failed release → ops Telegram chat.** Every failure path of the orchestrator logs
  `release_failed` (ERROR) and posts the failing step, the error and the Cloud Run
  execution name to the ops chat (`TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`,
  `orchestration/ops_telegram.py`). That covers a failed step, an unexpected exception,
  invalid job arguments, and an import error in the orchestrator itself (caught by
  `scripts/release_orchestrator.py`). A crash that kills the container outright (out of
  memory, a timeout) never reaches this code; the Cloud Monitoring policies cover that.
- **Cloud Monitoring.** `scripts/create_monitoring_alert_policies.sh` creates the
  log-based alert policies; see `docs/skipped_accounts_alerting.md`.
- **ECB fallback.** A warning to the same chat when the ECB API is down and the release
  keeps the stored rates; see `docs/fx_rates_operations.md`.

## Logging

Keep logs in Cloud Logging with searchable fields for:

- environment
- dbt command
- git revision
- execution time
- job status
- affected model count

Recommended retention:

- at least `30` days in phase 1

## Backfill Strategy

Use a separate operational path for backfills.

Rules:

- never hide backfill logic inside the normal daily schedule
- backfills must declare account scope and date range
- backfills must be idempotent
- backfills must log exactly what date range was rebuilt

Recommended backfill parameters:

- `environment`
- `account_id` or account list
- `start_date`
- `end_date`
- `models`

Recommended backfill modes:

- `full_refresh` for small marts
- `partition_overwrite` for heavy daily marts once incremental materializations are introduced

## Cost And Performance Controls

Phase-1 controls:

- daily build only
- no unnecessary intraday jobs
- partition large daily marts once materializations are upgraded
- monitor query bytes for `mart_ads_search_terms` and `mart_ads_ad_performance_daily`

Scale trigger:

- if daily mart rebuild cost becomes material, convert the largest marts to incremental partition-overwrite first

## Runbook Expectations

When a build fails:

1. identify whether the failure is raw-data freshness, dbt compile, dbt run, or dbt test
2. check whether the issue is account-specific or global
3. decide whether to rerun, backfill, or hold prod
4. record the incident date and resolution

When freshness fails:

1. verify the raw import gap
2. confirm whether the account was intentionally paused or newly onboarded
3. decide whether to wait, rerun ingestion, or backfill
4. if the release window itself is too early for `3` consecutive days, update the scheduled start time and document the new raw import completion window

## Phase-1 Non-Goals

- 24x7 on-call
- streaming or near-real-time rebuilds
- automated self-healing backfills
- fully automated release promotion without a human-reviewed stage pass

## Decision Summary

- one daily orchestrated release cycle in `Europe/Sofia`
- one scheduled `reporting-release-orchestrator` job instead of fixed independent stage and prod clocks
- raw freshness is a custom BigQuery gate against `gads_raw.p_ads_AccountStats_*`
- stage must pass before prod promotion
- explicit freshness and test gates
- separate backfill path
- alert on failures and freshness drift immediately
