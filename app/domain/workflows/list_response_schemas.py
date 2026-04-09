from pydantic import BaseModel, Field

from app.domain.workflows.response_schemas import JobResponse


class JobListResponse(BaseModel):
    items: list[JobResponse] = Field(default_factory=list)
    total: int = 0