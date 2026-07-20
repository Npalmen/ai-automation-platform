"""Pydantic schemas for operator alerts API (Kapitel 10)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

AlertSeverity = Literal["info", "warning", "high", "critical"]
AlertStatus = Literal["open", "acknowledged", "snoozed", "resolved", "suppressed"]
AlertScopeType = Literal[
    "system", "tenant", "integration", "job", "backup", "deploy", "capacity"
]
AlertSourceClass = Literal["intern_db_detected", "intern_metadata_detected"]
ReopenPolicy = Literal["reopen_existing", "create_new_after_grace", "never_reopen"]

ACTIVE_ALERT_STATUSES = frozenset({"open", "acknowledged", "snoozed"})


class AlertSafeDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: str | None = None
    source_id: str | None = None
    age_hours: int | None = None
    runbook_ref: str | None = None
    recommended_action: str | None = None


class AlertListItem(BaseModel):
    id: str
    alert_type: str
    alert_type_label: str
    scope_type: AlertScopeType
    tenant_id: str | None
    related_job_id: str | None
    integration_key: str | None
    severity: AlertSeverity
    status: AlertStatus
    title: str
    summary: str
    source_class: AlertSourceClass
    first_detected_at: datetime
    last_detected_at: datetime
    occurrence_count: int
    age_hours: int | None
    version: int


class AlertDetail(AlertListItem):
    safe_details: dict[str, Any]
    source: str
    source_version: str
    last_evaluated_at: datetime
    acknowledged_at: datetime | None
    acknowledged_by: str | None
    snoozed_until: datetime | None
    resolved_at: datetime | None
    resolution_reason: str | None
    runbook_ref: str | None
    recommended_action: str | None


class AlertSummaryResponse(BaseModel):
    generated_at: datetime
    open_critical: int
    open_high: int
    open_warning: int
    open_info: int
    total_open: int
    last_evaluation_at: datetime | None
    last_evaluation_status: str | None


class AlertListResponse(BaseModel):
    generated_at: datetime
    total: int
    items: list[AlertListItem]
    limit: int
    offset: int


class AlertRegistryItem(BaseModel):
    alert_type: str
    label_sv: str
    description_sv: str
    default_severity: AlertSeverity
    scope_type: AlertScopeType
    detection_class: str
    reopen_policy: ReopenPolicy
    manual_resolve_allowed: bool
    suppress_allowed: bool
    runbook_ref: str | None
    enabled_by_default: bool
    slice: int


class AlertRegistryResponse(BaseModel):
    registry_version: str
    items: list[AlertRegistryItem]


class AlertAcknowledgeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int
    reason: str | None = Field(default=None, max_length=500)


class AlertSnoozeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int
    snoozed_until: datetime
    reason: str | None = Field(default=None, max_length=500)


class AlertResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int
    reason: str = Field(min_length=3, max_length=500)


class AlertSuppressRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int
    reason: str = Field(min_length=3, max_length=500)
    expires_at: datetime | None = None


class AlertWriteResponse(BaseModel):
    alert: AlertDetail


class AlertEvaluationRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dry_run: bool = False
    scope: str = "platform"


class AlertEvaluationRunResponse(BaseModel):
    run_id: str | None
    status: str
    dry_run: bool
    created_count: int
    updated_count: int
    resolved_count: int
    error_count: int
    evaluator_results: list[dict[str, Any]]
    started_at: datetime
    completed_at: datetime | None


class AlertEvaluationStatusResponse(BaseModel):
    last_run: AlertEvaluationRunResponse | None


class OperatorDigestItem(BaseModel):
    priority: int
    kind: str
    title: str
    summary: str
    severity: AlertSeverity | None
    tenant_id: str | None
    alert_id: str | None
    link: str | None
    age_hours: int | None = None


class OperatorDigestResponse(BaseModel):
    id: str
    digest_date: str
    timezone: str
    generated_at: datetime
    period_start: datetime
    period_end: datetime
    delivery_status: str
    items: list[OperatorDigestItem]
    limitation_notes: list[str]


class OperatorDigestListResponse(BaseModel):
    items: list[OperatorDigestResponse]


class OperatorDigestGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    digest_date: str | None = None
    timezone: str = "Europe/Stockholm"
