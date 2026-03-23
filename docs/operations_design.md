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
- the reporting stack rebuilds after the raw import window
- the current pilot account runs in `Europe/Sofia`

## Daily Schedule

Recommended default schedule in `Europe/Sofia` time:

### 1. Raw Freshness Check

- `06:30`
- validate that raw data exists through the expected last date

### 2. Stage Build

- `07:00`
- run dbt staging models in `stage`

### 3. Stage Tests

- `07:10`
- run dbt tests in `stage`

### 4. Prod Build

- `07:30`
- run dbt marts in `prod` only if stage succeeded

### 5. Prod Tests

- `07:40`
- run full dbt tests in `prod`

### 6. Freshness Snapshot

- `07:50`
- persist or refresh `mart_data_freshness` once implemented

Why one daily cycle first:

- the current product is an ads-only reporting layer
- daily full builds are operationally simpler
- extra intraday runs can be added later if the HTML app needs them

## Jobs To Schedule

Recommended job set:

- `reporting-raw-freshness-check`
- `reporting-dbt-stage-build`
- `reporting-dbt-stage-test`
- `reporting-dbt-prod-build`
- `reporting-dbt-prod-test`

Optional later:

- `reporting-dbt-prod-intraday-refresh`
- `reporting-backfill-run`

## Build Policy

Stage policy:

- run on every merged change or on the daily release window
- must pass before prod promotion

Prod policy:

- run only from a known stage-validated revision
- prefer a single promoted artifact, not separate ad hoc builds

Failure policy:

- if stage fails, skip prod
- if prod build fails, alert immediately
- if prod tests fail after build, mark the release unhealthy and alert immediately

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

## Phase-1 Non-Goals

- 24x7 on-call
- streaming or near-real-time rebuilds
- automated self-healing backfills
- fully automated release promotion without a human-reviewed stage pass

## Decision Summary

- one daily operating cycle in `Europe/Sofia`
- stage before prod
- explicit freshness and test gates
- separate backfill path
- alert on failures and freshness drift immediately
