"""SQLAlchemy models for shadow observation ledger."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.postgres.database import Base

_JSONB = JSONB


class EndCustomerShadowObservationRecord(Base):
    __tablename__ = "end_customer_shadow_observations"

    observation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    campaign_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scenario_execution_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    source_message_id: Mapped[str] = mapped_column(String(320), nullable=False)
    source_thread_id: Mapped[str | None] = mapped_column(String(320), nullable=True)
    source_event_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    extraction_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    observation_type: Mapped[str] = mapped_column(String(64), nullable=False, default="intake_message")
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    raw_payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cleanup_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_by: Mapped[str | None] = mapped_column(String(128), nullable=True)


class EndCustomerShadowIdentitySignalRecord(Base):
    __tablename__ = "end_customer_shadow_identity_signals"

    signal_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    observation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    signal_type: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_value_redacted: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_value: Mapped[str | None] = mapped_column(String(512), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    source_path: Mapped[str | None] = mapped_column(String(256), nullable=True)
    trust_level: Mapped[str] = mapped_column(String(32), nullable=False, default="proposed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EndCustomerShadowFactProposalRecord(Base):
    __tablename__ = "end_customer_shadow_fact_proposals"

    proposal_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    observation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    field_name: Mapped[str] = mapped_column(String(128), nullable=False)
    proposed_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="ai_extraction")
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    target_end_customer_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    promotion_status: Mapped[str] = mapped_column(String(32), nullable=False, default="shadow")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    promoted_by: Mapped[str | None] = mapped_column(String(128), nullable=True)


class EndCustomerShadowMatchProposalRecord(Base):
    __tablename__ = "end_customer_shadow_match_proposals"

    match_proposal_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    observation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    candidate_end_customer_id: Mapped[str] = mapped_column(String(36), nullable=False)
    match_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    match_reasons: Mapped[list] = mapped_column(_JSONB, nullable=False, default=list)
    deterministic_signals: Mapped[list] = mapped_column(_JSONB, nullable=False, default=list)
    ambiguous_signals: Mapped[list] = mapped_column(_JSONB, nullable=False, default=list)
    matcher_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(64), nullable=True)
