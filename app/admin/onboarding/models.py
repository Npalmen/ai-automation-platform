"""ORM models for operator onboarding sessions (Kapitel 9)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.postgres.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


OPEN_SESSION_STATUSES = frozenset(
    {
        "draft",
        "in_progress",
        "blocked",
        "ready_for_review",
        "ready_for_activation",
    }
)

ALL_STEP_KEYS = (
    "identity",
    "modules",
    "automation",
    "service_profile",
    "routing",
    "integrations",
    "data_start",
    "readiness",
    "review",
)


class OnboardingSessionRecord(Base):
    __tablename__ = "onboarding_sessions"
    __table_args__ = (
        Index("ix_onboarding_sessions_tenant_id", "tenant_id"),
        Index("ix_onboarding_sessions_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    current_step: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    readiness_check_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    integration_state_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_operator_id: Mapped[str] = mapped_column(String(128), nullable=False)
    last_updated_by_operator_id: Mapped[str] = mapped_column(String(128), nullable=False)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class OnboardingStepStateRecord(Base):
    __tablename__ = "onboarding_step_states"
    __table_args__ = (
        Index("ix_onboarding_step_states_session_id", "session_id"),
    )

    session_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    step_key: Mapped[str] = mapped_column(String(32), primary_key=True)
    step_status: Mapped[str] = mapped_column(String(32), nullable=False)
    verification_level: Mapped[str] = mapped_column(String(32), nullable=False, default="declared")
    blocking_issues: Mapped[list | None] = mapped_column(JSON, nullable=True)
    warnings: Mapped[list | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_by_operator_id: Mapped[str | None] = mapped_column(String(128), nullable=True)


class OnboardingStepDraftRecord(Base):
    __tablename__ = "onboarding_step_drafts"

    session_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    step_key: Mapped[str] = mapped_column(String(32), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)


class OnboardingOAuthStateRecord(Base):
    __tablename__ = "onboarding_oauth_states"
    __table_args__ = (
        Index("ix_onboarding_oauth_states_session", "session_id", "provider"),
        Index("ix_onboarding_oauth_states_expires", "expires_at"),
    )

    state_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    state_hash: Mapped[str] = mapped_column(Text, nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    operator_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    redirect_target: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)


class OnboardingIntegrationVerificationRecord(Base):
    __tablename__ = "onboarding_integration_verifications"
    __table_args__ = (Index("ix_onboarding_integration_verifications_session", "session_id"),)

    session_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    integration_key: Mapped[str] = mapped_column(String(32), primary_key=True)
    verification_status: Mapped[str] = mapped_column(String(32), nullable=False)
    source_class: Mapped[str] = mapped_column(String(32), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by_operator_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    config_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    integration_state_revision_at_verify: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    environment_safe_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)


class TenantResourceBindingRecord(Base):
    __tablename__ = "tenant_resource_bindings"
    __table_args__ = (
        Index("ix_tenant_resource_bindings_tenant", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(256), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    bound_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    bound_by_operator_id: Mapped[str] = mapped_column(String(128), nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
