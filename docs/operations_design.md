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
- if the raw transfer completion window shifts later for `3` consecutive operating days, move the release window rather than weakening the freshness gate
- the current pilot account runs in `Europe/Sofia`

## Daily Release Window

Recommended default release window in `Europe/Sofia` time:

### 1. Scheduler Start

- `06:30`
- trigger one `reporting-release-orchestrator` job

### 2. Orchestrated Release Sequence

The orchestrator runs these steps in order:

1. raw freshness gate
2. stage build
3. stage tests
4. prod build
5. prod tests
6. post-release freshness snapshot refresh

Rules:

- each step starts only after the previous step succeeds
- prod never starts from a fixed clock gap after stage
- the same container or image revision must be used from stage validation through prod release
- the release stops on the first failing gate and alerts immediately

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

## Raw Freshness Gate

Phase-1 implementation uses a custom BigQuery probe, not `dbt source freshness`.

Rationale:

- the raw Google Ads tables are wildcarded by transfer suffix
- release gating is account-specific, not only table-specific
- the gate must answer "do all active accounts have T-1 raw data yet?" before `dbt` starts

Canonical source:

- `gads_raw.p_ads_AccountStats_*`

Current phase-1 rule:

- every active account in `cfg_accounts` must have raw data through its expected `T-1` date
- expected `T-1` is computed in the account timezone from `cfg_accounts.timezone`
- inactive or intentionally paused accounts are excluded by `cfg_accounts.is_active = false`

Recommended probe outputs by account:

- `client_id`
- `account_id`
- `account_timezone`
- `expected_last_date`
- `last_raw_date`
- `days_lag`
- `freshness_status`
- `checked_at`

Gate behavior:

- pass when every active account has `last_raw_date >= expected_last_date`
- fail when any active account is behind its expected `T-1` date
- emit the failing account list in the alert payload

Recommended query shape:

```sql
with active_accounts as (
  select
    client_id,
    cast(account_id as string) as account_id,
    timezone as account_timezone
  from `gads-export-all.gads_reporting_cfg.cfg_accounts`
  where is_active = true
),
raw_max_dates as (
  select
    cast(customer_id as string) as account_id,
    max(segments_date) as last_raw_date
  from `gads-export-all.gads_raw.p_ads_AccountStats_*`
  group by 1
)
select
  a.client_id,
  a.account_id,
  a.account_timezone,
  date_sub(current_date(a.account_timezone), interval 1 day) as expected_last_date,
  r.last_raw_date,
  date_diff(
    date_sub(current_date(a.account_timezone), interval 1 day),
    r.last_raw_date,
    day
  ) as days_lag,
  case
    when r.last_raw_date >= date_sub(current_date(a.account_timezone), interval 1 day) then 'healthy'
    when r.last_raw_date is null then 'error'
    else 'error'
  end as freshness_status,
  current_timestamp() as checked_at
from active_accounts a
left join raw_max_dates r using (account_id);
```

Persistence and visibility:

- the pre-build gate writes structured results to `Cloud Logging`
- the post-build reporting surface remains `mart_data_freshness` once that mart is implemented
- if historical raw-freshness diagnostics become necessary, persist the same probe output to BigQuery without changing the gate contract

## Freshness Monitoring

Recommended freshness outputs by account:

- `last_data_date`
- `hours_since_last_data`
- `freshness_status`
- `last_successful_build_at`
- `last_successful_test_at`

Recommended freshness states:

- `healthy`
- `warning`
- `error`

Recommended thresholds:

- `healthy`: up to `36h`
- `warning`: more than `36h`
- `error`: more than `72h`

Recommended checks:

- raw freshness by account
- mart freshness by account
- missing-date gaps inside active account ranges

Recommended ownership split:

- the raw freshness gate blocks the daily release before `dbt`
- `mart_data_freshness` is the user-facing diagnostic surface after the release

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
