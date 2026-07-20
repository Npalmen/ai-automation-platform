"""Presentation-safe schemas for onboarding registries."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Availability = Literal["available", "read_only", "deferred"]


class RegistryCapabilityOut(BaseModel):
    key: str
    label: str
    description: str
    availability: Availability
    supported_in_current_slice: bool
    dependencies: dict[str, list[str]] = Field(default_factory=dict)
    required_integration_groups: list[str] = Field(default_factory=list)
    recommended_integration_groups: list[str] = Field(default_factory=list)
    requires_api_key: bool = False


class RegistryIntegrationOut(BaseModel):
    key: str
    label: str
    description: str
    availability: Availability
    supported_in_current_slice: bool
    dependencies: dict[str, list[str]] = Field(default_factory=dict)
    verification_capability: str | None = None
    lifecycle_cap: str | None = None
    limitation_ids: list[str] = Field(default_factory=list)
    canonical_integration_key: str | None = None
    category: str | None = None
    alternatives_group: str | None = None
    alternatives_group_label_sv: str | None = None
    support_status: str | None = None
    selectable: bool | None = None


class RegistryExternalRoutingTargetOut(BaseModel):
    key: str
    label: str
    job_type: str
    integration_key: str
    enforced: bool
    availability: Availability
    supported_in_current_slice: bool


class RegistryRuntimeFeatureOut(BaseModel):
    key: str
    label: str
    description: str
    availability: Availability
    supported_in_current_slice: bool
    activation_note: str | None = None


class RegistryAutomationPresetOut(BaseModel):
    key: str
    version: int
    label: str
    description: str
    availability: Availability
    supported_in_current_slice: bool
    activation_allows_scheduler: bool
    scheduler_run_mode: str
    limitation: str | None = None


class RegistryServiceProfileOut(BaseModel):
    key: str
    label: str
    description: str
    category: str
    supported_job_types: list[str] = Field(default_factory=list)
    required_fields_summary: list[str] = Field(default_factory=list)
    optional_fields_summary: list[str] = Field(default_factory=list)
    default_route: str
    availability: Availability
    supported_in_current_slice: bool
    capability_dependencies: list[str] = Field(default_factory=list)
    industry_keys: list[str] = Field(default_factory=list)
    module_keys: list[str] = Field(default_factory=list)


class RegistryLeadFieldOut(BaseModel):
    key: str
    label: str


class RegistryRoutingDestinationOut(BaseModel):
    key: str
    label: str


class RegistryDataStartModeOut(BaseModel):
    key: str
    label: str
    description: str
    availability: Availability
    supported_in_current_slice: bool
    recommended: bool = False


class RegistryIndustryOut(BaseModel):
    key: str
    label: str
    description: str
    suggested_service_keys: list[str] = Field(default_factory=list)


class OnboardingRegistriesResponse(BaseModel):
    registry_schema_version: int
    registry_revision: str
    service_type_lead_type_map_version: int
    product_capabilities: list[RegistryCapabilityOut]
    integrations: list[RegistryIntegrationOut]
    runtime_features: list[RegistryRuntimeFeatureOut]
    automation_presets: list[RegistryAutomationPresetOut]
    service_profiles: list[RegistryServiceProfileOut] = Field(default_factory=list)
    lead_field_registry: list[RegistryLeadFieldOut] = Field(default_factory=list)
    routing_destinations: list[RegistryRoutingDestinationOut] = Field(default_factory=list)
    data_start_modes: list[RegistryDataStartModeOut] = Field(default_factory=list)
    external_routing_targets: list[RegistryExternalRoutingTargetOut] = Field(default_factory=list)
    industries: list[RegistryIndustryOut] = Field(default_factory=list)


class ActivationConsequenceOut(BaseModel):
    id: str
    message: str
    severity: Literal["info", "warning"]


class CapabilityStateOut(BaseModel):
    capability_key: str
    lifecycle_state: str
    selected: bool
    configured: bool
    activated: bool
    running: bool
    message: str


class RuntimeEffectOut(BaseModel):
    feature_key: str
    status: str
    configured: bool
    running: bool
    message: str


class ActivationPlanResponse(BaseModel):
    plan_id: str
    plan_hash: str
    session_version: int
    readiness_check_version: int
    registry_revision: str
    registry_schema_version: int
    warning_ids: list[str]
    consequences: list[ActivationConsequenceOut]
    capability_states: list[CapabilityStateOut]
    runtime_effects: list[RuntimeEffectOut]
