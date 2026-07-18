"""Visma OAuth2 endpoints for per-tenant connection management."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.admin.onboarding.errors import OnboardingConflictError
from app.admin.onboarding.audit_events import (
    OAUTH_CONNECTION_COMPLETED,
    OAUTH_CONNECTION_FAILED,
    emit_onboarding_audit,
)
from app.admin.onboarding.oauth_state_service import consume_oauth_state, is_onboarding_oauth_state
from app.admin.onboarding.integration_verification import IntegrationVerificationStore
from app.admin.onboarding.repository import OnboardingRepository
from app.api.dependencies import get_db
from app.core.auth import get_verified_tenant
from app.core.settings import Settings, get_settings
from app.integrations.visma.oauth_service import (
    exchange_code,
    get_auth_url,
    refresh_access_token,
    test_connection,
)
from app.repositories.postgres.oauth_credential_repository import OAuthCredentialRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/visma", tags=["visma-oauth"])


def _onboarding_redirect(base: str, *, outcome: str) -> str:
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}oauth={outcome}"


@router.get("/oauth/start")
def visma_oauth_start(
    tenant_id: str = Depends(get_verified_tenant),
):
    """Redirect user to Visma OAuth authorization page."""
    settings = get_settings()

    if not settings.VISMA_CLIENT_ID or not settings.VISMA_REDIRECT_URI:
        raise HTTPException(
            status_code=503,
            detail="Visma OAuth is not configured (VISMA_CLIENT_ID and VISMA_REDIRECT_URI required).",
        )

    url = get_auth_url(tenant_id)
    return RedirectResponse(url=url, status_code=302)


@router.get("/oauth/url")
def visma_oauth_url(
    tenant_id: str = Depends(get_verified_tenant),
):
    """Return Visma OAuth URL as JSON (for UI fetch with auth headers)."""
    settings = get_settings()

    if not settings.VISMA_CLIENT_ID or not settings.VISMA_REDIRECT_URI:
        raise HTTPException(
            status_code=503,
            detail="Visma OAuth is not configured (VISMA_CLIENT_ID and VISMA_REDIRECT_URI required).",
        )

    url = get_auth_url(tenant_id)
    return {"url": url}


@router.get("/oauth/callback")
def visma_oauth_callback(
    code: str,
    state: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Handle Visma OAuth callback — exchange code for tokens and store per-tenant."""
    if not state:
        raise HTTPException(status_code=400, detail="Missing state parameter.")

    if is_onboarding_oauth_state(state):
        try:
            oauth_state = consume_oauth_state(db, state_id=state, settings=settings)
        except OnboardingConflictError:
            logger.warning("Onboarding Visma OAuth state rejected")
            return RedirectResponse(url="/ops/customers?oauth=error", status_code=302)

        redirect_base = oauth_state.redirect_target
        try:
            tokens = exchange_code(code)
        except Exception as exc:
            logger.error(
                "Visma OAuth token exchange failed for onboarding session %s: %s",
                oauth_state.session_id,
                type(exc).__name__,
            )
            emit_onboarding_audit(
                db,
                tenant_id=oauth_state.tenant_id,
                action=OAUTH_CONNECTION_FAILED,
                status="failed",
                details={
                    "session_id": oauth_state.session_id,
                    "provider": "visma",
                    "error_code": "token_exchange_failed",
                },
            )
            try:
                db.commit()
            except Exception:
                db.rollback()
            return RedirectResponse(url=_onboarding_redirect(redirect_base, outcome="error"), status_code=302)

        OAuthCredentialRepository.upsert(
            db=db,
            tenant_id=oauth_state.tenant_id,
            provider="visma",
            access_token=tokens["access_token"],
            refresh_token=tokens.get("refresh_token"),
            expires_at=tokens.get("expires_at"),
            scopes=tokens.get("scopes"),
            metadata_json={"connected_via": "onboarding_oauth_callback"},
        )
        IntegrationVerificationStore.invalidate(
            db,
            session_id=oauth_state.session_id,
            integration_key="visma",
        )
        session = OnboardingRepository.get_session(db, oauth_state.session_id)
        if session is not None:
            OnboardingRepository.bump_integration_state_revision(session)
        emit_onboarding_audit(
            db,
            tenant_id=oauth_state.tenant_id,
            action=OAUTH_CONNECTION_COMPLETED,
            status="succeeded",
            details={
                "session_id": oauth_state.session_id,
                "provider": "visma",
                "integration_key": "visma",
            },
        )
        try:
            db.commit()
        except Exception:
            db.rollback()
            return RedirectResponse(url=_onboarding_redirect(redirect_base, outcome="error"), status_code=302)

        logger.info("Visma OAuth connected via onboarding for tenant %s", oauth_state.tenant_id)
        return RedirectResponse(url=_onboarding_redirect(redirect_base, outcome="complete"), status_code=302)

    # Legacy tenant_id-as-state flow disabled (Kapitel 11 — use onboarding wizard).
    logger.warning("Rejected legacy Visma OAuth callback with raw tenant state")
    return RedirectResponse(
        url="/ops/customers?oauth=error&reason=legacy_oauth_disabled",
        status_code=302,
    )


