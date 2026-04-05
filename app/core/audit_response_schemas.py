from pydantic import BaseModel
from datetime import datetime
from typing import Any, Dict


class AuditEventResponse(BaseModel):
    event_id: str
    tenant_id: str
    category: str
    action: str
    status: str
    details: Dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True