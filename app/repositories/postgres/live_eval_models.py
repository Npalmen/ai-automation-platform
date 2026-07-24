"""ORM models for Kapitel 2F live evaluation."""

from __future__ import annotations

from sqlalchemy import JSON, Column, DateTime, ForeignKeyConstraint, Integer, String, UniqueConstraint, func

from app.repositories.postgres.database import Base


class LiveEvalRunRow(Base):
    __tablename__ = "live_eval_runs"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "evaluation_run_id",
            name="uq_live_eval_runs_tenant_run",
        ),
    )

    evaluation_run_id = Column(String(36), primary_key=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    scenario_id = Column(String(128), nullable=False)
    attempt_id = Column(Integer, nullable=False)
    transport_mode = Column(String(32), nullable=False)
    ai_mode = Column(String(32), nullable=False)
    fixture_bundle_id = Column(String(64), nullable=True)
    expected_sender = Column(String(320), nullable=True)
    expected_recipient = Column(String(320), nullable=True)
    llm_provider = Column(String(64), nullable=True)
    llm_requested_model = Column(String(128), nullable=True)
    llm_max_calls = Column(Integer, nullable=True)
    status = Column(String(32), nullable=False, default="registered")
    root_gmail_message_id = Column(String(320), nullable=True)
    root_job_id = Column(String(64), nullable=True)
    activated_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(String(128), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    config_hash = Column(String(64), nullable=False)


class LiveEvalExternalEventRow(Base):
    __tablename__ = "live_eval_external_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "evaluation_run_id"],
            ["live_eval_runs.tenant_id", "live_eval_runs.evaluation_run_id"],
        ),
    )

    event_key = Column(String(160), primary_key=True)
    operation_key = Column(String(160), nullable=False, index=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    evaluation_run_id = Column(String(36), nullable=False, index=True)
    job_id = Column(String(64), nullable=True)
    pipeline_run_id = Column(String(36), nullable=True)
    action_operation_id = Column(String(36), nullable=True)
    integration_type = Column(String(64), nullable=False)
    category = Column(String(64), nullable=False)
    operation = Column(String(64), nullable=False)
    target = Column(String(320), nullable=True)
    outcome = Column(String(32), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    redacted_metadata = Column(JSON, nullable=False, default=dict)


class LiveEvalLlmOperationRow(Base):
    __tablename__ = "live_eval_llm_operations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "evaluation_run_id"],
            ["live_eval_runs.tenant_id", "live_eval_runs.evaluation_run_id"],
        ),
        UniqueConstraint("operation_key", name="uq_live_eval_llm_operations_operation_key"),
        UniqueConstraint(
            "evaluation_run_id",
            "prompt_name",
            name="uq_live_eval_llm_operations_run_prompt",
        ),
        UniqueConstraint(
            "evaluation_run_id",
            "request_ordinal",
            name="uq_live_eval_llm_operations_run_ordinal",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    evaluation_run_id = Column(String(36), nullable=False, index=True)
    scenario_id = Column(String(128), nullable=False)
    prompt_name = Column(String(64), nullable=False)
    request_ordinal = Column(Integer, nullable=False)
    operation_key = Column(String(200), nullable=False)
    prompt_version = Column(String(32), nullable=True)
    llm_provider = Column(String(64), nullable=False)
    requested_model = Column(String(128), nullable=False)
    returned_model = Column(String(128), nullable=True)
    status = Column(String(32), nullable=False)
    provider_started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    latency_ms = Column(Integer, nullable=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
    finish_reason = Column(String(64), nullable=True)
    schema_validation_status = Column(String(32), nullable=True)
    output_hash = Column(String(64), nullable=True)
    failure_reason = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
