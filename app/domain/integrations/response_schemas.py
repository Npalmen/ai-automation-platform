from datetime import datetime
from typing import Any

from pydantic import BaseModel


class IntegrationEventResponse(BaseModel):
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

    class Config:
        from_attributes = True


class IntegrationEventListResponse(BaseModel):
    tenant_id: str | None = None
    total: int
    limit: int
    offset: int
    events: list[IntegrationEventResponse]