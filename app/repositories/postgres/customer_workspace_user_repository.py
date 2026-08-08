"""Repository for customer workspace viewer identities."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.repositories.postgres.customer_workspace_user_models import CustomerWorkspaceUserRecord

CUSTOMER_VIEWER_ROLE = "customer_viewer"
USER_STATUS_ACTIVE = "active"
USER_STATUS_DISABLED = "disabled"


def normalize_email(email: str) -> str:
    return email.strip().lower()


class CustomerWorkspaceUserRepository:
    @staticmethod
    def get_by_id(db: Session, user_id: str) -> CustomerWorkspaceUserRecord | None:
        return (
            db.query(CustomerWorkspaceUserRecord)
            .filter(CustomerWorkspaceUserRecord.id == user_id)
            .first()
        )

    @staticmethod
    def get_active_by_email(db: Session, email: str) -> CustomerWorkspaceUserRecord | None:
        normalized = normalize_email(email)
        return (
            db.query(CustomerWorkspaceUserRecord)
            .filter(
                func.lower(CustomerWorkspaceUserRecord.email) == normalized,
                CustomerWorkspaceUserRecord.status == USER_STATUS_ACTIVE,
            )
            .first()
        )

    @staticmethod
    def active_email_taken(db: Session, email: str, *, exclude_user_id: str | None = None) -> bool:
        normalized = normalize_email(email)
        query = db.query(CustomerWorkspaceUserRecord).filter(
            func.lower(CustomerWorkspaceUserRecord.email) == normalized,
            CustomerWorkspaceUserRecord.status == USER_STATUS_ACTIVE,
        )
        if exclude_user_id:
            query = query.filter(CustomerWorkspaceUserRecord.id != exclude_user_id)
        return query.first() is not None

    @staticmethod
    def create_user(
        db: Session,
        *,
        tenant_id: str,
        email: str,
        password_hash: str,
        display_name: str,
    ) -> CustomerWorkspaceUserRecord:
        now = datetime.now(timezone.utc)
        record = CustomerWorkspaceUserRecord(
            id=str(uuid4()),
            tenant_id=tenant_id,
            email=normalize_email(email),
            password_hash=password_hash,
            display_name=display_name.strip() or normalize_email(email),
            role=CUSTOMER_VIEWER_ROLE,
            status=USER_STATUS_ACTIVE,
            created_at=now,
            updated_at=now,
            password_changed_at=now,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    @staticmethod
    def set_status(
        db: Session,
        user: CustomerWorkspaceUserRecord,
        status: str,
    ) -> CustomerWorkspaceUserRecord:
        user.status = status
        user.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def update_password_hash(
        db: Session,
        user: CustomerWorkspaceUserRecord,
        password_hash: str,
    ) -> CustomerWorkspaceUserRecord:
        now = datetime.now(timezone.utc)
        user.password_hash = password_hash
        user.password_changed_at = now
        user.updated_at = now
        db.commit()
        db.refresh(user)
        return user
