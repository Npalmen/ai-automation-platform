from pydantic import BaseModel
from datetime import datetime
from typing import Any, Dict


class JobResponse(BaseModel):
    job_id: str
    tenant_id: str
    job_type: str
    status: str
    input_data: Dict[str, Any]
    result: Dict[str, Any] | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True