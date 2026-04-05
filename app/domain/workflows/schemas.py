from pydantic import BaseModel, Field
from typing import Dict, Any

from app.domain.workflows.enums import JobType


class CreateJobRequest(BaseModel):
    job_type: JobType
    input_data: Dict[str, Any] = Field(default_factory=dict)