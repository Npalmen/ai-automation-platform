from app.domain.workflows.models import Job
from app.domain.workflows.enums import JobType


def get_job_type(job: Job) -> JobType:
    return job.job_type