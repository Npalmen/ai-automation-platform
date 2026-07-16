"""Tenant-scoped Visma OAuth access-token resolution for write paths."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.integrations.visma.oauth_service import refresh_access_token
from app.repositories.postgres.oauth_credential_repository import OAuthCredentialRepository

logger = logging.getLogger(__name__)

REFRESH_BUFFER = timedelta(minutes=5)


class VismaTokenError(Exception):
    """Base error for Visma tenant token resolution."""

    code = "visma_token_error"

    def __init__(self, message: str, *, tenant_id: str | None = None):
        super().__init__(message)
        self.tenant_id = tenant_id


class VismaNotConnectedError(VismaTokenError):
    code = "not_connected"


class VismaRefreshFailedError(VismaTokenError):
    code = "refresh_failed"


class VismaTenantMismatchError(VismaTokenError):
    code = "tenant_mismatch"


class VismaProviderDisabledError(VismaTokenError):
    code = "provider_disabled"


class VismaApiUnavailableError(VismaTokenError):
    code = "api_unavailable"


def _token_needs_refresh(expires_at: datetime | None, now: datetime) -> bool:
    if expires_at is None:
        return False
    return expires_at <= now + REFRESH_BUFFER


def resolve_visma_access_token(
    db: Session,
    tenant_id: str,
    *,
    check_allowlist: bool = False,
) -> str:
    """
    Resolve a tenant Visma access token for write paths.

    Never falls back to global VISMA_ACCESS_TOKEN.
    """
    if check_allowlist:
        from app.integrations.enums import IntegrationType
        from app.integrations.policies import is_integration_enabled_for_tenant

        if not is_integration_enabled_for_tenant(
            tenant_id,
            IntegrationType.VISMA,
            db=db,
        ):
            raise VismaProviderDisabledError(
                f"Visma is not enabled for tenant '{tenant_id}'.",
                tenant_id=tenant_id,
            )

    record = OAuthCredentialRepository.get(db, tenant_id, "visma")
    if record is None:
        raise VismaNotConnectedError(
            f"Visma OAuth is not connected for tenant '{tenant_id}'.",
            tenant_id=tenant_id,
        )

    if getattr(record, "tenant_id", tenant_id) != tenant_id:
        raise VismaTenantMismatchError(
            f"Visma credential tenant mismatch for '{tenant_id}'.",
            tenant_id=tenant_id,
        )

    now = datetime.now(timezone.utc)
    access_token = record.access_token

    if _token_needs_refresh(record.expires_at, now):
        if not record.refresh_token:
            raise VismaRefreshFailedError(
                "Visma access token expired and no refresh token is available.",
                tenant_id=tenant_id,
            )
        try:
            refreshed = refresh_access_token(record.refresh_token)
            OAuthCredentialRepository.upsert(
                db=db,
                tenant_id=tenant_id,
                provider="visma",
                access_token=refreshed["access_token"],
                refresh_token=refreshed["refresh_token"],
                expires_at=refreshed["expires_at"],
                scopes=refreshed.get("scopes") or record.scopes,
            )
            access_token = refreshed["access_token"]
            logger.info(
                "Visma token refreshed for tenant %s (expires_at=%s)",
                tenant_id,
                refreshed.get("expires_at"),
            )
        except Exception as exc:
            logger.warning(
                "Visma token refresh failed for tenant %s: %s",
                tenant_id,
                type(exc).__name__,
            )
            raise VismaRefreshFailedError(
                "Visma token refresh failed.",
                tenant_id=tenant_id,
            ) from exc

    if not access_token:
        raise VismaNotConnectedError(
            f"Visma OAuth is not connected for tenant '{tenant_id}'.",
            tenant_id=tenant_id,
        )

    return access_token
