from pydantic import BaseModel

from app.core.audit_response_schemas import AuditEventResponse


class AuditEventListResponse(BaseModel):
    tenant_id: str | None = None
    total: int
    limit: int
    offset: int
    events: list[AuditEventResponse]