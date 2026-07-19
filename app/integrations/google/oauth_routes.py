"""Google Mail OAuth2 endpoints — tenant-scoped credential storage."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.admin.onboarding.audit_events import emit_onboarding_audit
from app.admin.onboarding.errors import OnboardingConflictError
from app.admin.onboarding.oauth_state_service import consume_oauth_state
from app.api.dependencies import get_db
from app.core.auth import get_verified_tenant
from app.core.settings import Settings, get_settings
from app.integrations.google.oauth_service import exchange_code, fetch_user_email, get_auth_url_for_state, test_connection
from app.integrations.google.oauth_token_resolver import (
    PROVIDER,
    gmail_connection_status,
    refresh_tenant_google_mail_token,
)
from app.integrations.oauth_state import OAuthStateError, consume_integration_oauth_state
from app.integrations.oauth_state_resolver import lookup_oauth_state_source
from app.repositories.postgres.oauth_credential_repository import OAuthCredentialRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/google_mail", tags=["google-mail-oauth"])

OAUTH_CONNECTED = "integration.google_mail.oauth_connected"
OAUTH_FAILED = "integration.google_mail.oauth_failed"
OAUTH_DISCONNECTED = "integration.google_mail.oauth_disconnected"


def _redirect_with_outcome(base: str, outcome: str, *, reason: str | None = None) -> str:
    sep = "&" if "?" in base else "?"
    url = f"{base}{sep}oauth={outcome}"
    if reason:
        url = f"{url}&reason={reason}"
    return url


def _persist_tokens(
    db: Session,
    *,
    tenant_id: str,
    tokens: dict,
    existing_refresh: str | None = None,
    connected_via: str,
) -> None:
    refresh_token = tokens.get("refresh_token") or existing_refresh
    if not refresh_token:
        raise HTTPException(status_code=400, detail="missing_refresh_token")

    email = fetch_user_email(tokens["access_token"])
    OAuthCredentialRepository.upsert(
        db=db,
        tenant_id=tenant_id,
        provider=PROVIDER,
        access_token=tokens["access_token"],
        refresh_token=refresh_token,
        expires_at=tokens.get("expires_at"),
        scopes=tokens.get("scopes"),
        metadata_json={
            "email": email,
            "connected_via": connected_via,
            "connected_at": datetime.now(timezone.utc).isoformat(),
        },
    )


@router.get("/oauth/start")
def google_mail_oauth_start():
    """Legacy insecure start disabled — use admin connect endpoint with signed state."""
    raise HTTPException(
        status_code=410,
        detail="Use POST /admin/tenants/{tenant_id}/integrations/google_mail/connect with operator session.",
    )


@router.get("/oauth/url")
def google_mail_oauth_url():
    raise HTTPException(
        status_code=410,
        detail="Use POST /admin/tenants/{tenant_id}/integrations/google_mail/connect with operator session.",
    )


@router.get("/oauth/callback")
def google_mail_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if error:
        logger.warning("Google OAuth callback error: %s", error)
        return RedirectResponse(url="/ops/customers?oauth=error&reason=provider_denied", status_code=302)
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state parameter.")

    redirect_base = "/ops/customers"
    tenant_id: str | None = None

    state_source = lookup_oauth_state_source(db, state)

    if state_source == "onboarding":
        try:
            oauth_state = consume_oauth_state(db, state_id=state, settings=settings)
        except OnboardingConflictError as exc:
            reason = getattr(exc, "code", None) or "state_invalid"
            logger.warning("Onboarding Google OAuth state rejected: %s", reason)
            return RedirectResponse(
                url=f"/ops/customers?oauth=error&reason={reason}",
                status_code=302,
            )

        redirect_base = oauth_state.redirect_target
        tenant_id = oauth_state.tenant_id
        try:
            tokens = exchange_code(code)
            existing = OAuthCredentialRepository.get(db, tenant_id, PROVIDER)
            _persist_tokens(
                db,
                tenant_id=tenant_id,
                tokens=tokens,
                existing_refresh=existing.refresh_token if existing else None,
                connected_via="onboarding_oauth_callback",
            )
            emit_onboarding_audit(
                db,
                tenant_id=tenant_id,
                action=OAUTH_CONNECTED,
                status="succeeded",
                details={
                    "session_id": oauth_state.session_id,
                    "provider": PROVIDER,
                },
            )
            db.commit()
        except HTTPException:
            db.rollback()
            return RedirectResponse(url=_redirect_with_outcome(redirect_base, "error", reason="missing_refresh"), status_code=302)
        except Exception as exc:
            db.rollback()
            logger.error("Google OAuth exchange failed (onboarding): %s", type(exc).__name__)
            emit_onboarding_audit(
                db,
                tenant_id=tenant_id,
                action=OAUTH_FAILED,
                status="failed",
                details={"provider": PROVIDER, "error_code": "token_exchange_failed"},
            )
            try:
                db.commit()
            except Exception:
                db.rollback()
            return RedirectResponse(url=_redirect_with_outcome(redirect_base, "error"), status_code=302)

        logger.info("Google Mail OAuth connected via onboarding for tenant %s", tenant_id)
        return RedirectResponse(url=_redirect_with_outcome(redirect_base, "complete"), status_code=302)

    if state_source != "integration":
        logger.warning("Google OAuth callback state not found in any state table")
        return RedirectResponse(url="/ops/customers?oauth=error&reason=oauth_state_invalid", status_code=302)

    # Operator panel / integration oauth state (DB-backed; no admin session cookie required)
    try:
        oauth_state = consume_integration_oauth_state(
            db, state_id=state, provider=PROVIDER, settings=settings
        )
    except OAuthStateError as exc:
        logger.warning("Google OAuth state rejected: %s", exc.code)
        return RedirectResponse(
            url=f"/ops/customers?oauth=error&reason={exc.code}",
            status_code=302,
        )

    redirect_base = oauth_state.redirect_target
    tenant_id = oauth_state.tenant_id
    try:
        tokens = exchange_code(code)
        existing = OAuthCredentialRepository.get(db, tenant_id, PROVIDER)
        _persist_tokens(
            db,
            tenant_id=tenant_id,
            tokens=tokens,
            existing_refresh=existing.refresh_token if existing else None,
            connected_via="operator_oauth_callback",
        )
        emit_onboarding_audit(
            db,
            tenant_id=tenant_id,
            action=OAUTH_CONNECTED,
            status="succeeded",
            details={"provider": PROVIDER, "operator_id": oauth_state.operator_id},
        )
        db.commit()
    except HTTPException:
        db.rollback()
        return RedirectResponse(
            url=_redirect_with_outcome(redirect_base, "error", reason="missing_refresh"),
            status_code=302,
        )
    except Exception as exc:
        db.rollback()
        logger.error("Google OAuth exchange failed: %s", type(exc).__name__)
        emit_onboarding_audit(
            db,
            tenant_id=tenant_id,
            action=OAUTH_FAILED,
            status="failed",
            details={"provider": PROVIDER, "error_code": "token_exchange_failed"},
        )
        try:
            db.commit()
        except Exception:
            db.rollback()
        return RedirectResponse(url=_redirect_with_outcome(redirect_base, "error"), status_code=302)

    logger.info("Google Mail OAuth connected for tenant %s", tenant_id)
    return RedirectResponse(url=_redirect_with_outcome(redirect_base, "complete"), status_code=302)


@router.get("/status")
def google_mail_status(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
    settings: Settings = Depends(get_settings),
):
    status = gmail_connection_status(db, tenant_id, settings=settings)
    return {"status": "success", "provider": PROVIDER, "tenant_id": tenant_id, **status}


@router.post("/disconnect")
def google_mail_disconnect(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    deleted = OAuthCredentialRepository.delete(db, tenant_id, PROVIDER)
    if not deleted:
        return {
            "status": "not_connected",
            "provider": PROVIDER,
            "tenant_id": tenant_id,
        }
    emit_onboarding_audit(
        db,
        tenant_id=tenant_id,
        action=OAUTH_DISCONNECTED,
        status="succeeded",
        details={"provider": PROVIDER},
    )
    db.commit()
    logger.info("Google Mail OAuth disconnected for tenant %s", tenant_id)
    return {"status": "disconnected", "provider": PROVIDER, "tenant_id": tenant_id}


@router.post("/test-read")
def google_mail_test_read(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
    settings: Settings = Depends(get_settings),
):
    row = OAuthCredentialRepository.get(db, tenant_id, PROVIDER)
    if row is None and not settings.GOOGLE_MAIL_ACCESS_TOKEN:
        raise HTTPException(status_code=400, detail="Google Mail is not connected for this tenant.")

    from app.integrations.google.oauth_token_resolver import resolve_google_mail_connection_config

    try:
        cfg = resolve_google_mail_connection_config(tenant_id, db=db, settings=settings)
        profile = test_connection(cfg["access_token"], cfg.get("user_id") or "me")
    except RuntimeError as exc:
        code = str(exc)
        if "reconnect" in code:
            raise HTTPException(status_code=401, detail="Google Mail reconnect required.") from exc
        raise HTTPException(status_code=503, detail="Google Mail test-read failed.") from exc

    return {
        "status": "success",
        "provider": PROVIDER,
        "tenant_id": tenant_id,
        "api_readable": True,
        "email_address": profile.get("email_address"),
        "credential_source": cfg.get("credential_source"),
    }
