"""Resolve tenant-scoped Google Mail OAuth credentials with automatic refresh."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.settings import Settings, get_settings
from app.integrations.google.oauth_service import refresh_access_token
from app.repositories.postgres.oauth_credential_repository import OAuthCredentialRepository

logger = logging.getLogger(__name__)

PROVIDER = "google_mail"
_REFRESH_SKEW = timedelta(minutes=5)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def get_google_mail_oauth_row(db: Session, tenant_id: str):
    return OAuthCredentialRepository.get(db, tenant_id, PROVIDER)


def is_token_expired(record, *, skew: timedelta = _REFRESH_SKEW) -> bool:
    expires_at = _as_utc(getattr(record, "expires_at", None))
    if expires_at is None:
        return False
    return expires_at <= _utcnow() + skew


def refresh_tenant_google_mail_token(
    db: Session,
    tenant_id: str,
    *,
    record=None,
) -> dict[str, Any]:
    row = record or OAuthCredentialRepository.get(db, tenant_id, PROVIDER)
    if row is None or not row.refresh_token:
        raise RuntimeError("google_mail_not_connected")

    try:
        refreshed = refresh_access_token(row.refresh_token)
    except RuntimeError as exc:
        err = str(exc).lower()
        if "invalid_grant" in err or "401" in err:
            raise RuntimeError("google_mail_reconnect_required") from exc
        raise

    new_refresh = refreshed.get("refresh_token") or row.refresh_token
    OAuthCredentialRepository.upsert(
        db=db,
        tenant_id=tenant_id,
        provider=PROVIDER,
        access_token=refreshed["access_token"],
        refresh_token=new_refresh,
        expires_at=refreshed.get("expires_at"),
        scopes=refreshed.get("scopes") or row.scopes,
        metadata_json=row.metadata_json,
    )
    logger.info("Google Mail token refreshed for tenant %s", tenant_id)
    return refreshed


def resolve_google_mail_connection_config(
    tenant_id: str,
    *,
    db: Session | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Tenant OAuth row first; fallback to platform env for transitional deploys."""
    settings = settings or get_settings()
    base = {
        "api_url": settings.GOOGLE_MAIL_API_URL,
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
    }

    if db is not None:
        row = OAuthCredentialRepository.get(db, tenant_id, PROVIDER)
        if row is not None:
            access_token = row.access_token
            refresh_token = row.refresh_token or ""
            user_id = "me"
            meta = row.metadata_json or {}
            if meta.get("email"):
                user_id = str(meta["email"])
            if is_token_expired(row):
                if not refresh_token:
                    raise RuntimeError("google_mail_reconnect_required")
                refreshed = refresh_tenant_google_mail_token(db, tenant_id, record=row)
                access_token = refreshed["access_token"]
                refresh_token = refreshed.get("refresh_token") or refresh_token
            return {
                **base,
                "access_token": access_token,
                "user_id": user_id,
                "refresh_token": refresh_token,
                "credential_source": "tenant_oauth",
            }

    # Platform-level fallback (legacy)
    return {
        **base,
        "access_token": settings.GOOGLE_MAIL_ACCESS_TOKEN,
        "user_id": settings.GOOGLE_MAIL_USER_ID or "me",
        "refresh_token": settings.GOOGLE_OAUTH_REFRESH_TOKEN,
        "credential_source": "platform_env",
    }


def gmail_connection_status(db: Session, tenant_id: str, settings: Settings | None = None) -> dict[str, Any]:
    """UI-facing connection status — never includes tokens."""
    settings = settings or get_settings()
    row = OAuthCredentialRepository.get(db, tenant_id, PROVIDER)
    platform_fallback = bool(settings.GOOGLE_MAIL_ACCESS_TOKEN and settings.GOOGLE_OAUTH_REFRESH_TOKEN)

    if row is None:
        if platform_fallback:
            return {
                "connection_state": "connected",
                "credential_source": "platform_env",
                "connected": True,
                "reconnect_required": False,
                "email": settings.GOOGLE_MAIL_USER_ID if settings.GOOGLE_MAIL_USER_ID != "me" else None,
                "expires_at": None,
                "scopes": settings.GOOGLE_OAUTH_SCOPES or None,
                "connected_at": None,
            }
        return {
            "connection_state": "not_connected",
            "credential_source": None,
            "connected": False,
            "reconnect_required": False,
            "email": None,
            "expires_at": None,
            "scopes": None,
            "connected_at": None,
        }

    meta = row.metadata_json or {}
    expired = is_token_expired(row)
    reconnect = expired and not row.refresh_token
    state = "connected"
    if reconnect:
        state = "reconnect_required"
    elif expired:
        state = "connected"  # refresh on use

    return {
        "connection_state": state,
        "credential_source": "tenant_oauth",
        "connected": True,
        "reconnect_required": reconnect,
        "email": meta.get("email"),
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "scopes": row.scopes,
        "connected_at": row.connected_at.isoformat() if row.connected_at else None,
    }
