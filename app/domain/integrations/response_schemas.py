from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IntegrationEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: str
    tenant_id: str
    integration_type: str
    payload: dict[str, Any]
    status: str
    attempts: int
    last_error: str | None = None
    idempotency_key: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class IntegrationEventListResponse(BaseModel):
    items: list[IntegrationEventResponse] = Field(default_factory=list)
    total: int = 0