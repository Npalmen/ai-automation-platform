import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.automation.wow_flows import build_automation_case_payload
from app.core.audit_list_response_schemas import AuditEventListResponse
from app.core.audit_service import create_audit_event
from app.core.admin_auth import require_admin_api_key
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


def _is_production_env(app_settings) -> bool:
    return str(getattr(app_settings, "ENV", "") or "").strip().lower() in {"prod", "production"}


def _openapi_urls_for(app_settings) -> dict:
    """Return FastAPI docs URLs. Public docs are disabled in production."""
    if _is_production_env(app_settings):
        return {"docs_url": None, "redoc_url": None, "openapi_url": None}
    return {"docs_url": "/docs", "redoc_url": "/redoc", "openapi_url": "/openapi.json"}


app = FastAPI(title=settings.APP_NAME, **_openapi_urls_for(settings))


@app.on_event("startup")
async def on_startup():
    import app.repositories.postgres  # noqa: F401
    from app.repositories.postgres.schema_migrations import (
        ensure_runtime_schema,
        provision_tenant_defaults,
    )

    Base.metadata.create_all(bind=engine)
    ensure_runtime_schema(engine)
    provision_tenant_defaults(engine)
    print("Startup complete")

    # Warn if OAuth refresh credential set is incomplete — prevents silent invalid_grant failures.
    import logging as _logging
    _startup_log = _logging.getLogger("startup")
    _s = get_settings()
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


def _build_tenant_context_payload(tenant_id: str, db: Session) -> dict:
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

    cfg = get_tenant_config(tenant_id, db=db)
    control = _build_control_response(TenantConfigRepository.get_settings(db, tenant_id))
    onboarding = onboarding_status(db=db, tenant_id=tenant_id)
    return {
        "tenant_id": tenant_id,
        "name": cfg.get("name"),
        "enabled_job_types": cfg.get("enabled_job_types") or [],
        "demo_mode": bool((control.get("automation") or {}).get("demo_mode", False)),
        "onboarding": {
            "status": onboarding.get("status"),
            "percent": (onboarding.get("score") or {}).get("percent", 0),
            "completed": (onboarding.get("score") or {}).get("completed", 0),
            "total": (onboarding.get("score") or {}).get("total", 0),
        },
    }


@app.get("/tenant/context")
def tenant_context_current(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Return tenant context for the authenticated tenant API key."""
    return _build_tenant_context_payload(tenant_id=tenant_id, db=db)


from pydantic import BaseModel as _BaseModel


class TenantCreateRequest(_BaseModel):
    tenant_id: str
    name: str


class TenantConfigUpdateRequest(_BaseModel):
    enabled_job_types: list[str]
    allowed_integrations: list[str]
    auto_actions: dict[str, bool | str]


class CustomerAccountRequest(_BaseModel):
    company_name: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    support_email: str | None = None
    language: str | None = "sv"
    region: str | None = "SE"
    team_members: list[dict] | None = None


@app.get("/tenant/config/{tenant_id}")
def get_tenant_config_by_id(
    tenant_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_api_key),
):
    """Return config for any tenant by ID. Requires X-Admin-API-Key."""
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


@app.get("/admin/tenant-context/{tenant_id}")
def admin_tenant_context(
    tenant_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_api_key),
):
    """Return tenant context for admin tooling (navigation/onboarding context)."""
    return _build_tenant_context_payload(tenant_id=tenant_id, db=db)


@app.get("/tenants")
def list_tenants(
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_api_key),
):
    """Return all tenants in the DB. Requires X-Admin-API-Key."""
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
    _: None = Depends(require_admin_api_key),
):
    """
    Run a deterministic verification job for any tenant by ID.
    Requires X-Admin-API-Key header.

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
    _: None = Depends(require_admin_api_key),
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
    _: None = Depends(require_admin_api_key),
):
    """Save config for any tenant by ID. Requires X-Admin-API-Key."""
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


def _resolve_email_approval(
    db,
    approval,
    *,
    approved: bool,
    actor: str | None = None,
    note: str | None = None,
) -> dict:
    """Mark an email approval approved/rejected; send the email when approved."""
    from datetime import datetime, timezone
    from app.workflows.action_executor import execute_action

    now = datetime.now(timezone.utc)
    new_state = "approved" if approved else "rejected"

    send_result = None
    send_error = None

    if approved:
        delivery = approval.delivery_payload or {}
        if delivery:
            try:
                send_result = execute_action(delivery)
            except Exception as exc:
                send_error = str(exc)
                # Do not raise — record the failure but complete the approval
                import logging
                logging.getLogger(__name__).error(
                    "Email send failed for approval %s: %s",
                    approval.approval_id, exc,
                )

    # Update approval record state
    updated_payload = dict(approval.request_payload or {})
    updated_payload["state"] = new_state
    updated_payload["resolved_at"] = now.isoformat()
    updated_payload["resolved_by"] = actor or "operator"
    updated_payload["resolution_note"] = note

    ApprovalRequestRepository.upsert_from_payload(
        db=db,
        tenant_id=approval.tenant_id,
        job_id=approval.job_id,
        job_type=approval.job_type,
        approval_request=updated_payload,
        delivery_payload=approval.delivery_payload,
    )

    return {
        "approval_id": approval.approval_id,
        "status": new_state,
        "job_id": approval.job_id,
        "send_result": send_result,
        "send_error": send_error,
    }


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

    # Email approvals: execute the stored email payload then mark approved
    if approval.next_on_approve == "email_send":
        return _resolve_email_approval(db, approval, approved=True,
                                       actor=request.actor, note=request.note)

    # Finance approvals: execute the stored Fortnox payload after operator approval
    if approval.next_on_approve == "finance_fortnox_export":
        return _resolve_finance_fortnox_approval(
            db=db,
            approval=approval,
            approved=True,
            actor=request.actor,
            note=request.note,
        )

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

    # Email approvals: just mark rejected, no send
    if approval.next_on_approve == "email_send":
        return _resolve_email_approval(db, approval, approved=False,
                                       actor=request.actor, note=request.note)

    # Finance approvals: close without any external Fortnox write
    if approval.next_on_approve == "finance_fortnox_export":
        return _resolve_finance_fortnox_approval(
            db=db,
            approval=approval,
            approved=False,
            actor=request.actor,
            note=request.note,
        )

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
_GMAIL_UI_NOISE_PHRASES = (
    "Klicka för att informera Gmail om att den här konversationen är viktig",
)
_GMAIL_UI_NOISE_RE = re.compile(
    r"(?:klicka|kilcka)\s+för\s+att\s+informera\s+gmail\s+om\s+att\s+den\s+här\s+konversationen\s+är\s+viktig",
    re.IGNORECASE,
)


def _infer_priority(subject: str, body_text: str) -> str:
    """Return 'high', 'medium', or 'low' based on keyword presence."""
    combined = f"{subject} {body_text}".lower()
    if any(kw in combined for kw in _HIGH_PRIORITY_KEYWORDS):
        return "high"
    if subject.strip() and subject.strip() != "(no subject)":
        return "medium"
    return "low"


def _clean_gmail_subject(subject: str) -> str:
    cleaned = (subject or "").strip()
    if not cleaned:
        return cleaned
    for phrase in _GMAIL_UI_NOISE_PHRASES:
        cleaned = cleaned.replace(phrase, "").strip()
    cleaned = _GMAIL_UI_NOISE_RE.sub("", cleaned).strip()
    return cleaned


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

        subject = _clean_gmail_subject(msg.get("subject") or "(no subject)")
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
                "internet_message_id": msg.get("internet_message_id") or "",
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
                "internet_message_id": msg.get("internet_message_id") or "",
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


def _get_customer_account(settings_dict: dict, config: dict, tenant_id: str) -> dict:
    account = settings_dict.get("account") or {}
    branding = settings_dict.get("branding") or {}
    return {
        "tenant_id": tenant_id,
        "company_name": (
            account.get("company_name")
            or branding.get("company_display_name")
            or config.get("name")
            or tenant_id
        ),
        "contact_name": account.get("contact_name") or "",
        "contact_email": account.get("contact_email") or "",
        "support_email": account.get("support_email") or settings_dict.get("support_email") or "",
        "language": account.get("language") or "sv",
        "region": account.get("region") or "SE",
        "team_members": account.get("team_members") or [],
    }


def _normalise_team_members(items: list[dict] | None) -> list[dict]:
    normalised: list[dict] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        email = str(item.get("email") or "").strip()
        name = str(item.get("name") or "").strip()
        if not email and not name:
            continue
        normalised.append({
            "name": name,
            "email": email,
            "role": str(item.get("role") or "member").strip() or "member",
            "status": str(item.get("status") or "active").strip() or "active",
        })
    return normalised


def _customer_activity_label(item: dict) -> str:
    status = item.get("status")
    action = item.get("latest_action")
    if status == "awaiting_approval":
        return "Väntar på godkännande"
    if status == "failed":
        return "Behöver åtgärd"
    if action == "send_email":
        return "Kundmeddelande skickat"
    if action == "create_monday_item":
        return "Skapat i Monday"
    if status == "completed":
        return "Ärende klart"
    if status == "processing":
        return "Bearbetas"
    return "Aktivitet registrerad"


