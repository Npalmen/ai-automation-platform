"""Slice 2A onboarding service handlers (service profile, routing, data start)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.admin.onboarding.draft_schemas import (
    DataStartPatchRequest,
    DataStartDraftPayload,
    RoutingDraftPayload,
    RoutingPatchRequest,
    RoutingResetRequest,
    ServiceProfileDraftPayload,
    ServiceProfilePatchRequest,
)
from app.admin.onboarding.effective_config import (
    INTAKE_ENFORCEMENT_METADATA_ONLY,
    build_effective_config_summary,
    build_effective_data_start,
    build_effective_routing,
    build_effective_service_config,
    materialize_internal_routing_hints,
    materialize_lead_config,
    validate_routing_draft,
    validate_service_profile_draft,
)
from app.admin.onboarding.errors import (
    OnboardingAuditError,
    OnboardingNotFoundError,
    OnboardingValidationError,
    OnboardingVersionConflictError,
)
from app.admin.onboarding.repository import OnboardingRepository
from app.admin.onboarding.slice2a_registry import (
    DATA_START_MODES,
    capability_needs_service_profile,
    lead_field_registry,
    profiles_for_onboarding,
)
from app.core.admin_session import OperatorIdentity
from app.core.settings import Settings


def _session_ops():
    from app.admin.onboarding import service as onboarding_service

    return onboarding_service


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _allowed_profile_keys() -> set[str]:
    return {p["key"] for p in profiles_for_onboarding() if p["availability"] == "available"}


def _allowed_field_keys() -> set[str]:
    return {f["key"] for f in lead_field_registry()}


def _session_drafts(db: Session, session_id: str) -> tuple[dict, dict | None, dict | None, dict | None]:
    modules = OnboardingRepository.get_draft(db, session_id, "modules")
    sp = OnboardingRepository.get_draft(db, session_id, "service_profile")
    routing = OnboardingRepository.get_draft(db, session_id, "routing")
    data_start = OnboardingRepository.get_draft(db, session_id, "data_start")
    modules_payload = (modules.payload if modules else {}) or {}
    return (
        modules_payload,
        sp.payload if sp else None,
        routing.payload if routing else None,
        data_start.payload if data_start else None,
    )


def _synthetic_step_status(db: Session, session_id: str, step_key: str) -> str:
    record = OnboardingRepository.get_step_states(db, session_id)
    by_key = {s.step_key: s for s in record}
    if step_key in by_key:
        return by_key[step_key].step_status
    return "not_started"


def _evaluate_service_profile_step_status(
    modules_payload: dict,
    sp_payload: dict | None,
) -> tuple[str, str, bool]:
    caps = modules_payload.get("capabilities") or []
    if not caps:
        return "not_applicable", "not_applicable", False
    if not capability_needs_service_profile(caps):
        return "not_applicable", "not_applicable", False
    effective = build_effective_service_config(
        modules_payload,
        sp_payload,
        allowed_profile_keys=_allowed_profile_keys(),
        allowed_field_keys=_allowed_field_keys(),
    )
    if not effective["valid"]:
        if not (effective.get("selected_profiles") or []):
            return "in_progress", "declared", True
        return "blocked", "declared", True
    if effective["selected_profiles"]:
        return "completed", "locally_verified", False
    return "in_progress", "declared", True


def _evaluate_routing_step_status(
    modules_payload: dict,
    sp_payload: dict | None,
    routing_payload: dict | None,
) -> tuple[str, str, bool]:
    caps = modules_payload.get("capabilities") or []
    sp_draft = ServiceProfileDraftPayload.model_validate(sp_payload or {})
    if not sp_draft.selected_profiles:
        return "not_started", "declared", capability_needs_service_profile(caps)
    effective = build_effective_routing(sp_payload, routing_payload)
    if not effective["valid"]:
        return "blocked", "declared", True
    return "completed", "locally_verified", False


def _evaluate_data_start_step_status(data_start_payload: dict | None) -> tuple[str, str, bool]:
    effective = build_effective_data_start(data_start_payload)
    if not effective["valid"]:
        return "blocked", "declared", True
    return "completed", "locally_verified", False


def get_service_profile_step(
    db: Session,
    session_id: str,
    *,
    settings: Settings,
) -> dict[str, Any]:
    _session_ops()._get_session_or_raise(db, session_id)
    modules_payload, sp_payload, routing_payload, data_start_payload = _session_drafts(db, session_id)
    effective = build_effective_service_config(
        modules_payload,
        sp_payload,
        allowed_profile_keys=_allowed_profile_keys(),
        allowed_field_keys=_allowed_field_keys(),
    )
    draft = ServiceProfileDraftPayload.model_validate(sp_payload or {})
    step_status, verification_level, blocks = _evaluate_service_profile_step_status(
        modules_payload, sp_payload
    )
    return {
        "step_key": "service_profile",
        "step_status": step_status,
        "verification_level": verification_level,
        "blocks_activation": blocks,
        "draft": draft.model_dump(),
        "effective": effective,
    }


def patch_service_profile_step(
    db: Session,
    *,
    session_id: str,
    operator: OperatorIdentity,
    body: ServiceProfilePatchRequest,
    settings: Settings,
):
    session = _session_ops()._lock_session(db, session_id, body.version)
    _session_ops()._ensure_writable_session(session)
    tenant = _session_ops()._get_tenant(db, session.tenant_id)
    modules_payload, _, _, _ = _session_drafts(db, session_id)

    draft = ServiceProfileDraftPayload(
        selected_profiles=body.selected_profiles,
        lead_requirements=body.lead_requirements,
    )
    errors = validate_service_profile_draft(
        draft,
        capability_keys=modules_payload.get("capabilities") or [],
        allowed_profile_keys=_allowed_profile_keys(),
        allowed_field_keys=_allowed_field_keys(),
    )
    if errors:
        raise OnboardingValidationError("; ".join(errors))

    OnboardingRepository.upsert_draft(
        db, session_id=session_id, step_key="service_profile", payload=draft.model_dump()
    )
    step_status, verification_level, blocks = _evaluate_service_profile_step_status(
        modules_payload, draft.model_dump()
    )
    OnboardingRepository.set_step_state(
        db,
        session_id=session_id,
        step_key="service_profile",
        step_status=step_status,
        verification_level=verification_level,
        operator_id=operator["id"],
    )
    session.current_step = "automation"
    _session_ops()._sync_readonly_step_states(
        db, session_id=session_id, tenant=tenant, settings=settings, operator_id=operator["id"]
    )
    OnboardingRepository.bump_version(session, operator["id"])
    _session_ops()._add_audit_event_no_commit(
        db,
        tenant_id=session.tenant_id,
        action="onboarding.service_profiles_updated",
        status="succeeded",
        details=_session_ops()._operator_audit_details(
            operator,
            session_id=session_id,
            extra={
                "selected_profiles": draft.selected_profiles,
                "lead_requirement_profiles": list(draft.lead_requirements.keys()),
            },
        ),
    )
    if draft.lead_requirements:
        _session_ops()._add_audit_event_no_commit(
            db,
            tenant_id=session.tenant_id,
            action="onboarding.lead_requirements_updated",
            status="succeeded",
            details=_session_ops()._operator_audit_details(
                operator,
                session_id=session_id,
                extra={"profile_keys": list(draft.lead_requirements.keys())},
            ),
        )
    try:
        db.commit()
        db.refresh(session)
    except Exception as exc:
        db.rollback()
        raise OnboardingAuditError("Audit could not be recorded.") from exc
    return _session_ops()._build_session_response(db, session, settings=settings)


def get_routing_step(
    db: Session,
    session_id: str,
    *,
    settings: Settings,
) -> dict[str, Any]:
    _session_ops()._get_session_or_raise(db, session_id)
    modules_payload, sp_payload, routing_payload, _ = _session_drafts(db, session_id)
    effective = build_effective_routing(sp_payload, routing_payload)
    draft = RoutingDraftPayload.model_validate(routing_payload or {})
    step_status = _synthetic_step_status(db, session_id, "routing")
    if step_status == "not_started":
        step_status, verification_level, blocks = _evaluate_routing_step_status(
            modules_payload, sp_payload, routing_payload
        )
    else:
        step_status, verification_level, blocks = _evaluate_routing_step_status(
            modules_payload, sp_payload, routing_payload
        )
    return {
        "step_key": "routing",
        "step_status": step_status,
        "verification_level": verification_level,
        "blocks_activation": blocks,
        "draft": draft.model_dump(),
        "effective": effective,
    }


def patch_routing_step(
    db: Session,
    *,
    session_id: str,
    operator: OperatorIdentity,
    body: RoutingPatchRequest,
    settings: Settings,
):
    session = _session_ops()._lock_session(db, session_id, body.version)
    _session_ops()._ensure_writable_session(session)
    tenant = _session_ops()._get_tenant(db, session.tenant_id)
    modules_payload, sp_payload, _, _ = _session_drafts(db, session_id)
    sp_draft = ServiceProfileDraftPayload.model_validate(sp_payload or {})

    draft = RoutingDraftPayload(route_overrides=body.route_overrides)
    errors = validate_routing_draft(draft, selected_profiles=sp_draft.selected_profiles)
    if errors:
        raise OnboardingValidationError("; ".join(errors))

    OnboardingRepository.upsert_draft(
        db, session_id=session_id, step_key="routing", payload=draft.model_dump()
    )
    step_status, verification_level, blocks = _evaluate_routing_step_status(
        modules_payload, sp_payload, draft.model_dump()
    )
    OnboardingRepository.set_step_state(
        db,
        session_id=session_id,
        step_key="routing",
        step_status=step_status,
        verification_level=verification_level,
        operator_id=operator["id"],
    )
    session.current_step = "integrations"
    _session_ops()._sync_readonly_step_states(
        db, session_id=session_id, tenant=tenant, settings=settings, operator_id=operator["id"]
    )
    OnboardingRepository.bump_version(session, operator["id"])
    _session_ops()._add_audit_event_no_commit(
        db,
        tenant_id=session.tenant_id,
        action="onboarding.routing_overrides_updated",
        status="succeeded",
        details=_session_ops()._operator_audit_details(
            operator,
            session_id=session_id,
            extra={"service_types": list(draft.route_overrides.keys())},
        ),
    )
    try:
        db.commit()
        db.refresh(session)
    except Exception as exc:
        db.rollback()
        raise OnboardingAuditError("Audit could not be recorded.") from exc
    return _session_ops()._build_session_response(db, session, settings=settings)


def reset_routing_overrides(
    db: Session,
    *,
    session_id: str,
    operator: OperatorIdentity,
    body: RoutingResetRequest,
    settings: Settings,
):
    session = _session_ops()._lock_session(db, session_id, body.version)
    _session_ops()._ensure_writable_session(session)
    tenant = _session_ops()._get_tenant(db, session.tenant_id)
    modules_payload, sp_payload, routing_payload, _ = _session_drafts(db, session_id)
    draft = RoutingDraftPayload.model_validate(routing_payload or {})
    for st in body.service_types:
        draft.route_overrides.pop(st, None)
    OnboardingRepository.upsert_draft(
        db, session_id=session_id, step_key="routing", payload=draft.model_dump()
    )
    step_status, verification_level, blocks = _evaluate_routing_step_status(
        modules_payload, sp_payload, draft.model_dump()
    )
    OnboardingRepository.set_step_state(
        db,
        session_id=session_id,
        step_key="routing",
        step_status=step_status,
        verification_level=verification_level,
        operator_id=operator["id"],
    )
    OnboardingRepository.bump_version(session, operator["id"])
    _session_ops()._add_audit_event_no_commit(
        db,
        tenant_id=session.tenant_id,
        action="onboarding.routing_overrides_reset",
        status="succeeded",
        details=_session_ops()._operator_audit_details(
            operator,
            session_id=session_id,
            extra={"service_types": body.service_types},
        ),
    )
    try:
        db.commit()
        db.refresh(session)
    except Exception as exc:
        db.rollback()
        raise OnboardingAuditError("Audit could not be recorded.") from exc
    return get_routing_step(db, session_id, settings=settings)


def preview_routing(
    db: Session,
    session_id: str,
    *,
    settings: Settings,
) -> dict[str, Any]:
    _session_ops()._get_session_or_raise(db, session_id)
    modules_payload, sp_payload, routing_payload, _ = _session_drafts(db, session_id)
    effective = build_effective_routing(sp_payload, routing_payload)
    preview_rows = []
    for route in effective.get("routes") or []:
        preview_rows.append(
            {
                "service_type": route["service_type"],
                "effective_route": route["effective"],
                "source": route["source"],
                "manual_review": route["effective"] == "manual_review",
            }
        )
    return {"preview": preview_rows, "mutated": False}


def get_data_start_step(
    db: Session,
    session_id: str,
    *,
    settings: Settings,
) -> dict[str, Any]:
    _session_ops()._get_session_or_raise(db, session_id)
    _, _, _, data_start_payload = _session_drafts(db, session_id)
    effective = build_effective_data_start(data_start_payload)
    draft = DataStartDraftPayload.model_validate(data_start_payload or {})
    step_status, verification_level, blocks = _evaluate_data_start_step_status(data_start_payload)
    return {
        "step_key": "data_start",
        "step_status": step_status,
        "verification_level": verification_level,
        "blocks_activation": blocks,
        "draft": draft.model_dump(),
        "effective": effective,
    }


def patch_data_start_step(
    db: Session,
    *,
    session_id: str,
    operator: OperatorIdentity,
    body: DataStartPatchRequest,
    settings: Settings,
):
    session = _session_ops()._lock_session(db, session_id, body.version)
    _session_ops()._ensure_writable_session(session)
    tenant = _session_ops()._get_tenant(db, session.tenant_id)
    mode_def = DATA_START_MODES.get(body.mode)
    if mode_def is None or not mode_def.supported_in_current_slice:
        raise OnboardingValidationError(f"Data start mode '{body.mode}' is not available.")

    draft = DataStartDraftPayload(mode=body.mode)
    OnboardingRepository.upsert_draft(
        db, session_id=session_id, step_key="data_start", payload=draft.model_dump()
    )
    step_status, verification_level, blocks = _evaluate_data_start_step_status(draft.model_dump())
    OnboardingRepository.set_step_state(
        db,
        session_id=session_id,
        step_key="data_start",
        step_status=step_status,
        verification_level=verification_level,
        operator_id=operator["id"],
    )
    session.current_step = "readiness"
    _session_ops()._sync_readonly_step_states(
        db, session_id=session_id, tenant=tenant, settings=settings, operator_id=operator["id"]
    )
    OnboardingRepository.bump_version(session, operator["id"])
    _session_ops()._add_audit_event_no_commit(
        db,
        tenant_id=session.tenant_id,
        action="onboarding.data_start_updated",
        status="succeeded",
        details=_session_ops()._operator_audit_details(
            operator,
            session_id=session_id,
            extra={"mode": body.mode},
        ),
    )
    try:
        db.commit()
        db.refresh(session)
    except Exception as exc:
        db.rollback()
        raise OnboardingAuditError("Audit could not be recorded.") from exc
    return _session_ops()._build_session_response(db, session, settings=settings)
