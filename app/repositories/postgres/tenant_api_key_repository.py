"""Repository for tenant API key management.

Raw API keys are NEVER stored. Only the SHA-256 hex digest is persisted.
The raw key is generated once, returned to the caller, and then discarded.

Key format:  kw_{32 random hex chars}   (35 chars total)
Key hint:    last 4 chars, stored for identification display only.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.repositories.postgres.tenant_api_key_models import TenantApiKeyRecord


def _generate_raw_key() -> str:
    """Generate a cryptographically secure API key."""
    return "kw_" + secrets.token_hex(16)


def _hash_key(raw_key: str) -> str:
    """Return SHA-256 hex digest of the raw key."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


class TenantApiKeyRepository:

    @staticmethod
    def create_key(db: Session, tenant_id: str) -> tuple[str, TenantApiKeyRecord]:
        """Create a new active API key for tenant_id.

        Returns (raw_key, record). raw_key is the only time the secret is visible.
        """
        raw_key = _generate_raw_key()
        record = TenantApiKeyRecord(
            key_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            key_hash=_hash_key(raw_key),
            key_hint=raw_key[-4:],
            is_active=True,
            created_at=datetime.now(timezone.utc),
            revoked_at=None,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return raw_key, record

    @staticmethod
    def rotate_key(db: Session, tenant_id: str) -> tuple[str, TenantApiKeyRecord]:
        """Revoke all existing active keys for tenant and issue a new one.

        Returns (raw_key, new_record).
        """
        now = datetime.now(timezone.utc)
        existing = (
            db.query(TenantApiKeyRecord)
            .filter(
                TenantApiKeyRecord.tenant_id == tenant_id,
                TenantApiKeyRecord.is_active.is_(True),
            )
            .all()
        )
        for rec in existing:
            rec.is_active = False
            rec.revoked_at = now
        db.flush()

        raw_key = _generate_raw_key()
        new_record = TenantApiKeyRecord(
            key_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            key_hash=_hash_key(raw_key),
            key_hint=raw_key[-4:],
            is_active=True,
            created_at=now,
            revoked_at=None,
        )
        db.add(new_record)
        db.commit()
        db.refresh(new_record)
        return raw_key, new_record

    @staticmethod
    def lookup_tenant(db: Session, raw_key: str) -> str | None:
        """Resolve a raw API key to a tenant_id, or None if invalid/inactive."""
        key_hash = _hash_key(raw_key)
        record = (
            db.query(TenantApiKeyRecord)
            .filter(
                TenantApiKeyRecord.key_hash == key_hash,
                TenantApiKeyRecord.is_active.is_(True),
            )
            .first()
        )
        return record.tenant_id if record else None

    @staticmethod
    def revoke_all(db: Session, tenant_id: str) -> int:
        """Revoke all active keys for a tenant. Returns count revoked."""
        now = datetime.now(timezone.utc)
        records = (
            db.query(TenantApiKeyRecord)
            .filter(
                TenantApiKeyRecord.tenant_id == tenant_id,
                TenantApiKeyRecord.is_active.is_(True),
            )
            .all()
        )
        for rec in records:
            rec.is_active = False
            rec.revoked_at = now
        db.commit()
        return len(records)

    @staticmethod
    def list_for_tenant(db: Session, tenant_id: str) -> list[TenantApiKeyRecord]:
        """Return all key records for a tenant (active and revoked). Never includes raw keys."""
        return (
            db.query(TenantApiKeyRecord)
            .filter(TenantApiKeyRecord.tenant_id == tenant_id)
            .order_by(TenantApiKeyRecord.created_at.desc())
            .all()
        )
