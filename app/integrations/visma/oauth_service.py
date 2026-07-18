"""Visma OAuth2 service — handles authorization flow, token exchange, and refresh."""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any
from urllib.parse import urlencode

import requests

from app.core.settings import get_settings
from app.integrations.visma.client import VismaClient

logger = logging.getLogger(__name__)

VISMA_AUTHORIZE_URL = "https://identity.vismaonline.com/connect/authorize"
VISMA_TOKEN_URL = "https://identity.vismaonline.com/connect/token"


def _normalize_scopes(raw: str) -> str:
    """Convert comma-separated or space-separated scope string to OAuth2 space-separated format."""
    parts = [s.strip() for s in raw.replace(",", " ").split() if s.strip()]
    return " ".join(parts)


def get_auth_url(tenant_id: str) -> str:
    return get_auth_url_for_state(tenant_id)


def get_auth_url_for_state(state: str) -> str:
    settings = get_settings()
    scopes = _normalize_scopes(settings.VISMA_SCOPES)

    params = {
        "client_id": settings.VISMA_CLIENT_ID,
        "redirect_uri": settings.VISMA_REDIRECT_URI,
        "response_type": "code",
        "scope": scopes,
        "state": state,
        "prompt": "login",
    }
    return f"{VISMA_AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code(code: str) -> dict[str, Any]:
    """Exchange authorization code for access + refresh tokens."""
    settings = get_settings()

    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.VISMA_REDIRECT_URI,
        "client_id": settings.VISMA_CLIENT_ID,
        "client_secret": settings.VISMA_CLIENT_SECRET,
    }

    response = requests.post(VISMA_TOKEN_URL, data=payload, timeout=30)
    response.raise_for_status()
    data = response.json()

    expires_in = int(data.get("expires_in", 3600))
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    return {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token"),
        "expires_at": expires_at,
        "scopes": data.get("scope", settings.VISMA_SCOPES),
    }


def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    """Use refresh token to obtain a new access token."""
    settings = get_settings()

    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": settings.VISMA_CLIENT_ID,
        "client_secret": settings.VISMA_CLIENT_SECRET,
    }

    response = requests.post(VISMA_TOKEN_URL, data=payload, timeout=30)
    response.raise_for_status()
    data = response.json()

    expires_in = int(data.get("expires_in", 3600))
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    return {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token", refresh_token),
        "expires_at": expires_at,
        "scopes": data.get("scope"),
    }


def test_connection(access_token: str) -> dict[str, Any]:
    """Perform a safe read-only test against the Visma eAccounting API."""
    settings = get_settings()
    client = VismaClient(access_token=access_token, api_url=settings.VISMA_API_URL)
    return client.get_company()
