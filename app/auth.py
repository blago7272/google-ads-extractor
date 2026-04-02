"""OAuth 2.0 authentication and session management.

Flow:
  1. User visits any page -> middleware checks signed cookie
  2. No valid session -> redirect to /auth/login
  3. /auth/login -> redirect to Google OAuth consent screen
  4. Google redirects to /auth/callback with authorization code
  5. App exchanges code for ID token, extracts email
  6. App looks up email in cfg_app_users (BigQuery)
  7. If found and active -> create signed session cookie, redirect to /
  8. If not found -> show access-denied page
"""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

import httpx
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from google.cloud import bigquery

from app.settings import ReportingAppSettings


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


@dataclass(frozen=True)
class UserSession:
    """Represents an authenticated user's session data."""

    email: str
    role: str  # "admin" or "viewer"
    allowed_clients: list[str] = field(default_factory=list)
    allowed_accounts: dict[str, list[str]] = field(default_factory=dict)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def can_access_client(self, client_id: str) -> bool:
        if self.is_admin:
            return True
        return client_id in self.allowed_clients

    def can_access_account(self, client_id: str, account_id: str) -> bool:
        if self.is_admin:
            return True
        if client_id not in self.allowed_clients:
            return False
        accounts = self.allowed_accounts.get(client_id, [])
        return "__all__" in accounts or account_id in accounts


def build_google_auth_url(settings: ReportingAppSettings) -> str:
    """Build the Google OAuth consent screen URL."""
    state = secrets.token_urlsafe(32)
    params = {
        "client_id": settings.oauth_client_id,
        "redirect_uri": settings.oauth_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "state": state,
        "prompt": "select_account",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}", state


def exchange_code_for_id_token(
    code: str, settings: ReportingAppSettings
) -> dict[str, Any]:
    """Exchange the authorization code for tokens and verify the ID token."""
    resp = httpx.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": settings.oauth_client_id,
            "client_secret": settings.oauth_client_secret,
            "redirect_uri": settings.oauth_redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=15.0,
    )
    resp.raise_for_status()
    token_data = resp.json()

    id_info = id_token.verify_oauth2_token(
        token_data["id_token"],
        google_requests.Request(),
        settings.oauth_client_id,
    )
    return id_info


def lookup_user_grants(
    email: str, settings: ReportingAppSettings
) -> UserSession | None:
    """Look up user grants from cfg_app_users in BigQuery.

    Returns a UserSession if the user has active grants, None otherwise.
    """
    client = bigquery.Client(project=settings.project_id)
    table = f"`{settings.project_id}.{settings.auth_cfg_dataset}.cfg_app_users`"

    sql = f"""
    SELECT client_id, account_id, role
    FROM {table}
    WHERE LOWER(email) = @email
      AND is_active = TRUE
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("email", "STRING", email.lower()),
        ]
    )
    rows = list(client.query(sql, job_config=job_config).result())

    if not rows:
        return None

    # Determine effective role: admin if any grant is admin
    role = "viewer"
    allowed_clients: list[str] = []
    allowed_accounts: dict[str, list[str]] = {}

    for row in rows:
        row_client = row["client_id"]
        row_account = row["account_id"]
        row_role = row["role"]

        if row_role == "admin":
            role = "admin"

        if row_client == "__all__":
            # Admin with access to everything — no need to enumerate
            return UserSession(email=email, role="admin")

        if row_client not in allowed_clients:
            allowed_clients.append(row_client)

        if row_client not in allowed_accounts:
            allowed_accounts[row_client] = []
        if row_account not in allowed_accounts[row_client]:
            allowed_accounts[row_client].append(row_account)

    return UserSession(
        email=email,
        role=role,
        allowed_clients=allowed_clients,
        allowed_accounts=allowed_accounts,
    )


# --- Session cookie management ---

def create_session_serializer(secret_key: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key)


def encode_session(session: UserSession, serializer: URLSafeTimedSerializer) -> str:
    """Encode a UserSession into a signed cookie value."""
    payload = {
        "email": session.email,
        "role": session.role,
        "allowed_clients": session.allowed_clients,
        "allowed_accounts": session.allowed_accounts,
    }
    return serializer.dumps(payload)


def decode_session(
    cookie_value: str,
    serializer: URLSafeTimedSerializer,
    max_age: int,
) -> UserSession | None:
    """Decode and verify a signed session cookie. Returns None if invalid."""
    try:
        payload = serializer.loads(cookie_value, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None

    return UserSession(
        email=payload["email"],
        role=payload["role"],
        allowed_clients=payload.get("allowed_clients", []),
        allowed_accounts=payload.get("allowed_accounts", {}),
    )
