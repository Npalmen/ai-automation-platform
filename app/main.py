from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.audit_list_response_schemas import AuditEventListResponse
from app.core.audit_service import create_audit_event
from app.core.auth import get_verified_tenant
from app.core.config import get_tenant_config
from app.core.logging import setup_logging
from app.core.settings import get_settings
from app.core.tenancy import set_current_tenant
from app.domain.integrations.response_schemas import (
    IntegrationEventListResponse,
    IntegrationEventResponse,
)
from app.domain.workflows.action_execution_response_schemas import (
    ActionExecutionListResponse,
    ActionExecutionResponse,
)
from app.domain.workflows.approval_request_schemas import ApprovalDecisionRequest
from app.domain.workflows.approval_response_schemas import (
    ApprovalRequestListResponse,
    ApprovalRequestResponse,
)
from app.domain.workflows.list_response_schemas import JobListResponse
from app.domain.workflows.models import Job
from app.domain.workflows.response_schemas import JobResponse
from app.domain.workflows.schemas import JobCreateRequest
from app.integrations.enums import IntegrationType
from app.integrations.factory import get_integration_adapter
from app.integrations.metadata import INTEGRATION_METADATA
from app.integrations.policies import is_integration_enabled_for_tenant
from app.integrations.registry import IMPLEMENTED_INTEGRATIONS
from app.integrations.schemas import IntegrationActionRequest
from app.integrations.service import get_integration_connection_config
from app.repositories.postgres.action_execution_repository import ActionExecutionRepository
from app.repositories.postgres.approval_repository import ApprovalRequestRepository
from app.repositories.postgres.audit_repository import AuditRepository
from app.repositories.postgres.database import Base
from app.repositories.postgres.integration_repository import IntegrationRepository
from app.repositories.postgres.job_repository import JobRepository
from app.repositories.postgres.session import engine
from app.workflows.approval_service import resolve_approval
from app.workflows.pipeline_runner import run_pipeline
from app.workflows.policies import is_job_type_enabled_for_tenant
from app.workflows.processor_metadata import PROCESSOR_METADATA

settings = get_settings()
setup_logging()

app = FastAPI(title=settings.APP_NAME)


@app.on_event("startup")
async def on_startup():
    import app.repositories.postgres  # noqa: F401

    Base.metadata.create_all(bind=engine)
    print("Startup complete")


@app.middleware("http")
async def tenant_middleware(request: Request, call_next):
    tenant_id = request.headers.get("X-Tenant-ID", "TENANT_1001")
    set_current_tenant(tenant_id)
    response = await call_next(request)
    return response


@app.get("/")
def root():
    return {
        "status": "ok",
        "app_name": settings.APP_NAME,
        "env": settings.ENV,
    }


