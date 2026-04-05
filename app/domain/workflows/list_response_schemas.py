from pydantic import BaseModel

from app.domain.workflows.response_schemas import JobResponse


class JobListResponse(BaseModel):
    tenant_id: str
    total: int
    limit: int
    offset: int
    jobs: list[JobResponse]