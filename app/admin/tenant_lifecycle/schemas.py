"""Pydantic schemas for tenant lifecycle API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

LifecycleStatus = Literal[
    "draft",
    "onboarding",
    "waiting_for_customer",
    "technical_verification",
    "ready_for_activation",
    "active",
    "archived",
]


class LifecycleResponse(BaseModel):
    tenant_id: str
    lifecycle_status: LifecycleStatus
    lifecycle_label_sv: str
    config_version: int
    lifecycle_updated_at: datetime | None = None
    lifecycle_updated_by: str | None = None
    is_test_tenant: bool = False
    operations_paused: bool = False
    scheduler_run_mode: str | None = None


class LifecyclePatchRequest(BaseModel):
    config_version: int = Field(..., ge=1)
    lifecycle_status: LifecycleStatus
    reason: str | None = Field(default=None, max_length=512)


class LifecycleActionRequest(BaseModel):
    config_version: int = Field(..., ge=1)
    reason: str | None = Field(default=None, max_length=512)


class OperationsPauseRequest(BaseModel):
    config_version: int = Field(..., ge=1)
    reason: str | None = Field(default=None, max_length=512)


class ActivationSnapshotItem(BaseModel):
    id: str
    tenant_id: str
    config_version: int
    plan_hash: str
    readiness_check_version: int
    activated_by_operator_id: str
    activated_at: datetime


class ActivationHistoryResponse(BaseModel):
    tenant_id: str
    items: list[ActivationSnapshotItem]


class TenantSettingsSectionResponse(BaseModel):
    tenant_id: str
    section: str
    config_version: int
    payload: dict[str, Any]


class TenantSettingsSectionPatchRequest(BaseModel):
    expected_config_version: int = Field(..., ge=1)
    change_reason: str | None = Field(default=None, max_length=512)
    payload: dict[str, Any]


class TenantDeleteRequest(BaseModel):
    confirm_tenant_id: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=3, max_length=512)


class TenantDeleteDryRunResponse(BaseModel):
    tenant_id: str
    is_test_tenant: bool
    deletable: bool
    blocked_reason: str | None = None
    tables: list[dict[str, Any]] = Field(default_factory=list)
