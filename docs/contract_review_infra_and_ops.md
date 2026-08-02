# Contract Review: Infrastructure And Operations Design

This document captures review comments on the infrastructure and operations
design proposals (`infrastructure_design.md` and `operations_design.md`) as they
relate to the reporting contract.

Parent contract: `docs/reporting_contract.md`

Reviewed documents:

- `docs/infrastructure_design.md`
- `docs/operations_design.md`

---

## Infrastructure Design Review

### Overall Assessment

The infrastructure design is well-scoped for phase 1. Explicit dataset naming,
single GCP project, least-privilege service accounts, and a clear promotion flow
are all strong foundations.

### Comment 1: Dev Dataset Cleanup

Status: `PROPOSAL`

`*_dev_<owner>` datasets will accumulate over time as developers create and
abandon them.

Recommendation:

- add a housekeeping rule, for example: dev datasets are ephemeral and may be
  cleaned after 7 days of inactivity
- alternatively, set a BigQuery default table expiration on dev datasets so
  tables auto-expire after a defined period
- document this policy in `infrastructure_design.md` under the dataset naming
  section

### Comment 2: Container Image Versioning

Status: `PROPOSAL`

The promotion flow says "promote the same container/image revision to prod" but
does not specify where images are stored or how they are tagged.

Recommendation:

- use Google Artifact Registry for dbt container images
- tag images with the git commit SHA, never use `:latest` in prod
- document the tagging convention in `infrastructure_design.md` under the
  deployment pattern section

### Comment 3: Incremental Materialization Trigger

Status: `PROPOSAL`

The document lists priority candidates for incremental materialization but does
not define when the switch should happen.

Recommendation:

- add a concrete threshold, for example: when a single mart exceeds 1M rows or
  daily rebuild cost exceeds a defined dollar amount, convert to incremental
  partition-overwrite
- this avoids the risk of either switching too early (added complexity) or too
  late (unnecessary cost)

### Comment 4: Stage Build Data Scope

Status: `PROPOSAL`

Stage reads the same `gads_raw` as prod. This is correct for validation but means
stage rebuilds process all production data. As client count grows, this becomes a
cost concern.

Recommendation:

- consider a `--vars 'lookback_days: 30'` approach for stage builds so they
  validate logic against recent data without rebuilding full history
- this is not needed immediately but should be planned before onboarding a second
  or third client

### Comment 5: Disaster Recovery Note

Status: `PROPOSAL`

Neither document addresses what happens if someone accidentally drops a prod mart
dataset.

Recommendation:

- document that prod datasets rely on BigQuery time travel for recovery (7-day
  default window)
- confirm the time travel window is sufficient or increase it to 14 days via
  dataset-level configuration
- note that no additional backup strategy is planned for phase 1

---

## Operations Design Review

### Overall Assessment

The operations design is practical and appropriately scoped. Stage-before-prod
gating, explicit freshness states, separate backfill path, and a clear failure
runbook are all strong choices.

### Comment 6: Raw Import Completion Window

Status: `PROPOSAL`

The schedule starts the freshness check at 06:30 Sofia time, but the expected raw
import completion time is not documented.

Recommendation:

- document the expected Google Ads transfer completion window, for example:
  "Google Ads BigQuery transfer typically completes by 05:00-06:00 Sofia time"
- this validates that the 06:30 freshness check has an adequate buffer
- if the completion window is later than expected, the entire schedule shifts

### Comment 7: Event-Driven Prod Trigger

Status: `PROPOSAL`

The stage build starts at 07:00 and the prod build at 07:30 on a fixed clock.
With 30 minutes between them, this is tight if the model count grows or a large
backfill is running.

Recommendation:

- make the prod build conditional on stage completion rather than a fixed clock
  time
- Cloud Scheduler can trigger a single Cloud Run job that chains the steps:
  run stage build, run stage tests, if both pass then run prod build, run prod
  tests
- this eliminates the risk of prod starting before stage finishes

### Comment 8: Build Duration Alerting

Status: `PROPOSAL`

The logging section captures execution time, which is good. But there is no alert
for abnormal build durations.

Recommendation:

