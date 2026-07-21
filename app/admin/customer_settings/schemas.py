"""Pydantic schemas for customer settings API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CustomerSettingsDomainPatchRequest(BaseModel):
    expected_config_version: int = Field(..., ge=1)
    change_reason: str | None = Field(default=None, max_length=512)
    payload: dict[str, Any] = Field(default_factory=dict)


class CustomerSettingsDomainResponse(BaseModel):
    tenant_id: str
    domain: str
    config_version: int
    payload: dict[str, Any]


class CustomerSettingsPatchResponse(BaseModel):
    tenant_id: str
    domain: str
    config_version: int
    changed_domains: list[str]
    readiness_invalidated: list[str]
    runtime_projections_changed: list[str]
    warnings: list[str] = Field(default_factory=list)
    domain_payload: dict[str, Any]


class CustomerSettingsPreviewRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class CustomerSettingsPreviewResponse(BaseModel):
    tenant_id: str
    domain: str
    config_version: int
    valid: bool
    warnings: list[str] = Field(default_factory=list)
    blocking: list[str] = Field(default_factory=list)
    readiness_domains_affected: list[str] = Field(default_factory=list)
    runtime_gates: dict[str, Any] = Field(default_factory=dict)
    credential_preservation: bool = True
    normalized_payload: dict[str, Any] = Field(default_factory=dict)
    preview_fingerprint: str
    finance_destination: dict[str, Any] | None = None


class CustomerSettingsAggregateResponse(BaseModel):
    tenant_id: str
    tenant_status: str
    lifecycle_status: str
    config_version: int
    domains: dict[str, Any]
    effective_capabilities: list[dict[str, Any]]
    integration_selection_view: list[dict[str, Any]]
    integration_group_status: dict[str, Any]
    routing_summary: dict[str, Any]
    automation_policy_summary: dict[str, Any]
    readiness_summary: dict[str, Any]
    permissions: dict[str, dict[str, bool]]
    last_updated: dict[str, Any]
