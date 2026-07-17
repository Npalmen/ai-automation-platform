"""Pydantic models for operator panel safe-write actions (Kapitel 5)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

OperatorActionStatus = Literal[
    "completed", "no_change", "blocked", "failed", "uncertain"
]
SafetyClass = Literal["safe_write", "critical_write"]
ExternalEffect = Literal["no", "yes", "idempotent_side_effect"]


class OperatorActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(..., min_length=1, max_length=500)
    confirmation: Literal[True]
    idempotency_key: str | None = Field(default=None, max_length=128)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("reason must not be empty")
        return stripped


class AvailableActionMeta(BaseModel):
    action_id: str
    label: str
    safety_class: SafetyClass
    required_role: Literal["read_only", "operations", "admin"]
    requires_reason: bool
    requires_confirmation: bool
    allowed: bool
    blocked_reason: str | None = None


class OperatorActionResponse(BaseModel):
    action_id: str
    tenant_id: str
    resource_id: str | None
    status: OperatorActionStatus
    changed: bool
    message: str
    executed_at: datetime
    audit_event_id: str | None
