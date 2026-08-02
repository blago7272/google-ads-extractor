# Report Backlog Contract

## Purpose

This document tracks approved but not yet implemented reporting work.

Use it for:

- pending UI improvements
- deferred modeling work
- deferred infrastructure work
- implementation notes that should not be lost between passes

This is not a decision log. Approved design decisions belong in the main contracts. This backlog is only for open delivery items.

## Status Values

- `pending`: approved and not started
- `in_progress`: currently being implemented
- `deferred`: intentionally postponed

## Current Backlog

### Reporting Logic

- id: `ads.keyword_daily_fact_mart`
  status: `deferred`
  area: `ads`
  description: Add a daily keyword fact mart so date-windowed keyword reporting can be exact instead of overlap-based rollups.

- id: `ga4.help_screen_generation`
  status: `pending`
  area: `app`
  description: Generate a dedicated help screen from `docs/report_help_contract.md`.

### Hosting

- id: `hosting.custom_domain_lb_iap`
  status: `pending`
  area: `hosting`
  description: Finish the production HTTPS Load Balancer, managed certificate, IAP setup, and custom subdomain routing.

- id: `hosting.review_ready_cloud_run_validation`
  status: `pending`
  area: `hosting`
  description: Re-validate the hosted app runtime and confirm the deployed service entrypoint and protected URL are review-ready.

## Change Rules

- Add an item here when implementation is agreed but not completed.
- Remove an item only when the implementation is live and validated.
- Keep each entry concrete enough to turn into a ticket without re-discovery.
