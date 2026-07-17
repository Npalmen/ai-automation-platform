"""Notification delivery intents (separate from alert lifecycle)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.admin.alerts.models import NotificationDeliveryRecord
from app.admin.alerts.repository import AlertRepository
from app.admin.alerts.schemas import ACTIVE_ALERT_STATUSES
from app.core.settings import Settings

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def operator_alert_email_configured(settings: Settings) -> bool:
    """Email deferred until platform recipient is configured and safe."""
    recipient = getattr(settings, "OPERATOR_ALERT_RECIPIENT", "") or ""
    return bool(recipient.strip())


def enqueue_alert_notifications(db: Session, *, settings: Settings) -> int:
    """Create pending delivery rows for high/critical alerts. Does not send email."""
    if not operator_alert_email_configured(settings):
        return 0
    recipient = settings.OPERATOR_ALERT_RECIPIENT.strip()
    count = 0
    alerts = AlertRepository.list_active_alerts(db)
    hour_bucket = _utcnow().strftime("%Y%m%d%H")
    for alert in alerts:
        if alert.severity not in ("critical", "high"):
            continue
        if alert.status == "snoozed" and alert.snoozed_until and alert.snoozed_until > _utcnow():
            continue
        idempotency = f"{alert.id}:email:{alert.severity}:{hour_bucket}"
        if AlertRepository.get_delivery_by_idempotency(db, idempotency):
            continue
        now = _utcnow()
        delivery = NotificationDeliveryRecord(
            id=str(uuid4()),
            alert_id=alert.id,
            digest_id=None,
            channel="email",
            recipient_ref=recipient,
            status="pending",
            attempt_count=0,
            idempotency_key=idempotency,
            created_at=now,
            updated_at=now,
        )
        AlertRepository.add_delivery(db, delivery)
        count += 1
    return count


def process_pending_deliveries(db: Session, *, settings: Settings) -> dict[str, int]:
    """Attempt delivery for pending rows. Failures do not alter alert state."""
    if not operator_alert_email_configured(settings):
        return {"processed": 0, "sent": 0, "failed": 0, "deferred": 1}

    stats = {"processed": 0, "sent": 0, "failed": 0, "deferred": 0}
    pending = (
        db.query(NotificationDeliveryRecord)
        .filter(NotificationDeliveryRecord.status == "pending")
        .limit(20)
        .all()
    )
    for row in pending:
        stats["processed"] += 1
        try:
            from app.workflows.action_executor import execute_action

            alert = AlertRepository.get_alert(db, row.alert_id) if row.alert_id else None
            subject = f"[Krowolf] {alert.severity if alert else 'alert'}: {alert.title if alert else 'Operator alert'}"
            body = alert.summary if alert else "Operator alert notification."
            execute_action(
                {
                    "type": "send_email",
                    "tenant_id": "PLATFORM",
                    "to": row.recipient_ref,
                    "subject": subject,
                    "body": body,
                },
                db=db,
                settings=settings,
            )
            row.status = "sent"
            row.sent_at = _utcnow()
            row.attempt_count += 1
            stats["sent"] += 1
        except Exception:
            logger.exception("Notification delivery failed for %s", row.id)
            row.status = "failed"
            row.safe_error_code = "delivery_failed"
            row.attempt_count += 1
            stats["failed"] += 1
        row.updated_at = _utcnow()
    db.flush()
    return stats
