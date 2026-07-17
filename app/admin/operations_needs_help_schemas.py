"""Pydantic response models for GET /admin/operations/needs-help."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.admin.operations_overview_schemas import SeverityBadge
from app.admin.incident_schemas import (
    LinkedIncidentsGroup,
    RecommendedIncidentAction,
)
from app.admin.operator_actions_schemas import AvailableActionMeta

PanelSeverity = Literal["critical", "failed", "warning", "information"]
SignalState = Literal["yes", "no", "unknown", "not_applicable"]


class RunbookRef(BaseModel):
    id: str
    label: str


class NeedsHelpQueueItem(BaseModel):
    id: str
    tenant_id: str
    customer_name: str
    category: str
    title: str
    impact: str
    severity: PanelSeverity
    severity_badge: SeverityBadge
    detected_at: str | None
    age_hours: int | None
    recommended_action: str
    safe_retry_available: SignalState
    external_action_may_have_occurred: SignalState
    link: str
    source_type: str
    available_actions: list[AvailableActionMeta] = []


class NeedsHelpSummary(BaseModel):
    critical: int
    failed: int
    warning: int
    information: int
    affected_tenants: int
    safe_retry_yes: int
    external_action_yes_or_unknown: int


class NeedsHelpQueueResponse(BaseModel):
    generated_at: datetime
    total: int
    summary: NeedsHelpSummary
    items: list[NeedsHelpQueueItem]
    limit: int
    offset: int


class NeedsHelpItemDetail(NeedsHelpQueueItem):
    runbook: RunbookRef | None = None
    recommended_incident_action: RecommendedIncidentAction | None = None
    linked_incidents: LinkedIncidentsGroup = LinkedIncidentsGroup()
