from datetime import datetime, timezone
from typing import Any, Optional
import uuid

from pydantic import BaseModel, Field

from app.domain.workflows.enums import JobType
from app.domain.workflows.statuses import JobStatus


class Job(BaseModel):
    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    job_type: JobType = JobType.UNKNOWN
    status: JobStatus = JobStatus.PENDING
    input_data: dict[str, Any] = Field(default_factory=dict)
    result: Optional[dict[str, Any]] = None
    processor_history: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))