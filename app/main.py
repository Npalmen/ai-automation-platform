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
from app.workflows.approval_service import (
    build_dispatch_approval_request,
    resolve_approval,
    resolve_dispatch_approval,
)
from app.workflows.dispatchers.auto_dispatch import maybe_auto_dispatch_job
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
    from app.repositories.postgres.schema_migrations import ensure_runtime_schema

    Base.metadata.create_all(bind=engine)
    ensure_runtime_schema(engine)
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


@app.post("/approvals/{approval_id}/approve")
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

    # Dispatch approvals use a separate execution path (ControlledDispatchEngine)
    if (approval.next_on_approve == "controlled_dispatch"):
        try:
            return resolve_dispatch_approval(
                db=db,
                tenant_id=tenant_id,
                approval_id=approval_id,
                actor=request.actor,
                channel=request.channel,
                note=request.note,
                approved=True,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

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


@app.post("/approvals/{approval_id}/reject")
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

    # Dispatch approvals use a separate rejection path (no pipeline resume needed)
    if approval.next_on_approve == "controlled_dispatch":
        try:
            return resolve_dispatch_approval(
                db=db,
                tenant_id=tenant_id,
                approval_id=approval_id,
                actor=request.actor,
                channel=request.channel,
                note=request.note,
                approved=False,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

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


def _run_gmail_inbox_sync(
    tenant_id: str,
    db: "Session",
    max_results: int = 5,
    query: str | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Core Gmail inbox processing logic — shared by /gmail/process-inbox and
    /dashboard/inbox-sync.

    Raises HTTPException(503) if Gmail credentials are missing or the API call fails.
    Returns a raw result dict with created_jobs / skipped_messages / failed_messages lists.
    """
    from app.domain.workflows.enums import JobType

    query_used = query if query is not None else "is:unread"

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
            payload={"max_results": max_results, "query": query_used},
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=f"Gmail list_messages failed: {exc}") from exc

    messages = list_result.get("messages") or []
    created_jobs: list[dict] = []
    skipped_messages: list[dict] = []
    failed_messages: list[dict] = []

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

            if dry_run:
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
            "received_at": msg.get("received_at") or None,
        }

        if dry_run:
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
        "dry_run": dry_run,
        "query_used": query_used,
        "max_results": max_results,
        "scanned": len(messages),
        "created_jobs": created_jobs,
        "skipped_messages": skipped_messages,
        "failed_messages": failed_messages,
    }


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
    return _run_gmail_inbox_sync(
        tenant_id=tenant_id,
        db=db,
        max_results=request.max_results,
        query=request.query,
        dry_run=request.dry_run,
    )


def _compute_summary(db: "Session", tenant_id: str) -> dict:
    """Return today's job counts for the tenant. Shared by dashboard and digest."""
    from datetime import date, datetime, timezone
    from sqlalchemy import func

    today_start = datetime.combine(date.today(), datetime.min.time()).replace(tzinfo=timezone.utc)

    def _count(job_type: str | None, status: str | None, since: "datetime | None" = None) -> int:
        q = db.query(func.count(JobRecord.job_id)).filter(JobRecord.tenant_id == tenant_id)
        if job_type:
            q = q.filter(JobRecord.job_type == job_type)
        if status:
            q = q.filter(JobRecord.status == status)
        if since:
            q = q.filter(JobRecord.created_at >= since)
        return q.scalar() or 0

    leads_today      = _count("lead",             None,               today_start)
    inquiries_today  = _count("customer_inquiry", None,               today_start)
    invoices_today   = _count("invoice",          None,               today_start)
    ready_cases      = _count(None,               "awaiting_approval", None)
    completed_today  = _count(None,               "completed",        today_start)

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


@app.get("/dashboard/summary")
def dashboard_summary(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Return today's job counts grouped by type and status for the tenant."""
    return _compute_summary(db, tenant_id)


# ── ROI assumptions (minutes saved per handled item, hourly staff value) ──────
_ROI_LEAD_MIN      = 10
_ROI_SUPPORT_MIN   = 8
_ROI_INVOICE_MIN   = 6
_ROI_FOLLOWUP_MIN  = 5
_ROI_HOURLY_SEK    = 500


def _compute_roi(db: "Session", tenant_id: str) -> dict:
    """Return today's ROI metrics for the tenant. Shared by dashboard and digest."""
    from datetime import date, datetime, timezone
    from sqlalchemy import func
    from app.repositories.postgres.action_execution_models import ActionExecutionRecord

    today_start = datetime.combine(date.today(), datetime.min.time()).replace(tzinfo=timezone.utc)

    def _count_jobs(job_type: str) -> int:
        return (
            db.query(func.count(JobRecord.job_id))
            .filter(
                JobRecord.tenant_id == tenant_id,
                JobRecord.job_type == job_type,
                JobRecord.created_at >= today_start,
            )
            .scalar() or 0
        )

    leads_created      = _count_jobs("lead")
    support_cases      = _count_jobs("customer_inquiry")
    invoices_processed = _count_jobs("invoice")

    # Count send_email actions today where the job is a lead or customer_inquiry.
    followups_sent = (
        db.query(func.count(ActionExecutionRecord.execution_id))
        .join(JobRecord, ActionExecutionRecord.job_id == JobRecord.job_id)
        .filter(
            ActionExecutionRecord.tenant_id == tenant_id,
            ActionExecutionRecord.action_type == "send_email",
            ActionExecutionRecord.executed_at >= today_start,
            JobRecord.job_type.in_(["lead", "customer_inquiry"]),
        )
        .scalar() or 0
    )

    total_minutes       = (leads_created * _ROI_LEAD_MIN + support_cases * _ROI_SUPPORT_MIN
                           + invoices_processed * _ROI_INVOICE_MIN + followups_sent * _ROI_FOLLOWUP_MIN)
    total_hours         = round(total_minutes / 60, 2)
    estimated_value_sek = round(total_hours * _ROI_HOURLY_SEK)

    return {
        "period":                  "today",
        "leads_created":           leads_created,
        "support_cases_handled":   support_cases,
        "invoices_processed":      invoices_processed,
        "followups_sent":          followups_sent,
        "estimated_minutes_saved": total_minutes,
        "estimated_hours_saved":   total_hours,
        "estimated_value_sek":     estimated_value_sek,
        "assumptions": {
            "lead_minutes_saved":     _ROI_LEAD_MIN,
            "support_minutes_saved":  _ROI_SUPPORT_MIN,
            "invoice_minutes_saved":  _ROI_INVOICE_MIN,
            "followup_minutes_saved": _ROI_FOLLOWUP_MIN,
            "hourly_value_sek":       _ROI_HOURLY_SEK,
        },
    }


@app.get("/dashboard/roi")
def dashboard_roi(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Return today's ROI metrics for the tenant based on fixed time-saving assumptions."""
    return _compute_roi(db, tenant_id)


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


# ── Control panel ─────────────────────────────────────────────────────────────

_VALID_RUN_MODES = {"manual", "scheduled", "paused"}

_DEFAULT_CONTROL = {
    "automation": {
        "leads_enabled":    True,
        "support_enabled":  True,
        "invoices_enabled": True,
        "followups_enabled": True,
    },
    "support_email": "",
    "scheduler": {
        "run_mode": "manual",
    },
}


def _build_control_response(settings: dict) -> dict:
    auto = settings.get("automation") or {}
    sched = settings.get("scheduler") or {}
    return {
        "automation": {
            "leads_enabled":     bool(auto.get("leads_enabled",    _DEFAULT_CONTROL["automation"]["leads_enabled"])),
            "support_enabled":   bool(auto.get("support_enabled",  _DEFAULT_CONTROL["automation"]["support_enabled"])),
            "invoices_enabled":  bool(auto.get("invoices_enabled", _DEFAULT_CONTROL["automation"]["invoices_enabled"])),
            "followups_enabled": bool(auto.get("followups_enabled",_DEFAULT_CONTROL["automation"]["followups_enabled"])),
        },
        "support_email": settings.get("support_email") or "",
        "scheduler": {
            "run_mode": sched.get("run_mode") or "manual",
        },
    }


class ControlPanelRequest(_BaseModel):
    class _Automation(_BaseModel):
        leads_enabled:    bool = True
        support_enabled:  bool = True
        invoices_enabled: bool = True
        followups_enabled: bool = True

    class _Scheduler(_BaseModel):
        run_mode: str = "manual"

    automation:    _Automation = _Automation()
    support_email: str | None = None
    scheduler:     _Scheduler = _Scheduler()


@app.get("/dashboard/control")
def get_control_panel(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Return current tenant-scoped control panel settings."""
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
    settings = TenantConfigRepository.get_settings(db, tenant_id)
    return _build_control_response(settings)


@app.put("/dashboard/control")
def put_control_panel(
    request: ControlPanelRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Persist tenant-scoped control panel settings."""
    import re as _re
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

    run_mode = request.scheduler.run_mode
    if run_mode not in _VALID_RUN_MODES:
        raise HTTPException(
            status_code=422,
            detail=f"scheduler.run_mode must be one of: {', '.join(sorted(_VALID_RUN_MODES))}",
        )

    email = (request.support_email or "").strip()
    if email and not _re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(status_code=422, detail="support_email must be a valid email address or empty")

    settings = {
        "automation": {
            "leads_enabled":     request.automation.leads_enabled,
            "support_enabled":   request.automation.support_enabled,
            "invoices_enabled":  request.automation.invoices_enabled,
            "followups_enabled": request.automation.followups_enabled,
        },
        "support_email": email,
        "scheduler": {"run_mode": run_mode},
    }
    TenantConfigRepository.update_settings(db, tenant_id, settings)
    return _build_control_response(settings)


@app.post("/dashboard/inbox-sync")
def trigger_inbox_sync(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """
    Trigger a manual Gmail inbox sync for this tenant.

    Runs the same processing logic as POST /gmail/process-inbox (dedup, thread
    continuation, job creation, mark-as-read).  Uses default settings: max 10
    messages, query "is:unread", dry_run=False.

    Returns 503 with a clean JSON body if Gmail credentials are not configured.
    """
    s = get_settings()
    if not s.GOOGLE_MAIL_ACCESS_TOKEN:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "failed",
                "message": "Gmail not configured — set GOOGLE_MAIL_ACCESS_TOKEN in environment",
                "processed": 0,
                "created_jobs": 0,
                "continued_threads": 0,
                "deduped": 0,
                "errors": [],
            },
        )

    try:
        raw = _run_gmail_inbox_sync(
            tenant_id=tenant_id,
            db=db,
            max_results=10,
            query=None,
            dry_run=False,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "status": "failed",
                "message": f"Inbox sync failed: {exc}",
                "processed": 0,
                "created_jobs": 0,
                "continued_threads": 0,
                "deduped": 0,
                "errors": [{"message": str(exc)}],
            },
        ) from exc

    new_jobs       = sum(1 for j in raw["created_jobs"] if not j.get("continued"))
    continued      = sum(1 for j in raw["created_jobs"] if j.get("continued"))
    deduped        = sum(1 for s in raw["skipped_messages"] if s.get("reason") == "duplicate")
    errors         = [{"message": f["reason"]} for f in raw["failed_messages"]]

    overall_status = "failed" if raw["failed"] > 0 and raw["processed"] == 0 else \
                     "warning" if raw["failed"] > 0 else "success"

    return {
        "status":           overall_status,
        "processed":        raw["processed"],
        "created_jobs":     new_jobs,
        "continued_threads": continued,
        "deduped":          deduped,
        "errors":           errors,
        "message":          f"Inbox sync completed — {raw['scanned']} scanned, "
                            f"{raw['processed']} processed, {raw['skipped']} skipped",
    }


# ── Setup / Onboarding ────────────────────────────────────────────────────────

# Module → job types that must be enabled for the module to count as active.
_MODULE_JOB_TYPES: dict[str, list[str]] = {
    "sales":   ["lead"],
    "support": ["customer_inquiry"],
    "finance": ["invoice"],
}


def _build_setup_status(
    tenant_id: str,
    cfg: dict,
    ctrl_settings: dict,
    s: "Settings",
) -> dict:
    """Derive setup/readiness data from tenant config, control settings, and env."""
    enabled_types: list[str] = cfg.get("enabled_job_types") or []

    # Modules
    modules = {name: any(t in enabled_types for t in types)
               for name, types in _MODULE_JOB_TYPES.items()}

    # Connections — env-credential-based
    google_mail_ok   = bool(s.GOOGLE_MAIL_ACCESS_TOKEN)
    microsoft_mail_ok = bool(s.MICROSOFT_MAIL_ACCESS_TOKEN)
    monday_ok        = bool(s.MONDAY_API_KEY)
    fortnox_ok       = bool(s.FORTNOX_ACCESS_TOKEN)
    visma_ok         = bool(s.VISMA_ACCESS_TOKEN)
    email_connected  = google_mail_ok or microsoft_mail_ok

    connections = {
        "email_connected":   email_connected,
        "google_mail":       google_mail_ok,
        "microsoft_mail":    microsoft_mail_ok,
        "fortnox":           fortnox_ok,
        "visma":             visma_ok,
        "monday":            monday_ok,
    }

    # Automation
    sched = ctrl_settings.get("scheduler") or {}
    auto  = ctrl_settings.get("automation") or {}
    scheduler_mode     = sched.get("run_mode") or "manual"
    followups_enabled  = bool(auto.get("followups_enabled", True))
    support_email      = ctrl_settings.get("support_email") or ""

    automation = {
        "scheduler_mode":    scheduler_mode,
        "followups_enabled": followups_enabled,
    }

    # Readiness scoring
    score = 0
    missing: list[str] = []

    if email_connected:
        score += 30
    else:
        missing.append("No email integration connected")

    if any(modules.values()):
        score += 20
    else:
        missing.append("No modules enabled")

    if scheduler_mode != "paused":
        score += 20
    else:
        missing.append("Scheduler is paused")

    if support_email:
        score += 10
    else:
        missing.append("Support email not configured")

    if monday_ok or fortnox_ok or visma_ok:
        score += 20
    else:
        missing.append("No destination integration connected (Monday / Fortnox / Visma)")

    score = max(0, min(100, score))

    if score >= 90:
        readiness_status = "ready"
    elif score >= 50:
        readiness_status = "almost_ready"
    else:
        readiness_status = "needs_setup"

    return {
        "tenant_id":   tenant_id,
        "modules":     modules,
        "connections": connections,
        "automation":  automation,
        "readiness": {
            "score":  score,
            "status": readiness_status,
        },
        "missing": missing,
    }


@app.get("/setup/status")
def get_setup_status(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Return tenant-scoped readiness overview derived from config + env credentials."""
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

    cfg           = get_tenant_config(tenant_id, db=db)
    ctrl_settings = TenantConfigRepository.get_settings(db, tenant_id)
    s             = get_settings()
    return _build_setup_status(tenant_id, cfg, ctrl_settings, s)


class SetupModulesRequest(_BaseModel):
    sales:   bool = False
    support: bool = False
    finance: bool = False


@app.put("/setup/modules")
def put_setup_modules(
    request: SetupModulesRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Persist module enablement into tenant_configs.enabled_job_types."""
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

    enabled_types: list[str] = []
    for module, types in _MODULE_JOB_TYPES.items():
        if getattr(request, module):
            enabled_types.extend(types)

    # Preserve other job types that aren't mapped to a module (future-proofing).
    existing = TenantConfigRepository.get(db, tenant_id)
    if existing:
        current = existing.enabled_job_types or []
        non_module_types = [t for t in current
                            if not any(t in types for types in _MODULE_JOB_TYPES.values())]
        enabled_types = non_module_types + enabled_types

    TenantConfigRepository.upsert(db, tenant_id, enabled_job_types=enabled_types)
    return {
        "enabled_job_types": enabled_types,
        "modules": {m: getattr(request, m) for m in ("sales", "support", "finance")},
    }


@app.post("/setup/verify")
def post_setup_verify(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Run lightweight system checks and return structured readiness report."""
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

    cfg           = get_tenant_config(tenant_id, db=db)
    ctrl_settings = TenantConfigRepository.get_settings(db, tenant_id)
    s             = get_settings()

    checks: list[dict] = []
    warnings = 0
    failures = 0

    # Check 1: tenant config exists in DB
    record = TenantConfigRepository.get(db, tenant_id)
    if record is not None:
        checks.append({"name": "Tenant config", "status": "ok"})
    else:
        checks.append({"name": "Tenant config", "status": "warning",
                       "detail": "Tenant not in DB — using static fallback config"})
        warnings += 1

    # Check 2: at least one module enabled
    enabled_types = cfg.get("enabled_job_types") or []
    if enabled_types:
        checks.append({"name": "Modules", "status": "ok",
                       "detail": f"{len(enabled_types)} job type(s) enabled"})
    else:
        checks.append({"name": "Modules", "status": "failed",
                       "detail": "No job types enabled — no jobs will be processed"})
        failures += 1

    # Check 3: email connection
    if s.GOOGLE_MAIL_ACCESS_TOKEN or s.MICROSOFT_MAIL_ACCESS_TOKEN:
        checks.append({"name": "Email connection", "status": "ok"})
    else:
        checks.append({"name": "Email connection", "status": "warning",
                       "detail": "No email credentials configured"})
        warnings += 1

    # Check 4: scheduler mode
    sched_mode = (ctrl_settings.get("scheduler") or {}).get("run_mode") or "manual"
    if sched_mode == "paused":
        checks.append({"name": "Scheduler mode", "status": "warning",
                       "detail": "Scheduler is paused — inbox sync will not run automatically"})
        warnings += 1
    else:
        checks.append({"name": "Scheduler mode", "status": "ok",
                       "detail": f"Mode: {sched_mode}"})

    # Check 5: destination integration
    if s.MONDAY_API_KEY or s.FORTNOX_ACCESS_TOKEN or s.VISMA_ACCESS_TOKEN:
        checks.append({"name": "Destination integration", "status": "ok"})
    else:
        checks.append({"name": "Destination integration", "status": "warning",
                       "detail": "No destination integration credentials configured (Monday / Fortnox / Visma)"})
        warnings += 1

    if failures > 0:
        overall = "failed"
        message = f"System has {failures} critical issue(s) — action required before go-live"
    elif warnings > 0:
        overall = "warning"
        message = f"System has {warnings} warning(s) — review before go-live"
    else:
        overall = "ok"
        message = "System ready for onboarding"

    return {"status": overall, "checks": checks, "message": message}


# ── Notifications ─────────────────────────────────────────────────────────────

_VALID_FREQUENCIES = {"daily", "weekly", "off"}

_DEFAULT_NOTIF_SETTINGS: dict = {
    "enabled":          False,
    "recipient_email":  "",
    "frequency":        "daily",
    "send_hour":        8,
}


def _get_notif_settings(ctrl_settings: dict) -> dict:
    raw = ctrl_settings.get("notifications") or {}
    return {
        "enabled":         bool(raw.get("enabled",         _DEFAULT_NOTIF_SETTINGS["enabled"])),
        "recipient_email": raw.get("recipient_email",       _DEFAULT_NOTIF_SETTINGS["recipient_email"]) or "",
        "frequency":       raw.get("frequency",             _DEFAULT_NOTIF_SETTINGS["frequency"]),
        "send_hour":       int(raw.get("send_hour",         _DEFAULT_NOTIF_SETTINGS["send_hour"])),
    }


@app.get("/notifications/settings")
def get_notification_settings(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Return tenant-scoped notification settings."""
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
    ctrl = TenantConfigRepository.get_settings(db, tenant_id)
    return _get_notif_settings(ctrl)


class NotificationSettingsRequest(_BaseModel):
    enabled:         bool = False
    recipient_email: str = ""
    frequency:       str = "daily"
    send_hour:       int = 8


@app.put("/notifications/settings")
def put_notification_settings(
    request: NotificationSettingsRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Persist tenant-scoped notification settings."""
    import re as _re
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

    if request.frequency not in _VALID_FREQUENCIES:
        raise HTTPException(
            status_code=422,
            detail=f"frequency must be one of: {', '.join(sorted(_VALID_FREQUENCIES))}",
        )
    if not (0 <= request.send_hour <= 23):
        raise HTTPException(status_code=422, detail="send_hour must be 0–23")

    email = (request.recipient_email or "").strip()
    if request.enabled and not email:
        raise HTTPException(status_code=422, detail="recipient_email is required when enabled=true")
    if email and not _re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(status_code=422, detail="recipient_email must be a valid email address")

    existing = TenantConfigRepository.get_settings(db, tenant_id)
    updated = dict(existing)
    updated["notifications"] = {
        "enabled":        request.enabled,
        "recipient_email": email,
        "frequency":      request.frequency,
        "send_hour":      request.send_hour,
    }
    TenantConfigRepository.update_settings(db, tenant_id, updated)
    return _get_notif_settings(updated)


def _build_digest_body(tenant_id: str, summary: dict, roi: dict) -> tuple[str, str]:
    """Build (subject, body) for the daily digest email."""
    from datetime import date
    today_str = date.today().isoformat()
    subject   = f"AI Automation Report – {today_str}"

    errors_today = 0  # could be extended to query failed jobs; kept simple for now

    body = f"""Daglig rapport för {tenant_id} – {today_str}

Sammanfattning:
- Leads skapade:           {summary.get('leads_today', 0)}
- Supportärenden hanterade: {summary.get('inquiries_today', 0)}
- Fakturor behandlade:     {summary.get('invoices_today', 0)}
- Väntar på kund:          {summary.get('waiting_customer', 0)}
- Klara idag:              {summary.get('completed_today', 0)}

Uppskattat värde:
- Sparad tid:              {roi.get('estimated_hours_saved', 0)} h
- Uppskattat värde:        {roi.get('estimated_value_sek', 0)} SEK

Status:
- Fel idag:                {errors_today}

Logga in i dashboarden för mer detaljer.
"""
    return subject, body


@app.post("/notifications/daily-digest/send")
def send_daily_digest(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Manually trigger the daily digest email for this tenant."""
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

    ctrl = TenantConfigRepository.get_settings(db, tenant_id)
    notif = _get_notif_settings(ctrl)

    recipient = notif["recipient_email"]
    if not recipient:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "failed",
                "message": "No recipient_email configured. Set it via PUT /notifications/settings first.",
            },
        )

    summary = _compute_summary(db, tenant_id)
    roi     = _compute_roi(db, tenant_id)
    subject, body = _build_digest_body(tenant_id, summary, roi)

    try:
        dispatch_action({
            "type":      "send_email",
            "tenant_id": tenant_id,
            "to":        recipient,
            "subject":   subject,
            "body":      body,
        })
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"status": "failed", "message": f"Email dispatch failed: {exc}"},
        ) from exc

    return {
        "status":    "success",
        "recipient": recipient,
        "subject":   subject,
        "message":   "Daily digest sent",
    }


# ── Scheduler ─────────────────────────────────────────────────────────────────

def _run_scheduler_pass(tenant_id: str, db: "Session", now_utc: "datetime") -> dict:
    """Run one scheduler pass for a single tenant. Returns per-tenant result dict."""
    from datetime import datetime, timezone
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

    s = get_settings()
    ctrl = TenantConfigRepository.get_settings(db, tenant_id)
    sched = ctrl.get("scheduler") or {}
    run_mode = sched.get("run_mode") or "manual"
    state = ctrl.get("scheduler_state") or {}

    inbox_sync_result: dict | None = None
    digest_result: dict | None = None
    error: str | None = None

    try:
        # ── Inbox sync ────────────────────────────────────────────────────────
        if run_mode == "scheduled":
            if not s.GOOGLE_MAIL_ACCESS_TOKEN:
                inbox_sync_result = {"skipped": True, "reason": "gmail_not_configured"}
            else:
                raw = _run_gmail_inbox_sync(
                    tenant_id=tenant_id, db=db, max_results=10,
                )
                inbox_sync_result = {
                    "skipped":          False,
                    "processed":        raw.get("processed", 0),
                    "created_jobs":     raw.get("created_jobs", []),
                    "continued_threads": raw.get("continued_threads", 0),
                    "deduped":          raw.get("deduped", 0),
                    "errors":           raw.get("errors", []),
                }
                state["last_inbox_sync_at"] = now_utc.isoformat()
        else:
            inbox_sync_result = {"skipped": True, "reason": f"run_mode={run_mode}"}

        # ── Daily digest ──────────────────────────────────────────────────────
        notif = _get_notif_settings(ctrl)
        notif_enabled   = notif.get("enabled") and notif.get("frequency") != "off"
        send_hour       = notif.get("send_hour", 8)
        recipient       = notif.get("recipient_email") or ""

        if not notif_enabled or not recipient:
            digest_result = {"skipped": True, "reason": "notifications_disabled_or_no_recipient"}
        elif now_utc.hour < send_hour:
            digest_result = {"skipped": True, "reason": f"before_send_hour ({now_utc.hour} < {send_hour})"}
        else:
            last_sent = state.get("last_digest_sent_at")
            today_str = now_utc.strftime("%Y-%m-%d")
            if last_sent and last_sent[:10] == today_str:
                digest_result = {"skipped": True, "reason": "already_sent_today"}
            else:
                summary = _compute_summary(db, tenant_id)
                roi     = _compute_roi(db, tenant_id)
                subject, body = _build_digest_body(tenant_id, summary, roi)
                dispatch_action({
                    "type":      "send_email",
                    "tenant_id": tenant_id,
                    "to":        recipient,
                    "subject":   subject,
                    "body":      body,
                })
                state["last_digest_sent_at"] = now_utc.isoformat()
                digest_result = {"skipped": False, "recipient": recipient, "subject": subject}

        state["last_scheduler_run_at"] = now_utc.isoformat()
        state["last_status"] = "success"
        state["last_error"]  = None

    except Exception as exc:
        error = str(exc)
        state["last_scheduler_run_at"] = now_utc.isoformat()
        state["last_status"] = "failed"
        state["last_error"]  = error

    # persist updated state
    updated = dict(ctrl)
    updated["scheduler_state"] = state
    TenantConfigRepository.update_settings(db, tenant_id, updated)

    return {
        "tenant_id":        tenant_id,
        "run_mode":         run_mode,
        "inbox_sync":       inbox_sync_result,
        "digest":           digest_result,
        "error":            error,
    }


@app.post("/scheduler/run-once")
def scheduler_run_once(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Run one scheduler pass for all tenants. Returns aggregate result."""
    from datetime import datetime, timezone
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

    now_utc = datetime.now(timezone.utc)
    records = TenantConfigRepository.list_all(db)

    tenants_checked  = 0
    inbox_syncs_run  = 0
    digests_sent     = 0
    skipped          = 0
    errors: list[dict] = []
    tenant_results: list[dict] = []

    for record in records:
        tid = record.tenant_id
        tenants_checked += 1
        result = _run_scheduler_pass(tid, db, now_utc)
        tenant_results.append(result)

        if result.get("error"):
            errors.append({"tenant_id": tid, "error": result["error"]})
        else:
            ib = result.get("inbox_sync") or {}
            dg = result.get("digest") or {}
            if not ib.get("skipped"):
                inbox_syncs_run += 1
            if not dg.get("skipped"):
                digests_sent += 1
            if ib.get("skipped") and dg.get("skipped"):
                skipped += 1

    return {
        "status":         "success" if not errors else "warning",
        "run_at":         now_utc.isoformat(),
        "tenants_checked": tenants_checked,
        "inbox_syncs_run": inbox_syncs_run,
        "digests_sent":    digests_sent,
        "skipped":         skipped,
        "errors":          errors,
        "tenant_results":  tenant_results,
    }


@app.get("/scheduler/status")
def scheduler_status(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Return scheduler state and configuration for this tenant."""
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

    ctrl  = TenantConfigRepository.get_settings(db, tenant_id)
    sched = ctrl.get("scheduler") or {}
    state = ctrl.get("scheduler_state") or {}
    notif = _get_notif_settings(ctrl)

    return {
        "run_mode":              sched.get("run_mode") or "manual",
        "notifications_enabled": notif.get("enabled") or False,
        "notifications_frequency": notif.get("frequency") or "daily",
        "send_hour":             notif.get("send_hour") or 8,
        "last_inbox_sync_at":    state.get("last_inbox_sync_at"),
        "last_digest_sent_at":   state.get("last_digest_sent_at"),
        "last_scheduler_run_at": state.get("last_scheduler_run_at"),
        "last_status":           state.get("last_status") or "never_run",
        "last_error":            state.get("last_error"),
    }


_CASES_SORT_COLUMNS = {
    "created_at":    lambda: JobRecord.created_at,
    "received_at":   lambda: JobRecord.created_at,   # received_at not a DB column; proxy via created_at
    "status":        lambda: JobRecord.status,
    "type":          lambda: JobRecord.job_type,
}

_CASES_VALID_SORT_DIR = {"asc", "desc"}


def _derive_case_fields(r: "JobRecord") -> dict:
    """Extract derived display fields from a JobRecord (shared by list and detail)."""
    inp = r.input_data or {}
    result = r.result or {}
    history = result.get("processor_history") or []

    subject: str | None = inp.get("subject") or inp.get("latest_message_subject") or None

    sender = inp.get("sender") or {}
    customer_email: str | None = sender.get("email") or inp.get("sender_email") or None

    customer_name: str | None = None
    for entry in reversed(history):
        p = (entry.get("result") or {}).get("payload") or {}
        entities = p.get("entities") or {}
        name = entities.get("customer_name")
        if name:
            customer_name = name
            break
    if not customer_name:
        for entry in history:
            p = (entry.get("result") or {}).get("payload") or {}
            origin = p.get("origin") or {}
            name = origin.get("sender_name")
            if name:
                customer_name = name
                break
    if not customer_name:
        customer_name = sender.get("name") or inp.get("sender_name") or None

    priority: str | None = None
    for entry in reversed(history):
        if entry.get("processor") == "action_dispatch_processor":
            for action in ((entry.get("result") or {}).get("payload") or {}).get("actions_requested") or []:
                p = action.get("column_values", {}).get("priority")
                if p:
                    priority = p.lower()
                    break
        if priority:
            break

    received_at: str | None = inp.get("received_at") or None
    processed_at: str | None = r.created_at.isoformat() if r.created_at else None

    return {
        "subject":       subject,
        "customer_name": customer_name,
        "customer_email": customer_email,
        "priority":      priority,
        "received_at":   received_at,
        "processed_at":  processed_at,
    }


@app.get("/cases")
def list_cases(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    type: str | None = None,
    q: str | None = None,
    sort_by: str | None = None,
    sort_dir: str | None = None,
):
    """Tenant-scoped list of cases with search, filter, sort, and pagination."""
    from sqlalchemy import cast, String, or_

    query = db.query(JobRecord).filter(JobRecord.tenant_id == tenant_id)

    if status:
        query = query.filter(JobRecord.status == status)
    if type:
        query = query.filter(JobRecord.job_type == type)

    # Full-text search: ILIKE match against job_id and JSON input_data blob
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(
            or_(
                JobRecord.job_id.ilike(term),
                cast(JobRecord.input_data, String).ilike(term),
            )
        )

    total = query.count()

    # Sorting
    sort_col_key = sort_by if sort_by in _CASES_SORT_COLUMNS else "created_at"
    direction = (sort_dir or "desc").lower()
    if direction not in _CASES_VALID_SORT_DIR:
        direction = "desc"
    col = _CASES_SORT_COLUMNS[sort_col_key]()
    query = query.order_by(col.asc() if direction == "asc" else col.desc())

    records = query.offset(offset).limit(limit).all()

    items = []
    for r in records:
        derived = _derive_case_fields(r)
        items.append({
            "job_id":         r.job_id,
            "created_at":     r.created_at.isoformat() if r.created_at else None,
            "received_at":    derived["received_at"],
            "processed_at":   derived["processed_at"],
            "type":           r.job_type or "unknown",
            "status":         r.status or "unknown",
            "subject":        derived["subject"],
            "customer_name":  derived["customer_name"],
            "customer_email": derived["customer_email"],
            "priority":       derived["priority"],
        })

    return {"items": items, "total": total, "limit": limit, "offset": offset}


@app.get("/cases/{job_id}")
def get_case(
    job_id: str,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Tenant-scoped detailed case view including messages, actions, and errors."""
    from app.repositories.postgres.action_execution_models import ActionExecutionRecord

    r = (
        db.query(JobRecord)
        .filter(JobRecord.job_id == job_id, JobRecord.tenant_id == tenant_id)
        .first()
    )
    if r is None:
        raise HTTPException(status_code=404, detail="Case not found")

    inp = r.input_data or {}
    result = r.result or {}
    history = result.get("processor_history") or []

    # --- original_message ---
    sender = inp.get("sender") or {}
    original_message = {
        "from":  sender.get("name") or inp.get("sender_name") or None,
        "email": sender.get("email") or inp.get("sender_email") or None,
        "body":  inp.get("message_text") or None,
    }

    # --- extracted_data: from entity extraction processor ---
    extracted_data: dict | None = None
    for entry in history:
        p = (entry.get("result") or {}).get("payload") or {}
        if "entities" in p:
            extracted_data = p["entities"]
            break

    # --- thread_messages: from conversation_messages list ---
    raw_msgs = inp.get("conversation_messages") or []
    thread_messages = []
    for msg in raw_msgs:
        src = msg.get("source") or "gmail"
        direction = "outgoing" if src in ("system", "outgoing") else "incoming"
        thread_messages.append({
            "created_at": msg.get("received_at") or msg.get("created_at") or None,
            "direction":  direction,
            "subject":    msg.get("subject") or None,
            "body":       msg.get("message_text") or msg.get("body") or None,
        })

    # --- actions from action_executions table ---
    action_records = (
        db.query(ActionExecutionRecord)
        .filter(
            ActionExecutionRecord.job_id == job_id,
            ActionExecutionRecord.tenant_id == tenant_id,
        )
        .order_by(ActionExecutionRecord.executed_at.asc())
        .all()
    )
    actions = [
        {
            "created_at": a.executed_at.isoformat() if a.executed_at else None,
            "type":       a.action_type,
            "status":     a.status,
            "result":     a.result_payload,
        }
        for a in action_records
    ]

    # --- errors: failed actions + any processor error entries ---
    errors = []
    for a in action_records:
        if a.error_message:
            errors.append({
                "created_at": a.executed_at.isoformat() if a.executed_at else None,
                "message":    a.error_message,
            })
    for entry in history:
        err = (entry.get("result") or {}).get("error")
        if err:
            errors.append({"created_at": None, "message": str(err)})

    # --- subject + customer_name + priority (reuse same logic as list) ---
    subject: str | None = inp.get("subject") or inp.get("latest_message_subject") or None

    customer_name: str | None = None
    for entry in reversed(history):
        p = (entry.get("result") or {}).get("payload") or {}
        entities = p.get("entities") or {}
        name = entities.get("customer_name")
        if name:
            customer_name = name
            break
    if not customer_name:
        for entry in history:
            p = (entry.get("result") or {}).get("payload") or {}
            origin = p.get("origin") or {}
            name = origin.get("sender_name")
            if name:
                customer_name = name
                break
    if not customer_name:
        customer_name = sender.get("name") or inp.get("sender_name") or None

    priority: str | None = None
    for entry in reversed(history):
        if entry.get("processor") == "action_dispatch_processor":
            for action in ((entry.get("result") or {}).get("payload") or {}).get("actions_requested") or []:
                p = action.get("column_values", {}).get("priority")
                if p:
                    priority = p.lower()
                    break
        if priority:
            break

    received_at: str | None = inp.get("received_at") or None
    processed_at: str | None = r.created_at.isoformat() if r.created_at else None

    # --- routing_preview: where this job_type would be routed ---
    from app.workflows.scanners.routing_preview import resolve_routing_preview, SUPPORTED_JOB_TYPES
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository as _TCR
    _settings = _TCR.get_settings(db, tenant_id)
    _memory = _get_memory(_settings)
    _job_type_str = r.job_type or "unknown"
    routing_preview = (
        resolve_routing_preview(_memory["routing_hints"], _job_type_str)
        if _job_type_str in SUPPORTED_JOB_TYPES
        else None
    )

    return {
        "job_id":           r.job_id,
        "created_at":       r.created_at.isoformat() if r.created_at else None,
        "updated_at":       r.updated_at.isoformat() if r.updated_at else None,
        "received_at":      received_at,
        "processed_at":     processed_at,
        "type":             r.job_type or "unknown",
        "status":           r.status or "unknown",
        "priority":         priority,
        "subject":          subject,
        "customer_name":    customer_name,
        "original_message": original_message,
        "extracted_data":   extracted_data,
        "thread_messages":  thread_messages,
        "actions":          actions,
        "errors":           errors,
        "routing_preview":  routing_preview,
    }


# ---------------------------------------------------------------------------
# Tenant Memory
# ---------------------------------------------------------------------------

_DEFAULT_MEMORY: dict = {
    "business_profile": {
        "company_name": "",
        "industry": "",
        "services": [],
        "tone": "professional",
    },
    "system_map": {
        "gmail": {
            "known_senders": [],
            "subject_patterns": [],
            "detected_mail_types": [],
        },
        "monday": {
            "boards": [],
            "groups": [],
            "columns": [],
        },
    },
    "routing_hints": {
        "lead": None,
        "customer_inquiry": None,
        "invoice": None,
        "partnership": None,
        "supplier": None,
    },
}


def _get_memory(settings_dict: dict) -> dict:
    """Return memory from settings, merged with defaults so missing keys are always present."""
    import copy
    stored = settings_dict.get("memory") or {}
    merged = copy.deepcopy(_DEFAULT_MEMORY)
    # Top-level keys: only overwrite if present in stored
    for top_key in merged:
        if top_key in stored and isinstance(stored[top_key], dict):
            merged[top_key].update(stored[top_key])
        elif top_key in stored:
            merged[top_key] = stored[top_key]
    return merged


class TenantMemoryRequest(_BaseModel):
    business_profile: dict | None = None
    system_map: dict | None = None
    routing_hints: dict | None = None


@app.get("/tenant/memory")
def get_tenant_memory(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Return tenant-scoped memory (business profile, system map, routing hints)."""
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
    s = TenantConfigRepository.get_settings(db, tenant_id)
    return _get_memory(s)


@app.put("/tenant/memory")
def put_tenant_memory(
    request: TenantMemoryRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Persist tenant memory without clobbering other settings keys."""
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
    existing = TenantConfigRepository.get_settings(db, tenant_id)
    current_memory = _get_memory(existing)

    if request.business_profile is not None:
        current_memory["business_profile"].update(request.business_profile)
    if request.system_map is not None:
        for system, data in request.system_map.items():
            if system in current_memory["system_map"] and isinstance(data, dict):
                current_memory["system_map"][system].update(data)
            else:
                current_memory["system_map"][system] = data
    if request.routing_hints is not None:
        current_memory["routing_hints"].update(request.routing_hints)

    updated = dict(existing)
    updated["memory"] = current_memory
    TenantConfigRepository.update_settings(db, tenant_id, updated)
    return current_memory


# ---------------------------------------------------------------------------
# Routing Hint Drafts
# ---------------------------------------------------------------------------

_SUPPORTED_HINT_JOB_TYPES: set[str] = {
    "lead", "customer_inquiry", "invoice", "partnership", "supplier", "support", "internal",
}

_HINT_TARGET_KEYS: set[str] = {"board_id", "board_name", "group_id", "group_name"}
_HINT_TOP_KEYS:    set[str] = {"system", "target", "confidence", "reason"}
_VALID_CONFIDENCES: set[str] = {"high", "medium", "low"}


def _validate_hint(hint: dict, job_type: str) -> None:
    """Raise HTTPException(422) if hint shape is invalid."""
    unknown_top = set(hint) - _HINT_TOP_KEYS
    if unknown_top:
        raise HTTPException(status_code=422, detail=f"Unknown hint key(s) for '{job_type}': {sorted(unknown_top)}")
    if "system" not in hint or not hint["system"]:
        raise HTTPException(status_code=422, detail=f"Hint for '{job_type}' missing 'system'")
    if "target" not in hint or not isinstance(hint["target"], dict):
        raise HTTPException(status_code=422, detail=f"Hint for '{job_type}' missing or invalid 'target'")
    unknown_target = set(hint["target"]) - _HINT_TARGET_KEYS
    if unknown_target:
        raise HTTPException(status_code=422, detail=f"Unknown target key(s) for '{job_type}': {sorted(unknown_target)}")
    confidence = hint.get("confidence")
    if confidence is not None and confidence not in _VALID_CONFIDENCES:
        raise HTTPException(status_code=422, detail=f"Invalid confidence '{confidence}' for '{job_type}'. Must be high/medium/low")


@app.get("/tenant/routing-hint-drafts")
def get_routing_hint_drafts(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Return deterministic routing hint drafts based on current tenant memory (read-only)."""
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
    from app.workflows.scanners.routing_hint_drafts import generate_routing_hint_drafts
    s = TenantConfigRepository.get_settings(db, tenant_id)
    memory = _get_memory(s)
    return generate_routing_hint_drafts(memory)


class RoutingHintApplyRequest(_BaseModel):
    routing_hints: dict


@app.post("/tenant/routing-hints/apply")
def apply_routing_hints(
    request: RoutingHintApplyRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """
    Merge operator-selected routing hints into tenant memory.

    Only keys present in the request body are updated — existing hints for
    other job types are preserved.  system_map and business_profile are
    never modified.  No external systems are touched.
    """
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

    for job_type, hint in request.routing_hints.items():
        if job_type not in _SUPPORTED_HINT_JOB_TYPES:
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported job type '{job_type}'. Supported: {sorted(_SUPPORTED_HINT_JOB_TYPES)}",
            )
        if hint is not None:
            if not isinstance(hint, dict):
                raise HTTPException(status_code=422, detail=f"Hint for '{job_type}' must be an object or null")
            _validate_hint(hint, job_type)

    existing = TenantConfigRepository.get_settings(db, tenant_id)
    current_memory = _get_memory(existing)
    current_memory["routing_hints"].update(request.routing_hints)
    updated = dict(existing)
    updated["memory"] = current_memory
    TenantConfigRepository.update_settings(db, tenant_id, updated)
    return {"status": "ok", "routing_hints": current_memory["routing_hints"]}


# ---------------------------------------------------------------------------
# Routing Preview + Readiness
# ---------------------------------------------------------------------------

@app.get("/tenant/routing-preview/{job_type}")
def get_routing_preview(
    job_type: str,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Return routing preview for a single job type based on saved routing hints."""
    from app.workflows.scanners.routing_preview import (
        resolve_routing_preview,
        SUPPORTED_JOB_TYPES,
    )
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

    if job_type not in SUPPORTED_JOB_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported job type '{job_type}'. Supported: {SUPPORTED_JOB_TYPES}",
        )

    s = TenantConfigRepository.get_settings(db, tenant_id)
    memory = _get_memory(s)
    return resolve_routing_preview(memory["routing_hints"], job_type)


@app.get("/tenant/routing-readiness")
def get_routing_readiness(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Return routing readiness summary across all supported job types."""
    from app.workflows.scanners.routing_preview import resolve_routing_readiness
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

    s = TenantConfigRepository.get_settings(db, tenant_id)
    memory = _get_memory(s)
    return resolve_routing_readiness(memory["routing_hints"])


# ---------------------------------------------------------------------------
# Workflow Scanner Engine
# ---------------------------------------------------------------------------

# Re-export the Gmail analysis helper so existing tests that import
# _scan_gmail_jobs from app.main continue to work unchanged.
from app.workflows.scanners.gmail_adapter import analyse_records as _scan_gmail_jobs  # noqa: E402


def _make_scan_engine(db: Session, tenant_id: str):
    """Construct a WorkflowScannerEngine with the standard repo."""
    from app.workflows.scanners.engine import WorkflowScannerEngine
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
    return WorkflowScannerEngine(db, tenant_id, TenantConfigRepository)


def _scan_result_to_response(result) -> dict:
    return {
        "status":          result.status,
        "last_scan_at":    result.scanned_at,
        "systems_scanned": [result.system],
        "summary":         {result.system: result.summary} if result.summary else {},
    }


@app.post("/workflow-scan/gmail")
def scan_gmail(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """
    Scan stored Gmail-sourced jobs for this tenant and update tenant memory.
    Delegates to WorkflowScannerEngine with the GmailWorkflowScannerAdapter.
    No live Gmail API calls — reads only stored jobs (bounded to 250).
    """
    engine = _make_scan_engine(db, tenant_id)
    try:
        result = engine.run("gmail")
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return _scan_result_to_response(result)


@app.post("/workflow-scan/{system}")
def scan_workflow_system(
    system: str,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """
    Generic workflow scan endpoint.

    Supported systems: gmail (more coming — monday, microsoft_mail, visma, fortnox).
    Returns 404 for unrecognised system keys.
    """
    from app.workflows.scanners.engine import ADAPTER_REGISTRY
    if system not in ADAPTER_REGISTRY:
        from app.workflows.scanners.engine import list_supported_systems
        raise HTTPException(
            status_code=404,
            detail=f"No scanner registered for system '{system}'. "
                   f"Supported: {list_supported_systems()}",
        )
    engine = _make_scan_engine(db, tenant_id)
    try:
        result = engine.run(system)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return _scan_result_to_response(result)


@app.get("/workflow-scan/status")
def workflow_scan_status(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Return the status of the last workflow scan for this tenant."""
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
    s = TenantConfigRepository.get_settings(db, tenant_id)
    scan = s.get("workflow_scan") or {}
    return {
        "last_scan_at":    scan.get("last_scan_at") or None,
        "systems_scanned": scan.get("systems_scanned") or [],
        "status":          scan.get("status") or "never_run",
        "summary":         scan.get("summary") or {},
    }


# ---------------------------------------------------------------------------
# Controlled Dispatch Engine
# ---------------------------------------------------------------------------

def _make_dispatch_engine(db: Session, tenant_id: str):
    """Construct a ControlledDispatchEngine with current app settings."""
    from app.workflows.dispatchers.engine import ControlledDispatchEngine
    return ControlledDispatchEngine(db=db, tenant_id=tenant_id, settings=settings)


def _dispatch_result_to_response(result) -> dict:
    return result.to_dict()


def _get_dispatch_policy(db, tenant_id: str, job_type: str) -> dict:
    """Load tenant config and resolve dispatch policy for job_type."""
    from app.workflows.dispatchers.policy import resolve_dispatch_policy
    tenant_cfg = get_tenant_config(tenant_id, db=db)
    return resolve_dispatch_policy(tenant_cfg, job_type)


@app.get("/jobs/{job_id}/dispatch-policy")
def get_dispatch_policy(
    job_id: str,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Return dispatch policy for this job based on tenant control panel settings."""
    r = (
        db.query(JobRecord)
        .filter(JobRecord.job_id == job_id, JobRecord.tenant_id == tenant_id)
        .first()
    )
    if r is None:
        raise HTTPException(status_code=404, detail="Job not found")

    policy = _get_dispatch_policy(db, tenant_id, r.job_type or "")
    return {
        "job_id":            job_id,
        "job_type":          r.job_type or "unknown",
        **policy,
    }


@app.post("/jobs/{job_id}/dispatch-preview")
def dispatch_preview(
    job_id: str,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """
    Dry-run dispatch preview: resolves routing + policy, returns what would happen.
    Never writes to external systems.
    """
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

    r = (
        db.query(JobRecord)
        .filter(JobRecord.job_id == job_id, JobRecord.tenant_id == tenant_id)
        .first()
    )
    if r is None:
        raise HTTPException(status_code=404, detail="Job not found")

    s = TenantConfigRepository.get_settings(db, tenant_id)
    memory = _get_memory(s)
    policy = _get_dispatch_policy(db, tenant_id, r.job_type or "")
    engine = _make_dispatch_engine(db, tenant_id)
    result = engine.run(job=r, memory=memory, dry_run=True)
    response = _dispatch_result_to_response(result)
    response.update(policy)
    return response


@app.post("/jobs/{job_id}/dispatch")
def dispatch_job(
    job_id: str,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """
    Controlled live dispatch for a job, policy-aware.

    - manual / full_auto: executes immediately when operator calls this endpoint.
    - approval_required: blocks external dispatch; returns approval_required response.
    """
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

    r = (
        db.query(JobRecord)
        .filter(JobRecord.job_id == job_id, JobRecord.tenant_id == tenant_id)
        .first()
    )
    if r is None:
        raise HTTPException(status_code=404, detail="Job not found")

    policy = _get_dispatch_policy(db, tenant_id, r.job_type or "")

    if not policy["can_dispatch_now"]:
        # approval_required — create (or reuse) a dispatch approval record
        from app.repositories.postgres.approval_repository import ApprovalRequestRepository
        s = TenantConfigRepository.get_settings(db, tenant_id)
        memory = _get_memory(s)

        # Resolve which system/target we'd dispatch to (dry-run preview)
        engine = _make_dispatch_engine(db, tenant_id)
        dry = engine.run(job=r, memory=memory, dry_run=True)
        system   = dry.system   or "monday"
        job_type = dry.job_type or (r.job_type or "")

        # Duplicate-approval guard
        existing = ApprovalRequestRepository.find_pending_dispatch_approval(
            db=db, tenant_id=tenant_id, job_id=job_id,
            system=system, job_type=job_type,
        )
        if existing is not None:
            return {
                "status":      "approval_required",
                "approval_id": existing.approval_id,
                "policy_mode": "approval_required",
                "message":     "Redan väntande godkännande för detta jobb.",
            }

        routing_hint = memory.get("routing_hints", {}).get(job_type) or {}
        approval_req = build_dispatch_approval_request(
            job_id=job_id,
            tenant_id=tenant_id,
            job_type=job_type,
            system=system,
            routing_hint=routing_hint,
            dry_run_result=dry.to_dict(),
        )
        ApprovalRequestRepository.upsert_from_payload(
            db=db,
            tenant_id=tenant_id,
            job_id=job_id,
            job_type=job_type,
            approval_request=approval_req,
        )
        return {
            "status":      "approval_required",
            "approval_id": approval_req["approval_id"],
            "policy_mode": "approval_required",
            "message":     "Godkännande krävs innan dispatch.",
        }

    s = TenantConfigRepository.get_settings(db, tenant_id)
    memory = _get_memory(s)
    engine = _make_dispatch_engine(db, tenant_id)
    dispatch_mode = policy.get("policy_mode", "unknown")
    result = engine.run(job=r, memory=memory, dry_run=False, dispatch_mode=dispatch_mode)

    if result.status == "failed":
        raise HTTPException(status_code=400, detail=result.message)

    response = _dispatch_result_to_response(result)
    response.update(policy)
    return response


@app.get("/dispatch/summary")
def dispatch_summary(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
    range: str | None    = None,
    job_type: str | None = None,
    system: str | None   = None,
    limit_recent: int    = 10,
):
    """
    Tenant-scoped dispatch observability summary.

    range preset: today | 7d | 30d | all  (default: 30d)
    Returns counts, breakdown by mode/job_type/system, ROI estimate, recent list,
    and range metadata (range, from, to).
    """
    from app.workflows.dispatchers.observability import get_dispatch_summary
    return get_dispatch_summary(
        db=db,
        tenant_id=tenant_id,
        range_=range,
        job_type=job_type,
        system=system,
        limit_recent=limit_recent,
    )


@app.get("/dispatch/report")
def dispatch_report(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
    range: str | None = None,
):
    """
    Tenant-scoped executive ROI report (customer-facing).

    range preset: today | 7d | 30d | all  (default: 30d)
    Returns headline metrics: dispatches_completed, time_saved_hours,
    success_rate_percent, automation_share_percent, breakdown by mode/system/job_type,
    and a human-readable message.

    automation_share = (approval_required + full_auto) / (total - skipped) * 100
    success_rate     = successful / (total - skipped) * 100
    """
    from app.workflows.dispatchers.observability import get_dispatch_report
    return get_dispatch_report(
        db=db,
        tenant_id=tenant_id,
        range_=range,
    )


@app.post("/jobs/{job_id}/auto-dispatch")
def trigger_auto_dispatch(
    job_id: str,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """
    Manually trigger the auto-dispatch check for a specific job.

    Uses the same logic as the pipeline hook (maybe_auto_dispatch_job).
    Useful for testing and re-running auto-dispatch on existing jobs.

    Returns:
      status: "success" | "skipped" | "failed"
      reason: human-readable explanation
      dispatch_result: dispatch payload when status=success, else null
    """
    r = (
        db.query(JobRecord)
        .filter(JobRecord.job_id == job_id, JobRecord.tenant_id == tenant_id)
        .first()
    )
    if r is None:
        raise HTTPException(status_code=404, detail="Job not found")

    result = maybe_auto_dispatch_job(
        db=db,
        tenant_id=tenant_id,
        job=r,
        settings=settings,
    )
    return result.to_dict()


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