"""API and persistence schemas for live evaluation."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class LiveEvalRunRegisterRequest(BaseModel):
    evaluation_run_id: str = Field(min_length=8, max_length=36)
    tenant_id: str
    scenario_id: str
    attempt_id: int = Field(ge=1)
    transport_mode: Literal["live_gmail"] = "live_gmail"
    ai_mode: Literal["fixture_ai", "live_llm"]
    expected_sender: str
    expected_recipient: str
    expires_at: datetime | None = None


class LiveEvalRunResponse(BaseModel):
    evaluation_run_id: str
    tenant_id: str
    scenario_id: str
    attempt_id: int
    transport_mode: str
    ai_mode: str
    fixture_bundle_id: str | None
    expected_sender: str
    expected_recipient: str
    status: str
    created_by: str
    created_at: datetime
    expires_at: datetime
    config_hash: str


class LiveEvalRunStatusRequest(BaseModel):
    tenant_id: str
    status: Literal["completed", "aborted"]


class GmailReadinessRequest(BaseModel):
    tenant_id: str


class GmailReadinessResponse(BaseModel):
    ready: bool
    issues: list[str] = Field(default_factory=list)
    checks: dict[str, Any] = Field(default_factory=dict)


class TrustedLiveEvalSnapshot(BaseModel):
    """Immutable trusted runtime snapshot stored on job.input_data.live_eval."""

    evaluation_run_id: str
    tenant_id: str
    scenario_id: str
    attempt_id: int
    transport_mode: str
    ai_mode: str
    fixture_bundle_id: str | None = None
    expected_sender: str
    expected_recipient: str
    config_hash: str
    trusted: bool = True


class LiveEvalReport(BaseModel):
    report_schema_version: str = "2f.2"
    evaluation_run_id: str
    scenario_id: str | None = None
    attempt_id: int | None = None
    transport_mode: str | None = None
    ai_mode: str | None = None
    result: Literal["passed", "failed", "aborted", "dry_run", "cleanup_failed"] = "dry_run"
    failure_category: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    state_transitions: list[dict[str, Any]] = Field(default_factory=list)
    cleanup_result: str | None = None
    sender_gmail_message_id: str | None = None
    recipient_gmail_message_id: str | None = None
    sender_gmail_thread_id: str | None = None
    recipient_gmail_thread_id: str | None = None
    rfc_message_id: str | None = None
    job_id: str | None = None
    pipeline_run_id: str | None = None
    action_operation_id: str | None = None
    sender_account_fingerprint: str | None = None
    recipient_account_fingerprint: str | None = None
    assertion_results: list[str] = Field(default_factory=list)
    external_telemetry: dict[str, Any] = Field(default_factory=dict)
    latency_breakdown: dict[str, Any] = Field(default_factory=dict)
    redacted_diagnostics: dict[str, Any] = Field(default_factory=dict)


class ProcessDeliveryRequest(BaseModel):
    tenant_id: str
    recipient_gmail_message_id: str


class ProcessDeliveryResponse(BaseModel):
    evaluation_run_id: str
    recipient_gmail_message_id: str
    root_job_id: str | None = None
    job_status: str | None = None
    pipeline_run_id: str | None = None
    intake_status: str
    intake_detail: dict[str, Any] = Field(default_factory=dict)


class RecipientCleanupRequest(BaseModel):
    tenant_id: str
    recipient_gmail_message_id: str
    phase: Literal["pre_claim", "post_claim"] = "post_claim"


class RuntimeReadinessResponse(BaseModel):
    env: str
    env_fingerprint: str
    build_git_sha: str | None = None
    live_eval_enabled: bool
    gmail_eval_enabled: bool
    external_side_effects_enabled: bool
    tenant_allowlist_ok: bool
    database_ok: bool


class DeliveryObservationResponse(BaseModel):
    candidate_count: int
    valid_count: int
    duplicate_detected: bool
    confirmed: dict[str, Any] | None = None
    rejection_reasons: list[str] = Field(default_factory=list)

