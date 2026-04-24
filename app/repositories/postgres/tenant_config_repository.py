from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories.postgres.tenant_config_models import TenantConfigRecord


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
        enabled_job_types: list | None = None,
        allowed_integrations: list | None = None,
        auto_actions: dict | None = None,
    ) -> TenantConfigRecord:
        record = (
            db.query(TenantConfigRecord)
            .filter(TenantConfigRecord.tenant_id == tenant_id)
            .first()
        )
        if record is None:
            record = TenantConfigRecord(tenant_id=tenant_id)
            db.add(record)

        if name is not None:
            record.name = name
        if enabled_job_types is not None:
            record.enabled_job_types = enabled_job_types
        if allowed_integrations is not None:
            record.allowed_integrations = allowed_integrations
        if auto_actions is not None:
            record.auto_actions = auto_actions

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
    def update_settings(db: Session, tenant_id: str, settings: dict) -> TenantConfigRecord:
        record = (
            db.query(TenantConfigRecord)
            .filter(TenantConfigRecord.tenant_id == tenant_id)
            .first()
        )
        if record is None:
            record = TenantConfigRecord(tenant_id=tenant_id)
            db.add(record)
        record.settings = settings
        db.commit()
        db.refresh(record)
        return record

    @staticmethod
    def list_all(db: Session) -> list[TenantConfigRecord]:
        return db.query(TenantConfigRecord).order_by(TenantConfigRecord.tenant_id).all()

    @staticmethod
    def to_dict(record: TenantConfigRecord) -> dict:
        return {
            "name": record.name,
            "enabled_job_types": record.enabled_job_types or [],
            "allowed_integrations": record.allowed_integrations or [],
            "auto_actions": record.auto_actions or {},
        }
