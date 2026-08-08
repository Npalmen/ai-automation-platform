"""Repository for server-side customer workspace sessions."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.repositories.postgres.customer_workspace_session_models import CustomerWorkspaceSessionRecord

DEFAULT_SESSION_MAX_AGE_SECONDS = 8 * 3600


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


class CustomerWorkspaceSessionRepository:
    @staticmethod
    def create_session(
        db: Session,
        *,
        user_id: str,
        tenant_id: str,
        max_age_seconds: int = DEFAULT_SESSION_MAX_AGE_SECONDS,
    ) -> tuple[str, CustomerWorkspaceSessionRecord]:
        raw_token = generate_session_token()
        now = datetime.now(timezone.utc)
        record = CustomerWorkspaceSessionRecord(
            id=str(uuid4()),
            user_id=user_id,
            tenant_id=tenant_id,
            token_hash=hash_session_token(raw_token),
            expires_at=now + timedelta(seconds=max_age_seconds),
            created_at=now,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return raw_token, record

    @staticmethod
    def get_active_by_token_hash(
        db: Session,
        token_hash: str,
    ) -> CustomerWorkspaceSessionRecord | None:
        now = datetime.now(timezone.utc)
        return (
            db.query(CustomerWorkspaceSessionRecord)
            .filter(
                CustomerWorkspaceSessionRecord.token_hash == token_hash,
                CustomerWorkspaceSessionRecord.revoked_at.is_(None),
                CustomerWorkspaceSessionRecord.expires_at > now,
            )
            .first()
        )

    @staticmethod
    def revoke_session(db: Session, session: CustomerWorkspaceSessionRecord) -> None:
        if session.revoked_at is not None:
            return
        session.revoked_at = datetime.now(timezone.utc)
        db.commit()

    @staticmethod
    def revoke_all_for_user(db: Session, user_id: str) -> int:
        now = datetime.now(timezone.utc)
        sessions = (
            db.query(CustomerWorkspaceSessionRecord)
            .filter(
                CustomerWorkspaceSessionRecord.user_id == user_id,
                CustomerWorkspaceSessionRecord.revoked_at.is_(None),
            )
            .all()
        )
        for session in sessions:
            session.revoked_at = now
        if sessions:
            db.commit()
        return len(sessions)
