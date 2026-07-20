"""Pydantic models for evaluation scenario contracts (schema_version 2d.1 / 2e.1)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

SCHEMA_VERSION = "2e.1"
SUPPORTED_SCHEMA_VERSIONS = frozenset({"2d.1", "2e.1"})
SourceMode = Literal["fixture", "generated", "live_gmail", "replay"]


class InputContract(BaseModel):
    subject: str = ""
    message_text: str = ""
    sender: dict[str, str] = Field(default_factory=dict)
    actions: list[dict[str, Any]] | None = None
    cross_tenant_reference: dict[str, Any] | None = None


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
    run: Literal[
        "pipeline",
        "dispatch",
        "approve_action",
        "resume_dispatch",
        "retry_dispatch",
        "seed_pending_intent",
    ]
    approval_index: int = 0
    actor: str = "eval_operator"
    expect_blocked: bool = False


class PipelineContract(BaseModel):
    steps: list[PipelineStepContract] = Field(default_factory=lambda: [PipelineStepContract(run="pipeline")])
    pre_seed: list[dict[str, Any]] = Field(default_factory=list)


class GenerationContract(BaseModel):
    template_id: str | None = None
    seed: int | None = None
    variation_id: str | None = None
    generator_model: str | None = None
    generator_prompt_version: str | None = None
    parent_scenario_id: str | None = None
    mutation_types: list[str] = Field(default_factory=list)


class ForbiddenOutcomes(BaseModel):
    actions: list[str] = Field(default_factory=list)
    policy_authorizations: list[str] = Field(default_factory=list)
    reply_claims: list[str] = Field(default_factory=list)
    max_real_external_calls: int | None = None
    cross_tenant_access: bool = False
    automatic_retry: bool = False


class AllowedOutcomes(BaseModel):
    policy_authorizations: list[str] = Field(default_factory=list)
    routing: list[str] = Field(default_factory=list)
    next_step: list[str] = Field(default_factory=list)
    classification: list[str] = Field(default_factory=list)


class OutcomesContract(BaseModel):
    forbidden: ForbiddenOutcomes = Field(default_factory=ForbiddenOutcomes)
    allowed: AllowedOutcomes = Field(default_factory=AllowedOutcomes)


class RubricCheckContract(BaseModel):
    id: str
    params: dict[str, Any] = Field(default_factory=dict)


class RubricsContract(BaseModel):
    reply_quality: list[RubricCheckContract] = Field(default_factory=list)


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
    outcomes: OutcomesContract = Field(default_factory=OutcomesContract)
    rubrics: RubricsContract = Field(default_factory=RubricsContract)


class ScenarioContract(BaseModel):
    schema_version: str
    scenario_id: str
    scenario_version: int = 1
    dataset_version: str | None = None
    title: str = ""
    description: str = ""
    category: str
    risk_level: Literal["low", "medium", "high", "critical"] = "low"
    source_mode: SourceMode = "fixture"
    tags: list[str] = Field(default_factory=list)
    source: str = "committed"
    generation: GenerationContract = Field(default_factory=GenerationContract)
    input: InputContract
    tenant: TenantContract = Field(default_factory=TenantContract)
    ai: AIContract = Field(default_factory=AIContract)
    pipeline: PipelineContract = Field(default_factory=PipelineContract)
    expect: ExpectContract = Field(default_factory=ExpectContract)

    @field_validator("schema_version")
    @classmethod
    def _check_schema_version(cls, value: str) -> str:
        if value not in SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(f"Unsupported schema_version '{value}'")
        return value

    @field_validator("tags", mode="before")
    @classmethod
    def _normalize_tags(cls, value):
        return value or []

    @property
    def requires_forbidden(self) -> bool:
        return self.risk_level in ("high", "critical")
