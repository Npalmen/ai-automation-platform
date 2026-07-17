"""Pydantic response models for Kapitel 7 usage/cost/capacity endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.admin.operations_overview_schemas import StatusLevel

AUTOMATION_RATE_NOT_MEASURED_REASON = (
    "audit_events saknar en indexerad job_id-koppling för operator_action, "
    "vilket krävs för att verifiera frånvaro av ingripande per jobb under hela dess livscykel."
)
MANUAL_REVIEWS_NOT_MEASURED_REASON = (
    "Manual review-skapande loggas inte fullständigt oberoende av kanal; "
    "endast Gmail-överlämningar är auditerade."
)
AI_COST_UNKNOWN_REASON = "Kostnad mäts inte tillförlitligt ännu."

VALID_USAGE_DAYS = frozenset({7, 30, 90})


class UsagePeriod(BaseModel):
    days: int
    started_at: datetime
    ended_at: datetime
    comparison_started_at: datetime
    comparison_ended_at: datetime


class ComparisonInt(BaseModel):
    current: int
    previous: int
    absolute_change: int
    percentage_change: float | None


class ProxyTimestampMetric(BaseModel):
    value: int
    timestamp_basis: Literal["updated_at_proxy"] = "updated_at_proxy"


class ComparisonProxyMetric(BaseModel):
    current: ProxyTimestampMetric
    previous: ProxyTimestampMetric
    absolute_change: int
    percentage_change: float | None


class NotMeasuredValue(BaseModel):
    value: None = None
    status: Literal["not_measured"] = "not_measured"
    reason: str


class AiUsageBlock(BaseModel):
    status: Literal["measured", "not_measured"]
    input_tokens: int | None = None
    output_tokens: int | None = None
    requests: int | None = None
    reason: str | None = None


class AiCostBlock(BaseModel):
    status: Literal["measured", "estimated", "unknown"]
    amount: float | None = None
    currency: str | None = None
    calculation_method: str | None = None
    pricing_version: str | None = None
    reason: str | None = None


class CapacityBlock(BaseModel):
    status: Literal["measured", "baseline_missing", "warning", "unknown"]
    jobs_per_day_average: float | None = None
    peak_jobs_per_hour: int | None = None
    operator_actions_per_day: float | None = None
    open_incidents_current: int | None = None
    needs_help_open_current: int | None = None


class UsageSummary(BaseModel):
    active_tenants: int
    tenants_with_activity: int
    jobs_received: ComparisonInt
    jobs_completed: ComparisonProxyMetric
    jobs_failed: ComparisonProxyMetric
    automation_rate: NotMeasuredValue
    operator_actions: ComparisonInt
    gmail_manual_review_handoffs: ComparisonInt
    manual_reviews_created: NotMeasuredValue
    open_manual_reviews_current: int
    pending_approvals_current: int
    incidents_created: ComparisonInt
    incidents_resolved: ComparisonInt
    open_incidents_current: int
    critical_incidents_created: ComparisonInt
    integration_errors: ComparisonInt
    needs_help_open_current: int
    tenants_with_open_signals_current: int


class UsageTenantItem(BaseModel):
    tenant_id: str
    customer_name: str
    tenant_status: str
    jobs_received: int
    jobs_completed: ProxyTimestampMetric
    jobs_failed: ProxyTimestampMetric
    automation_rate: NotMeasuredValue
    gmail_manual_review_handoffs: int
    manual_reviews_created: NotMeasuredValue
    open_manual_reviews_current: int
    pending_approvals_current: int
    operator_actions: int
    incidents_created: int
    integration_errors: int
    ai_usage: AiUsageBlock
    ai_cost: AiCostBlock
    latest_activity_at: datetime | None = None
    attention_status: StatusLevel


class UsageOverviewResponse(BaseModel):
    generated_at: datetime
    period: UsagePeriod
    summary: UsageSummary
    ai_usage: AiUsageBlock
    ai_cost: AiCostBlock
    capacity: CapacityBlock
    data_quality_notes: list[str] = Field(default_factory=list)


class UsageTenantListResponse(BaseModel):
    generated_at: datetime
    period: UsagePeriod
    total: int
    limit: int
    offset: int
    items: list[UsageTenantItem]
