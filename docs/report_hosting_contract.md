# Report Hosting Contract

## Purpose

This document defines the target production hosting model for the reporting application layer.

It covers:

- stable web hosting for the FastAPI report app
- end-user access control
- runtime separation from the developer laptop
- subdomain and DNS expectations
- relationship to the existing WordPress site

It does not replace the data-pipeline contracts in:

- `docs/reporting_contract.md`
- `docs/ga4_reporting_contract.md`
- `docs/infrastructure_design.md`
- `docs/operations_design.md`

## Hosting Decision

The stable application runtime will be:

- a containerized FastAPI app
- deployed as a `Cloud Run service`
- running in GCP, not on a local machine

The current local `uvicorn` preview is a development-only runtime and is not part of the target production architecture.

## Runtime Topology

Production application flow:

1. user opens the reporting URL
2. request reaches a GCP-hosted HTTPS endpoint
3. access control is enforced before the app is reached
4. the `Cloud Run service` serves the HTML and API endpoints
5. the app reads from BigQuery with a read-only service account

Data-refresh flow remains separate:

- reporting data is built by the existing `reporting-release-orchestrator` `Cloud Run Job`
- the app does not build marts itself
- the app only reads prepared marts and approved source tables

## Access Control Contract

End-user access control will not be implemented inside the FastAPI application.

The approved production access pattern is:

- `IAP` in front of the hosted reporting app
- HTTPS Load Balancer in front of the app service
- access granted only to approved Google users or Google Groups

This means:

- the app itself stays simple
- users authenticate with Google
- unauthorized users are blocked before the request reaches the app
- session lifecycle is managed by Google authentication and `IAP`
- expired sessions should result in re-authentication rather than custom in-app session handling

The app still needs a dedicated runtime identity:

- service account: `reporting-app`
- permissions: read-only access to reporting datasets and approved source tables
- no write access to reporting datasets
- no access to `gads_raw` unless explicitly approved later

For environment isolation, the preferred runtime identities are:

- `reporting-app-stage`
- `reporting-app-prod`

## Data Access Boundary

The hosted reporting app may read:

- `gads_reporting_cfg`
- `gads_reporting_mart`
- approved source-local tables currently used by the UI:
  - `experimental-clients.sexwell_analyses.gads--impression_share--daily`
  - `experimental-clients.sexwell_analyses.gads--impression_share--weekly`
  - `experimental-clients.sexwell_analyses.gads--impression_share--monthly`
  - `experimental-clients.sexwell_analyses.GA4-345365542--historical`
  - approved ERP enrichment views if used by GA4 reporting

The app must not require the developer laptop, local credentials outside the runtime service account, or any local process to serve end users.

Application code should not depend long-term on hardcoded external source-table paths.

The preferred stable interface is:

- reporting-layer views
- or a configuration layer that resolves approved table names

The app should read stable reporting interfaces rather than raw source paths embedded in Python code.

## Environment Contract

Recommended app environments:

- `stage`
- `prod`

Expected usage:

- `stage`: internal QA and review
- `prod`: approved stakeholder access

Both environments should:

- run the same application codebase
- use explicit environment variables
- use commit-SHA-tagged images

Environment data isolation is required:

- `stage` app reads `stage` reporting datasets
- `prod` app reads `prod` reporting datasets

The hosted app must not point `stage` and `prod` at the same reporting marts.

## URL And Domain Contract

Recommended URL pattern:

- `reports.yourdomain.com` -> production app
- optional `reports-stage.yourdomain.com` -> stage app

This subdomain is intentionally independent from WordPress.

That means:

- the root site can stay on WordPress
- the reporting app can be hosted fully in GCP
- the only shared element may be DNS ownership under the same domain

WordPress is not a runtime dependency for the reporting application.

## DNS Contract

DNS will be managed where the domain is hosted, for example in SuperHosting.BG.

The domain host is responsible only for:

- creating the required DNS record for the reporting subdomain
- pointing that record to the GCP endpoint defined by the final deployment pattern

Two acceptable final patterns:

1. direct custom-domain mapping to the app service when compatible with the chosen access layer
2. subdomain mapped to an HTTPS Load Balancer in front of the app

The approved production network pattern is:

- custom subdomain
- HTTPS Load Balancer
- `IAP`
- backend `Cloud Run service`

## WordPress Relationship

The reporting app is a separate product surface.

Allowed WordPress relationship:

