"""Google Sheets OAuth access token resolution for manual export."""
from __future__ import annotations

from typing import Any

from app.core.settings import get_settings
from app.integrations.google.mail_client import refresh_access_token


def resolve_google_sheets_access_token(
    tenant_gs_settings: dict[str, Any] | None = None,
) -> str:
    """Return a Google access token for Sheets API calls.

    Token precedence (first match wins):
    1. ``settings.google_sheets.access_token`` on the tenant (optional override)
    2. Fresh access token from OAuth refresh using:
       ``GOOGLE_OAUTH_REFRESH_TOKEN``, ``GOOGLE_OAUTH_CLIENT_ID``,
       ``GOOGLE_OAUTH_CLIENT_SECRET``
    3. Never use a stale ``GOOGLE_MAIL_ACCESS_TOKEN`` env value

    Raises:
        RuntimeError: when no usable token can be obtained or refresh fails.
    """
    gs_settings = tenant_gs_settings or {}
    tenant_token = str(gs_settings.get("access_token") or "").strip()
    if tenant_token:
        return tenant_token

    settings = get_settings()
    refresh_token = str(settings.GOOGLE_OAUTH_REFRESH_TOKEN or "").strip()
    client_id = str(settings.GOOGLE_OAUTH_CLIENT_ID or "").strip()
    client_secret = str(settings.GOOGLE_OAUTH_CLIENT_SECRET or "").strip()

    if not (refresh_token and client_id and client_secret):
        raise RuntimeError(
            "Google OAuth refresh credentials are not configured for Sheets export."
        )

    return refresh_access_token(
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
    )
