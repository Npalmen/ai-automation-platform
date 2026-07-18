"""Slice 2B external routing draft service (enforced targets only)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.admin.onboarding.audit_events import (
    EXTERNAL_ROUTING_RESET,
    EXTERNAL_ROUTING_UPDATED,
    emit_onboarding_audit,
)
from app.admin.onboarding.integration_draft_schemas import (
    ExternalRoutingDraftPayload,
    ExternalRoutingPatchRequest,
    ExternalRoutingResetRequest,
    ExternalRoutingTargetDraft,
)
from app.admin.onboarding.integration_verification import IntegrationVerificationStore
from app.admin.onboarding.repository import OnboardingRepository
from app.admin.onboarding.resource_binding import RESOURCE_MONDAY_BOARD, ResourceBindingService
from app.admin.onboarding.slice2b_registry import enforced_external_routing_targets
from app.admin.onboarding.steps import evaluate_integrations_step
from app.core.admin_session import OperatorIdentity
from app.core.settings import Settings
from app.workflows.scanners.routing_preview import resolve_routing_preview


def _session_ops():
    from app.admin.onboarding import service as onboarding_service

    return onboarding_service


def _load_draft(db: Session, session_id: str) -> ExternalRoutingDraftPayload:
    record = OnboardingRepository.get_draft(db, session_id, "external_routing")
    return ExternalRoutingDraftPayload.model_validate((record.payload if record else {}) or {})


def _enforced_job_types() -> set[str]:
    return {t.job_type for t in enforced_external_routing_targets() if t.job_type}


def _filter_enforced_targets(targets: dict) -> dict:
    allowed = _enforced_job_types()
    return {k: v for k, v in targets.items() if k in allowed}


def _routing_hints_from_draft(draft: ExternalRoutingDraftPayload) -> dict[str, Any]:
    hints: dict[str, Any] = {}
    for job_type, target in draft.targets.items():
        if job_type != "lead":
            continue
        hints[job_type] = {
            "system": "monday",
            "target": {
                "board_id": target.board_id,
                "board_name": target.board_name,
                "group_id": target.group_id,
                "group_name": target.group_name,
            },
        }
    return hints


def get_external_routing_step(db: Session, session_id: str, *, settings: Settings) -> dict[str, Any]:
    session = _session_ops()._get_session_or_raise(db, session_id)
    draft = _load_draft(db, session_id)
    hints = _routing_hints_from_draft(draft)
    preview = [resolve_routing_preview(hints, job_type) for job_type in sorted(_enforced_job_types())]
    return {
        "step_key": "external_routing",
        "draft": draft.model_dump(),
        "enforced_targets": [
            {
                "key": t.key,
                "job_type": t.job_type,
                "integration_key": t.integration_key,
                "enforced": t.enforced,
            }
            for t in enforced_external_routing_targets()
        ],
        "preview": preview,
        "integration_state_revision": session.integration_state_revision,
    }


def patch_external_routing_step(
    db: Session,
    *,
    session_id: str,
    operator: OperatorIdentity,
    body: ExternalRoutingPatchRequest,
    settings: Settings,
):
    session = _session_ops()._lock_session(db, session_id, body.version)
    _session_ops()._ensure_writable_session(session)
    tenant = _session_ops()._get_tenant(db, session.tenant_id)
    filtered = _filter_enforced_targets(
        {k: v.model_dump() if hasattr(v, "model_dump") else v for k, v in body.targets.items()}
    )
    for job_type, raw in filtered.items():
        board_id = str(raw.get("board_id") or "").strip()
        board_name = str(raw.get("board_name") or "").strip()
        if not board_id or not board_name:
            raise OnboardingValidationError(f"External routing for {job_type} requires board_id and board_name.")
        ResourceBindingService.bind(
            db,
            resource_type=RESOURCE_MONDAY_BOARD,
            resource_id=board_id,
            tenant_id=session.tenant_id,
            session_id=session.id,
            operator_id=operator["id"],
        )

    draft = ExternalRoutingDraftPayload(
        targets={k: ExternalRoutingTargetDraft.model_validate(v) for k, v in filtered.items()}
    )
    OnboardingRepository.upsert_draft(
        db,
        session_id=session_id,
        step_key="external_routing",
        payload=draft.model_dump(),
    )
    IntegrationVerificationStore.invalidate(db, session_id=session_id, integration_key="monday")
    OnboardingRepository.bump_integration_state_revision(session)
    OnboardingRepository.bump_version(session, operator["id"])

    modules = OnboardingRepository.get_draft(db, session_id, "modules")
    modules_payload = (modules.payload if modules else {}) or {}
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
        operator_id=operator["id"],
    )
    _session_ops()._add_audit_event_no_commit(
        db,
        tenant_id=session.tenant_id,
        action="onboarding.external_routing_patched",
        status="succeeded",
        details=_session_ops()._operator_audit_details(operator, session_id=session_id),
    )
    emit_onboarding_audit(
        db,
        tenant_id=session.tenant_id,
        action=EXTERNAL_ROUTING_UPDATED,
        status="succeeded",
        details=_session_ops()._operator_audit_details(
            operator,
            session_id=session_id,
            extra={"job_types": sorted(filtered.keys())},
        ),
    )
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        from app.admin.onboarding.errors import OnboardingAuditError

        raise OnboardingAuditError("Audit could not be recorded.") from exc
    session = OnboardingRepository.get_session(db, session_id)
    return _session_ops()._build_session_response(db, session, settings=settings)


def preview_external_routing(db: Session, session_id: str, *, settings: Settings) -> dict[str, Any]:
    _ = settings
    draft = _load_draft(db, session_id)
    hints = _routing_hints_from_draft(draft)
    preview = [resolve_routing_preview(hints, job_type) for job_type in sorted(_enforced_job_types())]
    return {"preview": preview, "mutated": False}


def reset_external_routing(
    db: Session,
    *,
    session_id: str,
    operator: OperatorIdentity,
    body: ExternalRoutingResetRequest,
    settings: Settings,
):
    session = _session_ops()._lock_session(db, session_id, body.version)
    _session_ops()._ensure_writable_session(session)
    current = _load_draft(db, session_id)
    targets = dict(current.targets)
    for job_type in body.job_types:
        targets.pop(job_type, None)
    emit_onboarding_audit(
        db,
        tenant_id=session.tenant_id,
        action=EXTERNAL_ROUTING_RESET,
        status="succeeded",
        details=_session_ops()._operator_audit_details(
            operator,
            session_id=session_id,
            extra={"job_types": list(body.job_types)},
        ),
    )
    return patch_external_routing_step(
        db,
        session_id=session_id,
        operator=operator,
        body=ExternalRoutingPatchRequest(version=session.version, targets=targets),
        settings=settings,
    )
