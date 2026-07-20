"""Pydantic models for evaluation scenario contracts (schema_version 2d.1)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

SCHEMA_VERSION = "2d.1"


class InputContract(BaseModel):
    subject: str = ""
    message_text: str = ""
    sender: dict[str, str] = Field(default_factory=dict)
    actions: list[dict[str, Any]] | None = None


class TenantContract(BaseModel):
    tenant_id: str | None = None
    auto_actions: dict[str, Any] = Field(default_factory=dict)
    followups_enabled: bool = True
    internal_notification_email: str = ""
    email_signature_name: str = ""
    enabled_job_types: list[str] = Field(default_factory=lambda: ["lead", "customer_inquiry", "invoice"])
    allowed_integrations: list[str] = Field(default_factory=lambda: ["google_mail", "monday"])


class AIContract(BaseModel):
    mode: Literal["fixture_ai", "forced_fallback"] = "fixture_ai"
    fixtures: dict[str, dict[str, Any]] = Field(default_factory=dict)


class PipelineStepContract(BaseModel):
    run: Literal["pipeline", "dispatch", "approve_action", "resume_dispatch"]
    approval_index: int = 0
    actor: str = "eval_operator"


class PipelineContract(BaseModel):
    steps: list[PipelineStepContract] = Field(default_factory=lambda: [PipelineStepContract(run="pipeline")])
    pre_seed: list[dict[str, Any]] = Field(default_factory=list)


class ExpectContract(BaseModel):
    classification: dict[str, Any] = Field(default_factory=dict)
    policy: dict[str, Any] = Field(default_factory=dict)
    risk: dict[str, Any] = Field(default_factory=dict)
    service_profile: dict[str, Any] = Field(default_factory=dict)
    actions: dict[str, Any] = Field(default_factory=dict)
    reply: dict[str, Any] = Field(default_factory=dict)
    handoff: dict[str, Any] = Field(default_factory=dict)
    safety: dict[str, Any] = Field(default_factory=dict)
    decision_trace: dict[str, Any] = Field(default_factory=dict)
    job: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)


class ScenarioContract(BaseModel):
    schema_version: str
    scenario_id: str
    category: str
    tags: list[str] = Field(default_factory=list)
    source: str = "committed"
    input: InputContract
    tenant: TenantContract = Field(default_factory=TenantContract)
    ai: AIContract = Field(default_factory=AIContract)
    pipeline: PipelineContract = Field(default_factory=PipelineContract)
    expect: ExpectContract = Field(default_factory=ExpectContract)

    @field_validator("schema_version")
    @classmethod
    def _check_schema_version(cls, value: str) -> str:
        if value != SCHEMA_VERSION:
            raise ValueError(f"Unsupported schema_version '{value}', expected '{SCHEMA_VERSION}'")
        return value

    @field_validator("tags", mode="before")
    @classmethod
    def _normalize_tags(cls, value):
        return value or []
