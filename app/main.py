import re
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
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.job_repository import JobRepository
from app.repositories.postgres.session import engine
from app.workflows.action_executor import execute_action as dispatch_action
from app.workflows.approval_service import resolve_approval
from app.workflows.pipeline_runner import run_pipeline
from app.workflows.policies import is_job_type_enabled_for_tenant
from app.workflows.processor_metadata import PROCESSOR_METADATA
from app.workflows.processors.classification_processor import classify_email_type

settings = get_settings()
setup_logging()

app = FastAPI(title=settings.APP_NAME)


@app.on_event("startup")
async def on_startup():
    import app.repositories.postgres  # noqa: F401

    Base.metadata.create_all(bind=engine)
    print("Startup complete")

    # TEMPORARY: local-debug — verify Google OAuth env vars are loaded from .env
    import logging as _logging
    _startup_log = _logging.getLogger("startup")

    def _masked(val: str) -> str:
        return f"yes (prefix={val[:8]}...)" if val else "no"

    _s = get_settings()
    _startup_log.info("[DEBUG] GOOGLE_MAIL_ACCESS_TOKEN  : %s", _masked(_s.GOOGLE_MAIL_ACCESS_TOKEN))
    _startup_log.info("[DEBUG] GOOGLE_OAUTH_REFRESH_TOKEN: %s", _masked(_s.GOOGLE_OAUTH_REFRESH_TOKEN))
    _startup_log.info("[DEBUG] GOOGLE_OAUTH_CLIENT_ID    : %s", _masked(_s.GOOGLE_OAUTH_CLIENT_ID))
    _startup_log.info("[DEBUG] GOOGLE_OAUTH_CLIENT_SECRET: %s", _masked(_s.GOOGLE_OAUTH_CLIENT_SECRET))

    # Warn if OAuth refresh credential set is incomplete — prevents silent invalid_grant failures.
    _refresh_fields = [_s.GOOGLE_OAUTH_REFRESH_TOKEN, _s.GOOGLE_OAUTH_CLIENT_ID, _s.GOOGLE_OAUTH_CLIENT_SECRET]
    _refresh_set = sum(bool(f) for f in _refresh_fields)
    if 0 < _refresh_set < 3:
        _startup_log.warning(
            "[GoogleMail] WARNING: %d of 3 OAuth refresh fields are set. "
            "Token refresh will fail with invalid_grant. "
            "Set all three (GOOGLE_OAUTH_REFRESH_TOKEN, GOOGLE_OAUTH_CLIENT_ID, "
            "GOOGLE_OAUTH_CLIENT_SECRET) or none.",
            _refresh_set,
        )
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

    try:
        result = adapter.execute_action(
            action=request.action,
            payload=request.payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

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


class GmailProcessInboxRequest(_BaseModel):
    max_results: int = 5
    dry_run: bool = False
    query: str | None = None


def _parse_from_header(from_header: str) -> tuple[str, str]:
    """Parse RFC 2822 From header into (name, email).

    Handles: 'Name <email>', '"Name" <email>', bare 'email', empty/malformed.
    Returns ("", "") when nothing useful is found.
    If the parsed display name equals the email address, the name is suppressed
    to avoid storing a redundant fake-person name.
    """
    from email.utils import parseaddr as _parseaddr
    name, email = _parseaddr((from_header or "").strip())
    name = name.strip().strip('"').strip()
    email = email.strip().lower()
    # Suppress name when it's just a copy of the email address.
    if name and name.lower() == email:
        name = ""
    return name, email


_SUBJECT_MAX_LEN = 60

_HIGH_PRIORITY_KEYWORDS = {
    "urgent", "asap", "immediately", "akut", "omgående",
    "critical", "emergency", "prioritet",
}


def _infer_priority(subject: str, body_text: str) -> str:
    """Return 'high', 'medium', or 'low' based on keyword presence."""
    combined = f"{subject} {body_text}".lower()
    if any(kw in combined for kw in _HIGH_PRIORITY_KEYWORDS):
        return "high"
    if subject.strip() and subject.strip() != "(no subject)":
        return "medium"
    return "low"


def _make_monday_item_name(sender_name: str, sender_email: str, subject: str) -> str:
    """Build a clean, truncated Monday item name for a Gmail lead."""
    short_subject = subject.strip()[:_SUBJECT_MAX_LEN].rstrip()
    label = sender_name.strip() or sender_email.strip()
    if label:
        return f"Lead: {label} - {short_subject}"
    return f"Lead: {short_subject}"


# Matches: +46 70 123 45 67 / +46701234567 / 070-123 45 67 / 0701234567 / 018-123456
# Requires at least 7 digits after optional country prefix.
_PHONE_RE = re.compile(
    r"(?<!\d)"                    # not preceded by digit
    r"(\+46|0046)?"               # optional Swedish country prefix
    r"[\s\-]?"
    r"(0\d{1,3}|\d{2,3})"        # area code or first digit group
    r"[\s\-]?"
    r"\d{2,4}"                    # second group
    r"(?:[\s\-]?\d{2,4}){1,3}"   # remaining groups
    r"(?!\d)",                    # not followed by digit
)


def _extract_phone(subject: str, body_text: str) -> str | None:
    """Return the first plausible phone number found in subject or body, or None."""
    for text in (subject, body_text):
        m = _PHONE_RE.search(text or "")
        if m:
            # Collapse internal whitespace/hyphens into a single clean string.
            raw = m.group(0).strip()
            return re.sub(r"[\s\-]+", "-", raw)
    return None


@app.post("/gmail/process-inbox")
def gmail_process_inbox(
    request: GmailProcessInboxRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """
    Read recent unread Gmail messages and create or continue a job for each one.

    Processing order per message:
    1. Skip if message_id is missing.
    2. Dedup: skip if a job already exists for this Gmail message_id.
    3. Fetch full message detail.
    4. Thread continuation: if a job with the same thread_id exists, update it instead of
       creating a new one.
    5. If no existing thread: infer type, apply tenant gate, create new job.

    Marks successfully processed messages as read.
    Set dry_run=true to preview without any side effects.
    """
    from app.domain.workflows.enums import JobType

    query_used = request.query if request.query is not None else "is:unread"

    connection_config = get_integration_connection_config(
        tenant_id=tenant_id,
        integration_type=IntegrationType.GOOGLE_MAIL,
    )
    adapter = get_integration_adapter(
        integration_type=IntegrationType.GOOGLE_MAIL,
        connection_config=connection_config,
    )

    try:
        list_result = adapter.execute_action(
            action="list_messages",
            payload={"max_results": request.max_results, "query": query_used},
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=f"Gmail list_messages failed: {exc}") from exc

    messages = list_result.get("messages") or []
    created_jobs = []
    skipped_messages = []
    failed_messages = []

    tenant_config = get_tenant_config(tenant_id, db=db)
    enabled_job_types = set(tenant_config.get("enabled_job_types") or [])

    _INFERRED_TYPE_TO_JOB_TYPE = {
        "lead": JobType.LEAD,
        "customer_inquiry": JobType.CUSTOMER_INQUIRY,
        "invoice": JobType.INVOICE,
    }

    for stub in messages:
        message_id = stub.get("message_id", "")
        if not message_id:
            failed_messages.append({"message_id": "", "reason": "missing message_id"})
            continue

        # Step 1: dedup — skip if a job already exists for this exact Gmail message.
        existing_by_msg = JobRepository.get_by_gmail_message_id(db, tenant_id, message_id)
        if existing_by_msg is not None:
            skipped_messages.append({
                "message_id": message_id,
                "reason": "duplicate",
                "job_id": existing_by_msg.job_id,
            })
            continue

        # Step 2: fetch full message detail.
        try:
            detail_result = adapter.execute_action(
                action="get_message",
                payload={"message_id": message_id},
            )
        except (ValueError, RuntimeError) as exc:
            failed_messages.append({"message_id": message_id, "reason": str(exc)})
            continue

        msg = detail_result.get("message") or {}
        sender_name, sender_email = _parse_from_header(msg.get("from", ""))

        subject = msg.get("subject") or "(no subject)"
        body_text = msg.get("body_text") or ""
        thread_id = msg.get("thread_id") or ""

        # Step 3: thread continuation — look for existing job with same thread_id.
        continuation_job = None
        if thread_id:
            continuation_job = JobRepository.get_by_source_thread_id(
                db, tenant_id, "gmail", thread_id
            )

        if continuation_job is not None:
            # --- CONTINUATION PATH ---
            phone = _extract_phone(subject, body_text)
            sender_dict: dict = {"name": sender_name, "email": sender_email}
            if phone:
                sender_dict["phone"] = phone

            new_message_entry = {
                "source": "gmail",
                "message_id": message_id,
                "thread_id": thread_id,
                "subject": subject,
                "message_text": body_text,
                "sender": sender_dict,
            }

            inferred_type = classify_email_type(subject, body_text)

            if request.dry_run:
                created_jobs.append({
                    "message_id": message_id,
                    "job_id": continuation_job.job_id,
                    "status": "dry_run",
                    "inferred_type": inferred_type,
                    "continued": False,
                    "continuation_reason": "thread_id_match",
                    "marked_handled": False,
                    "notified": False,
                })
                continue

            # Merge new message into existing job input_data.
            updated_input = dict(continuation_job.input_data)
            conversation = list(updated_input.get("conversation_messages") or [])
            conversation.append(new_message_entry)
            updated_input["conversation_messages"] = conversation
            updated_input["latest_message_text"] = body_text
            updated_input["latest_subject"] = subject
            updated_input["latest_sender"] = sender_dict

            continuation_job.input_data = updated_input
            # Reset processor history so the pipeline runs fresh on updated data.
            continuation_job.processor_history = []

            try:
                JobRepository.update_job(db, continuation_job)
                processed_job = run_pipeline(continuation_job, db)
            except Exception as exc:
                failed_messages.append({"message_id": message_id, "reason": str(exc)})
                continue

            marked_handled = False
            mark_warning: str | None = None
            try:
                adapter.execute_action(action="mark_as_read", payload={"message_id": message_id})
                marked_handled = True
            except Exception as exc:
                mark_warning = str(exc)

            entry: dict = {
                "message_id": message_id,
                "job_id": processed_job.job_id,
                "inferred_type": inferred_type,
                "status": processed_job.status.value if hasattr(processed_job.status, "value") else str(processed_job.status),
                "continued": True,
                "continuation_reason": "thread_id_match",
                "marked_handled": marked_handled,
                "notified": False,
            }
            if mark_warning:
                entry["mark_warning"] = mark_warning
            created_jobs.append(entry)
            continue

        # --- NEW JOB PATH ---
        # Infer job type from message content, then gate against tenant config.
        inferred_type = classify_email_type(subject, body_text)
        if inferred_type not in enabled_job_types:
            skipped_messages.append({"message_id": message_id, "reason": f"{inferred_type}_disabled"})
            continue

        job_type = _INFERRED_TYPE_TO_JOB_TYPE[inferred_type]

        phone = _extract_phone(subject, body_text)
        sender_dict = {"name": sender_name, "email": sender_email}
        if phone:
            sender_dict["phone"] = phone

        input_data = {
            "subject": subject,
            "message_text": body_text,
            "sender": sender_dict,
            "source": {
                "system": "gmail",
                "message_id": message_id,
                "thread_id": thread_id,
            },
        }

        if request.dry_run:
            created_jobs.append({
                "message_id": message_id,
                "job_id": None,
                "status": "dry_run",
                "inferred_type": inferred_type,
                "continued": False,
                "marked_handled": False,
                "notified": False,
            })
            continue

        job = Job(
            tenant_id=tenant_id,
            job_type=job_type,
            input_data=input_data,
        )

        try:
            saved_job = JobRepository.create_job(db, job)
            processed_job = run_pipeline(saved_job, db)
        except Exception as exc:
            failed_messages.append({"message_id": message_id, "reason": str(exc)})
            continue

        marked_handled = False
        mark_warning = None
        try:
            adapter.execute_action(action="mark_as_read", payload={"message_id": message_id})
            marked_handled = True
        except Exception as exc:
            mark_warning = str(exc)

        notified = False
        notify_warning: str | None = None
        try:
            sender_label = sender_name or sender_email or "unknown"
            notify_body = (
                f"New {inferred_type} job created from Gmail.\n\n"
                f"From:    {sender_label}\n"
                f"Subject: {subject}\n"
                f"Type:    {inferred_type}\n"
                f"Job ID:  {processed_job.job_id}\n"
                f"Tenant:  {tenant_id}\n"
                f"Source:  gmail"
            )
            dispatch_action({
                "type": "notify_slack",
                "tenant_id": tenant_id,
                "channel": "#inbox",
                "message": notify_body,
            })
            notified = True
        except Exception as exc:
            notify_warning = str(exc)

        entry = {
            "message_id": message_id,
            "job_id": processed_job.job_id,
            "inferred_type": inferred_type,
            "status": processed_job.status.value if hasattr(processed_job.status, "value") else str(processed_job.status),
            "continued": False,
            "marked_handled": marked_handled,
            "notified": notified,
        }
        if mark_warning:
            entry["mark_warning"] = mark_warning
        if notify_warning:
            entry["notify_warning"] = notify_warning
        created_jobs.append(entry)

    return {
        "processed": len(created_jobs),
        "skipped": len(skipped_messages),
        "failed": len(failed_messages),
        "dry_run": request.dry_run,
        "query_used": query_used,
        "max_results": request.max_results,
        "scanned": len(messages),
        "created_jobs": created_jobs,
        "skipped_messages": skipped_messages,
        "failed_messages": failed_messages,
    }


@app.get("/dashboard/summary")
def dashboard_summary(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Return today's job counts grouped by type and status for the tenant."""
    from datetime import date, datetime, timezone
    from sqlalchemy import func

    today_start = datetime.combine(date.today(), datetime.min.time()).replace(tzinfo=timezone.utc)

    def _count(job_type: str | None, status: str | None, since: datetime | None = None) -> int:
        q = db.query(func.count(JobRecord.job_id)).filter(JobRecord.tenant_id == tenant_id)
        if job_type:
            q = q.filter(JobRecord.job_type == job_type)
        if status:
            q = q.filter(JobRecord.status == status)
        if since:
            q = q.filter(JobRecord.created_at >= since)
        return q.scalar() or 0

    leads_today      = _count("lead",             None,              today_start)
    inquiries_today  = _count("customer_inquiry", None,              today_start)
    invoices_today   = _count("invoice",          None,              today_start)
    ready_cases      = _count(None,               "awaiting_approval", None)
    completed_today  = _count(None,               "completed",       today_start)

    # waiting_customer: active jobs (not completed/failed) where the
    # action_dispatch result payload has recommended_status=needs_customer_info.
    # Use a JSON path filter on the result column.
    waiting_customer = (
        db.query(func.count(JobRecord.job_id))
        .filter(
            JobRecord.tenant_id == tenant_id,
            JobRecord.status.notin_(["completed", "failed"]),
            JobRecord.result["payload"]["recommended_status"].as_string() == "needs_customer_info",
        )
        .scalar() or 0
    )

    return {
        "leads_today":      leads_today,
        "inquiries_today":  inquiries_today,
        "invoices_today":   invoices_today,
        "waiting_customer": waiting_customer,
        "ready_cases":      ready_cases,
        "completed_today":  completed_today,
    }


@app.get("/dashboard/activity")
def dashboard_activity(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
    limit: int = 50,
    offset: int = 0,
):
    """Return recent jobs with type, status, latest action, and priority."""
    from app.repositories.postgres.action_execution_models import ActionExecutionRecord
    from sqlalchemy import func

    records = (
        db.query(JobRecord)
        .filter(JobRecord.tenant_id == tenant_id)
        .order_by(JobRecord.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    total = (
        db.query(func.count(JobRecord.job_id))
        .filter(JobRecord.tenant_id == tenant_id)
        .scalar() or 0
    )

    # Fetch latest action_type per job in one query.
    job_ids = [r.job_id for r in records]
    latest_actions: dict[str, str] = {}
    if job_ids:
        subq = (
            db.query(
                ActionExecutionRecord.job_id,
                func.max(ActionExecutionRecord.executed_at).label("max_at"),
            )
            .filter(
                ActionExecutionRecord.tenant_id == tenant_id,
                ActionExecutionRecord.job_id.in_(job_ids),
            )
            .group_by(ActionExecutionRecord.job_id)
            .subquery()
        )
        rows = (
            db.query(ActionExecutionRecord.job_id, ActionExecutionRecord.action_type)
            .join(
                subq,
                (ActionExecutionRecord.job_id == subq.c.job_id)
                & (ActionExecutionRecord.executed_at == subq.c.max_at),
            )
            .filter(ActionExecutionRecord.tenant_id == tenant_id)
            .all()
        )
        for job_id, action_type in rows:
            latest_actions[job_id] = action_type

    items = []
    for r in records:
        # Extract priority from result payload.
        priority: str | None = None
        result = r.result or {}
        history = result.get("processor_history") or []
        for entry in reversed(history):
            if entry.get("processor") == "action_dispatch_processor":
                for action in (entry.get("result") or {}).get("payload", {}).get("actions_requested") or []:
                    p = action.get("column_values", {}).get("priority")
                    if p:
                        priority = p.lower()
                        break
            if priority:
                break

        items.append({
            "job_id":        r.job_id,
            "created_at":    r.created_at.isoformat() if r.created_at else None,
            "type":          r.job_type or "unknown",
            "status":        r.status or "unknown",
            "latest_action": latest_actions.get(r.job_id),
            "tenant":        r.tenant_id,
            "priority":      priority,
        })

    return {"items": items, "total": total}


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