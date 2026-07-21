"""Operator onboarding service (Kapitel 9 slice 1)."""

from __future__ import annotations

import copy
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.admin.onboarding.activation_plan import build_activation_plan
from app.admin.onboarding.errors import (
    OnboardingAuditError,
    OnboardingConflictError,
    OnboardingNotFoundError,
    OnboardingStaleActivationPlanError,
    OnboardingStaleReadinessError,
    OnboardingValidationError,
    OnboardingVersionConflictError,
)
from app.admin.onboarding.integration_verification import IntegrationVerificationStore
from app.admin.onboarding.models import OPEN_SESSION_STATUSES
from app.admin.onboarding.readiness import compute_readiness
from app.admin.onboarding.registries import (
    INTEGRATIONS,
    PRODUCT_CAPABILITIES,
    capability_requires_api_key,
    preset_snapshot,
    resolve_modules_to_tenant_config,
    resolve_preset,
)
from app.admin.onboarding.registry_schemas import ActivationPlanResponse
from app.admin.onboarding.runtime_evaluation import validate_runtime_dependencies
from app.admin.onboarding.repository import OnboardingRepository
from app.admin.onboarding.schemas import (
    ActivateResponse,
    ApiKeyCreateResponse,
    OnboardingListResponse,
    OnboardingSessionResponse,
    OnboardingStepStateResponse,
    ReadinessResponse,
    StepDetailResponse,
)
from app.admin.onboarding.steps import (
    evaluate_data_start_step,
    evaluate_integrations_step,
    evaluate_routing_step,
    evaluate_service_profile_step,
    tenant_has_api_key,
)
from app.admin.onboarding.effective_config import materialize_slice2a_config, materialize_slice2b_config
from app.admin.integrations.selection_materialize import materialize_selections_config
from app.admin.integrations.selection_sync import sync_allowed_integrations_from_selections
from app.admin.onboarding.tenant_id import generate_tenant_id, normalize_slug, slug_exists
from app.core.admin_session import OperatorIdentity
from app.core.settings import Settings
from app.admin.onboarding.audit_events import (
    EXTERNAL_ROUTING_MATERIALIZED,
    INTEGRATION_CONFIG_MATERIALIZED,
    emit_onboarding_audit,
)
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.tenant_config_models import TenantConfigRecord

logger = logging.getLogger(__name__)

_ONBOARDING_AUDIT_CATEGORY = "onboarding"
_WRITE_ROLES = frozenset({"operations", "admin"})
_ADMIN_ROLES = frozenset({"admin"})
_READONLY_STEP_KEYS = frozenset()
_WRITABLE_SLICE2A_STEPS = frozenset({"service_profile", "routing", "data_start"})
_WRITABLE_SLICE2B_STEPS = frozenset({"integrations"})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sanitize_audit_details(details: dict[str, Any]) -> dict[str, Any]:
    blocked = {
        "password",
        "api_key",
        "token",
        "secret",
        "credential",
        "access_token",
        "refresh_token",
        "client_secret",
        "key_hash",
    }
    clean: dict[str, Any] = {}
    for key, value in details.items():
        lower = key.lower()
        if any(part in lower for part in blocked):
            continue
        if isinstance(value, dict):
            clean[key] = _sanitize_audit_details(value)
        else:
            clean[key] = value
    return clean


def _add_audit_event_no_commit(
    db: Session,
    *,
    tenant_id: str,
    action: str,
    status: str,
    details: dict[str, Any],
) -> AuditEventRecord:
    record = AuditEventRecord(
        event_id=str(uuid4()),
        tenant_id=tenant_id,
        category=_ONBOARDING_AUDIT_CATEGORY,
        action=action,
        status=status,
        details=_sanitize_audit_details(details),
        created_at=_utcnow(),
    )
    db.add(record)
    return record


