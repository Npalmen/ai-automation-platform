"""Customer integration invitation service."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.admin.tenant_lifecycle.invitation_models import IntegrationInvitationRecord
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

INVITATION_TTL_DAYS = 7


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_invitation(
    db: Session,
    *,
    tenant_id: str,
    integration_key: str,
    contact_email: str,
    contact_name: str | None,
    message_optional: str | None,
    operator_id: str,
) -> tuple[IntegrationInvitationRecord, str]:
    if TenantConfigRepository.get(db, tenant_id) is None:
        raise HTTPException(status_code=404, detail="Tenant not found.")
    raw_token = secrets.token_urlsafe(32)
    record = IntegrationInvitationRecord(
        id=str(uuid4()),
        tenant_id=tenant_id,
        integration_key=integration_key,
        contact_name=contact_name,
        contact_email=contact_email.strip(),
        token_hash=_hash_token(raw_token),
        status="pending",
        expires_at=_utcnow() + timedelta(days=INVITATION_TTL_DAYS),
        created_by_operator_id=operator_id,
        created_at=_utcnow(),
        message_optional=message_optional,
    )
    db.add(record)
    db.add(
        AuditEventRecord(
            event_id=str(uuid4()),
            tenant_id=tenant_id,
            category="integration_invite",
            action="integration.invitation_created",
            status="succeeded",
            details={
                "invitation_id": record.id,
                "integration_key": integration_key,
                "operator_id": operator_id,
            },
            created_at=_utcnow(),
        )
    )
    db.commit()
    db.refresh(record)
    return record, raw_token


def list_invitations(db: Session, tenant_id: str) -> list[IntegrationInvitationRecord]:
    return (
        db.query(IntegrationInvitationRecord)
        .filter(IntegrationInvitationRecord.tenant_id == tenant_id)
        .order_by(IntegrationInvitationRecord.created_at.desc())
        .all()
    )


def get_invitation_by_token(db: Session, raw_token: str) -> IntegrationInvitationRecord | None:
    token_hash = _hash_token(raw_token)
    return (
        db.query(IntegrationInvitationRecord)
        .filter(IntegrationInvitationRecord.token_hash == token_hash)
        .first()
    )


def present_invitation_public(record: IntegrationInvitationRecord) -> dict:
    return {
        "invitation_id": record.id,
        "tenant_id": record.tenant_id,
        "integration_key": record.integration_key,
        "contact_email": record.contact_email,
        "status": record.status,
        "expires_at": record.expires_at,
        "connected_account_email": record.connected_account_email,
    }


def revoke_invitation(
    db: Session,
    *,
    invitation_id: str,
    tenant_id: str,
    operator_id: str,
) -> IntegrationInvitationRecord:
    record = (
        db.query(IntegrationInvitationRecord)
        .filter(
            IntegrationInvitationRecord.id == invitation_id,
            IntegrationInvitationRecord.tenant_id == tenant_id,
        )
        .with_for_update()
        .first()
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Invitation not found.")
    if record.status != "pending":
        raise HTTPException(status_code=409, detail="Invitation cannot be revoked.")
    record.status = "revoked"
    record.revoked_at = _utcnow()
    db.add(
        AuditEventRecord(
            event_id=str(uuid4()),
            tenant_id=tenant_id,
            category="integration_invite",
            action="integration.invitation_revoked",
            status="succeeded",
            details={"invitation_id": invitation_id, "operator_id": operator_id},
            created_at=_utcnow(),
        )
    )
    db.commit()
    db.refresh(record)
    return record


def consume_invitation(
    db: Session,
    record: IntegrationInvitationRecord,
    *,
    connected_account_email: str | None,
) -> None:
    if record.status != "pending":
        raise HTTPException(status_code=409, detail="Invitation not pending.")
    if record.revoked_at is not None:
        raise HTTPException(status_code=410, detail="Invitation revoked.")
    if record.consumed_at is not None:
        raise HTTPException(status_code=409, detail="Invitation already consumed.")
    if _utcnow() > record.expires_at.astimezone(timezone.utc):
        raise HTTPException(status_code=410, detail="Invitation expired.")
    record.status = "consumed"
    record.consumed_at = _utcnow()
    if connected_account_email:
        record.connected_account_email = connected_account_email
    db.add(
        AuditEventRecord(
            event_id=str(uuid4()),
            tenant_id=record.tenant_id,
            category="integration_invite",
            action="integration.invitation_consumed",
            status="succeeded",
            details={
                "invitation_id": record.id,
                "integration_key": record.integration_key,
            },
            created_at=_utcnow(),
        )
    )