@app.get("/customer/account")
def get_customer_account(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Return customer-facing account/profile metadata for the authenticated tenant."""
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
    settings_dict = TenantConfigRepository.get_settings(db, tenant_id)
    config = get_tenant_config(tenant_id, db=db)
    return _get_customer_account(settings_dict, config, tenant_id)


@app.put("/customer/account")
def put_customer_account(
    request: CustomerAccountRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Persist simple customer account/team metadata without changing auth/RBAC."""
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
    existing = TenantConfigRepository.get_settings(db, tenant_id)
    config = get_tenant_config(tenant_id, db=db)
    current = _get_customer_account(existing, config, tenant_id)
    incoming = request.model_dump(exclude_unset=True)
    if "team_members" in incoming:
        incoming["team_members"] = _normalise_team_members(request.team_members)
    account = {**current, **incoming}
    account.pop("tenant_id", None)
    updated = dict(existing)
    updated["account"] = account
    if request.support_email is not None:
        updated["support_email"] = request.support_email or ""
    TenantConfigRepository.update_settings(db, tenant_id, updated)
    return _get_customer_account(updated, config, tenant_id)


@app.get("/customer/activity")
def customer_activity(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
    limit: int = 25,
    offset: int = 0,
):
    """Customer-friendly activity feed derived from existing dashboard activity."""
    raw = dashboard_activity(db=db, tenant_id=tenant_id, limit=limit, offset=offset)
    items = []
    for item in raw.get("items", []):
        items.append({
            "created_at": item.get("created_at"),
            "type": item.get("type"),
            "status": item.get("status"),
            "priority": item.get("priority"),
            "label": _customer_activity_label(item),
        })
    return {"items": items, "total": raw.get("total", 0)}


@app.get("/customer/results")
def customer_results(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Customer-facing ROI/result summary for the current tenant."""
    summary = _compute_summary(db, tenant_id)
    roi = _compute_roi(db, tenant_id)
    total_cases = (
        summary.get("leads_today", 0)
        + summary.get("inquiries_today", 0)
        + summary.get("invoices_today", 0)
    )
    completed = summary.get("completed_today", 0)
    automation_rate = round((completed / total_cases) * 100) if total_cases else 0
    return {
        "period": "today",
        "estimated_hours_saved": roi.get("estimated_hours_saved", 0),
        "estimated_value_sek": roi.get("estimated_value_sek", 0),
        "cases_handled": total_cases,
        "completed_cases": completed,
        "waiting_customer": summary.get("waiting_customer", 0),
        "automation_rate_percent": automation_rate,
        "breakdown": {
            "leads": summary.get("leads_today", 0),
            "support": summary.get("inquiries_today", 0),
            "invoices": summary.get("invoices_today", 0),
        },
    }


@app.get("/customer/health")
def customer_health(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Return a simplified, customer-safe health summary."""
    from app.health.integration_health import get_integration_health
    health = get_integration_health(db, tenant_id, app_settings=get_settings())
    overall = health.get("overall_status") or "warning"
    labels = {
        "healthy": "Allt fungerar",
        "warning": "Kontroll rekommenderas",
        "error": "Åtgärd krävs",
        "not_configured": "Integration saknas",
    }
    systems = {}
    for key, value in (health.get("systems") or {}).items():
        status = value.get("status") if isinstance(value, dict) else "warning"
        systems[key] = {
            "status": status,
            "label": labels.get(status, "Kontroll rekommenderas"),
        }
    return {
        "overall_status": overall,
        "message": labels.get(overall, "Kontroll rekommenderas"),
        "systems": systems,
    }


@app.get("/dashboard/leads")
def dashboard_leads(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Lead pipeline KPIs — counts by lead_status and score_category, plus pipeline value."""
    from sqlalchemy import func

    # All lead jobs for this tenant
    lead_records = (
        db.query(JobRecord)
        .filter(JobRecord.tenant_id == tenant_id, JobRecord.job_type == "lead")
        .all()
    )

    status_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {"hot": 0, "warm": 0, "cold": 0}
    service_counts: dict[str, int] = {}
    total_pipeline_low = 0
    total_pipeline_high = 0
    pipeline_leads = 0

    import re as _re
    _price_re = _re.compile(r"([\d\s]+)\s*[–\-]\s*([\d\s]+)\s*kr")

    for r in lead_records:
        stored = r.result or {}
        history = stored.get("processor_history") or []
        lead_payload: dict = {}
        for entry in history:
            if entry.get("processor") == "lead_analyzer_processor":
                lead_payload = (entry.get("result") or {}).get("payload") or {}
                break

        # lead_status
        status = (r.input_data or {}).get("lead_status") or lead_payload.get("lead_status") or "new"
        status_counts[status] = status_counts.get(status, 0) + 1

        # score category
        cat = (lead_payload.get("lead_score") or {}).get("category") or "cold"
        if cat in category_counts:
            category_counts[cat] += 1

        # matched_service / lead_type
        la = lead_payload.get("lead_analysis") or {}
        service = la.get("matched_service") or la.get("lead_type") or "unknown"
        service_counts[service] = service_counts.get(service, 0) + 1

        # Pipeline value estimate from offer_draft
        offer = lead_payload.get("offer_draft") or {}
        price_str = offer.get("estimated_price_range") or ""
        m = _price_re.search(price_str)
        if m:
            try:
                lo = int(m.group(1).replace(" ", ""))
                hi = int(m.group(2).replace(" ", ""))
                total_pipeline_low += lo
                total_pipeline_high += hi
                pipeline_leads += 1
            except ValueError:
                pass

    return {
        "total_leads": len(lead_records),
        "by_status": status_counts,
        "by_category": category_counts,
        "by_service": service_counts,
        "pipeline_value_estimate": {
            "leads_with_estimate": pipeline_leads,
            "low_sek": total_pipeline_low,
            "high_sek": total_pipeline_high,
        },
    }


@app.get("/dashboard/support")
def dashboard_support(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Support pipeline KPIs — counts by support_status, ticket_type, priority_category."""
    support_records = (
        db.query(JobRecord)
        .filter(JobRecord.tenant_id == tenant_id, JobRecord.job_type == "customer_inquiry")
        .all()
    )

    status_counts: dict[str, int] = {}
    ticket_type_counts: dict[str, int] = {}
    priority_counts: dict[str, int] = {"critical": 0, "urgent": 0, "normal": 0}
    next_action_counts: dict[str, int] = {}
    escalated = 0
    awaiting_info = 0

    for r in support_records:
        # support_status from input_data (operator-set) or from processor payload
        support_payload: dict = {}
        history = list(r.processor_history or [])
        for entry in history:
            if entry.get("processor") == "support_analyzer_processor":
                support_payload = (entry.get("result") or {}).get("payload") or {}
                break

        status = (r.input_data or {}).get("support_status") or support_payload.get("support_status") or "new"
        status_counts[status] = status_counts.get(status, 0) + 1

        # ticket_type
        analysis = support_payload.get("support_analysis") or {}
        ttype = analysis.get("ticket_type") or "unknown"
        ticket_type_counts[ttype] = ticket_type_counts.get(ttype, 0) + 1

        # priority category
        priority = support_payload.get("support_priority") or {}
        cat = priority.get("category") or "normal"
        if cat in priority_counts:
            priority_counts[cat] += 1

        # next_action
        next_action_dict = support_payload.get("support_next_action") or {}
        action = next_action_dict.get("action") or "unknown"
        next_action_counts[action] = next_action_counts.get(action, 0) + 1
        if action == "escalate":
            escalated += 1
        if action == "ask_for_info":
            awaiting_info += 1

    return {
        "total_cases": len(support_records),
        "by_status": status_counts,
        "by_ticket_type": ticket_type_counts,
        "by_priority": priority_counts,
        "by_next_action": next_action_counts,
        "escalated_count": escalated,
        "awaiting_info_count": awaiting_info,
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


# ── Extended dashboard KPIs + operational insights ────────────────────────────

@app.get("/dashboard/kpis")
def dashboard_kpis(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Extended operational KPIs: approval queues, underlag ready, active ops cases."""
    from app.insights.engine import compute_dashboard_kpis
    return compute_dashboard_kpis(db, tenant_id)


@app.get("/dashboard/operational-insights")
def dashboard_operational_insights(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
    limit: int = 30,
):
    """Tenant-scoped operational insights — deterministic rule-based signals."""
    from app.insights.engine import get_operational_insights
    rows = get_operational_insights(db, tenant_id, limit=limit)
    return {
        "tenant_id": tenant_id,
        "insights": rows,
        "count": len(rows),
    }


@app.get("/dashboard/sla-breaches")
def dashboard_sla_breaches(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """List leads that have breached or are approaching SLA window."""
    from app.insights.sla_reminders import find_sla_breaches
    breaches = find_sla_breaches(db, tenant_id)
    return {
        "tenant_id": tenant_id,
        "breaches": breaches,
        "count": len(breaches),
    }


@app.get("/dashboard/cockpit")
def dashboard_cockpit(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Daily pilot cockpit: aggregated action-oriented counts and top items.

    Returns five buckets a pilot operator needs to check every morning:
      actions_required  — pending approvals, hot leads, escalations
      sla_risk          — leads at or approaching SLA breach
      waiting_customer  — jobs stalled on customer response
      underlag_ready    — completed underlags not yet sent to Fortnox
      blocked           — work orders with status 'blocked'
    """
    from app.insights.sla_reminders import find_sla_breaches
    from app.insights.engine import (
        compute_dashboard_kpis,
        get_operational_insights,
        SEVERITY_ORDER,
    )
    from app.repositories.postgres.approval_models import ApprovalRequestRecord

    kpis = compute_dashboard_kpis(db, tenant_id)
    breaches = find_sla_breaches(db, tenant_id)

    pending_approvals = (
        db.query(ApprovalRequestRecord)
        .filter(
            ApprovalRequestRecord.tenant_id == tenant_id,
            ApprovalRequestRecord.state == "pending",
        )
        .all()
    )

    email_approvals   = [a for a in pending_approvals if a.next_on_approve == "email_send"]
    dispatch_approvals = [a for a in pending_approvals if a.next_on_approve == "controlled_dispatch"]

    # Top action items across all insight types
    all_insights = get_operational_insights(db, tenant_id, limit=50)
    high_priority = [
        i for i in all_insights
        if SEVERITY_ORDER.get(i["severity"], 99) <= 1  # critical + high
    ][:5]

    actions_required = (
        len(email_approvals)
        + len(dispatch_approvals)
        + len([i for i in all_insights if i["type"] in ("hot_lead_pending", "stale_lead", "support_escalation", "work_order_blocked")])
    )

    return {
        "tenant_id": tenant_id,
        "cockpit": {
            "actions_required":    actions_required,
            "sla_risk":            len(breaches),
            "waiting_customer":    kpis["waiting_customer"],
            "underlag_ready":      kpis["underlag_ready"],
            "blocked":             len([i for i in all_insights if i["type"] == "work_order_blocked"]),
        },
        "top_action_items": high_priority,
        "sla_breaches":     breaches[:3],
        "email_approvals_pending":    len(email_approvals),
        "dispatch_approvals_pending": len(dispatch_approvals),
    }


# ── Control panel ─────────────────────────────────────────────────────────────

_VALID_RUN_MODES = {"manual", "scheduled", "paused"}

_DEFAULT_CONTROL = {
    "automation": {
        "leads_enabled":    True,
        "support_enabled":  True,
        "invoices_enabled": True,
        "followups_enabled": True,
        "demo_mode": False,
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
            "demo_mode":         bool(auto.get("demo_mode",        _DEFAULT_CONTROL["automation"]["demo_mode"])),
        },
        "support_email": settings.get("support_email") or "",
        "scheduler": {
            "run_mode": sched.get("run_mode") or "manual",
        },
    }


def _is_demo_mode_enabled(settings: dict) -> bool:
    """Return whether this tenant is explicitly marked as demo/test."""
    if not isinstance(settings, dict):
        return False
    return bool(((settings or {}).get("automation") or {}).get("demo_mode", False))


class ControlPanelRequest(_BaseModel):
    class _Automation(_BaseModel):
        leads_enabled:    bool = True
        support_enabled:  bool = True
        invoices_enabled: bool = True
        followups_enabled: bool = True
        demo_mode: bool = False

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
            "demo_mode":         request.automation.demo_mode,
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
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

    ctrl_settings = TenantConfigRepository.get_settings(db, tenant_id)
    if _is_demo_mode_enabled(ctrl_settings):
        return {
            "status": "demo_mode",
            "processed": 0,
            "created_jobs": 0,
            "continued_threads": 0,
            "deduped": 0,
            "errors": [],
            "message": "Demo-läge är aktivt — live inbox-sync är spärrad. Använd demo-data i Onboarding.",
        }

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
        import logging as _log
        _log.getLogger(__name__).exception("Inbox sync failed")
        raise HTTPException(
            status_code=500,
            detail={
                "status": "failed",
                "message": "Inbox sync misslyckades. Kontrollera loggar för detaljer.",
                "processed": 0,
                "created_jobs": 0,
                "continued_threads": 0,
                "deduped": 0,
                "errors": [],
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
    demo_mode          = bool(auto.get("demo_mode", False))
    support_email      = ctrl_settings.get("support_email") or ""

    automation = {
        "scheduler_mode":    scheduler_mode,
        "followups_enabled": followups_enabled,
        "demo_mode":         demo_mode,
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

    signal: dict | None = None
    if overall == "failed":
        signal = {
            "severity": "critical",
            "title": "Setup verification failed",
            "action": "Fix failed checks before enabling scheduled pilot operations.",
            "runbook_ref": "docs/12-production-guide.md#pre-launch-checklist",
        }
    elif overall == "warning":
        signal = {
            "severity": "warning",
            "title": "Setup verification has warnings",
            "action": "Review warning checks and run a manual smoke flow before go-live.",
            "runbook_ref": "docs/12-production-guide.md#pre-launch-checklist",
        }

    return {"status": overall, "checks": checks, "message": message, "runbook_signal": signal}


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


def _build_digest_body(tenant_id: str, summary: dict, roi: dict, insights: list[dict] | None = None) -> tuple[str, str]:
    """Build (subject, body) for the daily digest email."""
    from datetime import date
    today_str = date.today().isoformat()
    subject   = f"AI Automation Report – {today_str}"

    errors_today = 0

    insights_section = ""
    if insights:
        top_items = insights[:5]
        lines = []
        for item in top_items:
            severity = item.get("severity", "info").upper()
            title = item.get("title", "")
            lines.append(f"  [{severity}] {title}")
        if lines:
            insights_section = "\nViktigt just nu:\n" + "\n".join(lines) + "\n"

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
{insights_section}
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
        import logging as _log
        _log.getLogger(__name__).exception("Daily digest dispatch failed")
        raise HTTPException(
            status_code=500,
            detail={"status": "failed", "message": "Utskick av daglig rapport misslyckades. Kontrollera loggar."},
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
    demo_mode = _is_demo_mode_enabled(ctrl)

    inbox_sync_result: dict | None = None
    digest_result: dict | None = None
    sla_result: dict | None = None
    error: str | None = None

    try:
        # ── Inbox sync ────────────────────────────────────────────────────────
        if demo_mode:
            inbox_sync_result = {"skipped": True, "reason": "demo_mode"}
        elif run_mode == "scheduled":
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

        if demo_mode:
            digest_result = {"skipped": True, "reason": "demo_mode"}
        elif not notif_enabled or not recipient:
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
                try:
                    from app.insights.engine import get_operational_insights
                    digest_insights = get_operational_insights(db, tenant_id, limit=5)
                except Exception:
                    digest_insights = []
                subject, body = _build_digest_body(tenant_id, summary, roi, insights=digest_insights)
                dispatch_action({
                    "type":      "send_email",
                    "tenant_id": tenant_id,
                    "to":        recipient,
                    "subject":   subject,
                    "body":      body,
                })
                state["last_digest_sent_at"] = now_utc.isoformat()
                digest_result = {"skipped": False, "recipient": recipient, "subject": subject}

        # ── SLA reminders ────────────────────────────────────────────────────
        try:
            from app.insights.sla_reminders import run_sla_reminder_pass
            sla_result = run_sla_reminder_pass(db, tenant_id, ctrl)
            if sla_result and not sla_result.get("skipped"):
                state["last_sla_reminder_at"] = now_utc.isoformat()
        except Exception as sla_exc:
            import logging as _sla_log
            _sla_log.getLogger(__name__).exception("SLA reminder pass failed")
            sla_result = {"skipped": False, "error": str(sla_exc)}

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
        "sla_reminders":    sla_result,
        "error":            error,
    }


@app.post("/scheduler/run-once")
def scheduler_run_once(
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_api_key),
):
    """Run one scheduler pass for all tenants. Requires admin API key."""
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


def _parse_iso_datetime(value: str | None):
    if not value:
        return None
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _build_case_timeline(
    *,
    inp: dict,
    thread_messages: list[dict],
    action_records: list,
    approval_records: list,
    history: list[dict],
) -> list[dict]:
    events: list[dict] = []

    received_at = inp.get("received_at")
    if received_at:
        events.append({
            "timestamp": received_at,
            "kind": "inbound_received",
            "title": "Inkommande meddelande",
            "status": "completed",
        })

    for msg in thread_messages:
        if msg.get("direction") != "incoming":
            continue
        ts = msg.get("created_at")
        if not ts:
            continue
        events.append({
            "timestamp": ts,
            "kind": "conversation_inbound",
            "title": "Kundsvar mottaget",
            "status": "completed",
        })

    for entry in history:
        if entry.get("processor") != "action_dispatch_processor":
            continue
        payload = (entry.get("result") or {}).get("payload") or {}
        lead_sla = payload.get("lead_sla") or {}
        if lead_sla.get("enabled") and lead_sla.get("first_follow_up_due_at"):
            due_at = lead_sla.get("first_follow_up_due_at")
            status = "warning" if lead_sla.get("status") in {"pending", "breached"} else "completed"
            events.append({
                "timestamp": due_at,
                "kind": "sla_deadline",
                "title": "SLA: första uppföljning",
                "status": status,
                "meta": {
                    "sla_status": lead_sla.get("status"),
                    "follow_up_state": lead_sla.get("first_follow_up_state"),
                },
            })
        break

    for approval in approval_records:
        payload = approval.request_payload or {}
        title = payload.get("title") or "Godkännande"
        state = approval.state or "unknown"
        ts = (
            approval.resolved_at.isoformat() if approval.resolved_at
            else approval.requested_at.isoformat() if approval.requested_at
            else approval.created_at.isoformat()
        )
        events.append({
            "timestamp": ts,
            "kind": "approval",
            "title": title,
            "status": state,
            "meta": {
                "approval_id": approval.approval_id,
                "next_on_approve": approval.next_on_approve,
                "resolved_by": approval.resolved_by,
            },
        })

    for action in action_records:
        ts = action.executed_at.isoformat() if action.executed_at else None
        if not ts:
            continue
        events.append({
            "timestamp": ts,
            "kind": "action",
            "title": f"Aktion: {action.action_type}",
            "status": action.status,
        })

    events.sort(
        key=lambda item: (
            _parse_iso_datetime(item.get("timestamp")) is None,
            _parse_iso_datetime(item.get("timestamp")) or item.get("timestamp"),
        )
    )
    return events


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
    sla_status: str | None = None
    for entry in reversed(history):
        if entry.get("processor") != "action_dispatch_processor":
            continue
        payload = (entry.get("result") or {}).get("payload") or {}
        lead_sla = payload.get("lead_sla") or {}
        sla_status = lead_sla.get("status")
        break

    return {
        "subject":       subject,
        "customer_name": customer_name,
        "customer_email": customer_email,
        "priority":      priority,
        "received_at":   received_at,
        "processed_at":  processed_at,
        "sla_status":    sla_status,
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
            "sla_status":     derived["sla_status"],
        })

    return {"items": items, "total": total, "limit": limit, "offset": offset}


def _is_finance_draft_available(record, inp: dict) -> bool:
    """True when a finance draft can meaningfully be generated for this case."""
    if (record.status or "").lower() == "completed":
        return True
    workspace = inp.get("operations_workspace") or {}
    wo_status = (workspace.get("work_order") or {}).get("status") or ""
    return wo_status.lower() == "completed"


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
    approval_records = ApprovalRequestRepository.list_for_job(
        db=db,
        tenant_id=tenant_id,
        job_id=job_id,
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

    # --- lead analysis fields (from lead_analyzer_processor) ---
    lead_payload: dict = {}
    for entry in history:
        if entry.get("processor") == "lead_analyzer_processor":
            lead_payload = (entry.get("result") or {}).get("payload") or {}
            break

    # lead_status: operator-set value in input_data takes precedence over pipeline value
    lead_status = (inp.get("lead_status")
                   or lead_payload.get("lead_status"))

    la = lead_payload.get("lead_analysis") or {}
    mi = lead_payload.get("missing_info") or {}
    ls = lead_payload.get("lead_score") or {}

    # --- support analysis fields (from support_analyzer_processor) ---
    support_payload: dict = {}
    for entry in history:
        if entry.get("processor") == "support_analyzer_processor":
            support_payload = (entry.get("result") or {}).get("payload") or {}
            break

    action_dispatch_payload: dict = {}
    for entry in reversed(history):
        if entry.get("processor") == "action_dispatch_processor":
            action_dispatch_payload = (entry.get("result") or {}).get("payload") or {}
            break

    timeline = _build_case_timeline(
        inp=inp,
        thread_messages=thread_messages,
        action_records=action_records,
        approval_records=approval_records,
        history=history,
    )
    automation_case = build_automation_case_payload(
        r,
        action_records=action_records,
        approval_records=approval_records,
    )

    support_status = (inp.get("support_status")
                      or support_payload.get("support_status"))

    sa = support_payload.get("support_analysis") or {}
    smi = support_payload.get("support_missing_info") or {}
    sp = support_payload.get("support_priority") or {}
    sna = support_payload.get("support_next_action") or {}

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
        "timeline":         timeline,
        "actions":          actions,
        "errors":           errors,
        "routing_preview":  routing_preview,
        "lead_sla":                     action_dispatch_payload.get("lead_sla"),
        "ai_reply_suggestions":         action_dispatch_payload.get("ai_reply_suggestions") or [],
        # Lead analysis (present only for lead job_type)
        "lead_analysis":                la or None,
        "missing_fields":               mi.get("missing_fields"),
        "completeness_score":           mi.get("completeness_score"),
        "lead_score":                   ls.get("score"),
        "score_category":               ls.get("category"),
        "score_reasons":                ls.get("reasons"),
        "offer_draft":                  lead_payload.get("offer_draft"),
        "next_action":                  lead_payload.get("next_action"),
        "generated_question_message":   lead_payload.get("generated_question_message"),
        # Extended lead intelligence
        "lead_status":                  lead_status,
        "tenant_context_used":          la.get("tenant_context_used"),
        "tenant_context_sources":       la.get("context_sources"),
        "matched_service":              la.get("matched_service"),
        "schema_source":                mi.get("schema_source"),
        "required_fields_used":         mi.get("required_fields"),
        "optional_fields_used":         mi.get("optional_fields"),
        "business_fit_reason":          ls.get("business_fit_reason"),
        # Support analysis (present only for customer_inquiry job_type)
        "support_analysis":             sa or None,
        "support_missing_fields":       smi.get("missing_fields"),
        "support_completeness_score":   smi.get("completeness_score"),
        "support_priority_score":       sp.get("score"),
        "support_priority_category":    sp.get("category"),
        "support_priority_reasons":     sp.get("reasons"),
        "support_response_draft":       support_payload.get("support_response_draft"),
        "support_next_action":          sna,
        "support_generated_question_message": support_payload.get("support_generated_question_message"),
        "support_status":               support_status,
        "support_tenant_context_used":  sa.get("tenant_context_used"),
        "support_context_sources":      sa.get("context_sources"),
        "support_business_risk_reason": sp.get("business_risk_reason"),
        "operations_workspace":         _merge_operations_workspace(inp.get("operations_workspace")),
        "finance_draft_available":      _is_finance_draft_available(r, inp),
        "finance_draft_url":            f"/finance/invoices/{r.job_id}/draft",
        "automation_summary":           automation_case["summary"],
        "automation_risks":             automation_case["risks"],
        "wow_flows":                    automation_case["wow_flows"],
    }


@app.get("/cases/{job_id}/automation-wow")
def get_case_automation_wow(
    job_id: str,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Return deterministic Phase 6 automation summary, risks, and safe flow previews."""
    from app.repositories.postgres.action_execution_models import ActionExecutionRecord

    record = (
        db.query(JobRecord)
        .filter(JobRecord.job_id == job_id, JobRecord.tenant_id == tenant_id)
        .first()
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Case not found")

    action_records = (
        db.query(ActionExecutionRecord)
        .filter(
            ActionExecutionRecord.job_id == job_id,
            ActionExecutionRecord.tenant_id == tenant_id,
        )
        .order_by(ActionExecutionRecord.executed_at.asc())
        .all()
    )
    approval_records = ApprovalRequestRepository.list_for_job(
        db=db,
        tenant_id=tenant_id,
        job_id=job_id,
    )
    return {
        "job_id": job_id,
        **build_automation_case_payload(
            record,
            action_records=action_records,
            approval_records=approval_records,
        ),
    }


# ---------------------------------------------------------------------------
# Operations Workspace v1 (Slice 4 + 5)
# ---------------------------------------------------------------------------

_VALID_WORK_ORDER_STATUSES = {
    "new", "planned", "scheduled", "in_progress", "blocked", "completed", "cancelled",
}
_VALID_PROJECT_STATUSES = {
    "intake", "planning", "active", "handover", "done", "on_hold",
}
_VALID_TASK_STATUSES = {
    "todo", "in_progress", "done", "blocked",
}
_VALID_DELIVERY_PACKAGE_STATUSES = {
    "not_started", "collecting", "ready", "sent",
}
_VALID_DOCUMENTATION_BUCKETS = {"before_images", "after_images", "documents"}


def _checklist_item(item_id: str, label: str) -> dict:
    return {
        "id": item_id,
        "label": label,
        "done": False,
        "note": None,
        "updated_at": None,
    }


_INSTALLER_CHECKLIST_TEMPLATES: dict[str, dict[str, list[dict]]] = {
    "general": {
        "site_survey": [
            _checklist_item("access_confirmed", "Atkomst till fastigheten bekräftad"),
            _checklist_item("site_conditions_documented", "Förutsättningar på plats dokumenterade"),
            _checklist_item("customer_requirements_confirmed", "Kundens krav och omfattning bekräftade"),
        ],
        "installation": [
            _checklist_item("materials_available", "Material och utrustning finns på plats"),
            _checklist_item("installation_completed", "Installation genomförd"),
            _checklist_item("work_area_cleaned", "Arbetsyta städad och återställd"),
        ],
        "commissioning": [
            _checklist_item("function_test_passed", "Funktionstest godkänt"),
            _checklist_item("safety_check_passed", "Säkerhetskontroll godkänd"),
        ],
        "handover": [
            _checklist_item("customer_walkthrough_done", "Genomgång med kund genomförd"),
            _checklist_item("documentation_collected", "Dokumentation och bilder insamlade"),
            _checklist_item("ready_for_invoice", "Underlag redo för fakturering"),
        ],
    },
    "solar": {
        "site_survey": [
            _checklist_item("roof_condition_checked", "Takets skick och bärighet kontrollerad"),
            _checklist_item("electrical_capacity_checked", "Elcentral och kapacitet kontrollerad"),
            _checklist_item("shading_documented", "Skuggning och placering dokumenterad"),
        ],
        "installation": [
            _checklist_item("mounting_installed", "Montagesystem installerat"),
            _checklist_item("panels_installed", "Paneler installerade"),
            _checklist_item("inverter_connected", "Växelriktare ansluten"),
        ],
        "commissioning": [
            _checklist_item("production_test_passed", "Produktionstest godkänt"),
            _checklist_item("monitoring_enabled", "Övervakning aktiverad"),
        ],
        "handover": [
            _checklist_item("customer_walkthrough_done", "Genomgång med kund genomförd"),
            _checklist_item("documentation_collected", "Dokumentation och bilder insamlade"),
            _checklist_item("ready_for_invoice", "Underlag redo för fakturering"),
        ],
    },
    "ev_charger": {
        "site_survey": [
            _checklist_item("parking_location_confirmed", "Placering vid parkeringsplats bekräftad"),
            _checklist_item("electrical_capacity_checked", "Elcentral och säkringsnivå kontrollerad"),
            _checklist_item("cable_route_documented", "Kabeldragning dokumenterad"),
        ],
        "installation": [
            _checklist_item("charger_mounted", "Laddbox monterad"),
            _checklist_item("cabling_completed", "Kabeldragning genomförd"),
            _checklist_item("load_balancing_configured", "Lastbalansering konfigurerad"),
        ],
        "commissioning": [
            _checklist_item("charging_test_passed", "Laddtest godkänt"),
            _checklist_item("app_pairing_verified", "App/konto verifierat med kund"),
        ],
        "handover": [
            _checklist_item("customer_walkthrough_done", "Genomgång med kund genomförd"),
            _checklist_item("documentation_collected", "Dokumentation och bilder insamlade"),
            _checklist_item("ready_for_invoice", "Underlag redo för fakturering"),
        ],
    },
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_operations_workspace() -> dict:
    return {
        "customer": {
            "name": None,
            "phone": None,
            "email": None,
        },
        "property": {
            "address": None,
            "property_type": None,
            "access_notes": None,
        },
        "project": {
            "project_code": None,
            "name": None,
            "status": "intake",
            "technician": None,
            "installation_type": None,
        },
        "work_order": {
            "status": "new",
            "scheduled_start_at": None,
            "scheduled_end_at": None,
            "technician": None,
        },
        "checklists": {
            phase: [dict(item) for item in items]
            for phase, items in _INSTALLER_CHECKLIST_TEMPLATES["general"].items()
        },
        "documentation": {
            "before_images": [],
            "after_images": [],
            "documents": [],
        },
        "delivery_package": {
            "status": "not_started",
            "items": [],
            "sent_at": None,
            "recipient_email": None,
        },
        "timeline": [],
        "internal_notes": [],
        "tasks": [],
        "attachments": [],
    }


def _merge_operations_workspace(data: dict | None) -> dict:
    """Merge user data into v1 operations defaults without clobbering shape."""
    merged = _default_operations_workspace()
    if not isinstance(data, dict):
        return merged

    for key, value in data.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key].update(value)
        elif key in ("timeline", "internal_notes", "tasks", "attachments") and isinstance(value, list):
            merged[key] = value
        elif key in merged:
            merged[key] = value
        else:
            # Keep unknown keys for forward compatibility.
            merged[key] = value
    return merged


def _apply_operations_workspace_patch(current: dict, patch: dict | None) -> dict:
    """Apply a partial update without dropping nested workspace keys."""
    merged = _merge_operations_workspace(current)
    if not isinstance(patch, dict):
        return merged
    for key, value in patch.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return merged


def _build_installer_checklists(installation_type: str | None = None) -> dict:
    template_key = (installation_type or "general").strip().lower() or "general"
    template = _INSTALLER_CHECKLIST_TEMPLATES.get(template_key, _INSTALLER_CHECKLIST_TEMPLATES["general"])
    return {
        phase: [dict(item) for item in items]
        for phase, items in template.items()
    }


def _merge_checklist_templates(existing: dict, template: dict, *, replace: bool = False) -> dict:
    if replace:
        return {
            phase: [dict(item) for item in items]
            for phase, items in template.items()
        }

    merged = {
        phase: list(existing.get(phase) or [])
        for phase in _INSTALLER_CHECKLIST_TEMPLATES["general"].keys()
    }
    for phase, items in template.items():
        by_id = {
            item.get("id"): item
            for item in merged.get(phase, [])
            if isinstance(item, dict) and item.get("id")
        }
        for item in items:
            if item["id"] not in by_id:
                merged.setdefault(phase, []).append(dict(item))
    return merged


def _validate_operations_workspace_shape(workspace: dict) -> None:
    work_order = workspace.get("work_order") or {}
    wo_status = work_order.get("status")
    if wo_status and wo_status not in _VALID_WORK_ORDER_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid work_order.status '{wo_status}'. Valid: {sorted(_VALID_WORK_ORDER_STATUSES)}",
        )

    project = workspace.get("project") or {}
    project_status = project.get("status")
    if project_status and project_status not in _VALID_PROJECT_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid project.status '{project_status}'. Valid: {sorted(_VALID_PROJECT_STATUSES)}",
        )

    delivery = workspace.get("delivery_package") or {}
    delivery_status = delivery.get("status")
    if delivery_status and delivery_status not in _VALID_DELIVERY_PACKAGE_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Invalid delivery_package.status '{delivery_status}'. "
                f"Valid: {sorted(_VALID_DELIVERY_PACKAGE_STATUSES)}"
            ),
        )

    tasks = workspace.get("tasks") or []
    if isinstance(tasks, list):
        for idx, task in enumerate(tasks):
            if not isinstance(task, dict):
                continue
            task_status = task.get("status")
            if task_status and task_status not in _VALID_TASK_STATUSES:
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid tasks[{idx}].status '{task_status}'. Valid: {sorted(_VALID_TASK_STATUSES)}",
                )


def _get_case_record_for_operations(db: Session, tenant_id: str, job_id: str) -> JobRecord:
    r = (
        db.query(JobRecord)
        .filter(JobRecord.job_id == job_id, JobRecord.tenant_id == tenant_id)
        .first()
    )
    if r is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return r


def _persist_operations_workspace(r: JobRecord, workspace: dict, db: Session) -> dict:
    _validate_operations_workspace_shape(workspace)
    updated_input = dict(r.input_data or {})
    updated_input["operations_workspace"] = workspace
    r.input_data = updated_input
    db.commit()
    return workspace


class OperationsWorkspaceUpdateRequest(_BaseModel):
    workspace: dict


class OperationsTimelineEventRequest(_BaseModel):
    message: str
    event_type: str = "note"
    metadata: dict | None = None


class OperationsTaskCreateRequest(_BaseModel):
    title: str
    assignee: str | None = None
    due_at: str | None = None


class OperationsAttachmentCreateRequest(_BaseModel):
    name: str
    url: str | None = None
    category: str = "document"


class OperationsChecklistUpdateRequest(_BaseModel):
    checklist: str
    item_id: str
    label: str | None = None
    done: bool = True
    note: str | None = None


class OperationsChecklistTemplateRequest(_BaseModel):
    installation_type: str | None = None
    replace: bool = False


class OperationsDocumentationCreateRequest(_BaseModel):
    bucket: str
    name: str
    url: str | None = None
    note: str | None = None
    taken_at: str | None = None


class DeliveryPackageUpdateRequest(_BaseModel):
    status: str
    recipient_email: str | None = None
    items: list[dict] | None = None


@app.get("/cases/{job_id}/operations")
def get_case_operations_workspace(
    job_id: str,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Return case-level operations/project workspace for installer workflows."""
    r = _get_case_record_for_operations(db, tenant_id, job_id)
    workspace = _merge_operations_workspace((r.input_data or {}).get("operations_workspace"))
    return {"job_id": job_id, "workspace": workspace}


@app.put("/cases/{job_id}/operations")
def put_case_operations_workspace(
    job_id: str,
    body: OperationsWorkspaceUpdateRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """
    Merge and persist operations workspace v1.

    Used for work order status, project context, installer checklists, and
    delivery package preparation in a single tenant-scoped case record.
    """
    r = _get_case_record_for_operations(db, tenant_id, job_id)
    current = _merge_operations_workspace((r.input_data or {}).get("operations_workspace"))
    merged = _apply_operations_workspace_patch(current, body.workspace)
    saved = _persist_operations_workspace(r, merged, db)
    return {"status": "ok", "job_id": job_id, "workspace": saved}


@app.post("/cases/{job_id}/operations/timeline")
def add_case_operations_timeline_event(
    job_id: str,
    body: OperationsTimelineEventRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Append a timeline event for project/work-order traceability."""
    r = _get_case_record_for_operations(db, tenant_id, job_id)
    workspace = _merge_operations_workspace((r.input_data or {}).get("operations_workspace"))
    timeline = list(workspace.get("timeline") or [])
    timeline.append(
        {
            "id": str(uuid4()),
            "created_at": _utc_now_iso(),
            "event_type": body.event_type,
            "message": body.message,
            "metadata": body.metadata or {},
        }
    )
    workspace["timeline"] = timeline
    saved = _persist_operations_workspace(r, workspace, db)
    return {"status": "ok", "job_id": job_id, "timeline_count": len(saved["timeline"])}


@app.post("/cases/{job_id}/operations/tasks")
def add_case_operations_task(
    job_id: str,
    body: OperationsTaskCreateRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Add an installer task under the case operations workspace."""
    r = _get_case_record_for_operations(db, tenant_id, job_id)
    workspace = _merge_operations_workspace((r.input_data or {}).get("operations_workspace"))
    tasks = list(workspace.get("tasks") or [])
    tasks.append(
        {
            "id": str(uuid4()),
            "title": body.title,
            "assignee": body.assignee,
            "status": "todo",
            "due_at": body.due_at,
            "created_at": _utc_now_iso(),
        }
    )
    workspace["tasks"] = tasks
    saved = _persist_operations_workspace(r, workspace, db)
    return {"status": "ok", "job_id": job_id, "tasks_count": len(saved["tasks"])}


@app.post("/cases/{job_id}/operations/attachments")
def add_case_operations_attachment(
    job_id: str,
    body: OperationsAttachmentCreateRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Add document/photo attachment metadata to the case workspace."""
    r = _get_case_record_for_operations(db, tenant_id, job_id)
    workspace = _merge_operations_workspace((r.input_data or {}).get("operations_workspace"))
    attachments = list(workspace.get("attachments") or [])
    attachments.append(
        {
            "id": str(uuid4()),
            "name": body.name,
            "url": body.url,
            "category": body.category,
            "created_at": _utc_now_iso(),
        }
    )
    workspace["attachments"] = attachments
    saved = _persist_operations_workspace(r, workspace, db)
    return {"status": "ok", "job_id": job_id, "attachments_count": len(saved["attachments"])}


@app.patch("/cases/{job_id}/operations/checklists")
def update_case_operations_checklist(
    job_id: str,
    body: OperationsChecklistUpdateRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Upsert/toggle checklist item state for installation phases."""
    r = _get_case_record_for_operations(db, tenant_id, job_id)
    workspace = _merge_operations_workspace((r.input_data or {}).get("operations_workspace"))
    checklists = workspace.get("checklists") or {}
    if body.checklist not in checklists:
        raise HTTPException(status_code=422, detail=f"Unknown checklist '{body.checklist}'")

    entries = list(checklists.get(body.checklist) or [])
    found = False
    for item in entries:
        if item.get("id") == body.item_id:
            item["done"] = body.done
            if body.note is not None:
                item["note"] = body.note
            item["updated_at"] = _utc_now_iso()
            found = True
            break
    if not found:
        entries.append(
            {
                "id": body.item_id,
                "label": body.label or body.item_id,
                "done": body.done,
                "note": body.note,
                "updated_at": _utc_now_iso(),
            }
        )
    checklists[body.checklist] = entries
    workspace["checklists"] = checklists
    saved = _persist_operations_workspace(r, workspace, db)
    return {"status": "ok", "job_id": job_id, "checklists": saved["checklists"]}


@app.post("/cases/{job_id}/operations/checklists/template")
def apply_case_operations_checklist_template(
    job_id: str,
    body: OperationsChecklistTemplateRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Seed installer phase checklists for a project type without external side effects."""
    r = _get_case_record_for_operations(db, tenant_id, job_id)
    workspace = _merge_operations_workspace((r.input_data or {}).get("operations_workspace"))
    installation_type = body.installation_type or (workspace.get("project") or {}).get("installation_type") or "general"
    template = _build_installer_checklists(installation_type)
    workspace["checklists"] = _merge_checklist_templates(
        workspace.get("checklists") or {},
        template,
        replace=body.replace,
    )
    project = dict(workspace.get("project") or {})
    project["installation_type"] = installation_type
    workspace["project"] = project
    saved = _persist_operations_workspace(r, workspace, db)
    return {
        "status": "ok",
        "job_id": job_id,
        "installation_type": installation_type,
        "checklists": saved["checklists"],
    }


@app.post("/cases/{job_id}/operations/documentation")
def add_case_operations_documentation(
    job_id: str,
    body: OperationsDocumentationCreateRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Add before/after photo or document metadata to the installer documentation flow."""
    if body.bucket not in _VALID_DOCUMENTATION_BUCKETS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown documentation bucket '{body.bucket}'. Valid: {sorted(_VALID_DOCUMENTATION_BUCKETS)}",
        )

    r = _get_case_record_for_operations(db, tenant_id, job_id)
    workspace = _merge_operations_workspace((r.input_data or {}).get("operations_workspace"))
    documentation = dict(workspace.get("documentation") or {})
    bucket_items = list(documentation.get(body.bucket) or [])
    bucket_items.append(
        {
            "id": str(uuid4()),
            "name": body.name,
            "url": body.url,
            "note": body.note,
            "taken_at": body.taken_at,
            "created_at": _utc_now_iso(),
        }
    )
    documentation[body.bucket] = bucket_items
    workspace["documentation"] = documentation
    saved = _persist_operations_workspace(r, workspace, db)
    return {
        "status": "ok",
        "job_id": job_id,
        "bucket": body.bucket,
        "count": len(saved["documentation"][body.bucket]),
        "documentation": saved["documentation"],
    }


@app.post("/cases/{job_id}/operations/delivery-package")
def update_case_delivery_package(
    job_id: str,
    body: DeliveryPackageUpdateRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Update delivery package status/items for installation handover."""
    if body.status not in _VALID_DELIVERY_PACKAGE_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Invalid delivery package status '{body.status}'. "
                f"Valid: {sorted(_VALID_DELIVERY_PACKAGE_STATUSES)}"
            ),
        )

    r = _get_case_record_for_operations(db, tenant_id, job_id)
    workspace = _merge_operations_workspace((r.input_data or {}).get("operations_workspace"))
    delivery = dict(workspace.get("delivery_package") or {})
    delivery["status"] = body.status
    if body.recipient_email is not None:
        delivery["recipient_email"] = body.recipient_email
    if body.items is not None:
        delivery["items"] = body.items
    if body.status == "sent":
        delivery["sent_at"] = _utc_now_iso()
    workspace["delivery_package"] = delivery
    saved = _persist_operations_workspace(r, workspace, db)
    return {"status": "ok", "job_id": job_id, "delivery_package": saved["delivery_package"]}


# ---------------------------------------------------------------------------
# Follow-up engine (P1)
# ---------------------------------------------------------------------------

_FOLLOWUP_STATE_MAP = {
    "new":                     "new",
    "contacted":               "replied_waiting_customer",
    "waiting_for_customer":    "replied_waiting_customer",
    "info_received":           "waiting_internal",
    "offer_ready":             "quote_sent",
    "offer_sent":              "quote_sent",
    "followup_due":            "followup_due",
    "won":                     "closed_won",
    "lost":                    "closed_lost",
    "resolved":                "closed_won",
    "closed":                  "closed_won",
    "pending":                 "new",
    "processing":              "waiting_internal",
    "awaiting_approval":       "waiting_internal",
    "manual_review":           "waiting_internal",
    "completed":               "closed_won",
    "failed":                  "closed_lost",
}

_FOLLOWUP_NEXT_ACTION = {
    "new":                    "Svara kunden — ingen kontakt etablerad",
    "replied_waiting_customer": "Invänta svar — kunden är kontaktad",
    "waiting_internal":       "Intern åtgärd krävs — fyll i uppgifter eller godkänn",
    "quote_sent":             "Följ upp om offert — vänta eller påminn kunden",
    "followup_due":           "Påminnelse förfallen — kontakta kunden nu",
    "closed_won":             "Avslutat med framgång — inga fler åtgärder",
    "closed_lost":            "Avslutat utan affär — kan arkiveras",
}


@app.get("/cases/{job_id}/followup")
def get_case_followup(
    job_id: str,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Return follow-up state, suggested reply, and pending approval for a case.

    Supports P1: productive follow-up engine with actionable reminders,
    suggested reply text, and direct link to approval queue.
    """
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

    # Resolve lead/support status
    lead_payload: dict = {}
    support_payload: dict = {}
    for entry in history:
        proc = entry.get("processor", "")
        p = (entry.get("result") or {}).get("payload") or {}
        if proc == "lead_analyzer_processor":
            lead_payload = p
        elif proc == "support_analyzer_processor":
            support_payload = p

    raw_lead_status = (
        inp.get("lead_status")
        or lead_payload.get("lead_status")
        or inp.get("support_status")
        or support_payload.get("support_status")
        or r.status
        or "new"
    )
    followup_state = _FOLLOWUP_STATE_MAP.get(raw_lead_status, "new")
    next_action_text = _FOLLOWUP_NEXT_ACTION.get(followup_state, "Kontrollera ärendet")

    # Suggested reply: prefer pre-generated ai suggestions
    action_dispatch_payload: dict = {}
    for entry in reversed(history):
        if entry.get("processor") == "action_dispatch_processor":
            action_dispatch_payload = (entry.get("result") or {}).get("payload") or {}
            break

    ai_suggestions = action_dispatch_payload.get("ai_reply_suggestions") or []
    offer_draft    = lead_payload.get("offer_draft") or {}
    support_draft  = support_payload.get("support_response_draft") or {}
    generated_q    = lead_payload.get("generated_question_message") or support_payload.get("support_generated_question_message")

    suggested_reply: str | None = None
    if ai_suggestions:
        first = ai_suggestions[0] if isinstance(ai_suggestions[0], str) else (ai_suggestions[0].get("body") or ai_suggestions[0].get("text") or "")
        suggested_reply = first
    elif generated_q:
        suggested_reply = generated_q if isinstance(generated_q, str) else generated_q.get("message_body")
    elif isinstance(offer_draft, dict) and offer_draft.get("body"):
        suggested_reply = offer_draft["body"]
    elif isinstance(support_draft, dict) and support_draft.get("body"):
        suggested_reply = support_draft["body"]
    elif isinstance(support_draft, str) and support_draft:
        suggested_reply = support_draft

    # Latest customer message
    msgs = inp.get("conversation_messages") or []
    last_customer_msg: dict | None = None
    for msg in reversed(msgs):
        if (msg.get("source") or "") not in ("system", "outgoing"):
            last_customer_msg = {
                "body":    msg.get("message_text") or msg.get("body"),
                "subject": msg.get("subject"),
                "received_at": msg.get("received_at") or msg.get("created_at"),
            }
            break

    # Pending approval for this job
    pending_approval = (
        db.query(ApprovalRequestRecord)
        .filter(
            ApprovalRequestRecord.tenant_id == tenant_id,
            ApprovalRequestRecord.job_id == job_id,
            ApprovalRequestRecord.state == "pending",
        )
        .order_by(ApprovalRequestRecord.requested_at.desc())
        .first()
    )

    pending_approval_id = pending_approval.approval_id if pending_approval else None
    pending_approval_type = pending_approval.next_on_approve if pending_approval else None

    # Customer contact info
    sender = inp.get("sender") or {}
    customer_email = sender.get("email") or inp.get("sender_email")
    customer_name  = sender.get("name") or inp.get("sender_name")
    subject        = inp.get("subject") or inp.get("latest_message_subject")

    return {
        "job_id":                 job_id,
        "job_type":               r.job_type,
        "job_status":             r.status,
        "followup_state":         followup_state,
        "raw_status":             raw_lead_status,
        "next_action":            next_action_text,
        "suggested_reply":        suggested_reply,
        "last_customer_message":  last_customer_msg,
        "customer_email":         customer_email,
        "customer_name":          customer_name,
        "subject":                subject,
        "pending_approval_id":    pending_approval_id,
        "pending_approval_type":  pending_approval_type,
    }


# ---------------------------------------------------------------------------
# Project Closeout Packet (P3)
# ---------------------------------------------------------------------------

@app.get("/cases/{job_id}/closeout")
def get_case_closeout(
    job_id: str,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Return a project closeout packet: customer summary, internal status, materials, docs, finance.

    Supports P3: 'Sammanställ projekt' — from messy job to finished underlag.
    Read-only, deterministic, no side effects.
    """
    from app.repositories.postgres.action_execution_models import ActionExecutionRecord
    from app.insights.engine import _is_underlag_ready
    from app.domain.integrations.models import IntegrationEvent

    r = (
        db.query(JobRecord)
        .filter(JobRecord.job_id == job_id, JobRecord.tenant_id == tenant_id)
        .first()
    )
    if r is None:
        raise HTTPException(status_code=404, detail="Case not found")

    inp   = r.input_data or {}
    result = r.result or {}
    history = result.get("processor_history") or []
    workspace = _merge_operations_workspace(inp.get("operations_workspace"))

    # --- source payloads ---
    lead_payload:    dict = {}
    support_payload: dict = {}
    for entry in history:
        proc = entry.get("processor", "")
        p = (entry.get("result") or {}).get("payload") or {}
        if proc == "lead_analyzer_processor":
            lead_payload = p
        elif proc == "support_analyzer_processor":
            support_payload = p

    # --- core fields ---
    sender   = inp.get("sender") or {}
    customer_name = (
        sender.get("name") or inp.get("sender_name")
        or (lead_payload.get("lead_analysis") or {}).get("customer_name")
        or "Okänd kund"
    )
    customer_email = sender.get("email") or inp.get("sender_email")
    subject        = inp.get("subject") or inp.get("latest_message_subject") or "Okänt ärende"

    # --- operations workspace data ---
    project    = workspace.get("project") or {}
    work_order = workspace.get("work_order") or {}
    checklist  = workspace.get("checklist") or {}
    docs       = workspace.get("documentation") or {}
    finance    = workspace.get("finance") or {}
    delivery   = workspace.get("delivery_package") or {}
    tasks      = workspace.get("tasks") or []
    timeline   = workspace.get("timeline") or []

    # Checklist progress
    items = checklist.get("items") or []
    checked = sum(1 for i in items if i.get("checked"))

    # Documentation counts
    doc_count = sum(len(v or []) for v in docs.values() if isinstance(v, list))
    photos     = len(docs.get("photos") or [])
    receipts   = len(docs.get("receipts") or [])

    # Material and time lines
    material_lines = _extract_material_lines(inp)
    time_entries   = finance.get("time_entries") or []
    total_material = sum(
        float(m.get("total_price") or m.get("unit_price", 0)) for m in material_lines
        if isinstance(m.get("total_price") or m.get("unit_price"), (int, float))
    )
    total_hours = sum(
        float(t.get("hours", 0)) for t in time_entries
        if isinstance(t.get("hours"), (int, float))
    )

    # Missing fields list
    missing: list[str] = []
    if not customer_email:
        missing.append("Kund-e-post")
    if not customer_name or customer_name == "Okänd kund":
        missing.append("Kundnamn")
    if work_order.get("status") not in ("completed", "cancelled"):
        missing.append("Arbetsorder ej avslutad")
    if delivery.get("status") not in ("ready", "sent"):
        missing.append("Leveransdokumentation ej redo")
    if not material_lines:
        missing.append("Material-rader (för underlag)")
    if doc_count == 0:
        missing.append("Bilder/dokument")

    # Fortnox export status
    fortnox_events = (
        db.query(IntegrationEvent)
        .filter(
            IntegrationEvent.tenant_id == tenant_id,
            IntegrationEvent.job_id == job_id,
            IntegrationEvent.integration_type.ilike("%fortnox%"),
        )
        .all()
    )
    exported_ids = {row.job_id for row in fortnox_events if row.job_id}
    finance_ready = _is_underlag_ready(r, workspace, exported_ids)
    fortnox_exported = job_id in exported_ids

    # Customer-friendly summary
    wo_status_sv = {
        "new": "Nytt", "in_progress": "Pågår", "on_hold": "Pausat",
        "completed": "Avslutat", "blocked": "Blockerat", "cancelled": "Avbrutet",
    }.get(work_order.get("status") or "", work_order.get("status") or "Okänd status")

    customer_summary_lines = [
        f"Ärende: {subject}",
        f"Kund: {customer_name}",
        f"Status: {wo_status_sv}",
    ]
    if checked and items:
        customer_summary_lines.append(f"Slutfört: {checked} av {len(items)} punkter")
    if delivery.get("status") == "sent":
        customer_summary_lines.append("Leveransdokumentation: Skickad")
    elif delivery.get("status") == "ready":
        customer_summary_lines.append("Leveransdokumentation: Redo att skickas")
    customer_summary = "\n".join(customer_summary_lines)

    # Internal summary
    internal_summary_lines = [
        f"Jobbtyp: {r.job_type or 'okänd'}",
        f"Jobbstatus: {r.status}",
        f"Arbetsorderstatus: {work_order.get('status') or '—'}",
        f"Projektstatus: {project.get('status') or '—'}",
        f"Checklista: {checked}/{len(items)} klara",
        f"Dokument: {doc_count} (foton: {photos}, kvitton: {receipts})",
        f"Material-rader: {len(material_lines)}, total: {total_material:.0f} kr",
        f"Tid: {total_hours:.1f} timmar",
        f"Underlag redo: {'Ja' if finance_ready else 'Nej'}",
        f"Fortnox exporterat: {'Ja' if fortnox_exported else 'Nej'}",
    ]
    if missing:
        internal_summary_lines.append(f"Saknas: {', '.join(missing)}")
    internal_summary = "\n".join(internal_summary_lines)

    return {
        "job_id":             job_id,
        "job_type":           r.job_type,
        "job_status":         r.status,
        "customer_name":      customer_name,
        "customer_email":     customer_email,
        "subject":            subject,
        "customer_summary":   customer_summary,
        "internal_summary":   internal_summary,
        "work_order_status":  work_order.get("status"),
        "project_status":     project.get("status"),
        "checklist": {
            "total":   len(items),
            "checked": checked,
        },
        "documentation": {
            "total":    doc_count,
            "photos":   photos,
            "receipts": receipts,
        },
        "material_lines":   material_lines,
        "time_entries":     time_entries,
        "total_material_sek": total_material,
        "total_hours":        total_hours,
        "timeline_events":  timeline[-10:] if timeline else [],
        "delivery_status":  delivery.get("status"),
        "finance_ready":    finance_ready,
        "fortnox_exported": fortnox_exported,
        "missing_fields":   missing,
        "risks":            [f"Saknas: {m}" for m in missing],
    }


# ---------------------------------------------------------------------------
# Finance export status (P4)
# ---------------------------------------------------------------------------

@app.get("/cases/{job_id}/finance/export-status")
def get_case_finance_export_status(
    job_id: str,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Return Fortnox export status for a case.

    Supports P4 finance hardening: operators can see export state and history
    without navigating away from the case.
    """
    from app.domain.integrations.models import IntegrationEvent
    from app.insights.engine import _is_underlag_ready

    r = (
        db.query(JobRecord)
        .filter(JobRecord.job_id == job_id, JobRecord.tenant_id == tenant_id)
        .first()
    )
    if r is None:
        raise HTTPException(status_code=404, detail="Case not found")

    inp = r.input_data or {}
    workspace = _merge_operations_workspace(inp.get("operations_workspace"))

    fortnox_events = (
        db.query(IntegrationEvent)
        .filter(
            IntegrationEvent.tenant_id == tenant_id,
            IntegrationEvent.job_id == job_id,
            IntegrationEvent.integration_type.ilike("%fortnox%"),
        )
        .order_by(IntegrationEvent.created_at.desc())
        .all()
    )

    exported_ids = {e.job_id for e in fortnox_events if e.job_id}
    finance_ready = _is_underlag_ready(r, workspace, exported_ids)
    exported      = job_id in exported_ids

    events_out = [
        {
            "event_id":         str(e.id) if hasattr(e, "id") else None,
            "integration_type": e.integration_type,
            "status":           e.status if hasattr(e, "status") else None,
            "created_at":       e.created_at.isoformat() if e.created_at else None,
        }
        for e in fortnox_events[:10]
    ]

    material_lines = _extract_material_lines(inp)
    finance_data   = workspace.get("finance") or {}

    return {
        "job_id":          job_id,
        "finance_ready":   finance_ready,
        "exported":        exported,
        "export_count":    len(fortnox_events),
        "export_events":   events_out,
        "material_lines":  material_lines,
        "time_entries":    finance_data.get("time_entries") or [],
        "preview_url":     f"/finance/invoices/{job_id}/fortnox/preview",
        "export_url":      f"/finance/invoices/{job_id}/fortnox/export",
        "draft_url":       f"/finance/invoices/{job_id}/draft",
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
        "fortnox": {
            "customers": [],
            "articles": [],
            "invoices": [],
            "summary": {
                "customers_scanned": 0,
                "articles_scanned": 0,
                "invoices_scanned": 0,
                "customer_emails_detected": 0,
                "invoice_statuses_detected": [],
            },
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
# Fortnox Customer + Invoice Actions
# ---------------------------------------------------------------------------

def _get_fortnox_client_or_raise():
    """Build a FortnoxClient from settings or raise 503."""
    from app.integrations.fortnox.client import FortnoxClient
    s = get_settings()
    token  = (getattr(s, "FORTNOX_ACCESS_TOKEN",  "") or "").strip()
    secret = (getattr(s, "FORTNOX_CLIENT_SECRET", "") or "").strip()
    api_url = (getattr(s, "FORTNOX_API_URL", "") or "https://api.fortnox.se/3").strip()
    if not token or not secret:
        raise HTTPException(
            status_code=503,
            detail="Fortnox credentials not configured (FORTNOX_ACCESS_TOKEN and FORTNOX_CLIENT_SECRET required).",
        )
    return FortnoxClient(access_token=token, client_secret=secret, api_url=api_url)


@app.post("/integrations/fortnox/customers/lookup")
def fortnox_customer_lookup(
    body: dict,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """
    Look up a Fortnox customer by email or name.

    Body: {"email": "..."} or {"name": "..."} (at least one required).
    Returns the first matching customer dict, or null when not found.
    """
    email = (body.get("email") or "").strip()
    name  = (body.get("name")  or "").strip()
    if not email and not name:
        raise HTTPException(status_code=422, detail="Provide 'email' or 'name' to search.")
    client = _get_fortnox_client_or_raise()
    customer = None
    if email:
        customer = client.find_customer_by_email(email)
    if customer is None and name:
        customer = client.find_customer_by_name(name)
    return {"customer": customer}


@app.post("/integrations/fortnox/customers/create")
def fortnox_customer_create(
    body: dict,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """
    Create a Fortnox customer.

    Body fields: name (required), email, organisation_number, phone.
    Returns the created customer object from Fortnox.
    """
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="'name' is required to create a customer.")
    payload: dict = {"Name": name}
    if body.get("email"):
        payload["Email"] = body["email"]
    if body.get("organisation_number"):
        payload["OrganisationNumber"] = body["organisation_number"]
    if body.get("phone"):
        payload["Phone1"] = body["phone"]
    client = _get_fortnox_client_or_raise()
    result = client.create_customer(payload)
    return {"customer": result.get("Customer") or result}


@app.post("/integrations/fortnox/invoices/lookup")
def fortnox_invoice_lookup(
    body: dict,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """
    Look up Fortnox invoices by document_number or customer_number.

    Body: {"document_number": "..."} or {"customer_number": "...", "limit": 10}.
    Returns {"invoice": {...}} or {"invoices": [...]} depending on lookup type.
    """
    doc_number  = (body.get("document_number")  or "").strip()
    cust_number = (body.get("customer_number")  or "").strip()
    if not doc_number and not cust_number:
        raise HTTPException(status_code=422, detail="Provide 'document_number' or 'customer_number'.")
    client = _get_fortnox_client_or_raise()
    if doc_number:
        invoice = client.find_invoice_by_document_number(doc_number)
        return {"invoice": invoice}
    limit = min(int(body.get("limit") or 10), 50)
    invoices = client.find_recent_invoices_by_customer(cust_number, limit=limit)
    return {"invoices": invoices}


def _extract_invoice_payload_from_history(record: JobRecord) -> dict:
    history = record.processor_history or []
    for entry in reversed(history):
        if entry.get("processor") != "invoice_processor":
            continue
        payload = (entry.get("result") or {}).get("payload") or {}
        if isinstance(payload, dict):
            return payload.get("invoice_data") or {}
    return {}


def _get_invoice_record_or_422(db: Session, tenant_id: str, job_id: str) -> JobRecord:
    record = (
        db.query(JobRecord)
        .filter(JobRecord.job_id == job_id, JobRecord.tenant_id == tenant_id)
        .first()
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if record.job_type != "invoice":
        raise HTTPException(status_code=422, detail="Job is not an invoice")
    return record


class FinanceFortnoxExportRequest(_BaseModel):
    create_customer_if_missing: bool = True
    approval_required: bool = True
    dry_run: bool = False


def _finance_fortnox_idempotency_key(tenant_id: str, job_id: str) -> str:
    return f"finance:fortnox_export:{tenant_id}:{job_id}"


def _get_successful_finance_export_event(db: Session, tenant_id: str, job_id: str):
    from app.domain.integrations.models import IntegrationEvent

    key = _finance_fortnox_idempotency_key(tenant_id, job_id)
    event = IntegrationRepository(db).get_by_idempotency_key(key)
    if isinstance(event, IntegrationEvent) and event.status == "success":
        return event
    return None


def _finance_event_response(event) -> dict:
    payload = event.payload or {}
    return {
        "status": "already_exported",
        "integration_event_id": event.id,
        "idempotency_key": event.idempotency_key,
        "draft": payload.get("draft"),
        "invoice": (payload.get("result") or {}).get("invoice"),
        "customer_number": (payload.get("result") or {}).get("customer_number"),
        "customer_created": (payload.get("result") or {}).get("customer_created", False),
    }


def _record_finance_fortnox_event(
    db: Session,
    *,
    tenant_id: str,
    job_id: str,
    draft: dict,
    export_payload: dict,
    result: dict,
):
    from app.domain.integrations.models import IntegrationEvent

    record = IntegrationEvent(
        tenant_id=tenant_id,
        job_id=job_id,
        integration_type="fortnox",
        payload={
            "action": "finance_fortnox_export",
            "request": export_payload,
            "draft": draft,
            "result": result,
        },
        status="success",
        attempts=1,
        idempotency_key=_finance_fortnox_idempotency_key(tenant_id, job_id),
    )
    repo = IntegrationRepository(db)
    try:
        return repo.create(record)
    except Exception:
        db.rollback()
        return repo.get_by_idempotency_key(record.idempotency_key)


def _execute_finance_fortnox_export(
    *,
    db: Session,
    tenant_id: str,
    job_id: str,
    draft: dict,
    export_payload: dict,
    create_customer_if_missing: bool,
) -> dict:
    existing_event = _get_successful_finance_export_event(db, tenant_id, job_id)
    if existing_event is not None:
        return _finance_event_response(existing_event)

    client = _get_fortnox_client_or_raise()
    customer_payload = export_payload["customer"]
    invoice_payload = dict(export_payload["invoice"])
    customer_number = customer_payload.get("CustomerNumber")

    existing_customer = None
    if draft.get("supplier_email"):
        existing_customer = client.find_customer_by_email(draft["supplier_email"])
    if existing_customer is None and draft.get("supplier_name"):
        existing_customer = client.find_customer_by_name(draft["supplier_name"])

    customer_created = False
    if existing_customer is None and create_customer_if_missing:
        created = client.create_customer(customer_payload)
        existing_customer = created.get("Customer") or created
        customer_created = True

    if existing_customer is None:
        raise HTTPException(
            status_code=422,
            detail="Fortnox customer not found and create_customer_if_missing=false.",
        )

    customer_number = existing_customer.get("CustomerNumber") or customer_number
    invoice_payload["CustomerNumber"] = customer_number
    invoice_result = client.create_invoice(invoice_payload)
    result = {
        "customer_created": customer_created,
        "customer_number": customer_number,
        "invoice": invoice_result.get("Invoice") or invoice_result,
    }
    event = _record_finance_fortnox_event(
        db,
        tenant_id=tenant_id,
        job_id=job_id,
        draft=draft,
        export_payload={**export_payload, "invoice": invoice_payload},
        result=result,
    )

    return {
        "status": "exported",
        "customer_created": customer_created,
        "customer_number": customer_number,
        "draft": draft,
        "invoice": result["invoice"],
        "integration_event_id": getattr(event, "id", None),
        "idempotency_key": _finance_fortnox_idempotency_key(tenant_id, job_id),
    }


def _create_finance_fortnox_approval(
    *,
    db: Session,
    tenant_id: str,
    job_id: str,
    draft: dict,
    export_payload: dict,
    create_customer_if_missing: bool,
):
    approval_payload = {
        "approval_id": f"finance_fortnox_export:{tenant_id}:{job_id}",
        "state": "pending",
        "channel": "dashboard",
        "title": f"Fortnox-export: {draft.get('invoice_number') or job_id}",
        "summary": (
            f"Väntande export av fakturaunderlag till Fortnox "
            f"({draft.get('amount_inc_vat') or draft.get('amount_ex_vat') or 0} "
            f"{draft.get('currency', 'SEK')})."
        ),
        "requested_by": "system",
        "requested_at": _utc_now_iso(),
        "next_on_approve": "finance_fortnox_export",
        "next_on_reject": "manual_review",
        "finance_context": {
            "system": "fortnox",
            "job_id": job_id,
            "idempotency_key": _finance_fortnox_idempotency_key(tenant_id, job_id),
        },
    }
    delivery_payload = {
        "draft": draft,
        "fortnox_payload": export_payload,
        "create_customer_if_missing": create_customer_if_missing,
    }
    return ApprovalRequestRepository.upsert_from_payload(
        db=db,
        tenant_id=tenant_id,
        job_id=job_id,
        job_type="invoice",
        approval_request=approval_payload,
        delivery_payload=delivery_payload,
    )


def _resolve_finance_fortnox_approval(
    *,
    db: Session,
    approval,
    approved: bool,
    actor: str | None,
    note: str | None,
) -> dict:
    payload = dict(approval.request_payload or {})
    new_state = "approved" if approved else "rejected"
    payload["state"] = new_state
    payload["resolved_at"] = _utc_now_iso()
    payload["resolved_by"] = actor or "operator"
    payload["resolution_note"] = note

    result = None
    if approved:
        delivery = approval.delivery_payload or {}
        result = _execute_finance_fortnox_export(
            db=db,
            tenant_id=approval.tenant_id,
            job_id=approval.job_id,
            draft=delivery.get("draft") or {},
            export_payload=delivery.get("fortnox_payload") or {},
            create_customer_if_missing=bool(delivery.get("create_customer_if_missing", True)),
        )

    ApprovalRequestRepository.upsert_from_payload(
        db=db,
        tenant_id=approval.tenant_id,
        job_id=approval.job_id,
        job_type=approval.job_type,
        approval_request=payload,
        delivery_payload=approval.delivery_payload,
    )

    return {
        "approval_id": approval.approval_id,
        "status": new_state,
        "job_id": approval.job_id,
        "export_result": result,
    }


def _extract_material_lines(input_data: dict) -> list[dict]:
    """Extract normalised material line items from operations_workspace.finance."""
    workspace = (input_data or {}).get("operations_workspace") or {}
    finance = workspace.get("finance") or {}
    raw_items = finance.get("material_costs") or finance.get("materials") or []
    if not isinstance(raw_items, list):
        return []
    lines: list[dict] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        desc = item.get("description") or item.get("name") or "Material"
        qty = item.get("quantity") or 1
        unit_price = (
            item.get("unit_price")
            or item.get("price")
            or item.get("cost")
            or item.get("amount")
            or item.get("total")
            or 0
        )
        try:
            qty = float(qty)
            unit_price = float(unit_price)
        except (TypeError, ValueError):
            qty = 1.0
            unit_price = 0.0
        total = round(qty * unit_price, 2)
        vat_rate = item.get("vat_rate", 25)
        lines.append({
            "description": str(desc),
            "quantity": qty,
            "unit_price": unit_price,
            "total": total,
            "vat_rate": vat_rate,
        })
    return lines


@app.post("/finance/invoices/{job_id}/draft")
def build_finance_invoice_draft(
    job_id: str,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Build deterministic pre-accounting draft from an invoice job."""
    from app.finance.pre_accounting import build_invoice_draft

    record = _get_invoice_record_or_422(db, tenant_id, job_id)
    invoice_payload = _extract_invoice_payload_from_history(record)
    draft = build_invoice_draft(
        tenant_id=tenant_id,
        job_id=job_id,
        input_data=record.input_data or {},
        invoice_payload=invoice_payload,
    )
    material_lines = _extract_material_lines(record.input_data or {})
    return {"status": "ok", "draft": draft, "material_lines": material_lines}


@app.post("/finance/invoices/{job_id}/fortnox/preview")
def finance_fortnox_export_preview(
    job_id: str,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Create a controlled Fortnox export preview payload, no external writes."""
    from app.finance.pre_accounting import build_fortnox_export_payload, build_invoice_draft

    record = _get_invoice_record_or_422(db, tenant_id, job_id)
    invoice_payload = _extract_invoice_payload_from_history(record)
    draft = build_invoice_draft(
        tenant_id=tenant_id,
        job_id=job_id,
        input_data=record.input_data or {},
        invoice_payload=invoice_payload,
    )
    export_payload = build_fortnox_export_payload(draft)
    return {
        "status": "preview",
        "draft": draft,
        "fortnox_payload": export_payload,
    }


@app.post("/finance/invoices/{job_id}/fortnox/export")
def finance_fortnox_export(
    job_id: str,
    body: FinanceFortnoxExportRequest | None = None,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """
    Controlled write to Fortnox for pre-accounting invoice drafts.

    Flow:
    1) Build deterministic draft from invoice job
    2) Build export payload
    3) Optionally create customer when missing
    4) Create invoice in Fortnox
    """
    from app.finance.pre_accounting import build_fortnox_export_payload, build_invoice_draft

    req = body or FinanceFortnoxExportRequest()
    record = _get_invoice_record_or_422(db, tenant_id, job_id)
    invoice_payload = _extract_invoice_payload_from_history(record)
    draft = build_invoice_draft(
        tenant_id=tenant_id,
        job_id=job_id,
        input_data=record.input_data or {},
        invoice_payload=invoice_payload,
    )
    export_payload = build_fortnox_export_payload(draft)

    if req.dry_run:
        return {
            "status": "dry_run",
            "draft": draft,
            "fortnox_payload": export_payload,
        }

    existing_event = _get_successful_finance_export_event(db, tenant_id, job_id)
    if existing_event is not None:
        return _finance_event_response(existing_event)

    if req.approval_required:
        approval = _create_finance_fortnox_approval(
            db=db,
            tenant_id=tenant_id,
            job_id=job_id,
            draft=draft,
            export_payload=export_payload,
            create_customer_if_missing=req.create_customer_if_missing,
        )
        return {
            "status": "approval_required",
            "approval_id": approval.approval_id,
            "draft": draft,
            "fortnox_payload": export_payload,
            "message": "Fortnox export queued for approval. No external write was performed.",
        }

    return _execute_finance_fortnox_export(
        db=db,
        tenant_id=tenant_id,
        job_id=job_id,
        draft=draft,
        export_payload=export_payload,
        create_customer_if_missing=req.create_customer_if_missing,
    )


@app.get("/finance/projects/{job_id}/profitability")
def finance_project_profitability(
    job_id: str,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Return deterministic project profitability from case operations data."""
    from app.finance.pre_accounting import build_invoice_draft, build_project_profitability

    record = (
        db.query(JobRecord)
        .filter(JobRecord.job_id == job_id, JobRecord.tenant_id == tenant_id)
        .first()
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found")

    invoice_draft = None
    if record.job_type == "invoice":
        invoice_draft = build_invoice_draft(
            tenant_id=tenant_id,
            job_id=job_id,
            input_data=record.input_data or {},
            invoice_payload=_extract_invoice_payload_from_history(record),
        )

    profitability = build_project_profitability(
        tenant_id=tenant_id,
        job_id=job_id,
        input_data=record.input_data or {},
        invoice_draft=invoice_draft,
    )
    return {"status": "ok", "profitability": profitability}


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


# ---------------------------------------------------------------------------
# Lead Status + Operational Actions
# ---------------------------------------------------------------------------

_VALID_LEAD_STATUSES = {
    "new", "waiting_for_customer", "info_received",
    "offer_ready", "offer_sent", "won", "lost", "manual_review",
}


class LeadStatusRequest(_BaseModel):
    status: str


@app.patch("/jobs/{job_id}/lead-status")
def set_lead_status(
    job_id: str,
    body: LeadStatusRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Set operational lead_status on a lead job (stored in input_data)."""
    if body.status not in _VALID_LEAD_STATUSES:
        raise HTTPException(status_code=422, detail=f"Invalid status. Valid: {sorted(_VALID_LEAD_STATUSES)}")

    r = (
        db.query(JobRecord)
        .filter(JobRecord.job_id == job_id, JobRecord.tenant_id == tenant_id)
        .first()
    )
    if r is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if r.job_type != "lead":
        raise HTTPException(status_code=422, detail="Job is not a lead")

    updated_input = dict(r.input_data or {})
    updated_input["lead_status"] = body.status
    r.input_data = updated_input
    db.commit()
    return {"job_id": job_id, "lead_status": body.status}


@app.post("/jobs/{job_id}/lead-regenerate")
def regenerate_lead_analysis(
    job_id: str,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Re-run lead analysis for a job without re-running the full pipeline.

    Useful after operator manual edits or customer reply merging.
    Updates the lead_analyzer_processor entry in processor_history in-place.
    """
    from app.domain.workflows.models import Job as _Job
    from app.lead.analyzer import analyze_lead
    from app.lead.missing_info import compute_missing_info
    from app.lead.next_action import decide_next_action
    from app.lead.offer_draft import build_offer_draft
    from app.lead.question_generator import generate_question_message, should_ask_questions
    from app.lead.scorer import score_lead
    from app.lead.tenant_context import load_tenant_context
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
    from app.repositories.postgres.job_repository import JobRepository

    r = (
        db.query(JobRecord)
        .filter(JobRecord.job_id == job_id, JobRecord.tenant_id == tenant_id)
        .first()
    )
    if r is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if r.job_type != "lead":
        raise HTTPException(status_code=422, detail="Job is not a lead")

    job = JobRepository._to_domain(r)
    input_data = job.input_data or {}

    # Load entities from existing history
    entities: dict = {}
    for entry in job.processor_history:
        p = (entry.get("result") or {}).get("payload") or {}
        if "entities" in p:
            entities = p["entities"]
            break

    # Load tenant context
    settings = TenantConfigRepository.get_settings(db, tenant_id)
    tenant_ctx = load_tenant_context(tenant_id, settings)

    # Re-run analysis
    auto_actions = dict(r.result or {})  # best effort
    analysis = analyze_lead(input_data, entities, tenant_ctx)
    missing_info = compute_missing_info(analysis.lead_type, input_data, entities, tenant_ctx)
    lead_score = score_lead(analysis, missing_info, entities, input_data, tenant_ctx)
    next_action = decide_next_action(lead_score, missing_info, {}, tenant_ctx)

    question_message: str | None = None
    if should_ask_questions(missing_info.completeness_score):
        question_message = generate_question_message(missing_info.missing_fields, tenant_ctx, analysis.lead_type)

    offer_draft_dict: dict | None = None
    draft = build_offer_draft(analysis, missing_info, entities, tenant_ctx)
    if draft:
        offer_draft_dict = draft.to_dict()

    new_payload: dict = {
        "processor_name": "lead_analyzer_processor",
        "lead_analysis": analysis.to_dict(),
        "missing_info": missing_info.to_dict(),
        "lead_score": lead_score.to_dict(),
        "next_action": next_action,
        "confidence": analysis.confidence,
        "regenerated": True,
    }
    if question_message:
        new_payload["generated_question_message"] = question_message
    if offer_draft_dict:
        new_payload["offer_draft"] = offer_draft_dict

    new_result = {
        "status": "completed",
        "summary": f"Lead re-analyserad: score={lead_score.score}, next_action={next_action}.",
        "requires_human_review": next_action in ("manual_review", "approval_required"),
        "payload": new_payload,
    }

    # Replace or append lead_analyzer_processor in history
    history = list(job.processor_history)
    replaced = False
    for i, entry in enumerate(history):
        if entry.get("processor") == "lead_analyzer_processor":
            history[i] = {"processor": "lead_analyzer_processor", "result": new_result}
            replaced = True
            break
    if not replaced:
        history.append({"processor": "lead_analyzer_processor", "result": new_result})

    job.processor_history = history
    job.result = new_result
    JobRepository.update_job(db, job)

    return {
        "job_id": job_id,
        "lead_analysis": analysis.to_dict(),
        "missing_info": missing_info.to_dict(),
        "lead_score": lead_score.to_dict(),
        "next_action": next_action,
        "generated_question_message": question_message,
        "offer_draft": offer_draft_dict,
    }


# ---------------------------------------------------------------------------
# Support Status + Operational Actions
# ---------------------------------------------------------------------------

_VALID_SUPPORT_STATUSES = {
    "new", "waiting_for_customer", "in_review",
    "escalated", "solution_suggested", "resolved", "closed",
}


class SupportStatusRequest(_BaseModel):
    status: str


@app.patch("/jobs/{job_id}/support-status")
def set_support_status(
    job_id: str,
    body: SupportStatusRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Set operational support_status on a customer_inquiry job (stored in input_data)."""
    if body.status not in _VALID_SUPPORT_STATUSES:
        raise HTTPException(status_code=422, detail=f"Invalid status. Valid: {sorted(_VALID_SUPPORT_STATUSES)}")

    r = (
        db.query(JobRecord)
        .filter(JobRecord.job_id == job_id, JobRecord.tenant_id == tenant_id)
        .first()
    )
    if r is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if r.job_type != "customer_inquiry":
        raise HTTPException(status_code=422, detail="Job is not a customer_inquiry")

    updated_input = dict(r.input_data or {})
    updated_input["support_status"] = body.status
    r.input_data = updated_input
    db.commit()
    return {"job_id": job_id, "support_status": body.status}


@app.post("/jobs/{job_id}/support-regenerate")
def regenerate_support_analysis(
    job_id: str,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """Re-run support analysis for a job without re-running the full pipeline.

    Useful after operator manual edits or customer reply merging.
    Updates the support_analyzer_processor entry in processor_history in-place.
    No external writes — only update_job().
    """
    from app.support.analyzer import analyze_support
    from app.support.missing_info import compute_support_missing_info
    from app.support.next_action import decide_support_next_action
    from app.support.prioritizer import prioritize_support
    from app.support.question_generator import generate_support_question_message, should_ask_questions
    from app.support.response_draft import build_support_response_draft
    from app.support.tenant_context import load_support_context
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
    from app.repositories.postgres.job_repository import JobRepository

    r = (
        db.query(JobRecord)
        .filter(JobRecord.job_id == job_id, JobRecord.tenant_id == tenant_id)
        .first()
    )
    if r is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if r.job_type != "customer_inquiry":
        raise HTTPException(status_code=422, detail="Job is not a customer_inquiry")

    job = JobRepository._to_domain(r)
    input_data = job.input_data or {}

    # Load entities from existing history
    entities: dict = {}
    for entry in job.processor_history:
        p = (entry.get("result") or {}).get("payload") or {}
        if "entities" in p:
            entities = p["entities"]
            break

    # Load tenant context
    settings = TenantConfigRepository.get_settings(db, tenant_id)
    tenant_ctx = load_support_context(tenant_id, settings)

    # Re-run analysis
    analysis = analyze_support(input_data, entities, tenant_ctx)
    missing_info = compute_support_missing_info(analysis.ticket_type, input_data, entities, tenant_ctx)
    priority = prioritize_support(analysis, missing_info, entities, input_data, tenant_ctx)
    next_action = decide_support_next_action(analysis, missing_info, priority, {}, tenant_ctx)

    question_message: str | None = None
    if should_ask_questions(missing_info.completeness_score):
        question_message = generate_support_question_message(
            missing_info.missing_fields,
            ticket_type=analysis.ticket_type,
            tenant_ctx=tenant_ctx,
            input_data=input_data,
        )

    response_draft = build_support_response_draft(analysis, missing_info, priority, entities, input_data, tenant_ctx)

    support_status = input_data.get("support_status") or _infer_support_status_from_action(next_action.action, input_data)

    new_payload: dict = {
        "processor_name": "support_analyzer_processor",
        "support_analysis": analysis.to_dict(),
        "support_missing_info": missing_info.to_dict(),
        "support_priority": priority.to_dict(),
        "support_next_action": next_action.to_dict(),
        "support_response_draft": response_draft.to_dict(),
        "support_status": support_status,
        "confidence": analysis.confidence,
        "regenerated": True,
    }
    if question_message:
        new_payload["support_generated_question_message"] = question_message

    new_result = {
        "status": "completed",
        "summary": f"Support re-analyserat: score={priority.score}, next_action={next_action.action}.",
        "requires_human_review": next_action.action in ("escalate", "manual_review", "create_task"),
        "payload": new_payload,
    }

    # Replace or append support_analyzer_processor in history
    history = list(job.processor_history)
    replaced = False
    for i, entry in enumerate(history):
        if entry.get("processor") == "support_analyzer_processor":
            history[i] = {"processor": "support_analyzer_processor", "result": new_result}
            replaced = True
            break
    if not replaced:
        history.append({"processor": "support_analyzer_processor", "result": new_result})

    job.processor_history = history
    job.result = new_result
    JobRepository.update_job(db, job)

    return {
        "job_id": job_id,
        "support_analysis": analysis.to_dict(),
        "support_missing_info": missing_info.to_dict(),
        "support_priority": priority.to_dict(),
        "support_next_action": next_action.to_dict(),
        "support_response_draft": response_draft.to_dict(),
        "support_status": support_status,
        "support_generated_question_message": question_message,
    }


def _infer_support_status_from_action(action: str, input_data: dict) -> str:
    """Infer support_status from next_action when not operator-set."""
    if input_data.get("conversation_messages") and len(input_data["conversation_messages"]) > 1:
        if action in ("suggest_solution", "ready_to_dispatch"):
            return "solution_suggested"
        return "in_review"
    if action == "ask_for_info":
        return "new"
    if action == "escalate":
        return "escalated"
    if action in ("suggest_solution", "ready_to_dispatch"):
        return "solution_suggested"
    return "new"


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


@app.get("/onboarding/status")
def onboarding_status(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """
    Tenant-scoped onboarding readiness checklist.

    Returns 8 deterministic steps (complete/incomplete/warning), an overall status
    (not_started/in_progress/ready), and a completion score.
    No external API calls are made.
    """
    from app.onboarding.readiness import get_onboarding_status
    s = get_settings()
    return get_onboarding_status(db=db, tenant_id=tenant_id, app_settings=s)


class _OnboardingTestLeadRequest(_BaseModel):
    company_name: str = "Testbolag AB"
    customer_name: str = "Test Lead"
    email: str = "test@onboarding.example.com"
    message: str = "Testlead skapad via onboarding-fliken för att verifiera pipelineflödet."


@app.post("/onboarding/test-lead", status_code=201)
def onboarding_test_lead(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
    request: _OnboardingTestLeadRequest | None = None,
):
    """
    Create a safe synthetic lead job for the tenant to verify the pipeline.

    Uses the same deterministic pipeline as POST /verify/{tenant_id}.
    Does not send external email; respects the tenant's dispatch policy.
    Response includes job_id and final status.
    """
    from app.domain.workflows.enums import JobType

    if request is None:
        request = _OnboardingTestLeadRequest()
    job_type_value = "lead"

    try:
        job_type_enum = JobType(job_type_value)
    except ValueError:
        raise HTTPException(status_code=400, detail="lead is not a recognised job type.")

    input_data = {
        "subject": f"Testlead – {request.company_name}",
        "message_text": request.message,
        "sender": {
            "name":  request.customer_name,
            "email": request.email,
            "phone": None,
        },
        "onboarding_test": True,
    }

    job = Job(
        tenant_id=tenant_id,
        job_type=job_type_enum,
        input_data=input_data,
    )

    set_current_tenant(tenant_id)
    saved_job = JobRepository.create_job(db, job)
    processed_job = _run_verification_pipeline(saved_job, job_type_value, db)

    create_audit_event(
        db=db,
        tenant_id=tenant_id,
        category="workflow",
        action="onboarding_test_lead_created",
        status="success",
        details={"job_id": processed_job.job_id, "job_type": job_type_value},
    )

    return {
        "job_id":   processed_job.job_id,
        "tenant_id": processed_job.tenant_id,
        "job_type": job_type_value,
        "status":   processed_job.status.value if hasattr(processed_job.status, "value") else str(processed_job.status),
        "message":  "Testlead skapad och processad via deterministisk pipeline.",
    }


class _DemoSeedRequest(_BaseModel):
    include_types: list[str] | None = None


def _seed_demo_jobs(
    *,
    request: _DemoSeedRequest | None = None,
    db: Session,
    tenant_id: str,
) -> dict:
    import copy
    from app.domain.workflows.enums import JobType
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

    ctrl_settings = TenantConfigRepository.get_settings(db, tenant_id)
    if not _is_demo_mode_enabled(ctrl_settings):
        raise HTTPException(
            status_code=400,
            detail="Enable demo_mode in the control panel before seeding demo data.",
        )

    tenant_cfg = get_tenant_config(tenant_id, db=db)
    enabled_types = set(tenant_cfg.get("enabled_job_types") or [])
    requested_types = request.include_types if request and request.include_types is not None else None
    candidate_types = requested_types or [t for t in _VERIFICATION_SUPPORTED_TYPES if t in enabled_types]

    unsupported = [t for t in candidate_types if t not in _VERIFICATION_SUPPORTED_TYPES]
    if unsupported:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported demo job type(s): {', '.join(unsupported)}",
        )

    demo_types = [t for t in candidate_types if t in enabled_types]
    if not demo_types:
        supported = ", ".join(_VERIFICATION_SUPPORTED_TYPES)
        raise HTTPException(
            status_code=400,
            detail=f"No enabled demo job types found. Enable at least one of: {supported}.",
        )

    created_jobs = []
    set_current_tenant(tenant_id)
    for job_type_value in demo_types:
        try:
            job_type_enum = JobType(job_type_value)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Job type '{job_type_value}' is not a recognised job type.",
            )

        input_data = copy.deepcopy(_VERIFICATION_PAYLOADS[job_type_value])
        input_data["demo_mode"] = True
        input_data["demo_seed"] = True
        input_data["source"] = {"system": "demo_seed", "synthetic": True}

        saved_job = JobRepository.create_job(
            db,
            Job(
                tenant_id=tenant_id,
                job_type=job_type_enum,
                input_data=input_data,
            ),
        )
        processed_job = _run_verification_pipeline(saved_job, job_type_value, db)
        created_jobs.append({
            "job_id": processed_job.job_id,
            "job_type": job_type_value,
            "status": processed_job.status.value if hasattr(processed_job.status, "value") else str(processed_job.status),
        })

    create_audit_event(
        db=db,
        tenant_id=tenant_id,
        category="demo",
        action="demo_seed_created",
        status="success",
        details={"created_jobs": created_jobs},
    )

    return {
        "tenant_id": tenant_id,
        "demo_mode": True,
        "created_jobs": created_jobs,
        "message": f"Skapade {len(created_jobs)} syntetiska demoärenden utan externa writes.",
    }


@app.post("/demo/seed", status_code=201)
def demo_seed(
    request: _DemoSeedRequest | None = None,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """
    Create safe synthetic demo jobs for the current tenant.

    The endpoint is gated by control-panel demo_mode and uses the deterministic
    verification pipeline only. It never reads Gmail, marks messages, sends
    emails, or dispatches external integration writes.
    """
    return _seed_demo_jobs(request=request, db=db, tenant_id=tenant_id)


@app.post("/admin/tenants/{tenant_id}/demo/seed", status_code=201)
def admin_demo_seed(
    tenant_id: str,
    request: _DemoSeedRequest | None = None,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_api_key),
):
    """Admin variant of demo seed for the explicitly selected tenant."""
    return _seed_demo_jobs(request=request, db=db, tenant_id=tenant_id)


@app.get("/integrations/health")
def integration_health(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """
    Tenant-scoped integration health report.

    Returns health status for Gmail and Monday based on internal signals only
    (env config, scanner results, dispatch events, audit events).
    No external API calls are made. No secret values appear in the response.
    """
    from app.health.integration_health import get_integration_health
    s = get_settings()
    return get_integration_health(db=db, tenant_id=tenant_id, app_settings=s)


@app.get("/pilot/readiness")
def pilot_readiness(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
):
    """
    Tenant-scoped pilot/production readiness report.

    Evaluates 11 deterministic checks from existing platform state.
    No external API calls. No secrets in response.
    Returns overall_status: ready | almost_ready | not_ready.
    """
    from app.health.production_readiness import get_pilot_readiness
    s = get_settings()
    return get_pilot_readiness(db=db, tenant_id=tenant_id, app_settings=s)


# ---------------------------------------------------------------------------
# Admin Customer Provisioning
# ---------------------------------------------------------------------------

_VALID_TENANT_STATUSES = {"active", "inactive"}

_SLUG_RE = __import__("re").compile(r"^[a-z0-9_-]{2,64}$")


class AdminTenantCreateRequest(_BaseModel):
    name: str
    slug: str
    enabled_job_types: list[str] = []
    allowed_integrations: list[str] = []
    auto_actions: dict[str, bool] = {}


class AdminTenantStatusRequest(_BaseModel):
    status: str


@app.post("/admin/tenants", status_code=201)
def admin_create_tenant(
    body: AdminTenantCreateRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_api_key),
):
    """Provision a new tenant with a generated API key.

    The api_key field in the response is shown exactly once and never stored
    in plaintext. Store it immediately — it cannot be retrieved again.
    Requires X-Admin-API-Key.
    """
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
    from app.repositories.postgres.tenant_api_key_repository import TenantApiKeyRepository

    if not _SLUG_RE.match(body.slug):
        raise HTTPException(
            status_code=422,
            detail="slug must be 2–64 lowercase alphanumeric chars, hyphens, or underscores.",
        )

    # Derive a deterministic tenant_id from slug
    tenant_id = "T_" + body.slug.upper().replace("-", "_")

    if TenantConfigRepository.get(db, tenant_id) is not None:
        raise HTTPException(status_code=409, detail=f"Tenant '{tenant_id}' already exists.")

    TenantConfigRepository.upsert(
        db=db,
        tenant_id=tenant_id,
        name=body.name,
        slug=body.slug,
        status="active",
        enabled_job_types=body.enabled_job_types,
        allowed_integrations=body.allowed_integrations,
        auto_actions=body.auto_actions,
    )

    raw_key, _ = TenantApiKeyRepository.create_key(db, tenant_id)

    try:
        create_audit_event(
            db=db,
            tenant_id=tenant_id,
            category="tenant_management",
            action="tenant_created",
            status="success",
            details={"name": body.name, "slug": body.slug,
                     "enabled_job_types": body.enabled_job_types,
                     "allowed_integrations": body.allowed_integrations},
        )
    except Exception:
        pass

    return {
        "tenant_id": tenant_id,
        "name": body.name,
        "slug": body.slug,
        "api_key": raw_key,
        "status": "active",
    }


@app.get("/admin/tenants")
def admin_list_tenants(
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_api_key),
):
    """List all tenants. Never returns API keys.

    Requires X-Admin-API-Key.
    """
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
    records = TenantConfigRepository.list_all(db)
    return {
        "items": [TenantConfigRepository.to_dict(r) for r in records],
        "total": len(records),
    }


@app.post("/admin/tenants/{tenant_id}/rotate-key", status_code=200)
def admin_rotate_tenant_key(
    tenant_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_api_key),
):
    """Revoke all existing API keys for the tenant and issue a new one.

    The new api_key is shown exactly once. Store it immediately.
    Requires X-Admin-API-Key.
    """
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
    from app.repositories.postgres.tenant_api_key_repository import TenantApiKeyRepository

    if TenantConfigRepository.get(db, tenant_id) is None:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found.")

    raw_key, _ = TenantApiKeyRepository.rotate_key(db, tenant_id)

    try:
        create_audit_event(
            db=db,
            tenant_id=tenant_id,
            category="tenant_management",
            action="api_key_rotated",
            status="success",
            details={},
        )
    except Exception:
        pass

    return {"tenant_id": tenant_id, "api_key": raw_key}


@app.patch("/admin/tenants/{tenant_id}/status", status_code=200)
def admin_set_tenant_status(
    tenant_id: str,
    body: AdminTenantStatusRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_api_key),
):
    """Set a tenant's status to 'active' or 'inactive'.

    Inactive tenants are rejected at auth with 403.
    Requires X-Admin-API-Key.
    """
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

    if body.status not in _VALID_TENANT_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status. Valid values: {sorted(_VALID_TENANT_STATUSES)}",
        )
    if TenantConfigRepository.get(db, tenant_id) is None:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found.")

    TenantConfigRepository.upsert(db=db, tenant_id=tenant_id, status=body.status)

    try:
        create_audit_event(
            db=db,
            tenant_id=tenant_id,
            category="tenant_management",
            action="status_changed",
            status="success",
            details={"new_status": body.status},
        )
    except Exception:
        pass

    return {"tenant_id": tenant_id, "status": body.status}


@app.get("/admin/tenants/overview")
def admin_tenants_overview(
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_api_key),
):
    """
    Super Admin: aggregate health overview for ALL tenants in the DB.

    Read-only. No external API calls. No secrets in response.

    Requires X-Admin-API-Key header matching ADMIN_API_KEY env var.
    Tenant X-API-Key keys are NOT accepted. Returns 401 if key is
    missing, wrong, or ADMIN_API_KEY is not configured.
    """
    from app.admin.super_admin import get_super_admin_overview
    s = get_settings()
    return get_super_admin_overview(db=db, app_settings=s)


@app.get("/admin/usage/analytics")
def admin_usage_analytics(
    range: str = "30d",
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_api_key),
):
    """
    Super Admin: ready-to-market usage analytics across all tenants.

    Read-only. No external API calls. No secrets in response.
    Requires X-Admin-API-Key.
    """
    from app.analytics.usage import get_usage_analytics
    return get_usage_analytics(db=db, range_=range)


@app.get("/admin/audit-events")
def admin_list_audit_events(
    tenant_id_filter: str | None = None,
    category: str | None = None,
    status_filter: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_api_key),
):
    """
    Super Admin: browse audit events across all tenants.

    Optional query params:
      tenant_id_filter — filter to a specific tenant
      category         — filter by event category
      status_filter    — filter by event status (e.g. 'failed')

    Read-only. No secrets in response. Requires X-Admin-API-Key.
    """
    from app.repositories.postgres.audit_models import AuditEventRecord

    q = db.query(AuditEventRecord)
    if tenant_id_filter:
        q = q.filter(AuditEventRecord.tenant_id == tenant_id_filter)
    if category:
        q = q.filter(AuditEventRecord.category == category)
    if status_filter:
        q = q.filter(AuditEventRecord.status == status_filter)

    total = q.count()
    records = (
        q.order_by(AuditEventRecord.created_at.desc())
        .offset(offset)
        .limit(min(limit, 500))
        .all()
    )

    items = [
        {
            "event_id":  r.event_id,
            "tenant_id": r.tenant_id,
            "category":  r.category,
            "action":    r.action,
            "status":    r.status,
            "details":   r.details or {},
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in records
    ]
    return {"items": items, "total": total, "offset": offset, "limit": min(limit, 500)}


@app.get("/admin/operations/needs-help")
def admin_operations_needs_help(
    limit: int = 50,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_api_key),
):
    """
    Super Admin: unified operational triage queue across all tenants.

    Returns actionable rows ordered by severity (critical → high → medium),
    covering integration errors, failed jobs, stale approvals, failed
    dispatches, and scheduler/OAuth failures.

    Read-only. No external API calls. No secrets in response.
    Requires X-Admin-API-Key.
    """
    from app.admin.operations_triage import get_admin_needs_help
    s = get_settings()
    return get_admin_needs_help(db=db, app_settings=s, limit=min(limit, 200))


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