def _operator_audit_details(
    operator: OperatorIdentity,
    *,
    session_id: str,
    reason: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    details: dict[str, Any] = {
        "operator_id": operator["id"],
        "operator_display_name": operator["display_name"],
        "operator_role": operator["role"],
        "session_id": session_id,
    }
    if reason:
        details["reason"] = reason
    if extra:
        details.update(extra)
    return details


def _get_tenant(db: Session, tenant_id: str) -> TenantConfigRecord:
    tenant = db.query(TenantConfigRecord).filter(TenantConfigRecord.tenant_id == tenant_id).first()
    if tenant is None:
        raise OnboardingNotFoundError(f"Tenant '{tenant_id}' not found.")
    return tenant


def _get_session_or_raise(db: Session, session_id: str):
    session = OnboardingRepository.get_session(db, session_id)
    if session is None:
        raise OnboardingNotFoundError(f"Onboarding session '{session_id}' not found.")
    return session


def _ensure_writable_session(session) -> None:
    if session.status not in OPEN_SESSION_STATUSES:
        raise OnboardingConflictError(
            f"Session is not open (status={session.status}).",
            code="session_closed",
        )


def _lock_session(db: Session, session_id: str, expected_version: int):
    session = OnboardingRepository.get_session_for_update(db, session_id)
    if session is None:
        raise OnboardingNotFoundError(f"Onboarding session '{session_id}' not found.")
    if session.version != expected_version:
        raise OnboardingVersionConflictError()
    return session


def _safe_defaults_settings() -> dict[str, Any]:
    return {
        "automation": {
            "demo_mode": True,
            "leads_enabled": False,
            "support_enabled": False,
            "invoices_enabled": False,
            "followups_enabled": False,
        },
        "scheduler": {"run_mode": "paused"},
    }


def _step_response_from_eval(step_key: str, evaluation: dict[str, Any]) -> OnboardingStepStateResponse:
    return OnboardingStepStateResponse(
        step_key=step_key,
        step_status=evaluation["step_status"],
        verification_level=evaluation["verification_level"],
        blocking_issues=[],
        warnings=[],
        blocks_activation=bool(evaluation.get("blocks_activation")),
        read_only=True,
        read_only_reason=evaluation.get("read_only_reason"),
    )


def _sync_readonly_step_states(
    db: Session,
    *,
    session_id: str,
    tenant: TenantConfigRecord,
    settings: Settings,
    operator_id: str,
) -> None:
    modules_draft = OnboardingRepository.get_draft(db, session_id, "modules")
    modules_payload = (modules_draft.payload if modules_draft else {}) or {}
    evaluation = evaluate_integrations_step(
        db,
        modules_draft=modules_payload,
        tenant=tenant,
        settings=settings,
        session_id=session_id,
    )
    OnboardingRepository.set_step_state(
        db,
        session_id=session_id,
        step_key="integrations",
        step_status=evaluation["step_status"],
        verification_level=evaluation["verification_level"],
        operator_id=operator_id,
    )


def _build_session_response(
    db: Session,
    session,
    *,
    settings: Settings,
) -> OnboardingSessionResponse:
    tenant = _get_tenant(db, session.tenant_id)
    identity = OnboardingRepository.get_draft(db, session.id, "identity")
    identity_payload = (identity.payload if identity else {}) or {}

    step_states = {s.step_key: s for s in OnboardingRepository.get_step_states(db, session.id)}
    modules_record = OnboardingRepository.get_draft(db, session.id, "modules")
    modules_payload = (modules_record.payload if modules_record else {}) or {}
    automation_record = OnboardingRepository.get_draft(db, session.id, "automation")
    automation_payload = (automation_record.payload if automation_record else {}) or {}

    capabilities = list(modules_payload.get("capabilities") or [])
    integrations = list(modules_payload.get("integrations") or [])
    preset_key = automation_payload.get("preset_key")
    preset_version_raw = automation_payload.get("preset_version")
    preset_version = int(preset_version_raw) if preset_version_raw is not None else None
    legacy_capability_keys = [c for c in capabilities if c not in PRODUCT_CAPABILITIES]
    legacy_preset = bool(
        preset_key
        and resolve_preset(str(preset_key), preset_version or 1) is None
    )

    sp_record = OnboardingRepository.get_draft(db, session.id, "service_profile")
    routing_record = OnboardingRepository.get_draft(db, session.id, "routing")
    data_start_record = OnboardingRepository.get_draft(db, session.id, "data_start")
    sp_payload = sp_record.payload if sp_record else None
    routing_payload = routing_record.payload if routing_record else None
    data_start_payload = data_start_record.payload if data_start_record else None

    slice2b_evals = {
        "integrations": evaluate_integrations_step(
            db,
            modules_draft=modules_payload,
            tenant=tenant,
            settings=settings,
            session_id=session.id,
        ),
    }

    readonly_evals: dict = {}

    slice2a_evals = {
        "service_profile": evaluate_service_profile_step(
            modules_draft=modules_payload,
            tenant=tenant,
            service_profile_draft=sp_payload,
        ),
        "routing": evaluate_routing_step(
            modules_draft=modules_payload,
            service_profile_draft=sp_payload,
            routing_draft=routing_payload,
        ),
        "data_start": evaluate_data_start_step(
            modules_draft=modules_payload,
            data_start_draft=data_start_payload,
        ),
    }

    steps: list[OnboardingStepStateResponse] = []
    for step_key in (
        "identity",
        "modules",
        "service_profile",
        "automation",
        "routing",
        "integrations",
        "data_start",
        "readiness",
        "review",
    ):
        if step_key in _WRITABLE_SLICE2B_STEPS:
            record = step_states.get(step_key)
            evaluation = slice2b_evals[step_key]
            steps.append(
                OnboardingStepStateResponse(
                    step_key=step_key,
                    step_status=record.step_status if record else evaluation["step_status"],
                    verification_level=(
                        record.verification_level if record else evaluation["verification_level"]
                    ),
                    blocking_issues=record.blocking_issues or [] if record else [],
                    warnings=record.warnings or [] if record else [],
                    blocks_activation=bool(evaluation.get("blocks_activation")),
                    read_only=False,
                )
            )
            continue
        if step_key in _READONLY_STEP_KEYS:
            evaluation = readonly_evals[step_key]
            steps.append(
                OnboardingStepStateResponse(
                    step_key=step_key,
                    step_status=evaluation["step_status"],
                    verification_level=evaluation["verification_level"],
                    blocking_issues=[],
                    warnings=[],
                    blocks_activation=bool(evaluation.get("blocks_activation")),
                    read_only=True,
                    read_only_reason=evaluation.get("read_only_reason"),
                )
            )
            continue
        if step_key in _WRITABLE_SLICE2A_STEPS:
            record = step_states.get(step_key)
            evaluation = slice2a_evals[step_key]
            steps.append(
                OnboardingStepStateResponse(
                    step_key=step_key,
                    step_status=record.step_status if record else evaluation["step_status"],
                    verification_level=(
                        record.verification_level if record else evaluation["verification_level"]
                    ),
                    blocking_issues=record.blocking_issues or [] if record else [],
                    warnings=record.warnings or [] if record else [],
                    blocks_activation=bool(evaluation.get("blocks_activation")),
                    read_only=False,
                )
            )
            continue
        record = step_states.get(step_key)
        if record is None:
            continue
        steps.append(
            OnboardingStepStateResponse(
                step_key=record.step_key,
                step_status=record.step_status,
                verification_level=record.verification_level,
                blocking_issues=record.blocking_issues or [],
                warnings=record.warnings or [],
                blocks_activation=False,
                read_only=False,
            )
        )

    return OnboardingSessionResponse(
        id=session.id,
        tenant_id=session.tenant_id,
        status=session.status,
        current_step=session.current_step,
        version=session.version,
        readiness_check_version=session.readiness_check_version,
        created_at=session.created_at,
        updated_at=session.updated_at,
        activated_at=session.activated_at,
        company_name=identity_payload.get("company_name") or tenant.name,
        slug=identity_payload.get("slug") or tenant.slug,
        industries=list(identity_payload.get("industries") or []),
        capabilities=capabilities,
        integrations=integrations,
        preset_key=str(preset_key) if preset_key else None,
        preset_version=preset_version,
        legacy_capability_keys=legacy_capability_keys,
        legacy_preset=legacy_preset,
        steps=steps,
    )


def list_onboarding_sessions(
    db: Session,
    *,
    open_only: bool = False,
    limit: int = 50,
    settings: Settings,
) -> OnboardingListResponse:
    sessions = OnboardingRepository.list_sessions(db, open_only=open_only, limit=limit)
    return OnboardingListResponse(
        items=[_build_session_response(db, s, settings=settings) for s in sessions]
    )


def create_onboarding_session(
    db: Session,
    *,
    operator: OperatorIdentity,
    company_name: str,
    slug: str,
    org_number: str | None,
    primary_contact: str | None,
    contact_email: str | None,
    phone: str | None,
    timezone: str,
    language: str,
    settings: Settings,
) -> OnboardingSessionResponse:
    if operator["role"] not in _WRITE_ROLES:
        raise OnboardingValidationError("Insufficient role for onboarding create.")

    try:
        normalized_slug = normalize_slug(slug)
    except ValueError as exc:
        raise OnboardingValidationError(str(exc)) from exc

    if slug_exists(db, normalized_slug):
        raise OnboardingConflictError("Slug is already in use.", code="slug_conflict")

    now = _utcnow()
    tenant_id = generate_tenant_id(db)

    try:
        tenant = TenantConfigRecord(
            tenant_id=tenant_id,
            name=company_name.strip(),
            slug=normalized_slug,
            status="inactive",
            enabled_job_types=[],
            allowed_integrations=[],
            auto_actions={},
            settings=_safe_defaults_settings(),
            created_at=now,
            updated_at=now,
        )
        db.add(tenant)
        db.flush()

        session = OnboardingRepository.create_session_record(
            db,
            tenant_id=tenant_id,
            operator_id=operator["id"],
        )

        identity_payload = {
            "company_name": company_name.strip(),
            "slug": normalized_slug,
            "org_number": org_number,
            "primary_contact": primary_contact,
            "contact_email": contact_email,
            "phone": phone,
            "timezone": timezone,
            "language": language,
        }
        OnboardingRepository.upsert_draft(
            db,
            session_id=session.id,
            step_key="identity",
            payload=identity_payload,
        )
        OnboardingRepository.set_step_state(
            db,
            session_id=session.id,
            step_key="identity",
            step_status="completed",
            verification_level="declared",
            operator_id=operator["id"],
        )
        OnboardingRepository.set_step_state(
            db,
            session_id=session.id,
            step_key="modules",
            step_status="not_started",
            verification_level="declared",
            operator_id=operator["id"],
        )
        session.status = "in_progress"
        session.current_step = "modules"

        _add_audit_event_no_commit(
            db,
            tenant_id=tenant_id,
            action="onboarding.session_created",
            status="succeeded",
            details=_operator_audit_details(
                operator,
                session_id=session.id,
                extra={
                    "tenant_id": tenant_id,
                    "slug": normalized_slug,
                    "company_name": company_name.strip(),
                },
            ),
        )
        db.commit()
        db.refresh(session)
    except IntegrityError as exc:
        db.rollback()
        existing = OnboardingRepository.get_open_session_for_tenant(db, tenant_id)
        if existing:
            raise OnboardingConflictError(
                "An open onboarding session already exists for this tenant.",
                code="open_session_exists",
                session_id=existing.id,
            ) from exc
        raise OnboardingConflictError("Could not create onboarding session.") from exc
    except Exception as exc:
        db.rollback()
        logger.exception("onboarding_create_failed")
        if isinstance(exc, (OnboardingConflictError, OnboardingValidationError)):
            raise
        raise OnboardingAuditError("Onboarding session could not be created.") from exc

    return _build_session_response(db, session, settings=settings)


def get_onboarding_session(
    db: Session,
    session_id: str,
    *,
    settings: Settings,
) -> OnboardingSessionResponse:
    session = _get_session_or_raise(db, session_id)
    return _build_session_response(db, session, settings=settings)


def patch_identity(
    db: Session,
    *,
    session_id: str,
    operator: OperatorIdentity,
    payload: dict[str, Any],
    expected_version: int,
    settings: Settings,
) -> OnboardingSessionResponse:
    session = _lock_session(db, session_id, expected_version)
    _ensure_writable_session(session)
    tenant = _get_tenant(db, session.tenant_id)

    draft = OnboardingRepository.get_draft(db, session_id, "identity")
    current = dict((draft.payload if draft else {}) or {})

    for field in (
        "company_name",
        "org_number",
        "primary_contact",
        "contact_email",
        "phone",
        "timezone",
        "language",
        "industries",
    ):
        if field in payload and payload[field] is not None:
            current[field] = payload[field]

    if payload.get("slug") is not None:
        try:
            new_slug = normalize_slug(payload["slug"])
        except ValueError as exc:
            raise OnboardingValidationError(str(exc)) from exc
        if slug_exists(db, new_slug, exclude_tenant_id=tenant.tenant_id):
            raise OnboardingConflictError("Slug is already in use.", code="slug_conflict")
        current["slug"] = new_slug
        tenant.slug = new_slug

    if payload.get("industries") is not None:
        from app.admin.onboarding.industry_registry import validate_industry_keys

        invalid = validate_industry_keys(list(payload.get("industries") or []))
        if invalid:
            raise OnboardingValidationError(f"Unknown industries: {', '.join(invalid)}")
        current["industries"] = list(payload.get("industries") or [])

    if not current.get("company_name"):
        raise OnboardingValidationError("company_name is required.")

    tenant.name = current["company_name"]
    tenant.updated_at = _utcnow()

    OnboardingRepository.upsert_draft(db, session_id=session_id, step_key="identity", payload=current)
    OnboardingRepository.set_step_state(
        db,
        session_id=session_id,
        step_key="identity",
        step_status="completed",
        verification_level="declared",
        operator_id=operator["id"],
    )
    _sync_readonly_step_states(
        db,
        session_id=session_id,
        tenant=tenant,
        settings=settings,
        operator_id=operator["id"],
    )
    OnboardingRepository.bump_version(session, operator["id"])

    _add_audit_event_no_commit(
        db,
        tenant_id=session.tenant_id,
        action="onboarding.identity_updated",
        status="succeeded",
        details=_operator_audit_details(
            operator,
            session_id=session_id,
            extra={"industries": current.get("industries")},
        ),
    )
    try:
        db.commit()
        db.refresh(session)
    except Exception as exc:
        db.rollback()
        raise OnboardingAuditError("Audit could not be recorded.") from exc

    return _build_session_response(db, session, settings=settings)


def patch_modules(
    db: Session,
    *,
    session_id: str,
    operator: OperatorIdentity,
    capabilities: list[str],
    integrations: list[str],
    expected_version: int,
    settings: Settings,
) -> OnboardingSessionResponse:
    session = _lock_session(db, session_id, expected_version)
    _ensure_writable_session(session)
    tenant = _get_tenant(db, session.tenant_id)

    unknown_caps = [c for c in capabilities if c not in PRODUCT_CAPABILITIES]
    if unknown_caps:
        raise OnboardingValidationError(f"Unknown capabilities: {', '.join(unknown_caps)}")

    unknown_integ = [i for i in integrations if i not in INTEGRATIONS]
    if unknown_integ:
        raise OnboardingValidationError(f"Unknown integrations: {', '.join(unknown_integ)}")

    unknown_runtime = validate_runtime_dependencies(capabilities)
    if unknown_runtime:
        raise OnboardingValidationError(
            f"Unknown runtime dependencies: {', '.join(unknown_runtime)}"
        )

    from app.admin.onboarding.orphan_services import detect_orphan_service_profiles

    sp_draft = OnboardingRepository.get_draft(db, session_id, "service_profile")
    sp_payload = (sp_draft.payload if sp_draft else {}) or {}
    identity_draft = OnboardingRepository.get_draft(db, session_id, "identity")
    identity_payload = (identity_draft.payload if identity_draft else {}) or {}
    orphans = detect_orphan_service_profiles(
        selected_profiles=sp_payload.get("selected_profiles") or [],
        capability_keys=capabilities,
        industry_keys=identity_payload.get("industries") or [],
    )
    if orphans:
        raise OnboardingValidationError(
            "Moduländring lämnar inkompatibla tjänster valda: "
            + ", ".join(f"{o['label_sv']} ({o['reason']})" for o in orphans)
            + ". Ta bort tjänsterna i Tjänster-steget först.",
        )

    modules_payload = {
        "capabilities": capabilities,
        "integrations": integrations,
        "requires_api_key": capability_requires_api_key(capabilities),
    }
    OnboardingRepository.upsert_draft(
        db,
        session_id=session_id,
        step_key="modules",
        payload=modules_payload,
    )
    step_status = "completed" if capabilities else "in_progress"
    OnboardingRepository.set_step_state(
        db,
        session_id=session_id,
        step_key="modules",
        step_status=step_status,
        verification_level="declared",
        operator_id=operator["id"],
    )
    session.current_step = "service_profile"
    _sync_readonly_step_states(
        db,
        session_id=session_id,
        tenant=tenant,
        settings=settings,
        operator_id=operator["id"],
    )
    OnboardingRepository.bump_version(session, operator["id"])

    _add_audit_event_no_commit(
        db,
        tenant_id=session.tenant_id,
        action="onboarding.modules_updated",
        status="succeeded",
        details=_operator_audit_details(
            operator,
            session_id=session_id,
            extra={"capabilities": capabilities, "integrations": integrations},
        ),
    )
    try:
        db.commit()
        db.refresh(session)
    except Exception as exc:
        db.rollback()
        raise OnboardingAuditError("Audit could not be recorded.") from exc

    return _build_session_response(db, session, settings=settings)


def patch_automation(
    db: Session,
    *,
    session_id: str,
    operator: OperatorIdentity,
    preset_key: str,
    preset_version: int,
    expected_version: int,
    settings: Settings,
) -> OnboardingSessionResponse:
    session = _lock_session(db, session_id, expected_version)
    _ensure_writable_session(session)
    tenant = _get_tenant(db, session.tenant_id)

    preset = resolve_preset(preset_key, preset_version)
    if preset is None:
        raise OnboardingValidationError("Unknown or mismatched automation preset.")

    automation_payload = {
        "preset_key": preset_key,
        "preset_version": preset_version,
        "effective_policy_snapshot": preset_snapshot(preset),
    }
    OnboardingRepository.upsert_draft(
        db,
        session_id=session_id,
        step_key="automation",
        payload=automation_payload,
    )
    OnboardingRepository.set_step_state(
        db,
        session_id=session_id,
        step_key="automation",
        step_status="completed",
        verification_level="declared",
        operator_id=operator["id"],
    )
    session.current_step = "routing"
    _sync_readonly_step_states(
        db,
        session_id=session_id,
        tenant=tenant,
        settings=settings,
        operator_id=operator["id"],
    )
    OnboardingRepository.bump_version(session, operator["id"])

    _add_audit_event_no_commit(
        db,
        tenant_id=session.tenant_id,
        action="onboarding.automation_updated",
        status="succeeded",
        details=_operator_audit_details(
            operator,
            session_id=session_id,
            extra={"preset_key": preset_key, "preset_version": preset_version},
        ),
    )
    try:
        db.commit()
        db.refresh(session)
    except Exception as exc:
        db.rollback()
        raise OnboardingAuditError("Audit could not be recorded.") from exc

    return _build_session_response(db, session, settings=settings)


def get_step_detail(
    db: Session,
    session_id: str,
    step_key: str,
    *,
    settings: Settings,
) -> StepDetailResponse:
    if step_key == "integrations":
        from app.admin.onboarding.slice2b_integrations_service import get_integrations_step

        data = get_integrations_step(db, session_id, settings=settings)
        return StepDetailResponse(
            step_key=step_key,
            step_status=data["step_status"],
            verification_level=data["verification_level"],
            blocks_activation=bool(data.get("blocks_activation")),
            read_only=False,
            read_only_reason=None,
            details=data,
        )
    raise OnboardingValidationError(f"Step '{step_key}' is not a read-only step.")


def run_readiness(
    db: Session,
    *,
    session_id: str,
    operator: OperatorIdentity,
    settings: Settings,
) -> ReadinessResponse:
    session = _get_session_or_raise(db, session_id)
    _ensure_writable_session(session)
    tenant = _get_tenant(db, session.tenant_id)

    session.readiness_check_version += 1
    session.updated_at = _utcnow()
    session.last_updated_by_operator_id = operator["id"]
    tenant.readiness_config_version = int(tenant.config_version or 1)
    tenant.readiness_checked_at = _utcnow()

    result = compute_readiness(
        db,
        session_id=session_id,
        tenant=tenant,
        settings=settings,
        check_version=session.readiness_check_version,
    )

    if result["overall_status"] == "ready":
        session.status = "ready_for_activation"
    elif result["overall_status"] == "ready_with_warnings":
        session.status = "ready_for_review"
    else:
        session.status = "blocked"

    OnboardingRepository.set_step_state(
        db,
        session_id=session_id,
        step_key="readiness",
        step_status="completed",
        verification_level="declared",
        operator_id=operator["id"],
    )
    session.current_step = "review"

    _add_audit_event_no_commit(
        db,
        tenant_id=session.tenant_id,
        action="onboarding.readiness_checked",
        status="succeeded",
        details=_operator_audit_details(
            operator,
            session_id=session_id,
            extra={
                "overall_status": result["overall_status"],
                "check_version": session.readiness_check_version,
            },
        ),
    )
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise OnboardingAuditError("Audit could not be recorded.") from exc

    return ReadinessResponse(**result)


def get_activation_plan(
    db: Session,
    session_id: str,
    *,
    settings: Settings,
) -> ActivationPlanResponse:
    session = _get_session_or_raise(db, session_id)
    tenant = _get_tenant(db, session.tenant_id)
    plan = build_activation_plan(db, session_id=session_id, tenant=tenant, settings=settings)
    return ActivationPlanResponse(**plan)


def activate_onboarding_session(
    db: Session,
    *,
    session_id: str,
    operator: OperatorIdentity,
    reason: str,
    confirmation_phrase: str,
    expected_version: int,
    readiness_check_version: int,
    plan_hash: str,
    acknowledged_warning_ids: list[str],
    settings: Settings,
) -> ActivateResponse:
    if operator["role"] not in _ADMIN_ROLES:
        raise OnboardingValidationError("Activation requires admin role.")

    session = OnboardingRepository.get_session_for_update(db, session_id)
    if session is None:
        raise OnboardingNotFoundError(f"Onboarding session '{session_id}' not found.")

    if session.status == "active" and session.activated_at is not None:
        tenant = _get_tenant(db, session.tenant_id)
        return ActivateResponse(
            status="no_change",
            tenant_id=session.tenant_id,
            session_id=session.id,
            tenant_status=tenant.status,
            message="Session is already active.",
        )

    if session.version != expected_version:
        raise OnboardingVersionConflictError()

    tenant = (
        db.query(TenantConfigRecord)
        .filter(TenantConfigRecord.tenant_id == session.tenant_id)
        .with_for_update()
        .first()
    )
    if tenant is None:
        raise OnboardingNotFoundError(f"Tenant '{session.tenant_id}' not found.")

    identity_draft = OnboardingRepository.get_draft(db, session_id, "identity")
    identity_payload = (identity_draft.payload if identity_draft else {}) or {}
    slug = identity_payload.get("slug") or tenant.slug or ""
    if confirmation_phrase != slug:
        raise OnboardingValidationError("Confirmation phrase must match tenant slug.")

    if readiness_check_version != session.readiness_check_version:
        raise OnboardingStaleReadinessError()

    readiness = compute_readiness(
        db,
        session_id=session_id,
        tenant=tenant,
        settings=settings,
        check_version=session.readiness_check_version,
    )
    overall = readiness["overall_status"]
    if overall in ("not_ready", "unknown"):
        raise OnboardingConflictError(
            "Tenant is not ready for activation.",
            code="not_ready",
        )

    warning_ids = {w["id"] for w in readiness.get("warnings") or []}
    if overall == "ready_with_warnings":
        if set(acknowledged_warning_ids) != warning_ids:
            raise OnboardingStaleReadinessError()

    fresh_plan = build_activation_plan(
        db, session_id=session_id, tenant=tenant, settings=settings
    )
    if fresh_plan["plan_hash"] != plan_hash:
        raise OnboardingStaleActivationPlanError()

    modules_draft = OnboardingRepository.get_draft(db, session_id, "modules")
    automation_draft = OnboardingRepository.get_draft(db, session_id, "automation")
    sp_draft = OnboardingRepository.get_draft(db, session_id, "service_profile")
    routing_draft = OnboardingRepository.get_draft(db, session_id, "routing")
    data_start_draft = OnboardingRepository.get_draft(db, session_id, "data_start")
    integrations_draft = OnboardingRepository.get_draft(db, session_id, "integrations")
    external_routing_draft = OnboardingRepository.get_draft(db, session_id, "external_routing")
    modules_payload = (modules_draft.payload if modules_draft else {}) or {}
    automation_payload = (automation_draft.payload if automation_draft else {}) or {}

    job_types, integration_keys = resolve_modules_to_tenant_config(
        modules_payload.get("capabilities") or [],
        modules_payload.get("integrations") or [],
    )
    snapshot = automation_payload.get("effective_policy_snapshot") or {}
    if not snapshot:
        preset_key = automation_payload.get("preset_key")
        preset_version = int(automation_payload.get("preset_version") or 1)
        preset = resolve_preset(preset_key or "", preset_version)
        if preset:
            snapshot = preset_snapshot(preset)

    workflow_scan_before = copy.deepcopy((tenant.settings or {}).get("workflow_scan"))
    activation_now = _utcnow()

    tenant.name = identity_payload.get("company_name") or tenant.name
    tenant.slug = slug
    tenant.status = "active"
    tenant.lifecycle_status = "active"
    tenant.lifecycle_updated_at = activation_now
    tenant.lifecycle_updated_by = operator["id"]
    tenant.enabled_job_types = job_types
    tenant.allowed_integrations = integration_keys
    tenant.auto_actions = snapshot.get("auto_actions") or {}
    tenant.updated_at = activation_now

    merged_settings = copy.deepcopy(tenant.settings or _safe_defaults_settings())
    company = merged_settings.setdefault("company", {})
    for key in ("industries", "org_number", "primary_contact", "contact_email", "phone", "timezone", "language"):
        if identity_payload.get(key) is not None:
            company[key] = identity_payload[key]
    automation_flags = snapshot.get("automation_flags") or {}
    merged_settings["automation"] = {
        **(merged_settings.get("automation") or {}),
        **automation_flags,
    }
    merged_settings["scheduler"] = {"run_mode": "paused"}
    if workflow_scan_before is not None:
        merged_settings["workflow_scan"] = workflow_scan_before
    merged_settings = materialize_slice2a_config(
        merged_settings,
        modules_payload=modules_payload,
        sp_payload=sp_draft.payload if sp_draft else None,
        routing_payload=routing_draft.payload if routing_draft else None,
        data_start_payload=data_start_draft.payload if data_start_draft else None,
        activation_cutoff_at=activation_now,
    )
    verification_records = IntegrationVerificationStore.list_for_session(db, session_id)
    merged_settings = materialize_slice2b_config(
        merged_settings,
        modules_payload=modules_payload,
        integrations_payload=integrations_draft.payload if integrations_draft else None,
        external_routing_payload=external_routing_draft.payload if external_routing_draft else None,
        verification_records=verification_records,
        integration_state_revision=int(session.integration_state_revision or 0),
        tenant_slug=slug,
    )
    merged_settings = materialize_selections_config(
        merged_settings,
        modules_payload=modules_payload,
        integrations_payload=integrations_draft.payload if integrations_draft else None,
        operator_id=operator["id"],
    )
    tenant.settings = merged_settings
    flag_modified(tenant, "settings")
    sync_allowed_integrations_from_selections(
        db,
        tenant,
        dry_run=False,
        fail_closed=True,
        allow_expand_on_activation=True,
    )

    now = activation_now
    session.status = "active"
    session.activated_at = now
    session.completed_at = now
    session.updated_at = now
    session.last_updated_by_operator_id = operator["id"]
    session.version += 1

    _add_audit_event_no_commit(
        db,
        tenant_id=session.tenant_id,
        action="onboarding.service_config_materialized",
        status="succeeded",
        details=_operator_audit_details(operator, session_id=session_id),
    )
    _add_audit_event_no_commit(
        db,
        tenant_id=session.tenant_id,
        action="onboarding.routing_config_materialized",
        status="succeeded",
        details=_operator_audit_details(operator, session_id=session_id),
    )
    emit_onboarding_audit(
        db,
        tenant_id=session.tenant_id,
        action=INTEGRATION_CONFIG_MATERIALIZED,
        status="succeeded",
        details=_operator_audit_details(operator, session_id=session_id),
    )
    emit_onboarding_audit(
        db,
        tenant_id=session.tenant_id,
        action=EXTERNAL_ROUTING_MATERIALIZED,
        status="succeeded",
        details=_operator_audit_details(operator, session_id=session_id),
    )
    cutoff = (tenant.settings or {}).get("intake", {}).get("activation_cutoff_at")
    if cutoff:
        _add_audit_event_no_commit(
            db,
            tenant_id=session.tenant_id,
            action="onboarding.intake_cutoff_created",
            status="succeeded",
            details=_operator_audit_details(
                operator,
                session_id=session_id,
                extra={"activation_cutoff_at": cutoff},
            ),
        )
    _add_audit_event_no_commit(
        db,
        tenant_id=session.tenant_id,
        action="onboarding.activation_succeeded",
        status="succeeded",
        details=_operator_audit_details(
            operator,
            session_id=session_id,
            reason=reason,
            extra={
                "readiness_check_version": readiness_check_version,
                "acknowledged_warning_ids": acknowledged_warning_ids,
                "preset_key": automation_payload.get("preset_key"),
                "plan_hash": plan_hash,
            },
        ),
    )
    from uuid import uuid4

    from app.admin.tenant_lifecycle.service import bump_config_version, save_activation_snapshot

    bump_config_version(tenant, operator_id=operator["id"])
    tenant.readiness_config_version = int(tenant.config_version or 1)
    tenant.readiness_checked_at = activation_now
    save_activation_snapshot(
        db,
        tenant_id=session.tenant_id,
        snapshot_id=str(uuid4()),
        config_version=int(tenant.config_version or 1),
        plan_hash=plan_hash,
        readiness_check_version=readiness_check_version,
        snapshot_json={
            "identity": identity_payload,
            "modules": modules_payload,
            "automation": automation_payload,
            "plan_hash": plan_hash,
        },
        operator_id=operator["id"],
        activated_at=activation_now,
    )
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise OnboardingAuditError("Activation could not be completed.") from exc

    return ActivateResponse(
        status="activated",
        tenant_id=session.tenant_id,
        session_id=session.id,
        tenant_status="active",
        message="Tenant activated successfully.",
    )


def cancel_onboarding_session(
    db: Session,
    *,
    session_id: str,
    operator: OperatorIdentity,
    reason: str,
    expected_version: int,
    settings: Settings,
) -> OnboardingSessionResponse:
    session = _lock_session(db, session_id, expected_version)
    if session.status == "cancelled":
        raise OnboardingConflictError("Session is already cancelled.", code="already_cancelled")
    if session.status == "active":
        raise OnboardingConflictError("Active sessions cannot be cancelled.", code="session_active")

    session.status = "cancelled"
    session.cancel_reason = reason
    session.completed_at = _utcnow()
    OnboardingRepository.bump_version(session, operator["id"])

    _add_audit_event_no_commit(
        db,
        tenant_id=session.tenant_id,
        action="onboarding.session_cancelled",
        status="succeeded",
        details=_operator_audit_details(operator, session_id=session_id, reason=reason),
    )
    try:
        db.commit()
        db.refresh(session)
    except Exception as exc:
        db.rollback()
        raise OnboardingAuditError("Audit could not be recorded.") from exc

    return _build_session_response(db, session, settings=settings)


def create_onboarding_api_key(
    db: Session,
    *,
    session_id: str,
    operator: OperatorIdentity,
    reason: str,
    confirmation: bool,
    expected_version: int,
) -> ApiKeyCreateResponse:
    if operator["role"] not in _ADMIN_ROLES:
        raise OnboardingValidationError("API key creation requires admin role.")
    if not confirmation:
        raise OnboardingValidationError("Confirmation is required.")

    session = _lock_session(db, session_id, expected_version)
    _ensure_writable_session(session)
    tenant = _get_tenant(db, session.tenant_id)

    modules_draft = OnboardingRepository.get_draft(db, session_id, "modules")
    modules_payload = (modules_draft.payload if modules_draft else {}) or {}
    if not capability_requires_api_key(modules_payload.get("capabilities") or []):
        raise OnboardingValidationError("API access is not required for this onboarding session.")

    if tenant_has_api_key(db, tenant.tenant_id):
        raise OnboardingConflictError("Tenant already has an active API key.", code="api_key_exists")

    import hashlib
    import secrets

    from app.repositories.postgres.tenant_api_key_models import TenantApiKeyRecord

    raw_key = "kw_" + secrets.token_hex(16)
    key_record = TenantApiKeyRecord(
        key_id=str(uuid4()),
        tenant_id=tenant.tenant_id,
        key_hash=hashlib.sha256(raw_key.encode()).hexdigest(),
        key_hint=raw_key[-4:],
        is_active=True,
        created_at=_utcnow(),
        revoked_at=None,
    )
    db.add(key_record)
    OnboardingRepository.bump_version(session, operator["id"])

    _add_audit_event_no_commit(
        db,
        tenant_id=session.tenant_id,
        action="onboarding.api_key_created",
        status="succeeded",
        details=_operator_audit_details(
            operator,
            session_id=session_id,
            reason=reason,
            extra={"key_hint": key_record.key_hint},
        ),
    )
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise OnboardingAuditError("Audit could not be recorded.") from exc

    return ApiKeyCreateResponse(
        api_key=raw_key,
        key_hint=key_record.key_hint,
        message="API key created. Store it securely — it will not be shown again.",
    )
