from datetime import datetime
from typing import Any, Dict

from pydantic import BaseModel, ConfigDict


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: str
    tenant_id: str
    category: str
    action: str
    status: str
    details: Dict[str, Any]
    created_at: datetime