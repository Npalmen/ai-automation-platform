"""Operator daily digest (Kapitel 10 Slice 3)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.admin.alerts.models import OperatorDigestRecord
from app.admin.alerts.registry import get_definition
from app.admin.alerts.repository import AlertRepository
from app.admin.alerts.schemas import ACTIVE_ALERT_STATUSES

_SEVERITY_ORDER = {"critical": 0, "high": 1, "warning": 2, "info": 3}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def generate_operator_digest(
    db: Session,
    *,
    digest_date: date | None = None,
    tz_name: str = "Europe/Stockholm",
) -> OperatorDigestRecord:
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc
        tz_name = "UTC"
    local_now = datetime.now(tz)
    target_date = digest_date or local_now.date()
    period_start = datetime.combine(target_date, datetime.min.time(), tzinfo=tz).astimezone(timezone.utc)
    period_end = period_start + timedelta(days=1)

    items: list[dict] = []
    limitation_notes: list[str] = []

    alerts = AlertRepository.list_active_alerts(db)
    alerts_sorted = sorted(
        alerts,
        key=lambda a: (_SEVERITY_ORDER.get(a.severity, 9), a.last_detected_at),
    )
    priority = 1
    for alert in alerts_sorted:
        definition = get_definition(alert.alert_type)
        label = definition.label_sv if definition else alert.alert_type
        details = alert.safe_details or {}
        items.append(
            {
                "priority": priority,
                "kind": "open_alert",
                "title": alert.title,
                "summary": alert.summary,
                "severity": alert.severity,
                "tenant_id": alert.tenant_id,
                "alert_id": alert.id,
                "link": f"/ops/alerts/{alert.id}",
                "age_hours": max(
                    0,
                    int((_utcnow() - _ensure_aware(alert.last_detected_at)).total_seconds() // 3600),
                ),
            }
        )
        priority += 1

    resolved_since = (
        db.query(OperatorDigestRecord)
        .order_by(OperatorDigestRecord.generated_at.desc())
        .first()
    )
    # Resolved alerts in period from operator_alerts
    from app.admin.alerts.models import OperatorAlertRecord

    resolved = (
        db.query(OperatorAlertRecord)
        .filter(
            OperatorAlertRecord.status == "resolved",
            OperatorAlertRecord.resolved_at >= period_start,
            OperatorAlertRecord.resolved_at < period_end,
        )
        .order_by(OperatorAlertRecord.resolved_at.desc())
        .limit(20)
        .all()
    )
    for alert in resolved:
        items.append(
            {
                "priority": priority,
                "kind": "resolved_alert",
                "title": alert.title,
                "summary": alert.resolution_reason or "Resolved",
                "severity": alert.severity,
                "tenant_id": alert.tenant_id,
                "alert_id": alert.id,
                "link": f"/ops/alerts/{alert.id}",
                "age_hours": None,
            }
        )
        priority += 1

    if not items:
        limitation_notes.append("Inga öppna eller nyligen lösta larm i perioden.")

    content = {
        "items": items,
        "limitation_notes": limitation_notes,
        "open_critical_high": sum(
            1 for a in alerts if a.severity in ("critical", "high") and a.status in ACTIVE_ALERT_STATUSES
        ),
    }

    record = OperatorDigestRecord(
        id=str(uuid4()),
        digest_date=target_date,
        timezone=tz_name,
        generated_at=_utcnow(),
        period_start=period_start,
        period_end=period_end,
        content_json=content,
        delivery_status="pending",
        created_at=_utcnow(),
    )
    AlertRepository.add_digest(db, record)
    db.flush()
    return record