- add a build duration alert: if the prod build takes more than 2x its 7-day
  rolling average, trigger a warning
- this catches performance regressions (new model, bad join, missing partition
  pruning) before they become cost problems
- can be implemented as a simple Cloud Monitoring metric on the Cloud Run job
  duration

### Comment 9: Row Count Drop Detection Mechanism

Status: `PROPOSAL`

"Account row counts drop abnormally versus recent baseline" is listed as an alert
trigger condition, but no implementation mechanism is specified.

Recommendation:

- implement as a dbt test or a post-build metadata query that compares today's
  mart row count per account against a rolling 7-day average
- flag when any account's row count drops by more than a defined percentage, for
  example 25%
- mark this item as "implementation pending" in the operations document so it is
  tracked

### Comment 10: Backfill Access Control

Status: `PROPOSAL`

The backfill parameters are well-defined but there is no access control
specification.

Recommendation:

- add a simple rule: prod backfills require the technical owner or data owner
- dev and stage backfills can be triggered by any team member
- this does not need to be enforced technically in phase 1 but should be
  documented as policy

### Comment 11: Positive Build Confirmation

Status: `PROPOSAL`

The alert section only covers failure conditions. There is no notification when
the build succeeds.

Recommendation:

- add a daily "build healthy" summary, even a simple Slack message or email
  confirming the pipeline ran successfully
- this gives the team positive confirmation rather than requiring them to assume
  silence means success
- particularly important during the first weeks of production operation

---

## Cross-Document Gaps

### Comment 12: CI/CD Pipeline Tooling

Status: `PROPOSAL`

Infrastructure says "merge to main, deploy to stage" and operations says "stage
must pass before prod." Neither document specifies the CI/CD tooling.

Recommendation:

- add a short section in `infrastructure_design.md` specifying the CI tool:
  GitHub Actions, Cloud Build, or manual `gcloud run jobs execute`
- document the minimum CI pipeline steps: lint, compile, stage deploy, stage
  test, prod deploy, prod test
- this can be a single paragraph; it does not need to be a full CI/CD design

### Comment 13: Seed Promotion Path

Status: `PROPOSAL`

When `cfg_exchange_rates` or `cfg_accounts` changes in git, does it follow the
same stage-to-prod flow as model changes?

Recommendation:

- document in `operations_design.md` that seed changes follow the same promotion
  path: merge to main, `dbt seed --full-refresh` in stage, validate, then
  `dbt seed --full-refresh` in prod
- note that `dbt seed --full-refresh` has different semantics than `dbt run` and
  should be called explicitly when seed data changes, not as part of every daily
  build

### Comment 14: Raw Freshness Check Implementation

Status: `PROPOSAL`

The job `reporting-raw-freshness-check` is listed in the schedule but has no
implementation detail.

Recommendation:

- specify the approach: dbt source freshness, a custom BigQuery query against
  `INFORMATION_SCHEMA.PARTITIONS`, or a direct `max(segments_date)` probe
  against the raw tables
- the earlier reporting contract noted that wildcarded source shapes may make
  standard dbt source freshness brittle, so the chosen approach should be
  documented explicitly

---

## Priority And Sequencing

| # | Comment | Priority | Blocks Phase 1 |
|---|---------|----------|-----------------|
| 7 | Event-driven prod trigger | High | No, but reduces failure risk |
| 6 | Raw import completion window | High | No, but validates schedule |
| 14 | Raw freshness check implementation | Medium | Yes, if freshness is a phase-1 deliverable |
| 12 | CI/CD pipeline tooling | Medium | Yes, for repeatable deployments |
| 13 | Seed promotion path | Medium | No, but avoids confusion |
| 2 | Container image versioning | Medium | No, but needed before first prod deploy |
| 5 | Disaster recovery note | Low | No |
| 11 | Positive build confirmation | Low | No |
| 1 | Dev dataset cleanup | Low | No |
| 3 | Incremental trigger threshold | Low | No, not relevant until scale |
| 4 | Stage build data scope | Low | No, not relevant until scale |
| 8 | Build duration alerting | Low | No |
| 9 | Row count drop detection | Low | No |
| 10 | Backfill access control | Low | No |
