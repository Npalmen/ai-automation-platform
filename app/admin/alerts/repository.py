"""Repository for operator alerts."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.admin.alerts.models import (
    AlertEvaluationRunRecord,
    NotificationDeliveryRecord,
    OperatorAlertRecord,
    OperatorDigestRecord,
)
from app.admin.alerts.schemas import ACTIVE_ALERT_STATUSES


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AlertRepository:
    @staticmethod
    def get_alert(db: Session, alert_id: str) -> OperatorAlertRecord | None:
        return db.query(OperatorAlertRecord).filter(OperatorAlertRecord.id == alert_id).first()

    @staticmethod
    def get_active_by_dedup_key(db: Session, deduplication_key: str) -> OperatorAlertRecord | None:
        return (
            db.query(OperatorAlertRecord)
            .filter(
                OperatorAlertRecord.deduplication_key == deduplication_key,
                OperatorAlertRecord.status.in_(tuple(ACTIVE_ALERT_STATUSES)),
            )
            .first()
        )

    @staticmethod
    def list_alerts(
        db: Session,
        *,
        status: list[str] | None = None,
        severity: list[str] | None = None,
        tenant_id: str | None = None,
        alert_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[OperatorAlertRecord], int]:
        q = db.query(OperatorAlertRecord)
        if status:
            q = q.filter(OperatorAlertRecord.status.in_(status))
        if severity:
            q = q.filter(OperatorAlertRecord.severity.in_(severity))
        if tenant_id is not None:
            q = q.filter(OperatorAlertRecord.tenant_id == tenant_id)
        if alert_type:
            q = q.filter(OperatorAlertRecord.alert_type == alert_type)
        total = q.count()
        items = (
            q.order_by(
                OperatorAlertRecord.severity.desc(),
                OperatorAlertRecord.last_detected_at.desc(),
            )
            .offset(offset)
            .limit(limit)
            .all()
        )
        return items, total

    @staticmethod
    def count_open_by_severity(db: Session) -> dict[str, int]:
        counts = {s: 0 for s in ("critical", "high", "warning", "info")}
        rows = (
            db.query(OperatorAlertRecord.severity, OperatorAlertRecord.id)
            .filter(OperatorAlertRecord.status.in_(tuple(ACTIVE_ALERT_STATUSES)))
            .all()
        )
        for sev, _ in rows:
            if sev in counts:
                counts[sev] += 1
        return counts

    @staticmethod
    def list_active_alerts(db: Session) -> list[OperatorAlertRecord]:
        return (
            db.query(OperatorAlertRecord)
            .filter(OperatorAlertRecord.status.in_(tuple(ACTIVE_ALERT_STATUSES)))
            .all()
        )

    @staticmethod
    def list_open_alerts_by_type(
        db: Session, alert_type: str, *, tenant_id: str | None = None
    ) -> list[OperatorAlertRecord]:
        q = db.query(OperatorAlertRecord).filter(
            OperatorAlertRecord.alert_type == alert_type,
            OperatorAlertRecord.status.in_(tuple(ACTIVE_ALERT_STATUSES)),
        )
        if tenant_id is not None:
            q = q.filter(OperatorAlertRecord.tenant_id == tenant_id)
        return q.all()

    @staticmethod
    def add_alert(db: Session, record: OperatorAlertRecord) -> OperatorAlertRecord:
        db.add(record)
        db.flush()
        return record

    @staticmethod
    def get_latest_evaluation_run(db: Session) -> AlertEvaluationRunRecord | None:
        return (
            db.query(AlertEvaluationRunRecord)
            .order_by(AlertEvaluationRunRecord.started_at.desc())
            .first()
        )

    @staticmethod
    def add_evaluation_run(db: Session, record: AlertEvaluationRunRecord) -> AlertEvaluationRunRecord:
        db.add(record)
        db.flush()
        return record

    @staticmethod
    def get_digest(db: Session, digest_id: str) -> OperatorDigestRecord | None:
        return db.query(OperatorDigestRecord).filter(OperatorDigestRecord.id == digest_id).first()

    @staticmethod
    def list_digests(db: Session, *, limit: int = 30) -> list[OperatorDigestRecord]:
        return (
            db.query(OperatorDigestRecord)
            .order_by(OperatorDigestRecord.digest_date.desc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def add_digest(db: Session, record: OperatorDigestRecord) -> OperatorDigestRecord:
        db.add(record)
        db.flush()
        return record

    @staticmethod
    def add_delivery(db: Session, record: NotificationDeliveryRecord) -> NotificationDeliveryRecord:
        db.add(record)
        db.flush()
        return record

    @staticmethod
    def get_delivery_by_idempotency(
        db: Session, idempotency_key: str
    ) -> NotificationDeliveryRecord | None:
        return (
            db.query(NotificationDeliveryRecord)
            .filter(NotificationDeliveryRecord.idempotency_key == idempotency_key)
            .first()
        )

    @staticmethod
    def lookup_active_alert_for_source(
        db: Session,
        *,
        tenant_id: str | None,
        source_type: str,
        source_id: str,
    ) -> OperatorAlertRecord | None:
        alerts = AlertRepository.list_active_alerts(db)
        for alert in alerts:
            details = alert.safe_details or {}
            if details.get("source_type") == source_type and details.get("source_id") == source_id:
                if tenant_id is None or alert.tenant_id == tenant_id:
                    return alert
        return None