@app.get("/ui", response_class=HTMLResponse, include_in_schema=False)
def operator_ui():
    html = (Path(__file__).parent / "ui" / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@app.get("/tenant")
def tenant_info(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    config = get_tenant_config(tenant_id, db=db)
    # Normalise allowed_integrations to strings (static config stores enum objects).
    allowed = [
        i.value if hasattr(i, "value") else str(i)
        for i in (config.get("allowed_integrations") or [])
    ]
    return {
        "current_tenant": tenant_id,
        "name": config.get("name"),
        "enabled_job_types": config.get("enabled_job_types") or [],
        "auto_actions": config.get("auto_actions") or {},
        "allowed_integrations": allowed,
    }


from pydantic import BaseModel as _BaseModel


class TenantCreateRequest(_BaseModel):
    tenant_id: str
    name: str


class TenantConfigUpdateRequest(_BaseModel):
    enabled_job_types: list[str]
    allowed_integrations: list[str]
    auto_actions: dict[str, bool]


@app.get("/tenant/config/{tenant_id}")
def get_tenant_config_by_id(
    tenant_id: str,
    db: Session = Depends(get_db),
):
    """Return config for any tenant by ID. No auth required — operator bootstrap helper."""
    config = get_tenant_config(tenant_id, db=db)
    allowed = [
        i.value if hasattr(i, "value") else str(i)
        for i in (config.get("allowed_integrations") or [])
    ]
    return {
        "current_tenant": tenant_id,
        "name": config.get("name"),
        "enabled_job_types": config.get("enabled_job_types") or [],
        "auto_actions": config.get("auto_actions") or {},
        "allowed_integrations": allowed,
    }


@app.get("/tenants")
def list_tenants(
    db: Session = Depends(get_db),
):
    """Return all tenants that exist in the DB. No fallback/static tenants included."""
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
    records = TenantConfigRepository.list_all(db)
    items = [{"tenant_id": r.tenant_id, "name": r.name} for r in records]
    return {"items": items, "total": len(items)}


@app.post("/tenant", status_code=201)
def create_tenant(
    request: TenantCreateRequest,
    db: Session = Depends(get_db),
):
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
    existing = TenantConfigRepository.get(db, request.tenant_id)
    if existing is not None:
        raise HTTPException(
            status_code=400,
            detail=f"Tenant '{request.tenant_id}' already exists.",
        )
    TenantConfigRepository.upsert(
        db=db,
        tenant_id=request.tenant_id,
        name=request.name,
        enabled_job_types=[],
        allowed_integrations=[],
        auto_actions={},
    )
    return {"status": "created", "tenant_id": request.tenant_id, "name": request.name}


@app.put("/tenant/config")
def update_tenant_config(
    request: TenantConfigUpdateRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
    TenantConfigRepository.upsert(
        db=db,
        tenant_id=tenant_id,
        enabled_job_types=request.enabled_job_types,
        allowed_integrations=request.allowed_integrations,
        auto_actions=request.auto_actions,
    )
    return {"status": "ok", "tenant_id": tenant_id}



@app.post("/jobs", response_model=Job)
def create_job(
    request: JobCreateRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):

    if tenant_id != request.tenant_id:
        raise HTTPException(
            status_code=400,
            detail=f"Tenant mismatch. Header tenant '{tenant_id}' does not match payload tenant '{request.tenant_id}'.",
        )

    if not is_job_type_enabled_for_tenant(request.job_type, tenant_id, db=db):
        raise HTTPException(
            status_code=403,
            detail=f"Job type '{request.job_type}' is not enabled for tenant '{tenant_id}'.",
        )

    job = Job(
        tenant_id=request.tenant_id,
        job_type=request.job_type,
        input_data=request.input_data,
    )

    saved_job = JobRepository.create_job(db, job)

    create_audit_event(
        db=db,
        tenant_id=tenant_id,
        category="workflow",
        action="job_created",
        status="success",
        details={
            "job_id": saved_job.job_id,
            "job_type": saved_job.job_type.value if hasattr(saved_job.job_type, "value") else str(saved_job.job_type),
        },
    )

    processed_job = run_pipeline(saved_job, db)

    return processed_job


@app.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(
    job_id: str,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):

    job = JobRepository.get_job_by_id(db, tenant_id, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    return JobResponse(**job.model_dump())


@app.get("/jobs", response_model=JobListResponse)
def list_jobs(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
    limit: int = 50,
    offset: int = 0,
):

    jobs = JobRepository.list_jobs(db, tenant_id=tenant_id, limit=limit, offset=offset)
    total = JobRepository.count_jobs(db, tenant_id=tenant_id)

    return JobListResponse(
        items=[JobResponse(**job.model_dump()) for job in jobs],
        total=total,
    )


@app.get("/jobs/{job_id}/actions", response_model=ActionExecutionListResponse)
def get_job_actions(
    job_id: str,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):

    job = JobRepository.get_job_by_id(db, tenant_id, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    records = ActionExecutionRepository.list_for_job(
        db=db,
        tenant_id=tenant_id,
        job_id=job_id,
    )

    return ActionExecutionListResponse(
        items=[
            ActionExecutionResponse(**ActionExecutionRepository.to_dict(record))
            for record in records
        ],
        total=len(records),
    )


@app.get("/jobs/{job_id}/approvals", response_model=ApprovalRequestListResponse)
def get_job_approvals(
    job_id: str,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):

    job = JobRepository.get_job_by_id(db, tenant_id, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    records = ApprovalRequestRepository.list_for_job(
        db=db,
        tenant_id=tenant_id,
        job_id=job_id,
    )

    return ApprovalRequestListResponse(
        items=[
            ApprovalRequestResponse(**ApprovalRequestRepository.to_dict(record))
            for record in records
        ],
        total=len(records),
    )


@app.get("/approvals/pending", response_model=ApprovalRequestListResponse)
def list_pending_approvals(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
    limit: int = 100,
    offset: int = 0,
):

    records = ApprovalRequestRepository.list_pending_for_tenant(
        db=db,
        tenant_id=tenant_id,
        limit=limit,
        offset=offset,
    )
    total = ApprovalRequestRepository.count_pending_for_tenant(
        db=db,
        tenant_id=tenant_id,
    )

    return ApprovalRequestListResponse(
        items=[
            ApprovalRequestResponse(**ApprovalRequestRepository.to_dict(record))
            for record in records
        ],
        total=total,
    )


@app.post("/approvals/{approval_id}/approve", response_model=JobResponse)
def approve_request(
    approval_id: str,
    request: ApprovalDecisionRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):

    approval = ApprovalRequestRepository.get_by_approval_id(
        db=db,
        tenant_id=tenant_id,
        approval_id=approval_id,
    )
    if approval is None:
        raise HTTPException(status_code=404, detail=f"Approval '{approval_id}' not found.")

    job = resolve_approval(
        db=db,
        tenant_id=tenant_id,
        job_id=approval.job_id,
        approved=True,
        actor=request.actor,
        channel=request.channel,
        note=request.note,
    )

    return JobResponse(**job.model_dump())


@app.post("/approvals/{approval_id}/reject", response_model=JobResponse)
def reject_request(
    approval_id: str,
    request: ApprovalDecisionRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):

    approval = ApprovalRequestRepository.get_by_approval_id(
        db=db,
        tenant_id=tenant_id,
        approval_id=approval_id,
    )
    if approval is None:
        raise HTTPException(status_code=404, detail=f"Approval '{approval_id}' not found.")

    job = resolve_approval(
        db=db,
        tenant_id=tenant_id,
        job_id=approval.job_id,
        approved=False,
        actor=request.actor,
        channel=request.channel,
        note=request.note,
    )

    return JobResponse(**job.model_dump())


@app.get("/processors")
def list_processors():
    return {
        "items": PROCESSOR_METADATA,
        "total": len(PROCESSOR_METADATA),
    }


@app.get("/integrations")
def list_integrations(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    items = []
    for integration_type in IMPLEMENTED_INTEGRATIONS:
        if is_integration_enabled_for_tenant(tenant_id, integration_type, db=db):
            items.append(INTEGRATION_METADATA[integration_type.value])

    return {
        "items": items,
        "total": len(items),
    }


@app.post("/integrations/{integration_type}/execute", response_model=IntegrationEventResponse)
def execute_integration_action(
    integration_type: IntegrationType,
    request: IntegrationActionRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):

    if not is_integration_enabled_for_tenant(tenant_id, integration_type, db=db):
        raise HTTPException(
            status_code=403,
            detail=f"Integration '{integration_type.value}' is not enabled for tenant '{tenant_id}'.",
        )

    connection_config = get_integration_connection_config(
        tenant_id=tenant_id,
        integration_type=integration_type,
    )
    adapter = get_integration_adapter(
        integration_type=integration_type,
        connection_config=connection_config,
    )

    result = adapter.execute_action(
        action=request.action,
        payload=request.payload,
    )

    from app.domain.integrations.models import IntegrationEvent
    status = result.get("status", "success")
    record = IntegrationEvent(
        tenant_id=tenant_id,
        job_id="direct",
        integration_type=integration_type.value,
        payload={"action": request.action, "request": request.payload, "result": result},
        status=status,
        attempts=1,
        idempotency_key=str(uuid4()),
    )
    repo = IntegrationRepository(db)
    saved = repo.create(record)

    return IntegrationEventResponse.model_validate(saved)


@app.get("/integration-events", response_model=IntegrationEventListResponse)
def list_integration_events(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
    limit: int = 50,
    offset: int = 0,
):

    events = IntegrationRepository.list_events(
        db=db,
        tenant_id=tenant_id,
        limit=limit,
        offset=offset,
    )
    total = IntegrationRepository.count_events(
        db=db,
        tenant_id=tenant_id,
    )

    return IntegrationEventListResponse(
        items=events,
        total=total,
    )


@app.get("/audit-events", response_model=AuditEventListResponse)
def list_audit_events(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
    limit: int = 50,
    offset: int = 0,
):

    events = AuditRepository.list_events(
        db=db,
        tenant_id=tenant_id,
        limit=limit,
        offset=offset,
    )
    total = AuditRepository.count_events(
        db=db,
        tenant_id=tenant_id,
    )

    return AuditEventListResponse(
        items=events,
        total=total,
    )