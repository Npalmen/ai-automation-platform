"""Repository for operator incident management (Kapitel 6)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import func, or_, update
from sqlalchemy.orm import Session

from app.admin.incident_models import (
    IncidentRecord,
    IncidentSignalRecord,
    IncidentTenantRecord,
    IncidentTimelineEventRecord,
)


class IncidentNotFoundError(Exception):
    """Incident does not exist."""


class IncidentConflictError(Exception):
    """Incident write conflict (version mismatch, closed, duplicate link, etc.)."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_incident_id() -> str:
    return f"INC_{uuid4()}"


def _new_event_id() -> str:
    return str(uuid4())


class IncidentRepository:
    @staticmethod
    def get_incident(db: Session, incident_id: str) -> IncidentRecord | None:
        return (
            db.query(IncidentRecord)
            .filter(IncidentRecord.incident_id == incident_id)
            .first()
        )

    @staticmethod
    def incident_exists(db: Session, incident_id: str) -> bool:
        return (
            db.query(IncidentRecord.incident_id)
            .filter(IncidentRecord.incident_id == incident_id)
            .first()
            is not None
        )

    @staticmethod
    def create_incident(
        db: Session,
        *,
        title: str,
        description: str | None,
        severity: str,
        created_by: str,
        created_by_display_name: str,
    ) -> IncidentRecord:
        now = _utcnow()
        record = IncidentRecord(
            incident_id=_new_incident_id(),
            title=title,
            description=description,
            severity=severity,
            status="open",
            owner_id=None,
            owner_display_name=None,
            created_by=created_by,
            created_by_display_name=created_by_display_name,
            created_at=now,
            updated_at=now,
            version=1,
        )
        db.add(record)
        db.flush()
        return record

    @staticmethod
    def atomic_update_incident(
        db: Session,
        incident_id: str,
        expected_version: int,
        *,
        values: dict[str, Any],
    ) -> IncidentRecord:
        now = _utcnow()
        payload = {**values, "updated_at": now, "version": IncidentRecord.version + 1}
        result = db.execute(
            update(IncidentRecord)
            .where(
                IncidentRecord.incident_id == incident_id,
                IncidentRecord.version == expected_version,
            )
            .values(**payload)
        )
        if result.rowcount == 0:
            if not IncidentRepository.incident_exists(db, incident_id):
                raise IncidentNotFoundError(f"Incident '{incident_id}' not found.")
            raise IncidentConflictError(
                "Incidenten har ändrats av någon annan. Ladda om och försök igen."
            )
        db.flush()
        updated = IncidentRepository.get_incident(db, incident_id)
        if updated is None:
            raise IncidentNotFoundError(f"Incident '{incident_id}' not found.")
        return updated

    @staticmethod
    def touch_incident_updated_at(db: Session, incident_id: str) -> None:
        db.execute(
            update(IncidentRecord)
            .where(IncidentRecord.incident_id == incident_id)
            .values(updated_at=_utcnow())
        )
        db.flush()

    @staticmethod
    def add_timeline_event(
        db: Session,
        *,
        incident_id: str,
        event_type: str,
        actor_id: str,
        actor_display_name: str,
        actor_role: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> IncidentTimelineEventRecord:
        record = IncidentTimelineEventRecord(
            event_id=_new_event_id(),
            incident_id=incident_id,
            event_type=event_type,
            actor_id=actor_id,
            actor_display_name=actor_display_name,
            actor_role=actor_role,
            message=message,
            metadata_json=metadata or {},
        )
        db.add(record)
        db.flush()
        return record

    @staticmethod
    def list_timeline(
        db: Session,
        incident_id: str,
    ) -> list[IncidentTimelineEventRecord]:
        return (
            db.query(IncidentTimelineEventRecord)
            .filter(IncidentTimelineEventRecord.incident_id == incident_id)
            .order_by(IncidentTimelineEventRecord.created_at.asc())
            .all()
        )

    @staticmethod
    def list_active_tenants(
        db: Session,
        incident_id: str,
    ) -> list[IncidentTenantRecord]:
        return (
            db.query(IncidentTenantRecord)
            .filter(
                IncidentTenantRecord.incident_id == incident_id,
                IncidentTenantRecord.unlinked_at.is_(None),
            )
            .order_by(IncidentTenantRecord.created_at.asc())
            .all()
        )

    @staticmethod
    def list_all_tenants(
        db: Session,
        incident_id: str,
    ) -> list[IncidentTenantRecord]:
        return (
            db.query(IncidentTenantRecord)
            .filter(IncidentTenantRecord.incident_id == incident_id)
            .order_by(IncidentTenantRecord.created_at.asc())
            .all()
        )

    @staticmethod
    def list_active_signals(
        db: Session,
        incident_id: str,
    ) -> list[IncidentSignalRecord]:
        return (
            db.query(IncidentSignalRecord)
            .filter(
                IncidentSignalRecord.incident_id == incident_id,
                IncidentSignalRecord.unlinked_at.is_(None),
            )
            .order_by(IncidentSignalRecord.linked_at.asc())
            .all()
        )

    @staticmethod
    def list_all_signals(
        db: Session,
        incident_id: str,
    ) -> list[IncidentSignalRecord]:
        return (
            db.query(IncidentSignalRecord)
            .filter(IncidentSignalRecord.incident_id == incident_id)
            .order_by(IncidentSignalRecord.linked_at.asc())
            .all()
        )

    @staticmethod
    def has_active_tenant_link(
        db: Session,
        incident_id: str,
        tenant_id: str,
    ) -> bool:
        return (
            db.query(IncidentTenantRecord.id)
            .filter(
                IncidentTenantRecord.incident_id == incident_id,
                IncidentTenantRecord.tenant_id == tenant_id,
                IncidentTenantRecord.unlinked_at.is_(None),
            )
            .first()
            is not None
        )

    @staticmethod
    def has_active_signal_link(
        db: Session,
        incident_id: str,
        signal_id: str,
    ) -> bool:
        return (
            db.query(IncidentSignalRecord.id)
            .filter(
                IncidentSignalRecord.incident_id == incident_id,
                IncidentSignalRecord.signal_id == signal_id,
                IncidentSignalRecord.unlinked_at.is_(None),
            )
            .first()
            is not None
        )

    @staticmethod
    def link_tenant(
        db: Session,
        *,
        incident_id: str,
        tenant_id: str,
        tenant_name_snapshot: str | None,
    ) -> IncidentTenantRecord:
        if IncidentRepository.has_active_tenant_link(db, incident_id, tenant_id):
            raise IncidentConflictError(
                f"Tenant '{tenant_id}' är redan kopplad till incidenten."
            )
        record = IncidentTenantRecord(
            incident_id=incident_id,
            tenant_id=tenant_id,
            tenant_name_snapshot=tenant_name_snapshot,
            created_at=_utcnow(),
        )
        db.add(record)
        db.flush()
        return record

    @staticmethod
    def unlink_tenant(
        db: Session,
        incident_id: str,
        tenant_id: str,
    ) -> IncidentTenantRecord:
        record = (
            db.query(IncidentTenantRecord)
            .filter(
                IncidentTenantRecord.incident_id == incident_id,
                IncidentTenantRecord.tenant_id == tenant_id,
                IncidentTenantRecord.unlinked_at.is_(None),
            )
            .first()
        )
        if record is None:
            raise IncidentNotFoundError(
                f"Aktiv tenantkoppling '{tenant_id}' hittades inte för incidenten."
            )
        record.unlinked_at = _utcnow()
        db.flush()
        return record

    @staticmethod
    def link_signal(
        db: Session,
        *,
        incident_id: str,
        signal_id: str,
        tenant_id: str,
        source_type: str,
        source_id: str,
        snapshot_title: str,
        snapshot_summary: str,
        snapshot_severity: str,
    ) -> IncidentSignalRecord:
        if IncidentRepository.has_active_signal_link(db, incident_id, signal_id):
            raise IncidentConflictError(
                f"Signal '{signal_id}' är redan kopplad till incidenten."
            )
        record = IncidentSignalRecord(
            incident_id=incident_id,
            signal_id=signal_id,
            tenant_id=tenant_id,
            source_type=source_type,
            source_id=source_id,
            snapshot_title=snapshot_title,
            snapshot_summary=snapshot_summary,
            snapshot_severity=snapshot_severity,
            linked_at=_utcnow(),
        )
        db.add(record)
        db.flush()
        return record

    @staticmethod
    def unlink_signal(
        db: Session,
        incident_id: str,
        signal_id: str,
    ) -> IncidentSignalRecord:
        record = (
            db.query(IncidentSignalRecord)
            .filter(
                IncidentSignalRecord.incident_id == incident_id,
                IncidentSignalRecord.signal_id == signal_id,
                IncidentSignalRecord.unlinked_at.is_(None),
            )
            .first()
        )
        if record is None:
            raise IncidentNotFoundError(
                f"Aktiv signalkoppling '{signal_id}' hittades inte för incidenten."
            )
        record.unlinked_at = _utcnow()
        db.flush()
        return record

    @staticmethod
    def list_incidents(
        db: Session,
        *,
        search: str | None = None,
        status: str | None = None,
        severity: str | None = None,
        tenant_id: str | None = None,
        owner: str | None = None,
        updated_since: datetime | None = None,
        sort: str = "updated_at",
        order: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[IncidentRecord], int]:
        query = db.query(IncidentRecord)

        if search:
            needle = f"%{search.strip().lower()}%"
            query = query.filter(
                or_(
                    func.lower(IncidentRecord.title).like(needle),
                    func.lower(IncidentRecord.description).like(needle),
                    func.lower(IncidentRecord.incident_id).like(needle),
                )
            )
        if status:
            query = query.filter(IncidentRecord.status == status)
        if severity:
            query = query.filter(IncidentRecord.severity == severity)
        if owner:
            query = query.filter(
                or_(
                    IncidentRecord.owner_id == owner,
                    func.lower(IncidentRecord.owner_display_name).like(
                        f"%{owner.strip().lower()}%"
                    ),
                )
            )
        if updated_since:
            query = query.filter(IncidentRecord.updated_at >= updated_since)
        if tenant_id:
            query = query.join(
                IncidentTenantRecord,
                IncidentTenantRecord.incident_id == IncidentRecord.incident_id,
            ).filter(
                IncidentTenantRecord.tenant_id == tenant_id,
                IncidentTenantRecord.unlinked_at.is_(None),
            )

        total = query.count()

        sort_col = {
            "updated_at": IncidentRecord.updated_at,
            "created_at": IncidentRecord.created_at,
            "severity": IncidentRecord.severity,
            "status": IncidentRecord.status,
            "title": IncidentRecord.title,
            "incident_id": IncidentRecord.incident_id,
        }.get(sort, IncidentRecord.updated_at)

        if order.lower() == "asc":
            query = query.order_by(sort_col.asc(), IncidentRecord.incident_id.asc())
        else:
            query = query.order_by(sort_col.desc(), IncidentRecord.incident_id.asc())

        records = query.offset(offset).limit(limit).all()
        return records, total

    @staticmethod
    def count_by_status(db: Session, statuses: set[str]) -> int:
        if not statuses:
            return 0
        return (
            db.query(IncidentRecord)
            .filter(IncidentRecord.status.in_(list(statuses)))
            .count()
        )

    @staticmethod
    def count_critical(db: Session) -> int:
        return (
            db.query(IncidentRecord)
            .filter(IncidentRecord.severity == "critical")
            .count()
        )

    @staticmethod
    def count_affected_tenants(db: Session) -> int:
        result = (
            db.query(func.count(func.distinct(IncidentTenantRecord.tenant_id)))
            .filter(IncidentTenantRecord.unlinked_at.is_(None))
            .scalar()
        )
        return int(result or 0)

    @staticmethod
    def find_linked_incidents_for_signal(
        db: Session,
        signal_id: str,
    ) -> list[IncidentRecord]:
        return (
            db.query(IncidentRecord)
            .join(
                IncidentSignalRecord,
                IncidentSignalRecord.incident_id == IncidentRecord.incident_id,
            )
            .filter(
                IncidentSignalRecord.signal_id == signal_id,
                IncidentSignalRecord.unlinked_at.is_(None),
            )
            .order_by(IncidentRecord.updated_at.desc())
            .all()
        )

    @staticmethod
    def active_tenant_count(db: Session, incident_id: str) -> int:
        return (
            db.query(IncidentTenantRecord)
            .filter(
                IncidentTenantRecord.incident_id == incident_id,
                IncidentTenantRecord.unlinked_at.is_(None),
            )
            .count()
        )

    @staticmethod
    def active_signal_count(db: Session, incident_id: str) -> int:
        return (
            db.query(IncidentSignalRecord)
            .filter(
                IncidentSignalRecord.incident_id == incident_id,
                IncidentSignalRecord.unlinked_at.is_(None),
            )
            .count()
        )
