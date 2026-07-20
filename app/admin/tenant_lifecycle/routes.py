"""FastAPI routes for tenant lifecycle (Onboarding 2.0)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.admin.tenant_lifecycle.deletion_service import TenantDeletionService
from app.admin.tenant_lifecycle.schemas import (
    ActivationHistoryResponse,
    LifecycleActionRequest,
    LifecyclePatchRequest,
    LifecycleResponse,
    OperationsPauseRequest,
    TenantDeleteDryRunResponse,
    TenantDeleteRequest,
    TenantSettingsSectionPatchRequest,
    TenantSettingsSectionResponse,
)
from app.admin.tenant_lifecycle.service import (
    archive_tenant,
    get_lifecycle,
    get_settings_section,
    list_activation_history,
    patch_lifecycle,
    patch_settings_section,
    pause_operations,
    restore_tenant,
    resume_operations,
)
from app.api.dependencies import get_db
from app.core.admin_auth import require_operator_role
from app.core.admin_session import OperatorIdentity, is_super_admin_operator

router = APIRouter(prefix="/admin/tenants", tags=["tenant-lifecycle"])

_READ_ROLES = frozenset({"read_only", "operations", "admin", "super_admin"})
_WRITE_ROLES = frozenset({"operations", "admin", "super_admin"})
_ADMIN_ROLES = frozenset({"admin", "super_admin"})
_SUPER_ADMIN_ROLES = frozenset({"super_admin"})


def _require_super_admin(operator: OperatorIdentity) -> None:
    if not is_super_admin_operator(operator):
        raise HTTPException(status_code=403, detail="super_admin required.")


@router.get("/{tenant_id}/lifecycle", response_model=LifecycleResponse)
def tenant_lifecycle_get(
    tenant_id: str,
    db: Session = Depends(get_db),
    operator: OperatorIdentity = Depends(require_operator_role(_READ_ROLES)),
):
    _ = operator
    return LifecycleResponse(**get_lifecycle(db, tenant_id))


@router.patch("/{tenant_id}/lifecycle", response_model=LifecycleResponse)
def tenant_lifecycle_patch(
    tenant_id: str,
    body: LifecyclePatchRequest,
    db: Session = Depends(get_db),
    operator: OperatorIdentity = Depends(require_operator_role(_WRITE_ROLES)),
):
    return LifecycleResponse(
        **patch_lifecycle(
            db,
            tenant_id=tenant_id,
            operator_id=operator["id"],
            lifecycle_status=body.lifecycle_status,
            config_version=body.config_version,
            reason=body.reason,
        )
    )


@router.post("/{tenant_id}/lifecycle/archive", response_model=LifecycleResponse)
def tenant_lifecycle_archive(
    tenant_id: str,
    body: LifecycleActionRequest,
    db: Session = Depends(get_db),
    operator: OperatorIdentity = Depends(require_operator_role(_ADMIN_ROLES)),
):
    return LifecycleResponse(
        **archive_tenant(
            db,
            tenant_id=tenant_id,
            operator_id=operator["id"],
            config_version=body.config_version,
            reason=body.reason,
        )
    )


@router.post("/{tenant_id}/lifecycle/restore", response_model=LifecycleResponse)
def tenant_lifecycle_restore(
    tenant_id: str,
    body: LifecycleActionRequest,
    db: Session = Depends(get_db),
    operator: OperatorIdentity = Depends(require_operator_role(_ADMIN_ROLES)),
):
    return LifecycleResponse(
        **restore_tenant(
            db,
            tenant_id=tenant_id,
            operator_id=operator["id"],
            config_version=body.config_version,
            reason=body.reason,
        )
    )


@router.post("/{tenant_id}/operations/pause", response_model=LifecycleResponse)
def tenant_operations_pause(
    tenant_id: str,
    body: OperationsPauseRequest,
    db: Session = Depends(get_db),
    operator: OperatorIdentity = Depends(require_operator_role(_WRITE_ROLES)),
):
    return LifecycleResponse(
        **pause_operations(
            db,
            tenant_id=tenant_id,
            operator_id=operator["id"],
            config_version=body.config_version,
            reason=body.reason,
        )
    )


@router.post("/{tenant_id}/operations/resume", response_model=LifecycleResponse)
def tenant_operations_resume(
    tenant_id: str,
    body: OperationsPauseRequest,
    db: Session = Depends(get_db),
    operator: OperatorIdentity = Depends(require_operator_role(_WRITE_ROLES)),
):
    return LifecycleResponse(
        **resume_operations(
            db,
            tenant_id=tenant_id,
            operator_id=operator["id"],
            config_version=body.config_version,
            reason=body.reason,
        )
    )


@router.get("/{tenant_id}/activation-history", response_model=ActivationHistoryResponse)
def tenant_activation_history(
    tenant_id: str,
    db: Session = Depends(get_db),
    operator: OperatorIdentity = Depends(require_operator_role(_READ_ROLES)),
):
    _ = operator
    return ActivationHistoryResponse(**list_activation_history(db, tenant_id))


@router.get("/{tenant_id}/settings/{section}", response_model=TenantSettingsSectionResponse)
def tenant_settings_get(
    tenant_id: str,
    section: str,
    db: Session = Depends(get_db),
    operator: OperatorIdentity = Depends(require_operator_role(_READ_ROLES)),
):
    _ = operator
    return TenantSettingsSectionResponse(**get_settings_section(db, tenant_id, section))


@router.patch("/{tenant_id}/settings/{section}", response_model=TenantSettingsSectionResponse)
def tenant_settings_patch(
    tenant_id: str,
    section: str,
    body: TenantSettingsSectionPatchRequest,
    db: Session = Depends(get_db),
    operator: OperatorIdentity = Depends(require_operator_role(_WRITE_ROLES)),
):
    return TenantSettingsSectionResponse(
        **patch_settings_section(
            db,
            tenant_id=tenant_id,
            section=section,
            operator_id=operator["id"],
            config_version=body.config_version,
            payload=body.payload,
        )
    )


@router.get("/{tenant_id}/delete/dry-run", response_model=TenantDeleteDryRunResponse)
def tenant_delete_dry_run(
    tenant_id: str,
    db: Session = Depends(get_db),
    operator: OperatorIdentity = Depends(require_operator_role(_SUPER_ADMIN_ROLES)),
):
    _require_super_admin(operator)
    dry = TenantDeletionService.dry_run(db, tenant_id)
    return TenantDeleteDryRunResponse(
        tenant_id=dry.tenant_id,
        is_test_tenant=dry.is_test_tenant,
        deletable=dry.deletable,
        blocked_reason=dry.blocked_reason,
        tables=dry.tables,
    )


@router.delete("/{tenant_id}", status_code=200)
def tenant_delete(
    tenant_id: str,
    body: TenantDeleteRequest,
    db: Session = Depends(get_db),
    operator: OperatorIdentity = Depends(require_operator_role(_SUPER_ADMIN_ROLES)),
):
    _require_super_admin(operator)
    try:
        report = TenantDeletionService.execute(
            db,
            tenant_id=tenant_id,
            operator_id=operator["id"],
            reason=body.reason,
            confirm_tenant_id=body.confirm_tenant_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "deleted", "tenant_id": tenant_id, "lines": len(report.lines)}