@router.get("/status")
def visma_status(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Return Visma connection status for the tenant."""
    record = OAuthCredentialRepository.get(db, tenant_id, "visma")

    if record is None:
        return {
            "status": "disconnected",
            "provider": "visma",
            "tenant_id": tenant_id,
            "connected": False,
        }

    now = datetime.now(timezone.utc)
    token_expired = record.expires_at is not None and record.expires_at < now

    return {
        "status": "connected",
        "provider": "visma",
        "tenant_id": tenant_id,
        "connected": True,
        "token_expired": token_expired,
        "expires_at": record.expires_at.isoformat() if record.expires_at else None,
        "scopes": record.scopes,
        "connected_at": record.connected_at.isoformat() if record.connected_at else None,
    }


@router.post("/disconnect")
def visma_disconnect(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Remove stored Visma tokens for the tenant."""
    deleted = OAuthCredentialRepository.delete(db, tenant_id, "visma")

    if not deleted:
        return {
            "status": "not_connected",
            "provider": "visma",
            "tenant_id": tenant_id,
            "message": "No Visma connection found for this tenant.",
        }

    logger.info("Visma OAuth disconnected for tenant %s", tenant_id)
    return {
        "status": "disconnected",
        "provider": "visma",
        "tenant_id": tenant_id,
        "message": "Visma integration disconnected.",
    }


@router.post("/test-read")
def visma_test_read(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Perform a safe read-only test against the Visma API using stored credentials."""
    record = OAuthCredentialRepository.get(db, tenant_id, "visma")

    if record is None:
        raise HTTPException(
            status_code=400,
            detail="Visma is not connected for this tenant. Start OAuth flow first.",
        )

    now = datetime.now(timezone.utc)
    access_token = record.access_token

    # Auto-refresh if expired
    if record.expires_at and record.expires_at < now:
        if not record.refresh_token:
            raise HTTPException(
                status_code=401,
                detail="Visma access token expired and no refresh token available. Re-authorize.",
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
            logger.info("Visma token refreshed for tenant %s during test-read", tenant_id)
        except Exception as exc:
            logger.error("Visma token refresh failed for tenant %s: %s", tenant_id, type(exc).__name__)
            raise HTTPException(
                status_code=401,
                detail="Visma token refresh failed. Please re-authorize.",
            ) from exc

    try:
        result = test_connection(access_token)
    except Exception as exc:
        logger.error("Visma test-read failed for tenant %s: %s", tenant_id, type(exc).__name__)
        err_str = str(exc)
        # Classify the failure so UI can show a useful message
        if "401" in err_str or "Unauthorized" in err_str:
            detail = "Visma OAuth-token är inte giltig. Koppla om Visma-integrationen."
            code = 401
        elif "403" in err_str or "Forbidden" in err_str:
            detail = "Behörighet nekad av Visma API. Kontrollera att scopes är rätt."
            code = 403
        elif "404" in err_str:
            detail = "Visma API-resursen hittades inte. Kontrollera VISMA_API_URL."
            code = 502
        elif "timeout" in err_str.lower() or "Timeout" in err_str:
            detail = "Visma API svarade inte i tid. Försök igen om en stund."
            code = 504
        else:
            detail = "Visma API-anrop misslyckades. OAuth-token finns men API-läsning misslyckades."
            code = 502
        raise HTTPException(status_code=code, detail=detail) from exc

    return {
        "status": "success",
        "oauth_connected": True,
        "api_readable": True,
        "provider": "visma",
        "tenant_id": tenant_id,
        "data": result,
    }
