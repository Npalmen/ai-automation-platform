import asyncio
from fastapi import FastAPI, Request, Header, HTTPException, Depends
from sqlalchemy.orm import Session

from app.core.logging import setup_logging
from app.core.settings import get_settings
from app.core.config import get_tenant_config
from app.core.tenancy import set_current_tenant, get_current_tenant

from app.domain.workflows.models import Job
from app.domain.workflows.schemas import JobCreateRequest
from app.domain.workflows.response_schemas import JobResponse
from app.domain.workflows.list_response_schemas import JobListResponse

from app.domain.integrations.response_schemas import (
    IntegrationEventResponse,
    IntegrationEventListResponse,
)

from app.workflows.processor_metadata import PROCESSOR_METADATA
from app.workflows.policies import is_job_type_enabled_for_tenant
from app.workflows.pipeline_runner import run_pipeline

from app.integrations.metadata import INTEGRATION_METADATA
from app.integrations.enums import IntegrationType
from app.integrations.policies import is_integration_enabled_for_tenant
from app.integrations.factory import get_integration_adapter
from app.integrations.schemas import IntegrationActionRequest
from app.integrations.registry import IMPLEMENTED_INTEGRATIONS
from app.integrations.service import get_integration_connection_config
from app.integrations.dispatcher import IntegrationDispatcher

from app.core.audit_service import create_audit_event
from app.core.audit_list_response_schemas import AuditEventListResponse

from app.api.dependencies import get_db
from app.repositories.postgres.audit_repository import AuditRepository
from app.repositories.postgres.job_repository import JobRepository
from app.repositories.postgres.integration_repository import IntegrationRepository
from app.repositories.postgres.base import Base
from app.repositories.postgres.session import engine

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


@app.get("/tenant")
def tenant_info(x_tenant_id: str = Header(default="TENANT_1001")):
    set_current_tenant(x_tenant_id)

    tenant_id = get_current_tenant()
    config = get_tenant_config(tenant_id)

    return {
        "current_tenant": tenant_id,
        "name": config.get("name"),
        "auto_actions": config.get("auto_actions"),
        "allowed_integrations": config.get("allowed_integrations"),
    }


@app.get("/tenant/test")
def tenant_test(tenant_id: str = "TENANT_1001"):
    set_current_tenant(tenant_id)

    config = get_tenant_config(tenant_id)

    return {
        "current_tenant": tenant_id,
        "name": config.get("name"),
        "auto_actions": config.get("auto_actions"),
        "allowed_integrations": config.get("allowed_integrations"),
    }


@app.post("/jobs")
def create_job(
    payload: JobCreateRequest,
    db: Session = Depends(get_db),
    x_tenant_id: str | None = Header(default=None),
):
    if x_tenant_id is not None:
        set_current_tenant(x_tenant_id)

    current_tenant = get_current_tenant()

    if not is_job_type_enabled_for_tenant(current_tenant, payload.job_type):
        raise HTTPException(
            status_code=403,
            detail=f"Job type '{payload.job_type.value}' is not enabled for tenant '{current_tenant}'.",
        )

    job = Job(
        tenant_id=current_tenant,
        job_type=payload.job_type,
        input_data=payload.input_data,
    )

    JobRepository.create_job(db, job)
    job = run_pipeline(job, db)
    JobRepository.update_job(db, job)

    return job


@app.get("/job-types")
def get_job_types(x_tenant_id: str | None = Header(default=None)):
    if x_tenant_id is not None:
        set_current_tenant(x_tenant_id)

    current_tenant = get_current_tenant()
    tenant_config = get_tenant_config(current_tenant)

    allowed_integrations = tenant_config.get("allowed_integrations", [])
    enabled_job_types = tenant_config.get("enabled_job_types", [])

    return {
        "tenant_id": current_tenant,
        "allowed_integrations": allowed_integrations,
        "job_types": [
            {
                "type": job_type.value,
                "label": PROCESSOR_METADATA[job_type]["label"],
                "description": PROCESSOR_METADATA[job_type]["description"],
            }
            for job_type in enabled_job_types
            if job_type in PROCESSOR_METADATA
        ],
    }


@app.get("/integrations")
def get_integrations(x_tenant_id: str | None = Header(default=None)):
    if x_tenant_id is not None:
        set_current_tenant(x_tenant_id)

    current_tenant = get_current_tenant()
    tenant_config = get_tenant_config(current_tenant)

    allowed_integrations = tenant_config.get("allowed_integrations", [])

    return {
        "tenant_id": current_tenant,
        "integrations": [
            {
                "type": integration.value,
                "label": INTEGRATION_METADATA[integration]["label"],
                "description": INTEGRATION_METADATA[integration]["description"],
            }
            for integration in allowed_integrations
            if integration in INTEGRATION_METADATA
        ],
    }


