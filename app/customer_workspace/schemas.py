"""Pydantic schemas for customer workspace API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CustomerStatusValue = Literal[
    "new",
    "prioritized",
    "in_progress",
    "waiting_for_decision",
    "waiting_for_customer",
    "prepared",
    "scheduled",
    "completed",
    "needs_help",
    "failed",
    "cancelled",
    "unknown",
]

WorkItemTypeValue = Literal["lead", "support", "needs_help"]
ActivityTypeValue = Literal["lead", "support", "invoice", "all"]


class PartialError(BaseModel):
    section: str
    code: str
    message: str


class FeatureFlags(BaseModel):
    customer_workspace_writes: bool = False
    connected_api: bool = True


class WorkspaceContextResponse(BaseModel):
    tenant_id: str
    company_name: str
    contact_name: str
    contact_email: str
    support_email: str
    language: str
    region: str
    workspace_mode: Literal["connected"] = "connected"
    feature_flags: FeatureFlags


class OverviewSummary(BaseModel):
    cases_handled_today: int = 0
    waiting_for_decision: int = 0
    waiting_for_customer: int = 0
    needs_help: int = 0
    failed_today: int = 0
    estimated_hours_saved: float = 0
    estimated_value_sek: float = 0


class PriorityWorkItem(BaseModel):
    work_item_id: str
    type: WorkItemTypeValue
    title: str
    customer_name: str | None = None
    customer_status: CustomerStatusValue
    customer_status_label: str
    priority_rank: int
    priority_label: str | None = None
    updated_at: datetime | str | None = None


class OverviewResponse(BaseModel):
    last_updated_at: datetime | str
    summary: OverviewSummary
    priority_work_items: list[PriorityWorkItem]
    partial_errors: list[PartialError] = Field(default_factory=list)


class WorkItemListItem(BaseModel):
    work_item_id: str
    type: WorkItemTypeValue
    title: str
    customer_name: str | None = None
    customer_email: str | None = None
    customer_status: CustomerStatusValue
    customer_status_label: str
    priority_rank: int
    priority_label: str | None = None
    summary: str | None = None
    created_at: datetime | str | None = None
    updated_at: datetime | str | None = None


class WorkItemListResponse(BaseModel):
    items: list[WorkItemListItem]
    total: int
    limit: int
    offset: int
    partial_errors: list[PartialError] = Field(default_factory=list)


class TimelineEvent(BaseModel):
    at: datetime | str | None
    kind: str
    label: str
    detail: str | None = None


class WorkItemDetailResponse(BaseModel):
    work_item_id: str
    type: WorkItemTypeValue
    title: str
    customer_name: str | None = None
    customer_email: str | None = None
    customer_status: CustomerStatusValue
    customer_status_label: str
    priority_rank: int
    summary: str | None = None
    created_at: datetime | str | None = None
    updated_at: datetime | str | None = None
    timeline: list[TimelineEvent]
    waiting_for: str | None = None
    human_takeover_required: bool = False


class ApprovalListItem(BaseModel):
    approval_id: str
    work_item_id: str
    work_item_type: WorkItemTypeValue
    work_item_title: str
    title: str
    summary: str | None = None
    customer_status: CustomerStatusValue
    customer_status_label: str
    requested_at: datetime | str | None = None


class ApprovalListResponse(BaseModel):
    items: list[ApprovalListItem]
    total: int
    limit: int
    offset: int
    partial_errors: list[PartialError] = Field(default_factory=list)


class ActivityListItem(BaseModel):
    at: datetime | str | None
    type: str
    customer_status: CustomerStatusValue
    customer_status_label: str
    priority: str | None = None
    label: str


class ActivityListResponse(BaseModel):
    items: list[ActivityListItem]
    total: int
    limit: int
    offset: int
    partial_errors: list[PartialError] = Field(default_factory=list)


class HealthSystemStatus(BaseModel):
    status: str
    label: str


class HealthResponse(BaseModel):
    overall_status: str
    message: str
    systems: dict[str, HealthSystemStatus]


class WorkItemsQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    type: Literal["lead", "support", "needs_help", "all"] = "all"
    status: CustomerStatusValue | None = None
    q: str | None = None
    from_: datetime | None = Field(default=None, alias="from")
    to: datetime | None = None
    sort: Literal["updated_at", "priority_rank", "created_at"] = "priority_rank"
    order: Literal["asc", "desc"] | None = None
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @field_validator("q")
    @classmethod
    def normalize_q(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def validate_date_range(self) -> WorkItemsQuery:
        if self.from_ and self.to and self.from_ > self.to:
            raise ValueError("from must be before to")
        return self

    def resolved_order(self) -> str:
        if self.order:
            return self.order
        if self.sort == "priority_rank":
            return "asc"
        return "desc"


class ApprovalsQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["pending", "all"] = "pending"
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class ActivityQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: ActivityTypeValue = "all"
    limit: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
