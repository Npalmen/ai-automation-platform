from datetime import datetime
from typing import Any, Dict

from pydantic import BaseModel, ConfigDict


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: str
    tenant_id: str
    job_type: str
    status: str
    input_data: Dict[str, Any]
    result: Dict[str, Any] | None
    created_at: datetime
    updated_at: datetime