@app.post("/integrations/{integration_type}/action")
def execute_integration_action(
    integration_type: IntegrationType,
    payload: IntegrationActionRequest,
    db: Session = Depends(get_db),
    x_tenant_id: str | None = Header(default=None),
):
    if x_tenant_id is not None:
        set_current_tenant(x_tenant_id)

    current_tenant = get_current_tenant()

    if not is_integration_enabled_for_tenant(current_tenant, integration_type):
        create_audit_event(
            db=db,
            tenant_id=current_tenant,
            category="integration",
            action="integration_action_denied",
            status="forbidden",
            details={
                "integration_type": integration_type.value,
                "action": payload.action,
            },
        )
        raise HTTPException(
            status_code=403,
            detail=f"Integration '{integration_type.value}' is not enabled for tenant '{current_tenant}'.",
        )

    connection_config = get_integration_connection_config(current_tenant, integration_type)
    adapter = get_integration_adapter(integration_type, connection_config=connection_config)
    result = adapter.execute_action(
        action=payload.action,
        payload=payload.payload,
    )

    create_audit_event(
        db=db,
        tenant_id=current_tenant,
        category="integration",
        action="integration_action_executed",
        status="success",
        details={
            "integration_type": integration_type.value,
            "action": payload.action,
        },
    )

    return result


@app.get("/integrations/{integration_type}/status")
def get_integration_status(
    integration_type: IntegrationType,
    db: Session = Depends(get_db),
    x_tenant_id: str | None = Header(default=None),
):
    if x_tenant_id is not None:
        set_current_tenant(x_tenant_id)

    current_tenant = get_current_tenant()

    if not is_integration_enabled_for_tenant(current_tenant, integration_type):
        create_audit_event(
            db=db,
            tenant_id=current_tenant,
            category="integration",
            action="integration_status_denied",
            status="forbidden",
            details={"integration_type": integration_type.value},
        )
        raise HTTPException(
            status_code=403,
            detail=f"Integration '{integration_type.value}' is not enabled for tenant '{current_tenant}'.",
        )

    connection_config = get_integration_connection_config(current_tenant, integration_type)
    adapter = get_integration_adapter(integration_type, connection_config=connection_config)
    result = adapter.get_status()

    create_audit_event(
        db=db,
        tenant_id=current_tenant,
        category="integration",
        action="integration_status_checked",
        status="success",
        details={"integration_type": integration_type.value},
    )

    return result


@app.post("/integrations/{integration_type}/smoke-test")
def smoke_test_integration(
    integration_type: IntegrationType,
    db: Session = Depends(get_db),
    x_tenant_id: str | None = Header(default=None),
):
    if x_tenant_id is not None:
        set_current_tenant(x_tenant_id)

    current_tenant = get_current_tenant()

    if not is_integration_enabled_for_tenant(current_tenant, integration_type):
        create_audit_event(
            db=db,
            tenant_id=current_tenant,
            category="integration",
            action="integration_smoke_test_denied",
            status="forbidden",
            details={"integration_type": integration_type.value},
        )
        raise HTTPException(
            status_code=403,
            detail=f"Integration '{integration_type.value}' is not enabled for tenant '{current_tenant}'.",
        )

    connection_config = get_integration_connection_config(current_tenant, integration_type)
    adapter = get_integration_adapter(integration_type, connection_config=connection_config)
    result = adapter.get_status()

    create_audit_event(
        db=db,
        tenant_id=current_tenant,
        category="integration",
        action="integration_smoke_test_executed",
        status="success",
        details={"integration_type": integration_type.value},
    )

    return {
        "tenant_id": current_tenant,
        "integration_type": integration_type.value,
        "status": "ok",
        "result": result,
    }


@app.get("/integrations/available")
def get_available_integrations(x_tenant_id: str | None = Header(default=None)):
    if x_tenant_id is not None:
        set_current_tenant(x_tenant_id)

    current_tenant = get_current_tenant()
    tenant_config = get_tenant_config(current_tenant)

    allowed_integrations = tenant_config.get("allowed_integrations", [])

    available_integrations = [
        integration
        for integration in allowed_integrations
        if integration in IMPLEMENTED_INTEGRATIONS
    ]

    return {
        "tenant_id": current_tenant,
        "integrations": [
            {
                "type": integration.value,
                "label": INTEGRATION_METADATA[integration]["label"],
                "description": INTEGRATION_METADATA[integration]["description"],
            }
            for integration in available_integrations
            if integration in INTEGRATION_METADATA
        ],
    }


@app.get("/integrations/events", response_model=IntegrationEventListResponse)
def list_integration_events(
    limit: int = 100,
    offset: int = 0,
    status: str | None = None,
    integration_type: str | None = None,
    db: Session = Depends(get_db),
    x_tenant_id: str | None = Header(default=None),
):
    if x_tenant_id is not None:
        set_current_tenant(x_tenant_id)

    current_tenant = get_current_tenant()
    repo = IntegrationRepository(db)

    events = repo.list_events_for_tenant(
        tenant_id=current_tenant,
        limit=limit,
        offset=offset,
        status=status,
        integration_type=integration_type,
    )
    total = repo.count_events_for_tenant(
        tenant_id=current_tenant,
        status=status,
        integration_type=integration_type,
    )

    return {
        "tenant_id": current_tenant,
        "total": total,
        "limit": limit,
        "offset": offset,
        "events": events,
    }


