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

    # TEMPORARY: local-debug — verify Google OAuth env vars are loaded from .env
    def _masked(val: str) -> str:
        return f"yes (prefix={val[:8]}...)" if val else "no"

    _s = get_settings()
    print("[DEBUG] GOOGLE_MAIL_ACCESS_TOKEN  :", _masked(_s.GOOGLE_MAIL_ACCESS_TOKEN))
    print("[DEBUG] GOOGLE_OAUTH_REFRESH_TOKEN:", _masked(_s.GOOGLE_OAUTH_REFRESH_TOKEN))
    print("[DEBUG] GOOGLE_OAUTH_CLIENT_ID    :", _masked(_s.GOOGLE_OAUTH_CLIENT_ID))
    print("[DEBUG] GOOGLE_OAUTH_CLIENT_SECRET:", _masked(_s.GOOGLE_OAUTH_CLIENT_SECRET))
    # END TEMPORARY


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
    auto_actions: dict[str, bool | str]


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


# --- Verification pipeline helpers ---

# Job types with full deterministic pipeline support (no LLM required).
_VERIFICATION_SUPPORTED_TYPES = ["lead", "customer_inquiry", "invoice"]

# Realistic input payloads per supported job type.
_VERIFICATION_PAYLOADS: dict[str, dict] = {
    "lead": {
        "subject": "Intresserad av era tjänster – önskar mer information",
        "message_text": (
            "Hej, jag heter Erik Lindqvist och arbetar som inköpschef på Lindqvist Industri AB. "
            "Vi har sett er presentation och är intresserade av att veta mer om era automationslösningar. "
            "Kan ni skicka en offert och boka ett möte? Telefon: 070-1234567."
        ),
        "sender": {"name": "Erik Lindqvist", "email": "erik@lindqvist-industri.se", "phone": "070-1234567"},
    },
    "customer_inquiry": {
        "subject": "Fråga angående faktura #INV-2024-0042",
        "message_text": (
            "Hej, jag har en fråga om faktura nummer INV-2024-0042 som vi fick förra veckan. "
            "Beloppet stämmer inte med den offert vi fick. Kan ni se över detta och återkomma? "
            "Med vänliga hälsningar, Sara Johansson."
        ),
        "sender": {"name": "Sara Johansson", "email": "sara@kund.se", "phone": None},
    },
    "invoice": {
        "subject": "Faktura #2024-0099 från Leverantör AB",
        "message_text": (
            "Bifogad faktura #2024-0099 från Leverantör AB, org.nr 556123-4567. "
            "Fakturadatum: 2024-01-15. Förfallodatum: 2024-02-14. "
            "Belopp exkl. moms: 15 000 SEK. Moms: 3 750 SEK. Totalt: 18 750 SEK. "
            "Referens: PO-2024-88."
        ),
        "sender": {"name": "Leverantör AB", "email": "faktura@leverantor.se", "phone": None},
    },
}

