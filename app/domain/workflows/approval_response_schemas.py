from __future__ import annotations

from pydantic import BaseModel, Field


class ApprovalRequestResponse(BaseModel):
    approval_id: str
    tenant_id: str
    job_id: str
    job_type: str | None = None
    state: str
    channel: str
    title: str | None = None
    summary: str | None = None
    requested_by: str | None = None
    requested_at: str | None = None
    resolved_at: str | None = None
    resolved_by: str | None = None
    resolved_via: str | None = None
    resolution_note: str | None = None
    next_on_approve: str | None = None
    next_on_reject: str | None = None
    request_payload: dict = Field(default_factory=dict)
    delivery_payload: dict | None = None
    created_at: str
    updated_at: str


class ApprovalRequestListResponse(BaseModel):
    items: list[ApprovalRequestResponse] = Field(default_factory=list)
    total: int