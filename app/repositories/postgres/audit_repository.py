from sqlalchemy.orm import Session

from app.core.audit_models import AuditEvent
from app.repositories.postgres.audit_models import AuditEventRecord


class AuditRepository:

    @staticmethod
    def create_event(db: Session, event: AuditEvent) -> AuditEventRecord:
        record = AuditEventRecord(
            event_id=event.event_id,
            tenant_id=event.tenant_id,
            category=event.category,
            action=event.action,
            status=event.status,
            details=event.details,
            created_at=event.created_at,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    @staticmethod
    def list_events_for_tenant(
        db: Session,
        tenant_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditEventRecord]:
        return (
            db.query(AuditEventRecord)
            .filter_by(tenant_id=tenant_id)
            .order_by(AuditEventRecord.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    @staticmethod
    def list_all_events(
        db: Session,
        limit: int = 200,
        offset: int = 0,
    ) -> list[AuditEventRecord]:
        return (
            db.query(AuditEventRecord)
            .order_by(AuditEventRecord.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    @staticmethod
    def count_events_for_tenant(db: Session, tenant_id: str) -> int:
        return db.query(AuditEventRecord).filter_by(tenant_id=tenant_id).count()

    @staticmethod
    def count_all_events(db: Session) -> int:
        return db.query(AuditEventRecord).count()

    # Aliases used by main.py
    @staticmethod
    def list_events(
        db: Session,
        tenant_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditEventRecord]:
        return AuditRepository.list_events_for_tenant(db, tenant_id, limit=limit, offset=offset)

    @staticmethod
    def count_events(db: Session, tenant_id: str) -> int:
        return AuditRepository.count_events_for_tenant(db, tenant_id)