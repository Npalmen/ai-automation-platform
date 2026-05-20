"""Visma OAuth2 endpoints for per-tenant connection management."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.auth import get_verified_tenant
from app.core.settings import get_settings
from app.integrations.visma.oauth_service import (
    exchange_code,
    get_auth_url,
    refresh_access_token,
    test_connection,
)
from app.repositories.postgres.oauth_credential_repository import OAuthCredentialRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/visma", tags=["visma-oauth"])


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


@router.get("/oauth/callback")
def visma_oauth_callback(
    code: str,
    state: str,
    db: Session = Depends(get_db),
):
    """Handle Visma OAuth callback — exchange code for tokens and store per-tenant."""
    if not state:
        raise HTTPException(status_code=400, detail="Missing state parameter.")

    tenant_id = state

    try:
        tokens = exchange_code(code)
    except Exception as exc:
        logger.error("Visma OAuth token exchange failed for tenant %s: %s", tenant_id, type(exc).__name__)
        raise HTTPException(
            status_code=502,
            detail="Failed to exchange authorization code with Visma.",
        ) from exc

    OAuthCredentialRepository.upsert(
        db=db,
        tenant_id=tenant_id,
        provider="visma",
        access_token=tokens["access_token"],
        refresh_token=tokens.get("refresh_token"),
        expires_at=tokens.get("expires_at"),
        scopes=tokens.get("scopes"),
        metadata_json={"connected_via": "oauth_callback"},
    )

    logger.info("Visma OAuth connected for tenant %s", tenant_id)
    return {
        "status": "connected",
        "provider": "visma",
        "tenant_id": tenant_id,
        "message": "Visma integration connected successfully.",
    }


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
        raise HTTPException(
            status_code=502,
            detail="Visma API test-read failed. Check connection.",
        ) from exc

    return {
        "status": "success",
        "provider": "visma",
        "tenant_id": tenant_id,
        "data": result,
    }