@app.get("/integrations/events/{event_id}", response_model=IntegrationEventResponse)
def get_integration_event(
    event_id: int,
    db: Session = Depends(get_db),
    x_tenant_id: str | None = Header(default=None),
):
    if x_tenant_id is not None:
        set_current_tenant(x_tenant_id)

    current_tenant = get_current_tenant()
    repo = IntegrationRepository(db)

    event = repo.get_event_by_id(
        tenant_id=current_tenant,
        event_id=event_id,
    )

    if event is None:
        raise HTTPException(
            status_code=404,
            detail=f"Integration event '{event_id}' not found for tenant '{current_tenant}'.",
        )

    return event


@app.post("/integrations/events/{event_id}/retry", response_model=IntegrationEventResponse)
async def retry_integration_event(
    event_id: int,
    db: Session = Depends(get_db),
    x_tenant_id: str | None = Header(default=None),
):
    if x_tenant_id is not None:
        set_current_tenant(x_tenant_id)

    current_tenant = get_current_tenant()
    repo = IntegrationRepository(db)

    event = repo.get_event_by_id(
        tenant_id=current_tenant,
        event_id=event_id,
    )

    if event is None:
        raise HTTPException(
            status_code=404,
            detail=f"Integration event '{event_id}' not found for tenant '{current_tenant}'.",
        )

    event.status = "failed"
    event.last_error = None
    repo.update(event)

    dispatcher = IntegrationDispatcher(db)
    await dispatcher._execute(event)

    create_audit_event(
        db=db,
        tenant_id=current_tenant,
        category="integration",
        action="integration_event_retried",
        status="success",
        details={
            "event_id": event.id,
            "integration_type": event.integration_type,
            "attempts": event.attempts,
            "final_status": event.status,
        },
    )

    return event


@app.get("/integrations/events/all", response_model=IntegrationEventListResponse)
def list_all_integration_events(
    limit: int = 100,
    offset: int = 0,
    status: str | None = None,
    integration_type: str | None = None,
    db: Session = Depends(get_db),
):
    repo = IntegrationRepository(db)

    events = repo.list_all_events(
        limit=limit,
        offset=offset,
        status=status,
        integration_type=integration_type,
    )
    total = repo.count_all_events(
        status=status,
        integration_type=integration_type,
    )

    return {
        "tenant_id": None,
        "total": total,
        "limit": limit,
        "offset": offset,
        "events": events,
    }


@app.get("/audit/events", response_model=AuditEventListResponse)
def get_audit_events(
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    x_tenant_id: str | None = Header(default=None),
):
    if x_tenant_id is not None:
        set_current_tenant(x_tenant_id)

    current_tenant = get_current_tenant()

    events = AuditRepository.list_events_for_tenant(
        db=db,
        tenant_id=current_tenant,
        limit=limit,
        offset=offset,
    )
    total = AuditRepository.count_events_for_tenant(db, current_tenant)

    return {
        "tenant_id": current_tenant,
        "total": total,
        "limit": limit,
        "offset": offset,
        "events": events,
    }


@app.get("/audit/events/all", response_model=AuditEventListResponse)
def get_all_audit_events(
    limit: int = 200,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    events = AuditRepository.list_all_events(
        db=db,
        limit=limit,
        offset=offset,
    )
    total = AuditRepository.count_all_events(db)

    return {
        "tenant_id": None,
        "total": total,
        "limit": limit,
        "offset": offset,
        "events": events,
    }


@app.get("/jobs", response_model=JobListResponse)
def list_jobs(
    limit: int = 20,
    offset: int = 0,
    job_type: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    x_tenant_id: str | None = Header(default=None),
):
    if x_tenant_id is not None:
        set_current_tenant(x_tenant_id)

    current_tenant = get_current_tenant()

    jobs = JobRepository.list_jobs_for_tenant(
        db=db,
        tenant_id=current_tenant,
        limit=limit,
        offset=offset,
        job_type=job_type,
        status=status,
    )

    total = JobRepository.count_jobs_for_tenant(
        db=db,
        tenant_id=current_tenant,
        job_type=job_type,
        status=status,
    )

    return {
        "tenant_id": current_tenant,
        "total": total,
        "limit": limit,
        "offset": offset,
        "jobs": jobs,
    }


@app.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(
    job_id: str,
    db: Session = Depends(get_db),
    x_tenant_id: str | None = Header(default=None),
):
    if x_tenant_id is not None:
        set_current_tenant(x_tenant_id)

    current_tenant = get_current_tenant()
    job = JobRepository.get_job_by_id(db, current_tenant, job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail=f"Job '{job_id}' not found for tenant '{current_tenant}'.",
        )

    return job