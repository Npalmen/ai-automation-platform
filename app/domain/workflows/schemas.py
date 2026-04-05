from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from app.domain.workflows.enums import JobType


class JobCreateRequest(BaseModel):
    tenant_id: str
    job_type: JobType = JobType.INTAKE
    input_data: Dict[str, Any] = Field(default_factory=dict)
    created_by: Optional[str] = None


class JobResponse(BaseModel):
    job_id: str
    tenant_id: str
    job_type: str
    status: str
    input_data: Dict[str, Any]
    result: Optional[Dict[str, Any]] = None
    processor_history: list[dict] = Field(default_factory=list)
    created_at: str
    updated_at: str