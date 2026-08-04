# PMax Historical Scheduler Contract

## Status

- status: `implemented locally; live job and trigger require explicit approval`
- runtime project: `gads-export-all`
- runner: dedicated Cloud Run Job `pmax-historical-backfill` (not provisioned)
- trigger: Cloud Scheduler `pmax-historical-backfill-offpeak` (not created)
- rolling transfer: `Google Ads MCC 8179020903 PMax Creative Test` (read only)

## Purpose

Schedule the already ledgered, manual-only PMax historical executor without
competing with the daily rolling refresh. This contract does not alter the
rolling transfer, create a historical transfer, or run any historical date.

## Schedule And Isolation

| Control | Contracted value |
| --- | --- |
| Cloud Scheduler window | `15 2-7 * * *` in `Etc/UTC` (02:15–07:15 UTC) |
| Cloud Run Job | one task, parallelism 1, no Cloud Run retries |
| Scheduler retries | 0 |
| Historical transfer | separate and manual-only |
| History submission | at most one date per invocation and in flight |
| Rolling-state gate | skip when rolling is `PENDING` or `RUNNING` |

The off-peak window avoids the rolling transfer's daily `08:00 UTC` launch and
its observed queue. The rolling-state gate is authoritative: it performs a
read-only lookup of the rolling transfer immediately before a history submission
and exits successfully without touching the history ledger or transfer if any
rolling run is active. If that lookup fails, the job fails closed and submits
nothing.

The history ledger is a second independent guard: it suppresses a submission
while any historical date is `PENDING` or `RUNNING`. Therefore an overlapping
Cloud Scheduler trigger or API retry cannot create a second historical run.

## Deployment Sequence

1. Obtain explicit approval for the separate historical dataset and transfer;
   deploy it with `scripts/deploy_pmax_historical_transfer.sh --apply`.
2. Provision the dedicated job with
   `deploy/cloud_run/deploy_pmax_historical_backfill.sh --provision IMAGE_URI`.
   Its service account must have only the BigQuery and Data Transfer permissions
   needed by the existing historical executor.
3. Run and accept exactly one manual smoke date, `2026-07-02`. Validate all
   three report views and the ledger.
4. Run `deploy/cloud_run/create_pmax_historical_scheduler.sh --check` to verify
   the job command, one-task limits, and target schedule.
5. Only after smoke-test approval, run the scheduler script with `--apply`.

The scheduler service account must retain permission to invoke only this Cloud
Run Job. The job's runtime service account must be able to read the rolling
transfer state, manage only the historical transfer's manual runs, and read and
write only the historical ledger/dataset. IAM bindings are a deployment-time
preflight, not created by these scripts.

## Monitoring And Change Control

- Inspect the rolling transfer during the first three scheduled days; a
  rolling-state skip is healthy evidence, not an error.
- Do not increase the six daily trigger opportunities until the smoke test and
  three-day rolling-health observation show no delayed or failed rolling run.
- Any increase in history cadence, in-flight limit, retry policy, destination,
  or transfer identity requires a contract change and renewed approval.

## Non-Goals

- schedule or change the rolling `gads_pmax_creative_test` transfer;
- bypass the rolling-state or ledger gate;
- add direct Google Ads API labels; or
- create a reporting consumer.
