from __future__ import annotations

import copy
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.repositories.postgres.tenant_config_models import TenantConfigRecord


def _deep_merge(base: dict, override: dict) -> None:
    """Recursively merge *override* into *base* in-place."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


class TenantConfigRepository:
    @staticmethod
    def get(db: Session, tenant_id: str) -> TenantConfigRecord | None:
        return (
            db.query(TenantConfigRecord)
            .filter(TenantConfigRecord.tenant_id == tenant_id)
            .first()
        )

    @staticmethod
    def upsert(
        db: Session,
        tenant_id: str,
        name: str | None = None,
        slug: str | None = None,
        status: str | None = None,
        enabled_job_types: list | None = None,
        allowed_integrations: list | None = None,
        auto_actions: dict | None = None,
    ) -> TenantConfigRecord:
        now = datetime.now(timezone.utc)
        record = (
            db.query(TenantConfigRecord)
            .filter(TenantConfigRecord.tenant_id == tenant_id)
            .first()
        )
        if record is None:
            record = TenantConfigRecord(tenant_id=tenant_id, created_at=now)
            db.add(record)

        if name is not None:
            record.name = name
        if slug is not None:
            record.slug = slug
        if status is not None:
            record.status = status
        if enabled_job_types is not None:
            record.enabled_job_types = enabled_job_types
        if allowed_integrations is not None:
            record.allowed_integrations = allowed_integrations
        if auto_actions is not None:
            record.auto_actions = auto_actions

        record.updated_at = now
        db.commit()
        db.refresh(record)
        return record

    @staticmethod
    def get_settings(db: Session, tenant_id: str) -> dict:
        record = (
            db.query(TenantConfigRecord)
            .filter(TenantConfigRecord.tenant_id == tenant_id)
            .first()
        )
        return (record.settings or {}) if record else {}

    @staticmethod
    def update_settings(db: Session, tenant_id: str, settings: dict, merge: bool = True) -> TenantConfigRecord:
        """Persist settings for a tenant.

        When *merge* is True (default) the incoming dict is deep-merged into the
        existing settings so callers that only update a sub-section (e.g. the
        Control Panel updating ``automation``) do not accidentally erase other
        top-level keys such as ``memory``, ``workflow_scan``, or
        ``notifications``.
        """
        now = datetime.now(timezone.utc)
        record = (
            db.query(TenantConfigRecord)
            .filter(TenantConfigRecord.tenant_id == tenant_id)
            .first()
        )
        if record is None:
            record = TenantConfigRecord(tenant_id=tenant_id, created_at=now)
            db.add(record)
        if merge:
            # Deep-copy so nested JSON mutations are not lost and SQLAlchemy
            # detects the assignment as a change.
            existing = copy.deepcopy(record.settings or {})
            _deep_merge(existing, settings)
            record.settings = existing
        else:
            record.settings = copy.deepcopy(settings)
        flag_modified(record, "settings")
        record.updated_at = now
        db.commit()
        db.refresh(record)
        return record

    @staticmethod
    def list_all(db: Session) -> list[TenantConfigRecord]:
        return db.query(TenantConfigRecord).order_by(TenantConfigRecord.tenant_id).all()

    @staticmethod
    def to_dict(record: TenantConfigRecord) -> dict:
        return {
            "tenant_id": record.tenant_id,
            "name": record.name,
            "slug": record.slug,
            "status": record.status or "active",
            "enabled_job_types": record.enabled_job_types or [],
            "allowed_integrations": record.allowed_integrations or [],
            "auto_actions": record.auto_actions or {},
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        }
