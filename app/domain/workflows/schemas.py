from typing import Any

from pydantic import BaseModel, Field

from app.domain.workflows.enums import JobType


class JobCreateRequest(BaseModel):
    tenant_id: str
    job_type: JobType
    input_data: dict[str, Any] = Field(default_factory=dict)


class CreateJobRequest(JobCreateRequest):
    pass


class IntegrationActionRequest(BaseModel):
    integration_type: str
    action: str
    payload: dict[str, Any] = Field(default_factory=dict)