# Synthetic processor history injected per type to bypass LLM steps.
def _synthetic_history(job_type_value: str) -> list[dict]:
    """
    Returns pre-seeded processor history entries for all AI steps.
    Policy and human_handoff processors read from this history and are deterministic.
    """
    classification = {
        "processor": "classification_processor",
        "result": {
            "status": "completed",
            "summary": "Verifieringsklassificering (deterministisk).",
            "requires_human_review": False,
            "payload": {
                "processor_name": "classification_processor",
                "detected_job_type": job_type_value,
                "confidence": 0.95,
                "reasons": ["verification_synthetic"],
                "recommended_next_step": job_type_value,
                "used_fallback": False,
                "prompt_name": "classification_v1",
                "duration_ms": 0,
                "low_confidence": False,
            },
        },
    }

    entity_extraction = {
        "processor": "entity_extraction_processor",
        "result": {
            "status": "completed",
            "summary": "Verifieringsentitetsextrahering (deterministisk).",
            "requires_human_review": False,
            "payload": {
                "processor_name": "entity_extraction_processor",
                "entities": {
                    "customer_name": "Verifieringskund",
                    "email": "verify@test.internal",
                },
                "confidence": 0.9,
                "validation": {"issues": []},
                "used_fallback": False,
                "prompt_name": "entity_extraction_v1",
                "duration_ms": 0,
                "low_confidence": False,
            },
        },
    }

    if job_type_value == "lead":
        type_specific = {
            "processor": "lead_processor",
            "result": {
                "status": "completed",
                "summary": "Verifiering lead scoring (deterministisk).",
                "requires_human_review": False,
                "payload": {
                    "processor_name": "lead_processor",
                    "lead_score": 70,
                    "priority": "medium",
                    "routing": "crm_update",
                    "reasons": ["verification_synthetic"],
                    "confidence": 0.85,
                    "recommended_next_step": "crm_update",
                    "used_fallback": False,
                    "prompt_name": "lead_scoring_v1",
                    "duration_ms": 0,
                    "low_confidence": False,
                },
            },
        }
        decisioning = {
            "processor": "decisioning_processor",
            "result": {
                "status": "completed",
                "summary": "Verifiering decisioning (deterministisk).",
                "requires_human_review": False,
                "payload": {
                    "processor_name": "decisioning_processor",
                    "decision": "auto_execute",
                    "target_queue": "crm_update",
                    "action_flags": {"create_crm_lead": True, "notify_human": False, "request_missing_data": False},
                    "reasons": ["verification_synthetic"],
                    "confidence": 0.9,
                    "recommended_next_step": "action_dispatch",
                    "used_fallback": False,
                    "prompt_name": "decisioning_v1",
                    "duration_ms": 0,
                    "low_confidence": False,
                },
            },
        }
        return [classification, entity_extraction, type_specific, decisioning]

    if job_type_value == "customer_inquiry":
        type_specific = {
            "processor": "customer_inquiry_processor",
            "result": {
                "status": "completed",
                "summary": "Verifiering kundförfrågan (deterministisk).",
                "requires_human_review": False,
                "payload": {
                    "processor_name": "customer_inquiry_processor",
                    "inquiry_type": "billing",
                    "priority": "medium",
                    "routing": "billing_queue",
                    "reasons": ["verification_synthetic"],
                    "confidence": 0.85,
                    "recommended_next_step": "billing_queue",
                    "used_fallback": False,
                    "prompt_name": "inquiry_analysis_v1",
                    "duration_ms": 0,
                    "low_confidence": False,
                },
            },
        }
        decisioning = {
            "processor": "decisioning_processor",
            "result": {
                "status": "completed",
                "summary": "Verifiering decisioning (deterministisk).",
                "requires_human_review": False,
                "payload": {
                    "processor_name": "decisioning_processor",
                    "decision": "auto_execute",
                    "target_queue": "billing_queue",
                    "action_flags": {"create_crm_lead": False, "notify_human": False, "request_missing_data": False},
                    "reasons": ["verification_synthetic"],
                    "confidence": 0.9,
                    "recommended_next_step": "action_dispatch",
                    "used_fallback": False,
                    "prompt_name": "decisioning_v1",
                    "duration_ms": 0,
                    "low_confidence": False,
                },
            },
        }
        return [classification, entity_extraction, type_specific, decisioning]

    if job_type_value == "invoice":
        type_specific = {
            "processor": "invoice_processor",
            "result": {
                "status": "completed",
                "summary": "Verifiering fakturaanalys (deterministisk).",
                "requires_human_review": False,
                "payload": {
                    "processor_name": "invoice_processor",
                    "invoice_data": {
                        "supplier_name": "Leverantör AB",
                        "invoice_number": "2024-0099",
                        "amount_ex_vat": 15000.0,
                        "vat_amount": 3750.0,
                        "amount_inc_vat": 18750.0,
                        "currency": "SEK",
                    },
                    "validation_status": "validated",
                    "duplicate_suspected": False,
                    "missing_critical": [],
                    "approval_route": "approval_required",
                    "reasons": ["verification_synthetic"],
                    "confidence": 0.9,
                    "validation": {"issues": []},
                    "used_fallback": False,
                    "prompt_name": "invoice_analysis_v1",
                    "duration_ms": 0,
                    "low_confidence": False,
                },
            },
        }
        return [classification, entity_extraction, type_specific]

    return [classification, entity_extraction]


