from pydantic import BaseModel, Field

from app.core.audit_response_schemas import AuditEventResponse


class AuditEventListResponse(BaseModel):
    items: list[AuditEventResponse] = Field(default_factory=list)
    total: int = 0