# cfg_app_users Expansion Contract

Parent contracts:

- `docs/auth_design.md`
- `docs/reporting_contract.md`
- `docs/contracts.md`

Status: in progress

## Purpose

Define the controlled expansion of `cfg_app_users` so the hosted reporting app
can expose the expanded `cfg_accounts` registry only to the intended users.

## Scope

This pass covers:

- inventory of current live grants
- review format for new user grants
- validation rules before new grants are applied

This pass does not cover:

- building an admin UI for access management
- BigQuery row-level security
- per-report or per-metric restrictions

## Source Of Truth

Table:

- `gads-export-all.gads_reporting_cfg.cfg_app_users`

This table is operational config and is maintained directly in BigQuery.

## Grain

- one row per user access grant

## Required Fields

- `email`
- `client_id`
- `account_id`
- `role`
- `is_active`

## Field Rules

### `email`

- lowercase Google account email
- one user may have multiple rows

### `client_id`

- must match an existing `cfg_accounts.client_id`
- use `__all__` only for `admin` rows

### `account_id`

- specific account ID for one-account access
- `__all__` for all accounts under the given `client_id`
- for `admin`, use `__all__`

### `role`

- allowed values:
  - `admin`
  - `viewer`

### `is_active`

- `true` means the grant is live
- `false` means the grant is soft-disabled and ignored by the app

## Access Rules

- `admin + __all__ / __all__` gives full app access
- `viewer + client_id / __all__` gives all accounts under one client
- `viewer + client_id / specific account_id` gives one-account access
- one account belongs to one `client_id` in `cfg_accounts`
- multi-client access is achieved by multiple `cfg_app_users` rows, not by
  duplicating accounts across client groups

## Current Live Grants

Current live rows at contract creation time:

- `biordanov@gmail.com` -> `viewer` -> `ITF / __all__`
- `biordanov@gmail.com` -> `viewer` -> `matraci.bg / 4848659150`
- `biordanov@gmail.com` -> `viewer` -> `sexwell / __all__`
- `blago@idconsult.bg` -> `admin` -> `__all__ / __all__`
- `deni@idconsult.bg` -> `admin` -> `__all__ / __all__`
- `kalina@idconsult.bg` -> `admin` -> `__all__ / __all__`
- `vlado@idconsult.bg` -> `admin` -> `__all__ / __all__`

## Review Input Format

Use one row per desired grant:

`email, role, client_id, account_id, is_active, notes`

Examples:

- `user@client.com, viewer, ITF, __all__, true, all ITF accounts`
- `user@client.com, viewer, MV3, 1234567890, true, one account only`
- `admin@agency.com, admin, __all__, __all__, true, full access`

## Validation Before Applying Grants

Before inserting or updating grants:

1. confirm every `client_id` exists in `cfg_accounts`
2. confirm every specific `account_id` exists under the same `client_id`
3. normalize email to lowercase
4. normalize wildcard access to `__all__`
5. reject duplicate active rows

## Validation After Applying Grants

After changes are applied:

1. query `cfg_app_users` and confirm the expected rows exist
2. test one restricted login for a viewer
3. verify the viewer sees only allowed client/account options
4. verify disallowed accounts do not load through direct URL parameters

## Next Step

- fill and review `docs/cfg_app_users_review_sheet.csv`
- apply approved grants to `gads_reporting_cfg.cfg_app_users`
- run a restricted-user QA pass
