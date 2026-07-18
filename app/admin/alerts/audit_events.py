"""Allowlisted audit events for operator alerts (Kapitel 10)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

ALERT_CREATED = "alert.created"
ALERT_REDETECTED = "alert.redetected"
ALERT_ACKNOWLEDGED = "alert.acknowledged"
ALERT_SNOOZED = "alert.snoozed"
ALERT_RESOLVED = "alert.resolved"
ALERT_SUPPRESSED = "alert.suppressed"
ALERT_EVALUATION_STARTED = "alert.evaluation_started"
ALERT_EVALUATION_COMPLETED = "alert.evaluation_completed"
ALERT_EVALUATION_EVALUATOR_FAILED = "alert.evaluation_evaluator_failed"
DIGEST_GENERATED = "digest.generated"
NOTIFICATION_QUEUED = "notification.queued"
NOTIFICATION_SENT = "notification.sent"
NOTIFICATION_FAILED = "notification.failed"

ALLOWED_ALERT_AUDIT_ACTIONS = frozenset(
    {
        ALERT_CREATED,
        ALERT_REDETECTED,
        ALERT_ACKNOWLEDGED,
        ALERT_SNOOZED,
        ALERT_RESOLVED,
        ALERT_SUPPRESSED,
        ALERT_EVALUATION_STARTED,
        ALERT_EVALUATION_COMPLETED,
        ALERT_EVALUATION_EVALUATOR_FAILED,
        DIGEST_GENERATED,
        NOTIFICATION_QUEUED,
        NOTIFICATION_SENT,
        NOTIFICATION_FAILED,
    }
)


class OperatorAlertAuditError(Exception):
    """Raised when alert audit write fails or action is not allowlisted."""


def write_operator_alert_audit(
    db: Session,
    *,
    action: str,
    tenant_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    if action not in ALLOWED_ALERT_AUDIT_ACTIONS:
        raise OperatorAlertAuditError(f"Disallowed alert audit action: {action}")
    from app.core.audit_service import create_audit_event

    safe_details: dict[str, Any] = {}
    for key, value in (details or {}).items():
        if key in {
            "alert_id",
            "alert_type",
            "deduplication_key",
            "severity",
            "status",
            "run_id",
            "error_code",
            "evaluator",
            "delivery_id",
        }:
            safe_details[key] = value
    try:
        create_audit_event(
            db=db,
            tenant_id=tenant_id or "platform",
            category="operator_alert",
            action=action,
            status="success",
            details=safe_details,
        )
    except Exception as exc:
        raise OperatorAlertAuditError("operator alert audit write failed") from exc
