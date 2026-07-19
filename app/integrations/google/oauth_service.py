"""Google OAuth2 service — authorization, token exchange, refresh, read-only test."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import requests

from app.core.settings import get_settings
from app.integrations.google.mail_client import _GOOGLE_TOKEN_URL

logger = logging.getLogger(__name__)

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

# Internal pilot: read + label/unread handoff (manual_review). Send requires separate consent later.
PILOT_GMAIL_SCOPES = (
    "https://www.googleapis.com/auth/gmail.readonly "
    "https://www.googleapis.com/auth/gmail.modify"
)
FULL_GMAIL_SCOPES = PILOT_GMAIL_SCOPES + " https://www.googleapis.com/auth/gmail.send"
DEFAULT_GMAIL_SCOPES = PILOT_GMAIL_SCOPES


def _normalize_scopes(raw: str) -> str:
    parts = [s.strip() for s in raw.replace(",", " ").split() if s.strip()]
    return " ".join(parts)


def get_auth_url_for_state(state: str) -> str:
    settings = get_settings()
    if not settings.GOOGLE_OAUTH_CLIENT_ID or not settings.GOOGLE_OAUTH_REDIRECT_URI:
        raise RuntimeError("Google OAuth is not configured (client id / redirect uri required).")

    scopes = _normalize_scopes(settings.GOOGLE_OAUTH_SCOPES or DEFAULT_GMAIL_SCOPES)
    params = {
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": scopes,
        "state": state,
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
    }
    return f"{GOOGLE_AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code(code: str) -> dict[str, Any]:
    settings = get_settings()
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.GOOGLE_OAUTH_REDIRECT_URI,
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
    }
    response = requests.post(_GOOGLE_TOKEN_URL, data=payload, timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f"Google token exchange failed ({response.status_code})")
    data = response.json()
    access_token = data.get("access_token")
    if not access_token:
        raise RuntimeError("Google token exchange succeeded but access_token missing.")

    expires_in = int(data.get("expires_in", 3600))
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    return {
        "access_token": access_token,
        "refresh_token": data.get("refresh_token"),
        "expires_at": expires_at,
        "scopes": data.get("scope", settings.GOOGLE_OAUTH_SCOPES or DEFAULT_GMAIL_SCOPES),
    }


def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    settings = get_settings()
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
    }
    response = requests.post(_GOOGLE_TOKEN_URL, data=payload, timeout=30)
    if response.status_code != 200:
        body = response.text.strip()[:200]
        raise RuntimeError(f"Google token refresh failed ({response.status_code}): {body}")

    data = response.json()
    access_token = data.get("access_token")
    if not access_token:
        raise RuntimeError("Google refresh succeeded but access_token missing.")

    expires_in = int(data.get("expires_in", 3600))
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    return {
        "access_token": access_token,
        "refresh_token": data.get("refresh_token"),
        "expires_at": expires_at,
        "scopes": data.get("scope"),
    }


def fetch_user_email(access_token: str) -> str | None:
    response = requests.get(
        GOOGLE_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    if response.status_code != 200:
        logger.warning("Google userinfo failed: %s", response.status_code)
        return None
    return response.json().get("email")


def test_connection(access_token: str, user_id: str = "me") -> dict[str, Any]:
    """Read-only Gmail profile check — no sends or mutations."""
    api_url = get_settings().GOOGLE_MAIL_API_URL.rstrip("/")
    response = requests.get(
        f"{api_url}/users/{user_id}/profile",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=20,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Gmail profile check failed ({response.status_code})")
    profile = response.json()
    return {
        "email_address": profile.get("emailAddress"),
        "messages_total": profile.get("messagesTotal"),
        "threads_total": profile.get("threadsTotal"),
    }
