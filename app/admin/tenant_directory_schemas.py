"""Pydantic response models for GET /admin/tenants and GET /admin/tenants/{tenant_id}/overview."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.admin.operations_overview_schemas import PriorityItem, StatusLevel
from app.admin.operator_actions_schemas import AvailableActionMeta

IntegrationSummaryStatus = Literal["healthy", "warning", "failed", "unknown"]
TenantStatusValue = Literal["active", "inactive", "unknown"]


class TenantHealth(BaseModel):
    level: StatusLevel
    label: str
    summary: str


class IntegrationSummary(BaseModel):
    gmail: IntegrationSummaryStatus
    visma: IntegrationSummaryStatus
    google_sheets: IntegrationSummaryStatus


class TenantListItem(BaseModel):
    tenant_id: str
    name: str
    slug: str | None
    tenant_status: TenantStatusValue
    health: TenantHealth
    package: None = None
    operator_owner: None = None
    enabled_modules: list[str]
    open_issues_count: int
    pending_approvals: int
    open_manual_reviews: int
    jobs_last_30d: int
    last_activity_at: datetime | None
    integrations_summary: IntegrationSummary
    created_at: datetime | None
    updated_at: datetime | None


class TenantListResponse(BaseModel):
    items: list[TenantListItem]
    total: int


class TenantBasicInfo(BaseModel):
    tenant_id: str
    name: str
    slug: str | None
    tenant_status: TenantStatusValue
    package: None = None
    operator_owner: None = None
    enabled_modules: list[str]
    enabled_job_types: list[str]
    allowed_integrations: list[str]
    auto_actions: dict[str, Any]
    created_at: datetime | None
    updated_at: datetime | None


class TenantIntegrationStatus(BaseModel):
    status: IntegrationSummaryStatus
    description: str
    recommended_action: str | None = None
    data_source: str
    last_success_at: str | None = None
    last_error_at: str | None = None


class TenantIntegrationsBlock(BaseModel):
    gmail: TenantIntegrationStatus
    monday: TenantIntegrationStatus
    fortnox: TenantIntegrationStatus
    visma: TenantIntegrationStatus
    google_sheets: TenantIntegrationStatus


class TenantJobSummary(BaseModel):
    job_id: str
    job_type: str
    status: str
    created_at: datetime
    updated_at: datetime


class TenantJobsBlock(BaseModel):
    total: int
    jobs_last_30d: int
    recent: list[TenantJobSummary]


class TenantApprovalSummary(BaseModel):
    approval_id: str
    job_id: str
    job_type: str
    state: str
    title: str | None
    summary: str | None
    created_at: str


class TenantApprovalsBlock(BaseModel):
    pending_count: int
    recent: list[TenantApprovalSummary]


class TenantManualReviewItem(BaseModel):
    job_id: str
    job_type: str
    status: str
    subject: str | None
    manual_review_reason: str | None
    unresolved: bool


class TenantManualReviewBlock(BaseModel):
    total: int
    recent: list[TenantManualReviewItem]


class TenantUsageBlock(BaseModel):
    jobs_created: int
    jobs_completed: int
    pending_approvals: int
    blocked_flows: int
    dispatches_total: int
    dispatches_successful: int
    dispatches_failed: int
    automation_rate_percent: int
    time_saved_hours: float


class TenantAuditEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: str
    tenant_id: str
    category: str
    action: str
    status: str
    details: dict[str, Any]
    created_at: datetime


class TenantAuditBlock(BaseModel):
    total: int
    recent: list[TenantAuditEvent]


class TenantOnboardingConfigSummary(BaseModel):
    schema_version: int | None = None
    service_profiles: list[str] = Field(default_factory=list)
    lead_requirements: dict[str, Any] = Field(default_factory=dict)
    internal_routing_hints: dict[str, str] = Field(default_factory=dict)
    intake: dict[str, Any] = Field(default_factory=dict)


class TenantLifecycleSummary(BaseModel):
    lifecycle_status: str
    lifecycle_label_sv: str
    config_version: int
    is_test_tenant: bool = False
    operations_paused: bool = False
    scheduler_run_mode: str | None = None
    lifecycle_updated_at: datetime | None = None
    lifecycle_updated_by: str | None = None
    last_config_updated_by: str | None = None


class TenantDetailResponse(BaseModel):
    tenant: TenantBasicInfo
    health: TenantHealth
    integrations: TenantIntegrationsBlock
    jobs: TenantJobsBlock
    approvals: TenantApprovalsBlock
    manual_review: TenantManualReviewBlock
    recent_errors: list[PriorityItem]
    usage: TenantUsageBlock
    audit: TenantAuditBlock
    onboarding_config: TenantOnboardingConfigSummary = Field(
        default_factory=TenantOnboardingConfigSummary
    )
    lifecycle: TenantLifecycleSummary | None = None
    available_actions: list[AvailableActionMeta] = []
