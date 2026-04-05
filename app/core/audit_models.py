from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Dict, Any
import uuid


class AuditEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    category: str
    action: str
    status: str
    details: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))