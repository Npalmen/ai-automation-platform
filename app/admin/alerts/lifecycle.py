"""Alert lifecycle: upsert, resolve, acknowledge, snooze (Kapitel 10)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.admin.alerts.audit_events import (
    ALERT_ACKNOWLEDGED,
    ALERT_CREATED,
    ALERT_REDETECTED,
    ALERT_RESOLVED,
    ALERT_SNOOZED,
    ALERT_SUPPRESSED,
    write_operator_alert_audit,
)
from app.admin.alerts.models import OperatorAlertRecord
from app.admin.alerts.registry import AlertDefinition, get_definition
from app.admin.alerts.repository import AlertRepository
from app.admin.alerts.schemas import ACTIVE_ALERT_STATUSES


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class AlertCandidate:
    alert_type: str
    deduplication_key: str
    scope_type: str
    tenant_id: str | None
    related_job_id: str | None
    integration_key: str | None
    severity: str
    title: str
    summary: str
    safe_details: dict[str, Any]
    source_class: str
    current_fingerprint: str


class AlertConflictError(Exception):
    """Optimistic locking conflict."""


class AlertValidationError(Exception):
    """Invalid lifecycle transition."""


def _age_hours(dt: datetime | None) -> int | None:
    if dt is None:
        return None
    return max(0, int((_utcnow() - dt).total_seconds() // 3600))


def apply_candidate(
    db: Session,
    candidate: AlertCandidate,
    *,
    definition: AlertDefinition,
    dry_run: bool,
) -> tuple[str, OperatorAlertRecord | None]:
    """Returns action: created|updated|reopened|unchanged and record."""
    now = _utcnow()
    existing = AlertRepository.get_active_by_dedup_key(db, candidate.deduplication_key)

    if existing is None:
        resolved = (
            db.query(OperatorAlertRecord)
            .filter(
                OperatorAlertRecord.deduplication_key == candidate.deduplication_key,
                OperatorAlertRecord.status == "resolved",
            )
            .order_by(OperatorAlertRecord.resolved_at.desc())
            .first()
        )
        if resolved is not None:
            if _should_reopen(resolved, candidate, definition, now):
                if dry_run:
                    return "reopened", resolved
                return _reopen_alert(db, resolved, candidate, definition, now)
        if dry_run:
            return "created", None
        record = OperatorAlertRecord(
            id=str(uuid4()),
            alert_type=candidate.alert_type,
            deduplication_key=candidate.deduplication_key,
            scope_type=candidate.scope_type,
            tenant_id=candidate.tenant_id,
            related_job_id=candidate.related_job_id,
            integration_key=candidate.integration_key,
            severity=candidate.severity,
            status="open",
            title=candidate.title,
            summary=candidate.summary,
            safe_details=candidate.safe_details,
            source_class=candidate.source_class,
            source_version="1",
            first_detected_at=now,
            last_detected_at=now,
            occurrence_count=1,
            last_evaluated_at=now,
            current_fingerprint=candidate.current_fingerprint,
            created_at=now,
            updated_at=now,
            version=1,
        )
        AlertRepository.add_alert(db, record)
        write_operator_alert_audit(
            db,
            action=ALERT_CREATED,
            tenant_id=candidate.tenant_id,
            details={
                "alert_id": record.id,
                "alert_type": candidate.alert_type,
                "deduplication_key": candidate.deduplication_key,
                "severity": candidate.severity,
            },
        )
        return "created", record

    if dry_run:
        return "updated", existing

    existing.last_detected_at = now
    existing.last_evaluated_at = now
    existing.occurrence_count += 1
    existing.current_fingerprint = candidate.current_fingerprint
    existing.summary = candidate.summary
    existing.safe_details = candidate.safe_details
    existing.updated_at = now
    if _severity_rank(candidate.severity) > _severity_rank(existing.severity):
        existing.severity = candidate.severity
  # unsnooze if expired
    if existing.status == "snoozed" and existing.snoozed_until and existing.snoozed_until <= now:
        existing.status = "open"
        existing.snoozed_until = None
    db.flush()
    write_operator_alert_audit(
        db,
        action=ALERT_REDETECTED,
        tenant_id=existing.tenant_id,
        details={
            "alert_id": existing.id,
            "alert_type": existing.alert_type,
            "deduplication_key": existing.deduplication_key,
            "severity": existing.severity,
        },
    )
    return "updated", existing


def _severity_rank(severity: str) -> int:
    return {"info": 0, "warning": 1, "high": 2, "critical": 3}.get(severity, 0)


def _should_reopen(
    resolved: OperatorAlertRecord,
    candidate: AlertCandidate,
    definition: AlertDefinition,
    now: datetime,
) -> bool:
    if definition.reopen_policy == "never_reopen":
        return False
    if resolved.resolved_at is None:
        return True
    grace = timedelta(minutes=definition.reopen_grace_minutes)
    if (
        resolved.current_fingerprint == candidate.current_fingerprint
        and (now - resolved.resolved_at) < grace
    ):
        return False
    return True


def _reopen_alert(
    db: Session,
    resolved: OperatorAlertRecord,
    candidate: AlertCandidate,
    definition: AlertDefinition,
    now: datetime,
) -> tuple[str, OperatorAlertRecord]:
    if definition.reopen_policy == "create_new_after_grace":
        record = OperatorAlertRecord(
            id=str(uuid4()),
            alert_type=candidate.alert_type,
            deduplication_key=candidate.deduplication_key,
            scope_type=candidate.scope_type,
            tenant_id=candidate.tenant_id,
            related_job_id=candidate.related_job_id,
            integration_key=candidate.integration_key,
            severity=candidate.severity,
            status="open",
            title=candidate.title,
            summary=candidate.summary,
            safe_details=candidate.safe_details,
            source_class=candidate.source_class,
            source_version="1",
            first_detected_at=now,
            last_detected_at=now,
            occurrence_count=1,
            last_evaluated_at=now,
            current_fingerprint=candidate.current_fingerprint,
            created_at=now,
            updated_at=now,
            version=1,
        )
        AlertRepository.add_alert(db, record)
        write_operator_alert_audit(
            db,
            action=ALERT_CREATED,
            tenant_id=candidate.tenant_id,
            details={
                "alert_id": record.id,
                "alert_type": candidate.alert_type,
                "deduplication_key": candidate.deduplication_key,
                "severity": candidate.severity,
            },
        )
        return "created", record

    resolved.status = "open"
    resolved.resolved_at = None
    resolved.resolution_reason = None
    resolved.last_detected_at = now
    resolved.last_evaluated_at = now
    resolved.occurrence_count += 1
    resolved.current_fingerprint = candidate.current_fingerprint
    resolved.summary = candidate.summary
    resolved.safe_details = candidate.safe_details
    resolved.updated_at = now
    resolved.version += 1
    db.flush()
    write_operator_alert_audit(
        db,
        action=ALERT_REDETECTED,
        tenant_id=resolved.tenant_id,
        details={
            "alert_id": resolved.id,
            "alert_type": resolved.alert_type,
            "deduplication_key": resolved.deduplication_key,
            "severity": resolved.severity,
            "status": "reopened",
        },
    )
    return "reopened", resolved


def auto_resolve_missing(
    db: Session,
    *,
    alert_type: str,
    active_keys: set[str],
    dry_run: bool,
) -> int:
    """Resolve active alerts of type whose dedup keys are not in active_keys."""
    count = 0
    alerts = AlertRepository.list_open_alerts_by_type(db, alert_type)
    for alert in alerts:
        if alert.deduplication_key not in active_keys:
            if dry_run:
                count += 1
                continue
            alert.status = "resolved"
            alert.resolved_at = _utcnow()
            alert.resolution_reason = "auto_resolved_condition_cleared"
            alert.updated_at = _utcnow()
            alert.version += 1
            count += 1
    if not dry_run:
        db.flush()
    return count


def acknowledge_alert(
    db: Session,
    alert: OperatorAlertRecord,
    *,
    operator_id: str,
    version: int,
) -> OperatorAlertRecord:
    if alert.version != version:
        raise AlertConflictError("Stale alert version.")
    if alert.status not in ACTIVE_ALERT_STATUSES:
        raise AlertValidationError("Alert is not active.")
    now = _utcnow()
    alert.status = "acknowledged"
    alert.acknowledged_at = now
    alert.acknowledged_by = operator_id
    alert.updated_at = now
    alert.version += 1
    db.flush()
    write_operator_alert_audit(
        db,
        action=ALERT_ACKNOWLEDGED,
        tenant_id=alert.tenant_id,
        details={"alert_id": alert.id, "alert_type": alert.alert_type},
    )
    return alert


def snooze_alert(
    db: Session,
    alert: OperatorAlertRecord,
    *,
    operator_id: str,
    version: int,
    snoozed_until: datetime,
) -> OperatorAlertRecord:
    if alert.version != version:
        raise AlertConflictError("Stale alert version.")
    if alert.status not in ("open", "acknowledged"):
        raise AlertValidationError("Only open or acknowledged alerts can be snoozed.")
    alert.status = "snoozed"
    alert.snoozed_until = snoozed_until
    alert.acknowledged_by = operator_id
    alert.updated_at = _utcnow()
    alert.version += 1
    db.flush()
    write_operator_alert_audit(
        db,
        action=ALERT_SNOOZED,
        tenant_id=alert.tenant_id,
        details={"alert_id": alert.id, "alert_type": alert.alert_type},
    )
    return alert


def resolve_alert(
    db: Session,
    alert: OperatorAlertRecord,
    *,
    operator_id: str,
    version: int,
    reason: str,
    definition: AlertDefinition | None,
) -> OperatorAlertRecord:
    if alert.version != version:
        raise AlertConflictError("Stale alert version.")
    if definition and not definition.manual_resolve_allowed:
        raise AlertValidationError("Manual resolve not allowed for this alert type.")
    alert.status = "resolved"
    alert.resolved_at = _utcnow()
    alert.resolution_reason = reason
    alert.acknowledged_by = operator_id
    alert.updated_at = _utcnow()
    alert.version += 1
    db.flush()
    write_operator_alert_audit(
        db,
        action=ALERT_RESOLVED,
        tenant_id=alert.tenant_id,
        details={"alert_id": alert.id, "alert_type": alert.alert_type},
    )
    return alert


def suppress_alert(
    db: Session,
    alert: OperatorAlertRecord,
    *,
    operator_id: str,
    version: int,
    reason: str,
    expires_at: datetime | None,
    definition: AlertDefinition | None,
) -> OperatorAlertRecord:
    if definition and not definition.suppress_allowed:
        raise AlertValidationError("Suppress not allowed for this alert type.")
    if alert.version != version:
        raise AlertConflictError("Stale alert version.")
    alert.status = "suppressed"
    alert.resolution_reason = reason
    alert.snoozed_until = expires_at
    alert.acknowledged_by = operator_id
    alert.updated_at = _utcnow()
    alert.version += 1
    db.flush()
    write_operator_alert_audit(
        db,
        action=ALERT_SUPPRESSED,
        tenant_id=alert.tenant_id,
        details={"alert_id": alert.id, "alert_type": alert.alert_type},
    )
    return alert


def record_to_detail_dict(alert: OperatorAlertRecord, *, label: str) -> dict:
    details = alert.safe_details or {}
    return {
        "id": alert.id,
        "alert_type": alert.alert_type,
        "alert_type_label": label,
        "scope_type": alert.scope_type,
        "tenant_id": alert.tenant_id,
        "related_job_id": alert.related_job_id,
        "integration_key": alert.integration_key,
        "severity": alert.severity,
        "status": alert.status,
        "title": alert.title,
        "summary": alert.summary,
        "source_class": alert.source_class,
        "first_detected_at": alert.first_detected_at,
        "last_detected_at": alert.last_detected_at,
        "occurrence_count": alert.occurrence_count,
        "age_hours": _age_hours(alert.last_detected_at),
        "version": alert.version,
        "safe_details": details,
        "source": alert.source,
        "source_version": alert.source_version,
        "last_evaluated_at": alert.last_evaluated_at,
        "acknowledged_at": alert.acknowledged_at,
        "acknowledged_by": alert.acknowledged_by,
        "snoozed_until": alert.snoozed_until,
        "resolved_at": alert.resolved_at,
        "resolution_reason": alert.resolution_reason,
        "runbook_ref": details.get("runbook_ref"),
        "recommended_action": details.get("recommended_action"),
    }
