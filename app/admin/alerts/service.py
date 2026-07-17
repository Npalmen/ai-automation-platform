"""Operator alerts API service layer (Kapitel 10)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.admin.alerts.digest_service import generate_operator_digest
from app.admin.alerts.evaluation_service import run_alert_evaluation
from app.admin.alerts.lifecycle import (
    AlertConflictError,
    AlertValidationError,
    acknowledge_alert,
    record_to_detail_dict,
    resolve_alert,
    snooze_alert,
    suppress_alert,
)
from app.admin.alerts.notification_service import (
    operator_alert_email_configured,
    process_pending_deliveries,
)
from app.admin.alerts.registry import ALERT_REGISTRY, get_definition
from app.admin.alerts.repository import AlertRepository
from app.admin.alerts.schemas import (
    AlertDetail,
    AlertEvaluationRunResponse,
    AlertEvaluationStatusResponse,
    AlertListItem,
    AlertListResponse,
    AlertRegistryItem,
    AlertRegistryResponse,
    AlertSummaryResponse,
    AlertWriteResponse,
    OperatorDigestListResponse,
    OperatorDigestResponse,
)
from app.core.admin_session import OperatorIdentity
from app.core.settings import Settings

_WRITE_ROLES = frozenset({"operations", "admin"})
_ADMIN_ROLES = frozenset({"admin"})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def list_alerts(
    db: Session,
    *,
    status: list[str] | None = None,
    severity: list[str] | None = None,
    tenant_id: str | None = None,
    alert_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> AlertListResponse:
    items, total = AlertRepository.list_alerts(
        db,
        status=status,
        severity=severity,
        tenant_id=tenant_id,
        alert_type=alert_type,
        limit=limit,
        offset=offset,
    )
    out: list[AlertListItem] = []
    for alert in items:
        definition = get_definition(alert.alert_type)
        out.append(
            AlertListItem(
                **record_to_detail_dict(alert, label=definition.label_sv if definition else alert.alert_type)
            )
        )
    return AlertListResponse(
        generated_at=_utcnow(),
        total=total,
        items=out,
        limit=limit,
        offset=offset,
    )


def get_alert_summary(db: Session) -> AlertSummaryResponse:
    counts = AlertRepository.count_open_by_severity(db)
    last_run = AlertRepository.get_latest_evaluation_run(db)
    return AlertSummaryResponse(
        generated_at=_utcnow(),
        open_critical=counts.get("critical", 0),
        open_high=counts.get("high", 0),
        open_warning=counts.get("warning", 0),
        open_info=counts.get("info", 0),
        total_open=sum(counts.values()),
        last_evaluation_at=last_run.completed_at if last_run else None,
        last_evaluation_status=last_run.status if last_run else None,
    )


def get_alert_detail(db: Session, alert_id: str) -> AlertDetail | None:
    alert = AlertRepository.get_alert(db, alert_id)
    if alert is None:
        return None
    definition = get_definition(alert.alert_type)
    return AlertDetail(
        **record_to_detail_dict(alert, label=definition.label_sv if definition else alert.alert_type)
    )


def get_registry() -> AlertRegistryResponse:
    items = [
        AlertRegistryItem(
            alert_type=d.alert_type,
            label_sv=d.label_sv,
            description_sv=d.description_sv,
            default_severity=d.default_severity,
            scope_type=d.scope_type,
            detection_class=d.detection_class,
            reopen_policy=d.reopen_policy,
            manual_resolve_allowed=d.manual_resolve_allowed,
            suppress_allowed=d.suppress_allowed,
            runbook_ref=d.runbook_ref,
            enabled_by_default=d.enabled_by_default,
            slice=d.slice,
        )
        for d in ALERT_REGISTRY.values()
    ]
    return AlertRegistryResponse(registry_version="1", items=items)


def acknowledge(
    db: Session,
    *,
    alert_id: str,
    operator: OperatorIdentity,
    version: int,
    reason: str | None,
) -> AlertWriteResponse:
    alert = AlertRepository.get_alert(db, alert_id)
    if alert is None:
        raise AlertValidationError("Alert not found.")
    acknowledge_alert(db, alert, operator_id=operator["id"], version=version)
    db.commit()
    definition = get_definition(alert.alert_type)
    return AlertWriteResponse(
        alert=AlertDetail(
            **record_to_detail_dict(alert, label=definition.label_sv if definition else alert.alert_type)
        )
    )


def snooze(
    db: Session,
    *,
    alert_id: str,
    operator: OperatorIdentity,
    version: int,
    snoozed_until: datetime,
    reason: str | None,
) -> AlertWriteResponse:
    alert = AlertRepository.get_alert(db, alert_id)
    if alert is None:
        raise AlertValidationError("Alert not found.")
    snooze_alert(
        db,
        alert,
        operator_id=operator["id"],
        version=version,
        snoozed_until=snoozed_until,
    )
    db.commit()
    definition = get_definition(alert.alert_type)
    return AlertWriteResponse(
        alert=AlertDetail(
            **record_to_detail_dict(alert, label=definition.label_sv if definition else alert.alert_type)
        )
    )


def resolve(
    db: Session,
    *,
    alert_id: str,
    operator: OperatorIdentity,
    version: int,
    reason: str,
) -> AlertWriteResponse:
    alert = AlertRepository.get_alert(db, alert_id)
    if alert is None:
        raise AlertValidationError("Alert not found.")
    definition = get_definition(alert.alert_type)
    resolve_alert(
        db,
        alert,
        operator_id=operator["id"],
        version=version,
        reason=reason,
        definition=definition,
    )
    db.commit()
    return AlertWriteResponse(
        alert=AlertDetail(
            **record_to_detail_dict(alert, label=definition.label_sv if definition else alert.alert_type)
        )
    )


def suppress(
    db: Session,
    *,
    alert_id: str,
    operator: OperatorIdentity,
    version: int,
    reason: str,
    expires_at: datetime | None,
) -> AlertWriteResponse:
    alert = AlertRepository.get_alert(db, alert_id)
    if alert is None:
        raise AlertValidationError("Alert not found.")
    definition = get_definition(alert.alert_type)
    suppress_alert(
        db,
        alert,
        operator_id=operator["id"],
        version=version,
        reason=reason,
        expires_at=expires_at,
        definition=definition,
    )
    db.commit()
    return AlertWriteResponse(
        alert=AlertDetail(
            **record_to_detail_dict(alert, label=definition.label_sv if definition else alert.alert_type)
        )
    )


def run_evaluation(
    db: Session,
    *,
    operator: OperatorIdentity,
    settings: Settings,
    dry_run: bool = False,
    scope: str = "platform",
    max_slice: int = 3,
) -> AlertEvaluationRunResponse:
    result = run_alert_evaluation(
        db,
        settings=settings,
        dry_run=dry_run,
        scope=scope,
        max_slice=max_slice,
        operator_id=operator["id"],
    )
    return AlertEvaluationRunResponse(**result)


def evaluation_status(db: Session) -> AlertEvaluationStatusResponse:
    last = AlertRepository.get_latest_evaluation_run(db)
    if last is None:
        return AlertEvaluationStatusResponse(last_run=None)
    return AlertEvaluationStatusResponse(
        last_run=AlertEvaluationRunResponse(
            run_id=last.run_id,
            status=last.status,
            dry_run=last.dry_run,
            created_count=last.created_count,
            updated_count=last.updated_count,
            resolved_count=last.resolved_count,
            error_count=last.error_count,
            evaluator_results=last.evaluator_results_json or [],
            started_at=last.started_at,
            completed_at=last.completed_at,
        )
    )


def generate_digest(
    db: Session,
    *,
    digest_date: str | None = None,
    timezone: str = "Europe/Stockholm",
) -> OperatorDigestResponse:
    from datetime import date as date_type

    parsed = date_type.fromisoformat(digest_date) if digest_date else None
    record = generate_operator_digest(db, digest_date=parsed, tz_name=timezone)
    db.commit()
    return _digest_to_response(record)


def list_digests(db: Session) -> OperatorDigestListResponse:
    records = AlertRepository.list_digests(db)
    return OperatorDigestListResponse(items=[_digest_to_response(r) for r in records])


def get_digest(db: Session, digest_id: str) -> OperatorDigestResponse | None:
    record = AlertRepository.get_digest(db, digest_id)
    if record is None:
        return None
    return _digest_to_response(record)


def send_digest(db: Session, *, digest_id: str, settings: Settings) -> dict[str, Any]:
    record = AlertRepository.get_digest(db, digest_id)
    if record is None:
        raise AlertValidationError("Digest not found.")
    if operator_alert_email_configured(settings):
        process_pending_deliveries(db, settings=settings)
        record.delivery_status = "deferred_email_unsafe_path"
    else:
        record.delivery_status = "in_app_only"
    db.commit()
    return {"digest_id": digest_id, "delivery_status": record.delivery_status}


def _digest_to_response(record) -> OperatorDigestResponse:
    content = record.content_json or {}
    return OperatorDigestResponse(
        id=record.id,
        digest_date=str(record.digest_date),
        timezone=record.timezone,
        generated_at=record.generated_at,
        period_start=record.period_start,
        period_end=record.period_end,
        delivery_status=record.delivery_status,
        items=content.get("items") or [],
        limitation_notes=content.get("limitation_notes") or [],
    )