def _run_verification_pipeline(job: Job, job_type_value: str, db) -> Job:
    """
    Run a deterministic verification pipeline without LLM calls.

    Injects synthetic processor history for all AI steps, then runs the
    deterministic processors (intake, policy, human_handoff) directly.
    Policy reads from the injected history and routes correctly without LLM.
    """
    from datetime import datetime, timezone
    from app.domain.workflows.statuses import JobStatus
    from app.workflows.processors.intake_processor import process_universal_intake_job
    from app.workflows.processors.policy_processor import process_policy_job
    from app.workflows.processors.human_handoff_processor import process_human_handoff_job

    # Step 1: intake (deterministic, no LLM)
    job = process_universal_intake_job(job)

    # Step 2: inject synthetic AI step results
    for entry in _synthetic_history(job_type_value):
        job.processor_history.append(entry)
        job.result = entry["result"]

    # Step 3: policy (deterministic — reads from injected history)
    job = process_policy_job(job)

    # Step 4: human_handoff (deterministic — reads from policy result)
    job = process_human_handoff_job(job)

    # Step 5: finalise status
    from app.workflows.approval_service import has_pending_approval
    requires_human_review = bool((job.result or {}).get("requires_human_review", False))

    if has_pending_approval(job):
        job.status = JobStatus.AWAITING_APPROVAL
    elif requires_human_review:
        job.status = JobStatus.MANUAL_REVIEW
    else:
        job.status = JobStatus.COMPLETED

    job.updated_at = datetime.now(timezone.utc)

    if db is not None:
        job = JobRepository.update_job(db, job)

    return job


@app.post("/verify/{tenant_id}", status_code=200)
def verify_tenant(
    tenant_id: str,
    db: Session = Depends(get_db),
):
    """
    Run a deterministic verification job for any tenant by ID.
    No auth required — operator bootstrap helper.

    Picks the first supported enabled job type from the tenant's DB config and
    runs a synthetic pipeline that bypasses LLM calls. Returns a meaningful
    result (completed / awaiting_approval) without requiring AI credentials.
    """
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
    from app.domain.workflows.enums import JobType

    record = TenantConfigRepository.get(db, tenant_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"Tenant '{tenant_id}' not found.",
        )

    enabled = record.enabled_job_types or []
    if not enabled:
        raise HTTPException(
            status_code=400,
            detail=f"Tenant '{tenant_id}' has no enabled job types. Configure at least one job type before verifying.",
        )

    # Pick the first enabled type that has full verification support.
    job_type_value = next(
        (t for t in enabled if t in _VERIFICATION_SUPPORTED_TYPES),
        None,
    )
    if job_type_value is None:
        supported_str = ", ".join(_VERIFICATION_SUPPORTED_TYPES)
        raise HTTPException(
            status_code=400,
            detail=(
                f"Tenant '{tenant_id}' has no verifiable job types enabled. "
                f"Enable at least one of: {supported_str}."
            ),
        )

    try:
        job_type_enum = JobType(job_type_value)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Job type '{job_type_value}' is not a recognised job type.",
        )

    input_data = _VERIFICATION_PAYLOADS[job_type_value]
    job = Job(
        tenant_id=tenant_id,
        job_type=job_type_enum,
        input_data=input_data,
    )

    set_current_tenant(tenant_id)
    saved_job = JobRepository.create_job(db, job)
    processed_job = _run_verification_pipeline(saved_job, job_type_value, db)

    return {
        "job_id": processed_job.job_id,
        "tenant_id": processed_job.tenant_id,
        "job_type": job_type_value,
        "status": processed_job.status.value if hasattr(processed_job.status, "value") else str(processed_job.status),
        "result": processed_job.result,
        "verification_type": job_type_value,
    }


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


@app.put("/tenant/config/{tenant_id}")
def update_tenant_config_by_id(
    tenant_id: str,
    request: TenantConfigUpdateRequest,
    db: Session = Depends(get_db),
):
    """Save config for any tenant by ID. No auth required — operator bootstrap helper."""
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
    existing = TenantConfigRepository.get(db, tenant_id)
    if existing is None:
        raise HTTPException(
            status_code=404,
            detail=f"Tenant '{tenant_id}' not found.",
        )
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