from __future__ import annotations

from pydantic import BaseModel, Field


class ActionExecutionResponse(BaseModel):
    execution_id: str
    tenant_id: str
    job_id: str
    action_type: str
    status: str
    target: str | None = None
    provider: str | None = None
    external_id: str | None = None
    attempt_no: int = 1
    request_payload: dict = Field(default_factory=dict)
    result_payload: dict | None = None
    error_message: str | None = None
    executed_at: str
    created_at: str
    updated_at: str


class ActionExecutionListResponse(BaseModel):
    items: list[ActionExecutionResponse] = Field(default_factory=list)
    total: int