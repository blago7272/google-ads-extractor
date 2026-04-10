# Report Hosting — Improvement Areas

## Purpose

This document captures identified gaps and improvement areas for the report hosting contract defined in `docs/report_hosting_contract.md`.

Each item is a recommended addition to the hosting contract or a design clarification that should be resolved before production rollout.

## Cost and Scaling Constraints

The hosting contract does not define resource limits or scaling behavior for the `Cloud Run service`.

The priority is to keep costs low.

Requirements:

- `min-instances: 0` for both stage and prod (scale to zero when idle)
- `max-instances: 1` for stage, `2` for prod
- CPU allocation: request-based (CPU billed only during request processing)
- concurrency: `80` requests per instance
- resources per instance: `1 vCPU / 512MB`
- request timeout: `60s`

Trade-offs:

- scale-to-zero means cold starts of approximately 2-5 seconds on the first request after idle
- if cold starts become unacceptable for prod, `min-instances` for prod may be raised to `1` at an estimated additional cost of $15-25/month
- at light usage with scale-to-zero, the service is expected to remain within or near the Cloud Run free tier

## Secret Management

The hosting contract mentions environment variables but does not specify how secrets are stored.

Requirements:

- all secrets must be stored in `Secret Manager`, not in plain environment variables
- the `Cloud Run service` must mount secrets at runtime, not bake them into the image
- service account keys should be avoided where possible in favor of workload identity

## CI/CD Contract

The hosting contract lists deployment scripts as an open item but does not define the delivery path.

Requirements:

- container images must be stored in `Artifact Registry`
- builds should be triggered by a defined event (merge to main, tag, or manual trigger)
- the promotion path from stage to prod must be explicit (e.g., manual promotion, not automatic)
- no deploy should depend on a developer laptop

## IAP vs Cloud Run Auth — Design Decision

The hosting contract classifies the choice between `Cloud Run` built-in authentication and HTTPS Load Balancer + `IAP` as an implementation task.

This is a design decision because:

- it changes the DNS and network architecture
- it affects whether a load balancer is required
- it determines cost and operational complexity

This choice must be resolved and documented before deployment scripts are written.

## Monitoring and Alerting

The hosting contract requires Cloud Logging and a `/healthz` endpoint but does not define what acts on them.

Requirements:

- an uptime check must poll `/healthz` at a defined interval
- an alert must fire if the health check fails for a defined duration
- error-rate and latency thresholds should be defined as operational targets, even if informal

## Rollback Procedure

The hosting contract enables rollback through commit-SHA-tagged images but does not define when or how rollback happens.

Requirements:

- rollback must be possible by redeploying a previous image tag
- the trigger for rollback should be defined (manual, or automated on health check failure)
- the previous known-good image tag must be discoverable (e.g., from deploy history or Artifact Registry)

## Stage/Prod Data Isolation

The hosting contract does not clarify whether stage and prod read from the same BigQuery datasets.

Clarification needed:

- if both environments read the same datasets, stage queries could affect prod data availability or cost
- options:
  - same datasets with query limits on the stage service account
  - separate stage datasets populated by a copy or snapshot
- the chosen approach must be documented

## CORS and Content Security Policy

If the reporting app serves both HTML and API from the same origin, no CORS policy may be needed.

However, if any cross-origin access is planned (e.g., WordPress embedding the app in an iframe), the contract must state:

- whether cross-origin access is allowed
- which origins are permitted
- whether `Content-Security-Policy` headers are set

If no cross-origin access is planned, the contract should state that explicitly.

## Service Account Environment Isolation

The hosting contract names a single `reporting-app` service account.

Recommendation:

- use `reporting-app-stage` and `reporting-app-prod` as separate identities
- this enforces environment isolation at the IAM level
- prevents a stage misconfiguration from affecting prod permissions

## Data Freshness Contract

The reporting app reads marts built by the `reporting-release-orchestrator`. The hosting contract does not define behavior when data is stale.

Requirements:

- the app should expose a staleness indicator (e.g., last-refresh timestamp visible in the UI or via an API endpoint)
- define acceptable staleness threshold (phase-1 baseline: stale after 36h, error after 72h)
- if the orchestrator fails, the app should degrade gracefully rather than show broken or empty reports

## Session and Timeout Behavior

IAP handles authentication, but the hosting contract does not define session lifecycle.

Clarification needed:

- what happens when an IAP session expires during active use
- whether the user is redirected to re-authenticate or sees an error
- recommended IAP session length for the reporting use case

## Hardcoded Table References

The Data Access Boundary in the hosting contract lists specific BigQuery table paths.

Risk:

- these references will break if datasets are renamed or restructured

Recommendation:

- reference tables through a configuration layer (e.g., environment variable or config file listing allowed tables)
- or use BigQuery views as a stable interface between the data layer and the app
- the app should not embed dataset paths in application code
