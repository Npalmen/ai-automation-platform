"""SQLAlchemy model for production pilot message reviews."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.postgres.database import Base


class ProductionPilotMessageReviewRecord(Base):
    __tablename__ = "production_pilot_message_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    pilot_phase: Mapped[str] = mapped_column(String(8), nullable=False, default="P1")
    provider_message_ref_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    intake_event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    job_id: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewed_by: Mapped[str] = mapped_column(String(128), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    classification_verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    extraction_verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    routing_verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    manual_review_verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    shadow_observation_verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    match_proposal_verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    incident_severity: Mapped[str] = mapped_column(String(16), nullable=False, default="none")
    error_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    business_risk: Mapped[str | None] = mapped_column(String(16), nullable=True)
    blocks_next_phase: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    review_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
