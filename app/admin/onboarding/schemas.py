"""Pydantic schemas for operator onboarding API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

StepStatus = Literal[
    "not_started",
    "in_progress",
    "blocked",
    "completed",
    "not_applicable",
    "not_implemented",
]

VerificationLevel = Literal[
    "declared",
    "locally_verified",
    "externally_verified",
    "not_verifiable",
    "not_applicable",
]

ReadinessSourceClass = Literal[
    "tenant_specific",
    "platform_level",
    "declared",
    "locally_verified",
    "externally_verified",
    "not_verifiable",
    "not_applicable",
]

OverallReadinessStatus = Literal[
    "not_ready",
    "ready_with_warnings",
    "ready",
    "unknown",
]


class OnboardingCreateRequest(BaseModel):
    company_name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=2, max_length=48)
    org_number: str | None = None
    primary_contact: str | None = None
    contact_email: str | None = None
    phone: str | None = None
    timezone: str = "Europe/Stockholm"
    language: str = "sv"


class IdentityPatchRequest(BaseModel):
    company_name: str | None = Field(default=None, min_length=1, max_length=200)
    slug: str | None = Field(default=None, min_length=2, max_length=48)
    org_number: str | None = None
    primary_contact: str | None = None
    contact_email: str | None = None
    phone: str | None = None
    timezone: str | None = None
    language: str | None = None
    version: int


class ModulesPatchRequest(BaseModel):
    capabilities: list[str] = Field(default_factory=list)
    integrations: list[str] = Field(default_factory=list)
    version: int


class AutomationPatchRequest(BaseModel):
    preset_key: str
    preset_version: int = 1
    version: int


class OnboardingStepStateResponse(BaseModel):
    step_key: str
    step_status: StepStatus
    verification_level: VerificationLevel
    blocking_issues: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    blocks_activation: bool = False
    read_only: bool = False
    read_only_reason: str | None = None


class OnboardingSessionResponse(BaseModel):
    id: str
    tenant_id: str
    status: str
    current_step: str
    version: int
    readiness_check_version: int
    created_at: datetime
    updated_at: datetime
    activated_at: datetime | None = None
    company_name: str | None = None
    slug: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    integrations: list[str] = Field(default_factory=list)
    preset_key: str | None = None
    preset_version: int | None = None
    legacy_capability_keys: list[str] = Field(default_factory=list)
    legacy_preset: bool = False
    steps: list[OnboardingStepStateResponse] = Field(default_factory=list)


class OnboardingListResponse(BaseModel):
    items: list[OnboardingSessionResponse]


class ReadinessCheckItem(BaseModel):
    id: str
    message: str
    source_class: ReadinessSourceClass
    step_key: str | None = None


class ReadinessResponse(BaseModel):
    overall_status: OverallReadinessStatus
    check_version: int
    blocking_checks: list[ReadinessCheckItem]
    warnings: list[ReadinessCheckItem]
    passed_checks: list[ReadinessCheckItem]
    not_applicable: list[ReadinessCheckItem]
    not_verifiable: list[ReadinessCheckItem]
    last_checked_at: datetime


class ActivateRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
    confirmation_phrase: str
    version: int
    readiness_check_version: int
    plan_hash: str = Field(min_length=64, max_length=64)
    acknowledged_warning_ids: list[str] = Field(default_factory=list)


class CancelRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
    version: int


class ApiKeyCreateRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
    confirmation: bool
    version: int


class ApiKeyCreateResponse(BaseModel):
    api_key: str
    key_hint: str
    message: str


class StepDetailResponse(BaseModel):
    step_key: str
    step_status: StepStatus
    verification_level: VerificationLevel
    blocks_activation: bool
    read_only: bool
    read_only_reason: str | None
    details: dict[str, Any] = Field(default_factory=dict)


class ActivateResponse(BaseModel):
    status: str
    tenant_id: str
    session_id: str
    tenant_status: str
    message: str


class Slice2aStepResponse(BaseModel):
    step_key: str
    step_status: StepStatus
    verification_level: VerificationLevel
    blocks_activation: bool
    draft: dict[str, Any] = Field(default_factory=dict)
    effective: dict[str, Any] = Field(default_factory=dict)


class RoutingPreviewResponse(BaseModel):
    preview: list[dict[str, Any]] = Field(default_factory=list)
    mutated: bool = False


class IntegrationsStepResponse(BaseModel):
    step_key: str
    step_status: StepStatus
    verification_level: VerificationLevel
    blocks_activation: bool
    integration_state_revision: int = 0
    draft: dict[str, Any] = Field(default_factory=dict)
    integrations: list[dict[str, Any]] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class IntegrationStatusResponse(BaseModel):
    integration_key: str
    lifecycle_status: str
    verified: bool = False
    connected: bool = False
    configured: bool = False
    source_class: str = "declared"
    details: dict[str, Any] = Field(default_factory=dict)


class ConnectIntegrationRequest(BaseModel):
    version: int
    redirect_target: str


class ExternalRoutingStepResponse(BaseModel):
    step_key: str
    draft: dict[str, Any] = Field(default_factory=dict)
    enforced_targets: list[dict[str, Any]] = Field(default_factory=list)
    preview: list[dict[str, Any]] = Field(default_factory=list)
    integration_state_revision: int = 0
