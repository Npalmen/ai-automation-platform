from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.tenancy import get_current_tenant, set_current_tenant
from app.domain.workflows.approval_schemas import ApprovalDecisionRequest
from app.domain.workflows.models import Job
from app.workflows.approval_service import get_approval_status, resolve_approval
from app.repositories.postgres.job_repository import JobRepository

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("/{job_id}")
def get_job_approval(
    job_id: str,
    db: Session = Depends(get_db),
    x_tenant_id: str | None = Header(default=None),
):
    if x_tenant_id is not None:
        set_current_tenant(x_tenant_id)

    tenant_id = get_current_tenant()
    job = JobRepository.get_job_by_id(db, tenant_id, job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail=f"Job '{job_id}' not found for tenant '{tenant_id}'.",
        )

    return get_approval_status(job)


@router.post("/{job_id}/approve", response_model=Job)
def approve_job(
    job_id: str,
    request: ApprovalDecisionRequest,
    db: Session = Depends(get_db),
    x_tenant_id: str | None = Header(default=None),
):
    if x_tenant_id is not None:
        set_current_tenant(x_tenant_id)

    tenant_id = get_current_tenant()

    try:
        return resolve_approval(
            db=db,
            tenant_id=tenant_id,
            job_id=job_id,
            approved=True,
            actor=request.actor,
            channel=request.channel,
            note=request.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{job_id}/reject", response_model=Job)
def reject_job(
    job_id: str,
    request: ApprovalDecisionRequest,
    db: Session = Depends(get_db),
    x_tenant_id: str | None = Header(default=None),
):
    if x_tenant_id is not None:
        set_current_tenant(x_tenant_id)

    tenant_id = get_current_tenant()

    try:
        return resolve_approval(
            db=db,
            tenant_id=tenant_id,
            job_id=job_id,
            approved=False,
            actor=request.actor,
            channel=request.channel,
            note=request.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc