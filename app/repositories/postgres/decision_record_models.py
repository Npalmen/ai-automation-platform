from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Identity, Integer, JSON, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.postgres.database import Base


class DecisionRecordRow(Base):
    __tablename__ = "decision_records"

    decision_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    job_id: Mapped[str] = mapped_column(String, nullable=False, index=True)

    event_sequence: Mapped[int] = mapped_column(BigInteger, Identity(), nullable=False)
    pipeline_run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    parent_pipeline_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    stage_sequence: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    record_type: Mapped[str] = mapped_column(String(48), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)

    processor_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recommendation: Mapped[str | None] = mapped_column(String(32), nullable=True)
    policy_authorization: Mapped[str | None] = mapped_column(String(32), nullable=True)
    policy_decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    action_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action_operation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    action_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    fingerprint_key_version: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    action_authorization: Mapped[str | None] = mapped_column(String(32), nullable=True)
    execution_phase: Mapped[str | None] = mapped_column(String(16), nullable=True)
    execution_status: Mapped[str | None] = mapped_column(String(32), nullable=True)

    confidence: Mapped[float | None] = mapped_column(nullable=True)
    reason_codes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    tenant_config_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    code_version: Mapped[str] = mapped_column(String(64), nullable=False)
    service_profile_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(64), nullable=True)

    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    supersedes_decision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    job_status_at_record: Mapped[str] = mapped_column(String(32), nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
