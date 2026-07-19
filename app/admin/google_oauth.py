"""Admin routes for tenant Google Mail OAuth (operator panel)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.admin.onboarding.audit_events import emit_onboarding_audit
from app.api.dependencies import get_db
from app.core.admin_auth import require_operator_role
from app.core.admin_session import OperatorIdentity, require_same_origin
from app.core.settings import Settings, get_settings
from app.integrations.google.oauth_service import get_auth_url_for_state
from app.integrations.google.oauth_token_resolver import PROVIDER, gmail_connection_status
from app.integrations.oauth_state import create_integration_oauth_state
from app.repositories.postgres.oauth_credential_repository import OAuthCredentialRepository
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/tenants", tags=["admin-google-oauth"])

_OPERATOR_WRITE_ROLES = frozenset({"operations", "admin"})
_OPERATOR_READ_ROLES = frozenset({"read_only", "operations", "admin"})

OAUTH_STARTED = "integration.google_mail.oauth_started"
OAUTH_DISCONNECTED = "integration.google_mail.oauth_disconnected"


class GoogleMailConnectRequest(BaseModel):
    redirect_target: str = Field(..., min_length=1, max_length=512)


@router.get("/{tenant_id}/integrations/google_mail/status")
def admin_google_mail_status(
    tenant_id: str,
    db: Session = Depends(get_db),
    operator: OperatorIdentity = Depends(require_operator_role(_OPERATOR_READ_ROLES)),
    settings: Settings = Depends(get_settings),
):
    _ = operator
    if TenantConfigRepository.get(db, tenant_id) is None:
        raise HTTPException(status_code=404, detail="Tenant not found.")
    return gmail_connection_status(db, tenant_id, settings=settings)


@router.post("/{tenant_id}/integrations/google_mail/connect")
def admin_google_mail_connect(
    tenant_id: str,
    body: GoogleMailConnectRequest,
    request: Request,
    db: Session = Depends(get_db),
    operator: OperatorIdentity = Depends(require_operator_role(_OPERATOR_WRITE_ROLES)),
    settings: Settings = Depends(get_settings),
):
    require_same_origin(request)
    if TenantConfigRepository.get(db, tenant_id) is None:
        raise HTTPException(status_code=404, detail="Tenant not found.")
    if not settings.GOOGLE_OAUTH_CLIENT_ID or not settings.GOOGLE_OAUTH_REDIRECT_URI:
        raise HTTPException(status_code=503, detail="Google OAuth is not configured on the platform.")

    state_id, _ = create_integration_oauth_state(
        db,
        tenant_id=tenant_id,
        operator_id=operator["id"],
        provider=PROVIDER,
        redirect_target=body.redirect_target,
        settings=settings,
    )
    url = get_auth_url_for_state(state_id)
    emit_onboarding_audit(
        db,
        tenant_id=tenant_id,
        action=OAUTH_STARTED,
        status="succeeded",
        details={"provider": PROVIDER, "operator_id": operator["id"]},
    )
    db.commit()
    return {"authorization_url": url, "provider": PROVIDER, "state_id": state_id}


@router.post("/{tenant_id}/integrations/google_mail/disconnect")
def admin_google_mail_disconnect(
    tenant_id: str,
    request: Request,
    db: Session = Depends(get_db),
    operator: OperatorIdentity = Depends(require_operator_role(_OPERATOR_WRITE_ROLES)),
):
    require_same_origin(request)
    _ = operator
    if TenantConfigRepository.get(db, tenant_id) is None:
        raise HTTPException(status_code=404, detail="Tenant not found.")
    deleted = OAuthCredentialRepository.delete(db, tenant_id, PROVIDER)
    if not deleted:
        return {"status": "not_connected", "provider": PROVIDER, "tenant_id": tenant_id}
    emit_onboarding_audit(
        db,
        tenant_id=tenant_id,
        action=OAUTH_DISCONNECTED,
        status="succeeded",
        details={"provider": PROVIDER, "operator_id": operator["id"]},
    )
    db.commit()
    logger.info("Google Mail disconnected for tenant %s by operator %s", tenant_id, operator["id"])
    return {"status": "disconnected", "provider": PROVIDER, "tenant_id": tenant_id}
