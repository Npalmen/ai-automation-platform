"""Pydantic response models for GET /admin/operations/overview."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

StatusLevel = Literal["healthy", "warning", "failed", "critical", "paused", "unknown"]
SeverityBadge = Literal["P1", "P2", "P3", "P4"]
TriState = Literal["yes", "no", "unknown"]


class PeriodInfo(BaseModel):
    hours: int
    started_at: datetime


class PlatformStatus(BaseModel):
    level: StatusLevel
    label: str
    summary: str


class CounterValue(BaseModel):
    value: int
    window_hours: int | None


class Counters(BaseModel):
    active_tenants: CounterValue
    jobs_last_24h: CounterValue
    pending_approvals: CounterValue
    open_manual_reviews: CounterValue
    failed_jobs: CounterValue
    stuck_jobs: CounterValue
    integration_errors: CounterValue


class IntegrationStatus(BaseModel):
    status: StatusLevel
    issues: int
    affected_tenants: int
    data_source: str


class IntegrationsBlock(BaseModel):
    gmail: IntegrationStatus
    visma: IntegrationStatus
    google_sheets: IntegrationStatus


class SystemComponentStatus(BaseModel):
    status: StatusLevel
    description: str | None = None


class BackupStatus(BaseModel):
    status: StatusLevel
    data_source: str


class DeployStatus(BaseModel):
    status: StatusLevel
    data_source: str


class SystemBlock(BaseModel):
    api: SystemComponentStatus
    database: SystemComponentStatus
    scheduler: SystemComponentStatus
    backup: BackupStatus
    deploy: DeployStatus


class PriorityItem(BaseModel):
    id: str
    tenant_id: str
    customer_name: str
    category: str
    title: str
    impact: str
    severity: str
    severity_badge: SeverityBadge
    detected_at: str | None
    age_hours: int | None
    recommended_action: str
    safe_retry_available: TriState
    external_action_may_have_occurred: TriState
    link: str


class OperationsOverviewResponse(BaseModel):
    generated_at: datetime
    period: PeriodInfo
    platform_status: PlatformStatus
    counters: Counters
    integrations: IntegrationsBlock
    system: SystemBlock
    priorities: list[PriorityItem]
