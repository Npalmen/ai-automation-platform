"""
Operator panel safe-write actions (Kapitel 5).

Explicit per-action execution — not a generic action engine.
State-based idempotency; idempotency_key stored in audit for traceability only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.admin.operator_actions_schemas import (
    AvailableActionMeta,
    OperatorActionResponse,
)
from app.core.audit_service import create_audit_event
from app.core.admin_session import OperatorIdentity
from app.repositories.postgres.approval_repository import ApprovalRequestRepository
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
from app.workflows.approval_service import resolve_dispatch_approval

logger = logging.getLogger(__name__)

_ACTION_CATEGORY = "operator_action"
_EXECUTOR_ROLES = frozenset({"operations", "admin"})

# Rejection is only exposed for dispatch approvals whose reject path is verified
# local-only (resolve_dispatch_approval approved=False).
_SAFE_REJECT_APPROVAL_KINDS = frozenset({"controlled_dispatch"})


class OperatorActionNotFoundError(Exception):
    """Tenant or resource not found for the stated tenant scope."""


class OperatorActionConflictError(Exception):
    """Action is not valid in the current resource state."""


class OperatorActionValidationError(Exception):
    """Approval type or resource is not eligible for this action."""


class OperatorAuditError(Exception):
    """Audit could not be written — fail closed on response."""


@dataclass(frozen=True)
class OperatorActionDefinition:
    action_id: str
    required_role: Literal["operations", "admin"]
    safety_class: Literal["safe_write"] = "safe_write"
    requires_reason: bool = True
    requires_confirmation: bool = True
    idempotent: bool = True
    external_effect: Literal["no"] = "no"
    label_sv: str = ""
    consequence_sv: str = ""


ACTION_REGISTRY: dict[str, OperatorActionDefinition] = {
    "tenant.pause_automation": OperatorActionDefinition(
        action_id="tenant.pause_automation",
        required_role="operations",
        label_sv="Pausa automation",
        consequence_sv=(
            "Pausar automatisk bearbetning för kunden. Befintliga jobb ändras inte "
            "och inga externa system anropas."
        ),
    ),
    "tenant.resume_automation": OperatorActionDefinition(
        action_id="tenant.resume_automation",
        required_role="operations",
        label_sv="Återuppta automation",
        consequence_sv=(
            "Återupptar automatisk bearbetning för kunden. Inga externa system "
            "anropas direkt av denna åtgärd."
        ),
    ),
    "tenant.scheduler.pause": OperatorActionDefinition(
        action_id="tenant.scheduler.pause",
        required_role="operations",
        label_sv="Pausa scheduler",
        consequence_sv=(
            "Stoppar schemalagd inkorgssynk för kunden. Befintliga jobb påverkas "
            "inte och inga externa anrop görs."
        ),
    ),
    "tenant.scheduler.resume": OperatorActionDefinition(
        action_id="tenant.scheduler.resume",
        required_role="operations",
        label_sv="Återuppta scheduler",
        consequence_sv=(
            "Återaktiverar schemalagd inkorgssynk för kunden. Inga externa anrop "
            "görs direkt av denna åtgärd."
        ),
    ),
    "approval.reject": OperatorActionDefinition(
        action_id="approval.reject",
        required_role="operations",
        label_sv="Avslå väntande dispatch-godkännande",
        consequence_sv=(
            "Markerar det väntande dispatch-godkännandet som avslaget. Ingen "
            "extern dispatch eller export utförs."
        ),
    ),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _get_automation(settings: dict) -> dict:
    return dict(settings.get("automation") or {})


def _get_scheduler(settings: dict) -> dict:
    return dict(settings.get("scheduler") or {})


def _tenant_record(db: Session, tenant_id: str):
    record = TenantConfigRepository.get(db, tenant_id)
    if record is None:
        raise OperatorActionNotFoundError(f"Tenant '{tenant_id}' not found.")
    return record


def _pause_signals(settings: dict | None) -> tuple[bool, bool]:
    settings = settings or {}
    automation = _get_automation(settings)
    scheduler = _get_scheduler(settings)
    automation_paused = bool(automation.get("demo_mode", False))
    scheduler_paused = scheduler.get("run_mode") == "paused"
    return automation_paused, scheduler_paused


def _sanitize_state(settings: dict | None) -> dict[str, Any]:
    settings = settings or {}
    automation_paused, scheduler_paused = _pause_signals(settings)
    scheduler = _get_scheduler(settings)
    return {
        "automation_paused": automation_paused,
        "scheduler_paused": scheduler_paused,
        "scheduler_run_mode": scheduler.get("run_mode") or "manual",
    }


def _write_operator_audit(
    db: Session,
    *,
    tenant_id: str,
    action_id: str,
    status: str,
    operator: OperatorIdentity,
    reason: str,
    idempotency_key: str | None,
    resource_type: str,
    resource_id: str | None,
    changed: bool,
    result: str,
    before_state: dict[str, Any],
    after_state: dict[str, Any],
    requested_at: datetime,
    completed_at: datetime,
) -> str:
    definition = ACTION_REGISTRY[action_id]
    details: dict[str, Any] = {
        "operator_id": operator["id"],
        "operator_display_name": operator["display_name"],
        "operator_role": operator["role"],
        "tenant_id": tenant_id,
        "action_id": action_id,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "reason": reason,
        "safety_class": definition.safety_class,
        "idempotency_key": idempotency_key,
        "external_effect": definition.external_effect,
        "changed": changed,
        "result": result,
        "requested_at": _iso(requested_at),
        "completed_at": _iso(completed_at),
        "before_state": before_state,
        "after_state": after_state,
    }
    try:
        event = create_audit_event(
            db=db,
            tenant_id=tenant_id,
            category=_ACTION_CATEGORY,
            action=action_id,
            status=status,
            details=details,
        )
        return event.event_id
    except Exception as exc:
        logger.exception(
            "operator_action_audit_failed",
            extra={"tenant_id": tenant_id, "action_id": action_id},
        )
        raise OperatorAuditError("Audit could not be recorded.") from exc


def _role_allowed(operator_role: str, required_role: str) -> bool:
    if operator_role == "admin":
        return True
    if operator_role == "operations":
        return required_role in ("operations", "read_only")
    return False


def resolve_available_actions(
    candidate_action_ids: list[str],
    operator_role: str,
    resource_state: dict[str, Any],
) -> list[AvailableActionMeta]:
    """
    Return state-applicable actions with role gating expressed via allowed/blocked_reason.

    State-invalid actions are omitted entirely. read_only receives allowed=false entries.
    """
    result: list[AvailableActionMeta] = []
    for action_id in candidate_action_ids:
        definition = ACTION_REGISTRY.get(action_id)
        if definition is None:
            continue
        if not _is_state_applicable(action_id, resource_state):
            continue
        allowed = operator_role in _EXECUTOR_ROLES and _role_allowed(
            operator_role, definition.required_role
        )
        result.append(
            AvailableActionMeta(
                action_id=action_id,
                label=definition.label_sv,
                safety_class=definition.safety_class,
                required_role=definition.required_role,
                requires_reason=definition.requires_reason,
                requires_confirmation=definition.requires_confirmation,
                allowed=allowed,
                blocked_reason=None if allowed else "insufficient_role",
            )
        )
    return result


def _is_state_applicable(action_id: str, resource_state: dict[str, Any]) -> bool:
    if action_id == "tenant.pause_automation":
        return not bool(resource_state.get("automation_paused"))
    if action_id == "tenant.resume_automation":
        return bool(resource_state.get("automation_paused"))
    if action_id == "tenant.scheduler.pause":
        return not bool(resource_state.get("scheduler_paused"))
    if action_id == "tenant.scheduler.resume":
        return bool(resource_state.get("scheduler_paused"))
    if action_id == "approval.reject":
        return (
            resource_state.get("approval_state") == "pending"
            and resource_state.get("approval_kind") in _SAFE_REJECT_APPROVAL_KINDS
        )
    return False


def tenant_detail_candidate_actions(
    automation_paused: bool,
    scheduler_paused: bool,
) -> list[str]:
    candidates: list[str] = []
    if not automation_paused:
        candidates.append("tenant.pause_automation")
    if automation_paused:
        candidates.append("tenant.resume_automation")
    if not scheduler_paused:
        candidates.append("tenant.scheduler.pause")
    if scheduler_paused:
        candidates.append("tenant.scheduler.resume")
    return candidates


def needs_help_candidate_actions(item: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    if item.get("source_type") == "approval" and item.get("_approval_id"):
        candidates.append("approval.reject")
    return candidates


def load_approval_resource_state(
    db: Session,
    tenant_id: str,
    approval_id: str,
) -> dict[str, Any]:
    record = ApprovalRequestRepository.get_by_approval_id(
        db=db, tenant_id=tenant_id, approval_id=approval_id,
    )
    if record is None:
        return {}
    return {
        "approval_state": record.state,
        "approval_kind": record.next_on_approve or "",
        "approval_id": approval_id,
    }


def _finalize_response(
    *,
    action_id: str,
    tenant_id: str,
    resource_id: str | None,
    status: Literal["completed", "no_change"],
    changed: bool,
    message: str,
    audit_event_id: str | None,
    completed_at: datetime,
) -> OperatorActionResponse:
    return OperatorActionResponse(
        action_id=action_id,
        tenant_id=tenant_id,
        resource_id=resource_id,
        status=status,
        changed=changed,
        message=message,
        executed_at=completed_at,
        audit_event_id=audit_event_id,
    )


def execute_pause_automation(
    db: Session,
    tenant_id: str,
    *,
    operator: OperatorIdentity,
    reason: str,
    idempotency_key: str | None,
) -> OperatorActionResponse:
    action_id = "tenant.pause_automation"
    requested_at = _utcnow()
    record = _tenant_record(db, tenant_id)
    before = _sanitize_state(record.settings)
    if before["automation_paused"]:
        completed_at = _utcnow()
        audit_id = _write_operator_audit(
            db,
            tenant_id=tenant_id,
            action_id=action_id,
            status="no_change",
            operator=operator,
            reason=reason,
            idempotency_key=idempotency_key,
            resource_type="tenant",
            resource_id=None,
            changed=False,
            result="no_change",
            before_state=before,
            after_state=before,
            requested_at=requested_at,
            completed_at=completed_at,
        )
        return _finalize_response(
            action_id=action_id,
            tenant_id=tenant_id,
            resource_id=None,
            status="no_change",
            changed=False,
            message="Tenantens automation är redan pausad.",
            audit_event_id=audit_id,
            completed_at=completed_at,
        )

    settings = dict(record.settings or {})
    automation = _get_automation(settings)
    automation["demo_mode"] = True
    settings["automation"] = automation
    TenantConfigRepository.update_settings(db, tenant_id, settings)
    after = _sanitize_state(settings)
    completed_at = _utcnow()
    audit_id = _write_operator_audit(
        db,
        tenant_id=tenant_id,
        action_id=action_id,
        status="completed",
        operator=operator,
        reason=reason,
        idempotency_key=idempotency_key,
        resource_type="tenant",
        resource_id=None,
        changed=True,
        result="completed",
        before_state=before,
        after_state=after,
        requested_at=requested_at,
        completed_at=completed_at,
    )
    return _finalize_response(
        action_id=action_id,
        tenant_id=tenant_id,
        resource_id=None,
        status="completed",
        changed=True,
        message="Tenantens automation är pausad.",
        audit_event_id=audit_id,
        completed_at=completed_at,
    )


def execute_resume_automation(
    db: Session,
    tenant_id: str,
    *,
    operator: OperatorIdentity,
    reason: str,
    idempotency_key: str | None,
) -> OperatorActionResponse:
    action_id = "tenant.resume_automation"
    requested_at = _utcnow()
    record = _tenant_record(db, tenant_id)
    before = _sanitize_state(record.settings)
    if not before["automation_paused"]:
        completed_at = _utcnow()
        audit_id = _write_operator_audit(
            db,
            tenant_id=tenant_id,
            action_id=action_id,
            status="no_change",
            operator=operator,
            reason=reason,
            idempotency_key=idempotency_key,
            resource_type="tenant",
            resource_id=None,
            changed=False,
            result="no_change",
            before_state=before,
            after_state=before,
            requested_at=requested_at,
            completed_at=completed_at,
        )
        return _finalize_response(
            action_id=action_id,
            tenant_id=tenant_id,
            resource_id=None,
            status="no_change",
            changed=False,
            message="Tenantens automation är redan aktiv.",
            audit_event_id=audit_id,
            completed_at=completed_at,
        )

    settings = dict(record.settings or {})
    automation = _get_automation(settings)
    automation["demo_mode"] = False
    settings["automation"] = automation
    TenantConfigRepository.update_settings(db, tenant_id, settings)
    after = _sanitize_state(settings)
    completed_at = _utcnow()
    audit_id = _write_operator_audit(
        db,
        tenant_id=tenant_id,
        action_id=action_id,
        status="completed",
        operator=operator,
        reason=reason,
        idempotency_key=idempotency_key,
        resource_type="tenant",
        resource_id=None,
        changed=True,
        result="completed",
        before_state=before,
        after_state=after,
        requested_at=requested_at,
        completed_at=completed_at,
    )
    return _finalize_response(
        action_id=action_id,
        tenant_id=tenant_id,
        resource_id=None,
        status="completed",
        changed=True,
        message="Tenantens automation är återupptagen.",
        audit_event_id=audit_id,
        completed_at=completed_at,
    )


def execute_pause_scheduler(
    db: Session,
    tenant_id: str,
    *,
    operator: OperatorIdentity,
    reason: str,
    idempotency_key: str | None,
) -> OperatorActionResponse:
    action_id = "tenant.scheduler.pause"
    requested_at = _utcnow()
    record = _tenant_record(db, tenant_id)
    before = _sanitize_state(record.settings)
    if before["scheduler_paused"]:
        completed_at = _utcnow()
        audit_id = _write_operator_audit(
            db,
            tenant_id=tenant_id,
            action_id=action_id,
            status="no_change",
            operator=operator,
            reason=reason,
            idempotency_key=idempotency_key,
            resource_type="tenant",
            resource_id=None,
            changed=False,
            result="no_change",
            before_state=before,
            after_state=before,
            requested_at=requested_at,
            completed_at=completed_at,
        )
        return _finalize_response(
            action_id=action_id,
            tenant_id=tenant_id,
            resource_id=None,
            status="no_change",
            changed=False,
            message="Schedulern är redan pausad för kunden.",
            audit_event_id=audit_id,
            completed_at=completed_at,
        )

    settings = dict(record.settings or {})
    scheduler = _get_scheduler(settings)
    scheduler["run_mode"] = "paused"
    settings["scheduler"] = scheduler
    TenantConfigRepository.update_settings(db, tenant_id, settings)
    after = _sanitize_state(settings)
    completed_at = _utcnow()
    audit_id = _write_operator_audit(
        db,
        tenant_id=tenant_id,
        action_id=action_id,
        status="completed",
        operator=operator,
        reason=reason,
        idempotency_key=idempotency_key,
        resource_type="tenant",
        resource_id=None,
        changed=True,
        result="completed",
        before_state=before,
        after_state=after,
        requested_at=requested_at,
        completed_at=completed_at,
    )
    return _finalize_response(
        action_id=action_id,
        tenant_id=tenant_id,
        resource_id=None,
        status="completed",
        changed=True,
        message="Schedulern är pausad för kunden.",
        audit_event_id=audit_id,
        completed_at=completed_at,
    )


def execute_resume_scheduler(
    db: Session,
    tenant_id: str,
    *,
    operator: OperatorIdentity,
    reason: str,
    idempotency_key: str | None,
) -> OperatorActionResponse:
    action_id = "tenant.scheduler.resume"
    requested_at = _utcnow()
    record = _tenant_record(db, tenant_id)
    before = _sanitize_state(record.settings)
    if not before["scheduler_paused"]:
        completed_at = _utcnow()
        audit_id = _write_operator_audit(
            db,
            tenant_id=tenant_id,
            action_id=action_id,
            status="no_change",
            operator=operator,
            reason=reason,
            idempotency_key=idempotency_key,
            resource_type="tenant",
            resource_id=None,
            changed=False,
            result="no_change",
            before_state=before,
            after_state=before,
            requested_at=requested_at,
            completed_at=completed_at,
        )
        return _finalize_response(
            action_id=action_id,
            tenant_id=tenant_id,
            resource_id=None,
            status="no_change",
            changed=False,
            message="Schedulern är redan aktiv för kunden.",
            audit_event_id=audit_id,
            completed_at=completed_at,
        )

    settings = dict(record.settings or {})
    scheduler = _get_scheduler(settings)
    scheduler["run_mode"] = "scheduled"
    settings["scheduler"] = scheduler
    TenantConfigRepository.update_settings(db, tenant_id, settings)
    after = _sanitize_state(settings)
    completed_at = _utcnow()
    audit_id = _write_operator_audit(
        db,
        tenant_id=tenant_id,
        action_id=action_id,
        status="completed",
        operator=operator,
        reason=reason,
        idempotency_key=idempotency_key,
        resource_type="tenant",
        resource_id=None,
        changed=True,
        result="completed",
        before_state=before,
        after_state=after,
        requested_at=requested_at,
        completed_at=completed_at,
    )
    return _finalize_response(
        action_id=action_id,
        tenant_id=tenant_id,
        resource_id=None,
        status="completed",
        changed=True,
        message="Schedulern är återupptagen för kunden.",
        audit_event_id=audit_id,
        completed_at=completed_at,
    )


def execute_reject_approval(
    db: Session,
    tenant_id: str,
    approval_id: str,
    *,
    operator: OperatorIdentity,
    reason: str,
    idempotency_key: str | None,
) -> OperatorActionResponse:
    action_id = "approval.reject"
    requested_at = _utcnow()

    record = ApprovalRequestRepository.get_by_approval_id(
        db=db, tenant_id=tenant_id, approval_id=approval_id,
    )
    if record is None:
        raise OperatorActionNotFoundError(
            f"Approval '{approval_id}' not found for tenant '{tenant_id}'."
        )

    approval_kind = record.next_on_approve or ""
    if approval_kind not in _SAFE_REJECT_APPROVAL_KINDS:
        raise OperatorActionValidationError(
            "Approval type is not eligible for safe rejection from the operator panel."
        )

    before = {
        "approval_state": record.state,
        "approval_kind": approval_kind,
        "approval_id": approval_id,
    }

    if record.state != "pending":
        raise OperatorActionConflictError(
            f"Approval is already {record.state}."
        )

    try:
        resolve_dispatch_approval(
            db=db,
            tenant_id=tenant_id,
            approval_id=approval_id,
            actor=operator["id"],
            channel="operator_panel",
            note=reason,
            approved=False,
        )
    except ValueError as exc:
        message = str(exc)
        if "already" in message.lower():
            raise OperatorActionConflictError(message) from exc
        raise OperatorActionValidationError(message) from exc

    after = {**before, "approval_state": "rejected"}
    completed_at = _utcnow()
    audit_id = _write_operator_audit(
        db,
        tenant_id=tenant_id,
        action_id=action_id,
        status="completed",
        operator=operator,
        reason=reason,
        idempotency_key=idempotency_key,
        resource_type="approval",
        resource_id=approval_id,
        changed=True,
        result="completed",
        before_state=before,
        after_state=after,
        requested_at=requested_at,
        completed_at=completed_at,
    )
    return _finalize_response(
        action_id=action_id,
        tenant_id=tenant_id,
        resource_id=approval_id,
        status="completed",
        changed=True,
        message="Dispatch-godkännandet är avslaget.",
        audit_event_id=audit_id,
        completed_at=completed_at,
    )
