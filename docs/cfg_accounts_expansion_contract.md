# `cfg_accounts` Expansion Contract

Parent contracts:

- `docs/contracts.md`
- `docs/reporting_contract.md`
- `docs/auth_design.md`

## Purpose

Define the controlled expansion of `cfg_accounts` from the current pilot set to
the full managed account registry used by the reporting app.

This contract covers:

- what data must be curated per account
- the order of implementation
- what inputs are still required from the business side
- what validations must pass before the expansion is considered complete

This contract does not cover user access grants. Those remain in
`cfg_app_users` and are handled in the next step.

Status:

- initial curated expansion completed on `2026-04-09`

## Current State

Current repo seed:

- `94` curated accounts
- `40` active accounts
- client groups:
  - `idconsult`
  - `MV3`
  - `ITF`
  - `sexwell`
  - `matraci.bg`
  - `external`

Current seed file:

- `seeds/cfg_accounts.csv`

Current implemented columns:

- `client_id`
- `account_id`
- `account_name`
- `timezone`
- `currency`
- `is_active`
- `has_auction_insights`
- `has_ga4`
- `notes`

## Target Outcome

After this pass:

- every intended managed Google Ads account exists in `cfg_accounts`
- each account is assigned to the correct `client_id`
- each account has approved display name, timezone, and currency
- each account has approved feature flags for:
  - `has_ga4`
  - `has_auction_insights`
- the expanded seed is deployed to stage and prod
- the app selectors reflect the curated registry

Not included in this pass:

- expanding `cfg_app_users`
- testing viewer-specific access grants
- row-level BigQuery security

## Required Decisions Per Account

Each account row must be curated for:

- `client_id`
  logical client grouping used by the app and access layer
- `account_id`
  Google Ads customer ID without formatting punctuation
- `account_name`
  user-facing label shown in the app
- `timezone`
  IANA timezone used for freshness and date interpretation
- `currency`
  account native currency
- `is_active`
  whether the account should appear in the live reporting app
- `has_ga4`
  whether GA4 pages should be visible for that account
- `has_auction_insights`
  whether auction insights page should be visible for that account
- `notes`
  optional operator note

## Default Rules

Unless explicitly approved otherwise:

- `account_id` is stored as digits only
- `is_active` defaults to `true` only for accounts approved for the live app
- `has_ga4` defaults to `false` unless a GA4-backed source is confirmed
- `has_auction_insights` defaults to `false` unless an auction source is confirmed
- `notes` may be blank

## Review Outcome

The following were approved during the Phase 1 and Phase 2 review:

- final `client_id` grouping per account
- final `account_name`
- final `timezone`
- final `currency`
- final `is_active`
- final `has_ga4`
- final `has_auction_insights`

## Implementation Plan

### Phase 1. Candidate Inventory

- collect candidate accounts from the available reporting/raw datasets
- normalize account IDs and names
- prepare a review table

### Phase 2. Curated Mapping

- assign `client_id`
- assign display names
- assign timezone and currency
- assign feature flags
- mark inactive accounts where needed

### Phase 3. Seed Update

- update `seeds/cfg_accounts.csv`
- keep the file sorted and reviewable
- preserve existing pilot accounts unless explicitly replaced

### Phase 4. Deployment

- run `dbt seed` in stage
- validate `/api/options`
- run `dbt seed` in prod
- validate the app selectors and page visibility

### Phase 5. Post-Seed Validation

- verify the account selector shows the curated list
- verify GA4 pages only appear where `has_ga4 = true`
- verify Auction page only appears where `has_auction_insights = true`
- verify no inactive account appears in the live selector

## Validation Criteria

The expansion is complete only when:

- `seeds/cfg_accounts.csv` matches the approved curated list
- stage and prod `cfg_accounts` match the seed
- `/api/options` returns the expected accounts and flags
- the app navigation respects the feature flags
- the active account list is reviewed and accepted

## Risks

- incorrect `client_id` grouping will break access scoping later
- incorrect timezone will distort freshness expectations
- incorrect feature flags will expose empty report pages
- blindly importing all discovered accounts without curation will create noisy selectors and unclear ownership

## Recommended Next Action

The next step after this completed pass is:

1. expand and validate `cfg_app_users`
2. test client-level and account-level viewer access
3. confirm page visibility and selector behavior under restricted users
