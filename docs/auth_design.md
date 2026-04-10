# Auth And Access Control Design

Parent contract: `docs/reporting_contract.md`

Status: approved direction, implementation pending

## Purpose

Define how the reporting web application authenticates users, maps them to
client data, and enforces access isolation at the application layer.

## Authentication Method

Google OAuth 2.0 via Google ID tokens.

- Users click "Sign in with Google" on the app.
- The login redirect issues a short-lived, httpOnly OAuth `state` cookie,
  marked `Secure` on HTTPS.
- The app receives a Google ID token, verifies it server-side, and extracts
  the user's email address.
- The OAuth callback must validate the returned `state` value against the
  cookie before issuing an application session.
- No passwords are stored or managed by the application.
- Session is maintained via a signed cookie, marked `Secure` on HTTPS.

## Session

- Duration: 24 hours.
- After expiry, the user must re-authenticate.
- Logout clears the session cookie immediately.
- The transient OAuth `state` cookie expires after a short interval and is
  cleared after callback success, mismatch, or restart.

## User-To-Client Mapping

A BigQuery table `cfg_app_users` in the `gads_reporting_cfg` dataset maps
authenticated emails to access grants.

This table is **not** a dbt seed. It is a manually maintained BigQuery table
to allow operational changes without a deploy cycle.

### Schema

| Column | Type | Description |
|--------|------|-------------|
| `email` | STRING | Google account email, lowercase |
| `client_id` | STRING | The client this grant applies to |
| `account_id` | STRING | Specific account within the client, or `__all__` for all accounts |
| `role` | STRING | `admin` or `viewer` |
| `is_active` | BOOLEAN | Soft-delete flag |

### Access Rules

- A user may have **multiple rows** — one per client or account they can access.
- `admin` role: can see all clients and all accounts. The `client_id` and
  `account_id` columns are ignored for admins; they receive the full client
  and account switcher.
- `viewer` role: can see only the clients and accounts listed in their rows.
  If a viewer has rows for `client_id=acme, account_id=__all__`, they see all
  accounts under `acme`. If they have `client_id=acme, account_id=12345`,
  they see only that one account.
- A viewer with grants across multiple clients sees a client switcher.
- A viewer with grants across multiple accounts within a client sees an
  account switcher.

### Example Data

```text
email,client_id,account_id,role,is_active
maria@agency.com,__all__,__all__,admin,true
ivan@agency.com,__all__,__all__,admin,true
contact@sexwell.bg,sexwell,__all__,viewer,true
manager@client-b.com,client_b,__all__,viewer,true
analyst@client-b.com,client_b,555666777,viewer,true
```

## Server-Side Enforcement

- Every BigQuery query from the app includes `WHERE client_id IN (@allowed_clients)`.
- For viewers, the allowed list is resolved from `cfg_app_users` at login and
  cached in the session. It is never taken from query parameters.
- For admins, the allowed list is all clients (no filter), but the UI provides
  a switcher so admins can focus on a specific client.
- Account-level filtering follows the same pattern using `account_id`.

## Report Visibility

- All report pages are visible to all authenticated users.
- GA4 and auction insights pages may have no data for a given client. When a
  report page returns zero rows, the app displays a notice:
  "No data available for this report. This data source may not be configured
  for your account."
- This avoids hiding pages and instead explains the absence clearly.

## App Changes Required

| Component | Change |
|-----------|--------|
| `app/main.py` | Add OAuth login/callback/logout routes, session middleware |
| `app/service.py` | Accept resolved access grants from auth context |
| `app/settings.py` | Add OAuth client ID/secret env vars |
| `app/templates/base.html` | Add login/logout UI, show current user and role |
| `app/templates/hub.html` | Add client/account switcher for multi-grant users |
| Cloud Run env | Set `OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET` |

## Infrastructure

- OAuth credentials are created in the GCP project via the Cloud Console.
- The OAuth consent screen is configured for internal use (agency domain) plus
  explicitly added external test users (client contacts).
- Client ID and secret are stored as Cloud Run environment variables or
  Secret Manager references.

## Managing User Access

Phase 1: manual BigQuery SQL.

```sql
INSERT INTO `gads-export-all.gads_reporting_cfg.cfg_app_users`
  (email, client_id, account_id, role, is_active)
VALUES
  ('new-user@client.com', 'client_x', '__all__', 'viewer', true);
```

Phase 2 (optional): a simple admin page in the app for managing users without
SQL access.

## Relationship To Other Contracts

- The `client_id` filtering rule in `reporting_contract.md` ("application
  queries must always filter by client_id") is enforced by this design.
- The access isolation decision ("application-level isolation for phase 1")
  is implemented by this design.
- Row-level BigQuery security remains deferred unless direct warehouse access
  is introduced.