- optional menu link from WordPress to the reports URL

Not required:

- embedding the report app inside WordPress
- using WordPress authentication for the app
- hosting reporting code inside WordPress

No cross-origin embedding is planned in phase 1.

The expected browser access pattern is:

- same-origin HTML and API delivery
- no iframe embedding from WordPress
- no cross-origin API consumers by default

## Security Model

The security model has two distinct layers:

1. user access layer
   - controlled by `IAP`
   - determines who may open the application

2. data access layer
   - controlled by the `reporting-app` service account
   - determines what the application may read from BigQuery

If future requirements need per-client visibility restrictions, an extra layer must be added:

- app-level user-to-client authorization
- or BigQuery row-level security

That requirement is not part of the current phase-1 hosting contract.

## Operational Contract

The hosted app must support:

- stable HTTPS URL
- container image versioning by commit SHA
- redeploy without relying on a developer laptop
- Cloud Logging for request/debug visibility
- health check endpoint: `/healthz`

The hosted app runtime baseline is:

- `min-instances: 0` for `stage` and `prod`
- `max-instances: 1` for `stage`
- `max-instances: 2` for `prod`
- concurrency: `80`
- CPU allocation: request-based
- instance size: `1 vCPU / 512MB`
- request timeout: `60s`

Expected trade-off:

- scale-to-zero is preferred to keep phase-1 cost low
- cold starts are acceptable in phase 1
- if cold starts become unacceptable, `prod` may later move to `min-instances: 1`

The hosted app must not:

- depend on a local tunnel
- depend on a local `uvicorn` process
- require WordPress to proxy requests

Monitoring requirements:

- uptime check against `/healthz`
- alert on repeated health-check failure
- basic error-rate and latency monitoring in Cloud Monitoring

Rollback requirements:

- rollback must be possible by redeploying a previous commit-SHA-tagged image
- rollback is manual in phase 1
- the previously deployed image tag must remain discoverable from deploy history or Artifact Registry

Data freshness requirements:

- the app should expose the latest successful data-refresh timestamp
- the UI should warn when data is older than the approved freshness threshold
- stale data should degrade gracefully with an explicit warning rather than a broken page

Freshness baseline for phase 1:

- stale threshold: data older than `36h`
- error threshold: data older than `72h`

## Recommended First Production Rollout

1. package the FastAPI app as a production image
2. build and store images in `Artifact Registry`
3. deploy `stage` as a `Cloud Run service`
4. assign the `reporting-app-stage` service account with read-only BigQuery permissions
5. validate stage with internal users
6. deploy `prod` as a separate `Cloud Run service`
7. assign the `reporting-app-prod` service account with read-only BigQuery permissions
8. place `prod` behind the HTTPS Load Balancer and `IAP`
9. attach the reporting subdomain

## Delivery Contract

Deployment must not depend on a developer laptop.

Required delivery characteristics:

- images stored in `Artifact Registry`
- deployable images tagged by git commit SHA
- explicit promotion path from `stage` to `prod`
- production deployment triggered by a defined process, not ad hoc local steps

Phase-1 acceptable promotion model:

- merge to `main`
- build image
- deploy `stage`
- validate `stage`
- manually promote the same image SHA to `prod`

Automatic promotion from `stage` to `prod` is not part of phase 1.

## Secret Handling Note

Secret handling needs a dedicated implementation pass before production deployment.

Current contract note:

- avoid service account keys where possible
- prefer workload identity
- document which values are true secrets versus normal runtime configuration

## Open Implementation Items

The following are still implementation tasks, not unresolved design decisions:

- add app deployment scripts for `Cloud Run service`
- create the `reporting-app-stage` and `reporting-app-prod` service accounts if not already created
- define exact IAM bindings for BigQuery reads
- create the HTTPS Load Balancer and `IAP` configuration
- add freshness metadata to the app response and UI
- add stable reporting views or config indirection for external source tables
- add uptime checks and alert policies
- add CI/CD deployment scripts or pipeline configuration for app images and service rollout
- configure the production subdomain

## Approved Phase-1 Position

The reporting application will be hosted independently from the local machine and independently from WordPress.

The preferred production pattern is:

- `Cloud Run service`
- HTTPS Load Balancer + `IAP`
- separate `stage` and `prod` runtime identities
- separate `stage` and `prod` reporting datasets
- read-only runtime identity
- dedicated reporting subdomain
