"""Pydantic models for operator incident management (Kapitel 6)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.admin.operations_overview_schemas import SeverityBadge

PanelSeverity = Literal["critical", "failed", "warning", "information"]
IncidentStatus = Literal[
    "open",
    "acknowledged",
    "investigating",
    "monitoring",
    "resolved",
    "closed",
]

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "open": {"acknowledged", "investigating"},
    "acknowledged": {"investigating"},
    "investigating": {"monitoring", "resolved"},
    "monitoring": {"investigating", "resolved"},
    "resolved": {"closed", "investigating"},
    "closed": set(),
}

OPEN_STATUSES = frozenset({"open", "acknowledged", "investigating", "monitoring"})
CLOSED_STATUSES = frozenset({"closed"})


class _IncidentWriteBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(..., min_length=1, max_length=500)
    confirmation: Literal[True]

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("reason must not be empty")
        return stripped


class IncidentCreateRequest(_IncidentWriteBase):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    severity: PanelSeverity
    tenant_ids: list[str] = Field(default_factory=list, max_length=50)
    signal_links: list["IncidentSignalLinkInput"] = Field(default_factory=list, max_length=50)

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("title must not be empty")
        return stripped


class IncidentSignalLinkInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., min_length=1, max_length=128)
    signal_id: str = Field(..., min_length=1, max_length=256)


class IncidentStatusChangeRequest(_IncidentWriteBase):
    target_status: IncidentStatus
    resolution_summary: str | None = Field(default=None, max_length=5000)
    expected_version: int = Field(..., ge=1)


class IncidentNoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(..., min_length=1, max_length=5000)
    confirmation: Literal[True]

    @field_validator("message")
    @classmethod
    def strip_message(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("message must not be empty")
        return stripped


class IncidentTenantLinkRequest(_IncidentWriteBase):
    tenant_id: str = Field(..., min_length=1, max_length=128)


class IncidentSignalLinkRequest(_IncidentWriteBase):
    tenant_id: str = Field(..., min_length=1, max_length=128)
    signal_id: str = Field(..., min_length=1, max_length=256)


class IncidentFieldUpdateRequest(_IncidentWriteBase):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    severity: PanelSeverity | None = None
    expected_version: int = Field(..., ge=1)

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("title must not be empty")
        return stripped


class IncidentAssignSelfRequest(_IncidentWriteBase):
    expected_version: int = Field(..., ge=1)


class AvailableIncidentAction(BaseModel):
    action_id: str
    label: str
    required_role: Literal["read_only", "operations", "admin"]
    requires_reason: bool
    requires_confirmation: bool
    allowed: bool
    blocked_reason: str | None = None


class LinkedIncidentSummary(BaseModel):
    incident_id: str
    title: str
    status: IncidentStatus
    severity: PanelSeverity


class LinkedIncidentsGroup(BaseModel):
    open: list[LinkedIncidentSummary] = []
    closed: list[LinkedIncidentSummary] = []


class RecommendedIncidentAction(BaseModel):
    action: Literal["create_from_signal"] = "create_from_signal"
    tenant_id: str
    signal_id: str
    prefill_title: str
    prefill_severity: PanelSeverity


class IncidentSummary(BaseModel):
    open: int
    investigating: int
    monitoring: int
    resolved: int
    critical: int
    affected_tenants: int


class IncidentTenantOut(BaseModel):
    tenant_id: str
    tenant_name_snapshot: str | None
    linked_at: datetime
    unlinked_at: datetime | None = None


class IncidentSignalOut(BaseModel):
    signal_id: str
    tenant_id: str
    source_type: str
    source_id: str
    snapshot_title: str
    snapshot_summary: str
    snapshot_severity: PanelSeverity
    linked_at: datetime
    unlinked_at: datetime | None = None


class IncidentTimelineEventOut(BaseModel):
    event_id: str
    event_type: str
    actor_id: str
    actor_display_name: str
    actor_role: str
    message: str
    metadata: dict = Field(default_factory=dict)
    created_at: datetime


class IncidentListItem(BaseModel):
    incident_id: str
    title: str
    description: str | None
    severity: PanelSeverity
    severity_badge: SeverityBadge
    status: IncidentStatus
    owner_id: str | None
    owner_display_name: str | None
    tenant_count: int
    signal_count: int
    created_at: datetime
    updated_at: datetime
    age_hours: int | None


class IncidentListResponse(BaseModel):
    generated_at: datetime
    total: int
    limit: int
    offset: int
    summary: IncidentSummary
    items: list[IncidentListItem]


class IncidentDetail(BaseModel):
    incident_id: str
    title: str
    description: str | None
    severity: PanelSeverity
    severity_badge: SeverityBadge
    status: IncidentStatus
    owner_id: str | None
    owner_display_name: str | None
    created_by: str
    created_by_display_name: str
    created_at: datetime
    updated_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    closed_at: datetime | None
    resolution_summary: str | None
    version: int
    tenants: list[IncidentTenantOut]
    signals: list[IncidentSignalOut]
    timeline: list[IncidentTimelineEventOut]
    available_actions: list[AvailableIncidentAction] = []


class IncidentWriteResponse(BaseModel):
    incident_id: str
    version: int
    message: str
    changed: bool = True
