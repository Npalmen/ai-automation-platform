"""Admin provisioning routes for customer workspace viewer identities."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.admin_auth import require_operator_role
from app.core.admin_session import OperatorIdentity, hash_password
from app.customer_auth.password_policy import CustomerPasswordPolicyError, validate_customer_password
from app.repositories.postgres.customer_workspace_session_repository import (
    CustomerWorkspaceSessionRepository,
)
from app.repositories.postgres.customer_workspace_user_repository import (
    CUSTOMER_VIEWER_ROLE,
    USER_STATUS_ACTIVE,
    USER_STATUS_DISABLED,
    CustomerWorkspaceUserRepository,
)
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

router = APIRouter(prefix="/admin/tenants", tags=["customer-workspace-users"])

_ADMIN_ROLES = frozenset({"admin", "super_admin"})


class WorkspaceUserCreateRequest(BaseModel):
    email: str = Field(min_length=3, max_length=256)
    password: str = Field(min_length=1, max_length=64)
    display_name: str = Field(default="", max_length=256)


class WorkspaceUserStatusPatchRequest(BaseModel):
    status: Literal["active", "disabled"]


class WorkspaceUserPasswordResetRequest(BaseModel):
    password: str = Field(min_length=1, max_length=64)


class WorkspaceUserResponse(BaseModel):
    user_id: str
    tenant_id: str
    email: str
    display_name: str
    role: Literal["customer_viewer"] = "customer_viewer"
    status: str


def _require_tenant(db: Session, tenant_id: str) -> None:
    if TenantConfigRepository.get(db, tenant_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")


def _to_response(user) -> WorkspaceUserResponse:
    return WorkspaceUserResponse(
        user_id=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
        display_name=user.display_name,
        status=user.status,
    )


@router.post("/{tenant_id}/workspace-users", response_model=WorkspaceUserResponse)
def create_workspace_user(
    tenant_id: str,
    body: WorkspaceUserCreateRequest,
    db: Session = Depends(get_db),
    operator: OperatorIdentity = Depends(require_operator_role(_ADMIN_ROLES)),
):
    _ = operator
    _require_tenant(db, tenant_id)
    try:
        validate_customer_password(body.password)
    except CustomerPasswordPolicyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if CustomerWorkspaceUserRepository.active_email_taken(db, body.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="En aktiv användare med den e-postadressen finns redan.",
        )

    user = CustomerWorkspaceUserRepository.create_user(
        db,
        tenant_id=tenant_id,
        email=body.email,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
    )
    return _to_response(user)


@router.patch("/{tenant_id}/workspace-users/{user_id}", response_model=WorkspaceUserResponse)
def patch_workspace_user_status(
    tenant_id: str,
    user_id: str,
    body: WorkspaceUserStatusPatchRequest,
    db: Session = Depends(get_db),
    operator: OperatorIdentity = Depends(require_operator_role(_ADMIN_ROLES)),
):
    _ = operator
    _require_tenant(db, tenant_id)
    user = CustomerWorkspaceUserRepository.get_by_id(db, user_id)
    if user is None or user.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    if body.status == USER_STATUS_ACTIVE:
        if CustomerWorkspaceUserRepository.active_email_taken(db, user.email, exclude_user_id=user.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="En aktiv användare med den e-postadressen finns redan.",
            )

    user = CustomerWorkspaceUserRepository.set_status(db, user, body.status)
    if body.status == USER_STATUS_DISABLED:
        CustomerWorkspaceSessionRepository.revoke_all_for_user(db, user.id)
    return _to_response(user)


@router.post("/{tenant_id}/workspace-users/{user_id}/reset-password", response_model=WorkspaceUserResponse)
def reset_workspace_user_password(
    tenant_id: str,
    user_id: str,
    body: WorkspaceUserPasswordResetRequest,
    db: Session = Depends(get_db),
    operator: OperatorIdentity = Depends(require_operator_role(_ADMIN_ROLES)),
):
    _ = operator
    _require_tenant(db, tenant_id)
    user = CustomerWorkspaceUserRepository.get_by_id(db, user_id)
    if user is None or user.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    try:
        validate_customer_password(body.password)
    except CustomerPasswordPolicyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    user = CustomerWorkspaceUserRepository.update_password_hash(
        db, user, hash_password(body.password)
    )
    CustomerWorkspaceSessionRepository.revoke_all_for_user(db, user.id)
    return _to_response(user)
