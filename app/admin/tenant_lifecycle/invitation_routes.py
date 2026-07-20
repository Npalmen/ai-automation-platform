"""Public and admin routes for customer integration invitations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.admin.tenant_lifecycle.invitation_service import (
    create_invitation,
    get_invitation_by_token,
    list_invitations,
    present_invitation_public,
)
from app.api.dependencies import get_db
from app.core.admin_auth import require_operator_role
from app.core.admin_session import OperatorIdentity
from app.core.settings import Settings, get_settings
from app.integrations.google.oauth_service import get_auth_url_for_state
from app.integrations.oauth_state import create_integration_oauth_state

admin_router = APIRouter(prefix="/admin/tenants", tags=["integration-invitations"])
public_router = APIRouter(prefix="/integrations/invite", tags=["integration-invitations-public"])

_WRITE_ROLES = frozenset({"operations", "admin", "super_admin"})
_READ_ROLES = frozenset({"read_only", "operations", "admin", "super_admin"})


class CreateInvitationRequest(BaseModel):
    integration_key: str = Field(..., min_length=1, max_length=32)
    contact_email: str = Field(..., min_length=3, max_length=256)
    contact_name: str | None = Field(default=None, max_length=256)
    message_optional: str | None = Field(default=None, max_length=2000)


class CreateInvitationResponse(BaseModel):
    invitation_id: str
    invite_path: str
    expires_at: str
    status: str


class InvitationListItem(BaseModel):
    id: str
    integration_key: str
    contact_email: str
    contact_name: str | None
    status: str
    expires_at: str
    connected_account_email: str | None


@admin_router.post("/{tenant_id}/integrations/invitations", response_model=CreateInvitationResponse)
def admin_create_invitation(
    tenant_id: str,
    body: CreateInvitationRequest,
    db: Session = Depends(get_db),
    operator: OperatorIdentity = Depends(require_operator_role(_WRITE_ROLES)),
):
    record, raw_token = create_invitation(
        db,
        tenant_id=tenant_id,
        integration_key=body.integration_key,
        contact_email=str(body.contact_email),
        contact_name=body.contact_name,
        message_optional=body.message_optional,
        operator_id=operator["id"],
    )
    return CreateInvitationResponse(
        invitation_id=record.id,
        invite_path=f"/integrations/invite/{raw_token}",
        expires_at=record.expires_at.isoformat(),
        status=record.status,
    )


@admin_router.post("/{tenant_id}/integrations/invitations/{invitation_id}/revoke")
def admin_revoke_invitation(
    tenant_id: str,
    invitation_id: str,
    db: Session = Depends(get_db),
    operator: OperatorIdentity = Depends(require_operator_role(_WRITE_ROLES)),
):
    from app.admin.tenant_lifecycle.invitation_service import revoke_invitation

    record = revoke_invitation(
        db,
        invitation_id=invitation_id,
        tenant_id=tenant_id,
        operator_id=operator["id"],
    )
    return {"status": record.status, "invitation_id": record.id}


@admin_router.get("/{tenant_id}/integrations/invitations", response_model=list[InvitationListItem])
def admin_list_invitations(
    tenant_id: str,
    db: Session = Depends(get_db),
    operator: OperatorIdentity = Depends(require_operator_role(_READ_ROLES)),
):
    _ = operator
    rows = list_invitations(db, tenant_id)
    return [
        InvitationListItem(
            id=row.id,
            integration_key=row.integration_key,
            contact_email=row.contact_email,
            contact_name=row.contact_name,
            status=row.status,
            expires_at=row.expires_at.isoformat(),
            connected_account_email=row.connected_account_email,
        )
        for row in rows
    ]


@public_router.get("/{token}")
def public_invite_metadata(token: str, db: Session = Depends(get_db)):
    record = get_invitation_by_token(db, token)
    if record is None:
        raise HTTPException(status_code=404, detail="Invitation not found.")
    return present_invitation_public(record)


@public_router.post("/{token}/start")
def public_invite_start(
    token: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    record = get_invitation_by_token(db, token)
    if record is None:
        raise HTTPException(status_code=404, detail="Invitation not found.")
    if record.status != "pending":
        raise HTTPException(status_code=409, detail="Invitation not available.")
    if not settings.GOOGLE_OAUTH_CLIENT_ID:
        raise HTTPException(status_code=503, detail="OAuth not configured.")

    redirect_target = f"/integrations/invite/{token}/complete"
    state_id, oauth_state = create_integration_oauth_state(
        db,
        tenant_id=record.tenant_id,
        operator_id=f"invite:{record.id}",
        provider="google_mail",
        redirect_target=redirect_target,
        settings=settings,
        invitation_id=record.id,
    )
    db.commit()
    return {
        "auth_url": get_auth_url_for_state(state_id),
        "state_id": state_id,
        "invitation_id": record.id,
        "expires_at": oauth_state.expires_at.isoformat(),
    }
