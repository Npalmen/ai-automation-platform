"""Tenant resource binding for Monday boards and Google Sheets spreadsheets."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.admin.onboarding.errors import OnboardingConflictError
from app.admin.onboarding.models import TenantResourceBindingRecord


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


RESOURCE_MONDAY_BOARD = "monday_board"
RESOURCE_SHEETS_SPREADSHEET = "google_sheets_spreadsheet"


class ResourceBindingService:
    @staticmethod
    def get_active_binding(
        db: Session,
        *,
        resource_type: str,
        resource_id: str,
    ) -> TenantResourceBindingRecord | None:
        return (
            db.query(TenantResourceBindingRecord)
            .filter(
                TenantResourceBindingRecord.resource_type == resource_type,
                TenantResourceBindingRecord.resource_id == resource_id,
                TenantResourceBindingRecord.status == "active",
            )
            .first()
        )

    @staticmethod
    def bind(
        db: Session,
        *,
        resource_type: str,
        resource_id: str,
        tenant_id: str,
        session_id: str,
        operator_id: str,
    ) -> TenantResourceBindingRecord:
        resource_id = resource_id.strip()
        if not resource_id:
            raise OnboardingConflictError("Resource id is required.", code="resource_invalid")

        existing = ResourceBindingService.get_active_binding(
            db, resource_type=resource_type, resource_id=resource_id
        )
        if existing and existing.tenant_id != tenant_id:
            raise OnboardingConflictError(
                "Resource is already bound to another active tenant.",
                code="resource_already_bound",
            )

        if existing and existing.tenant_id == tenant_id and existing.session_id == session_id:
            return existing

        if existing and existing.tenant_id == tenant_id:
            existing.status = "released"
            existing.released_at = _utcnow()

        record = TenantResourceBindingRecord(
            id=str(uuid4()),
            resource_type=resource_type,
            resource_id=resource_id,
            tenant_id=tenant_id,
            session_id=session_id,
            status="active",
            bound_at=_utcnow(),
            bound_by_operator_id=operator_id,
        )
        db.add(record)
        db.flush()
        return record

    @staticmethod
    def release_for_session(
        db: Session,
        *,
        session_id: str,
        resource_type: str | None = None,
    ) -> None:
        q = db.query(TenantResourceBindingRecord).filter(
            TenantResourceBindingRecord.session_id == session_id,
            TenantResourceBindingRecord.status == "active",
        )
        if resource_type:
            q = q.filter(TenantResourceBindingRecord.resource_type == resource_type)
        now = _utcnow()
        for record in q.all():
            record.status = "released"
            record.released_at = now
        db.flush()

    @staticmethod
    def release_resource(
        db: Session,
        *,
        tenant_id: str,
        resource_type: str,
        resource_id: str,
    ) -> None:
        record = ResourceBindingService.get_active_binding(
            db, resource_type=resource_type, resource_id=resource_id.strip()
        )
        if record and record.tenant_id == tenant_id:
            record.status = "released"
            record.released_at = _utcnow()
            db.flush()
