"""Persistence helpers for onboarding sessions."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.admin.onboarding.models import (
    ALL_STEP_KEYS,
    OPEN_SESSION_STATUSES,
    OnboardingSessionRecord,
    OnboardingStepDraftRecord,
    OnboardingStepStateRecord,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OnboardingRepository:
    @staticmethod
    def get_session(db: Session, session_id: str) -> OnboardingSessionRecord | None:
        return (
            db.query(OnboardingSessionRecord)
            .filter(OnboardingSessionRecord.id == session_id)
            .first()
        )

    @staticmethod
    def get_session_for_update(db: Session, session_id: str) -> OnboardingSessionRecord | None:
        return (
            db.query(OnboardingSessionRecord)
            .filter(OnboardingSessionRecord.id == session_id)
            .with_for_update()
            .first()
        )

    @staticmethod
    def get_open_session_for_tenant(db: Session, tenant_id: str) -> OnboardingSessionRecord | None:
        return (
            db.query(OnboardingSessionRecord)
            .filter(
                OnboardingSessionRecord.tenant_id == tenant_id,
                OnboardingSessionRecord.status.in_(tuple(OPEN_SESSION_STATUSES)),
            )
            .first()
        )

    @staticmethod
    def list_sessions(
        db: Session,
        *,
        open_only: bool = False,
        limit: int = 50,
    ) -> list[OnboardingSessionRecord]:
        q = db.query(OnboardingSessionRecord).order_by(OnboardingSessionRecord.updated_at.desc())
        if open_only:
            q = q.filter(OnboardingSessionRecord.status.in_(tuple(OPEN_SESSION_STATUSES)))
        return q.limit(limit).all()

    @staticmethod
    def get_step_states(db: Session, session_id: str) -> list[OnboardingStepStateRecord]:
        return (
            db.query(OnboardingStepStateRecord)
            .filter(OnboardingStepStateRecord.session_id == session_id)
            .all()
        )

    @staticmethod
    def get_step_state(db: Session, session_id: str, step_key: str) -> OnboardingStepStateRecord | None:
        return (
            db.query(OnboardingStepStateRecord)
            .filter(
                OnboardingStepStateRecord.session_id == session_id,
                OnboardingStepStateRecord.step_key == step_key,
            )
            .first()
        )

    @staticmethod
    def get_draft(db: Session, session_id: str, step_key: str) -> OnboardingStepDraftRecord | None:
        return (
            db.query(OnboardingStepDraftRecord)
            .filter(
                OnboardingStepDraftRecord.session_id == session_id,
                OnboardingStepDraftRecord.step_key == step_key,
            )
            .first()
        )

    @staticmethod
    def upsert_draft(
        db: Session,
        *,
        session_id: str,
        step_key: str,
        payload: dict,
    ) -> OnboardingStepDraftRecord:
        now = _utcnow()
        record = OnboardingRepository.get_draft(db, session_id, step_key)
        if record is None:
            record = OnboardingStepDraftRecord(
                session_id=session_id,
                step_key=step_key,
                payload=payload,
                updated_at=now,
            )
            db.add(record)
        else:
            record.payload = payload
            record.updated_at = now
        db.flush()
        return record

    @staticmethod
    def init_step_states(
        db: Session,
        *,
        session_id: str,
        operator_id: str,
    ) -> None:
        now = _utcnow()
        for step_key in ALL_STEP_KEYS:
            db.add(
                OnboardingStepStateRecord(
                    session_id=session_id,
                    step_key=step_key,
                    step_status="not_started",
                    verification_level="declared",
                    blocking_issues=[],
                    warnings=[],
                    updated_at=now,
                    updated_by_operator_id=operator_id,
                )
            )
        db.flush()

    @staticmethod
    def set_step_state(
        db: Session,
        *,
        session_id: str,
        step_key: str,
        step_status: str,
        verification_level: str,
        blocking_issues: list | None = None,
        warnings: list | None = None,
        operator_id: str | None = None,
    ) -> OnboardingStepStateRecord:
        record = OnboardingRepository.get_step_state(db, session_id, step_key)
        now = _utcnow()
        if record is None:
            record = OnboardingStepStateRecord(
                session_id=session_id,
                step_key=step_key,
                step_status=step_status,
                verification_level=verification_level,
                blocking_issues=blocking_issues or [],
                warnings=warnings or [],
                updated_at=now,
                updated_by_operator_id=operator_id,
            )
            db.add(record)
        else:
            record.step_status = step_status
            record.verification_level = verification_level
            record.blocking_issues = blocking_issues or []
            record.warnings = warnings or []
            record.updated_at = now
            record.updated_by_operator_id = operator_id
        db.flush()
        return record

    @staticmethod
    def create_session_record(
        db: Session,
        *,
        tenant_id: str,
        operator_id: str,
    ) -> OnboardingSessionRecord:
        now = _utcnow()
        session = OnboardingSessionRecord(
            id=str(uuid4()),
            tenant_id=tenant_id,
            status="in_progress",
            current_step="identity",
            version=1,
            readiness_check_version=0,
            integration_state_revision=0,
            created_at=now,
            updated_at=now,
            created_by_operator_id=operator_id,
            last_updated_by_operator_id=operator_id,
        )
        db.add(session)
        db.flush()
        OnboardingRepository.init_step_states(db, session_id=session.id, operator_id=operator_id)
        return session

    @staticmethod
    def bump_version(session: OnboardingSessionRecord, operator_id: str) -> None:
        session.version += 1
        session.updated_at = _utcnow()
        session.last_updated_by_operator_id = operator_id

    @staticmethod
    def bump_integration_state_revision(session: OnboardingSessionRecord) -> int:
        session.integration_state_revision = int(session.integration_state_revision or 0) + 1
        session.updated_at = _utcnow()
        return session.integration_state_revision
