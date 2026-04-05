from datetime import datetime, timezone

from app.domain.workflows.models import Job
from app.workflows.processor_registry import PROCESSOR_REGISTRY


def run_job(job: Job, db=None) -> Job:
    processor = PROCESSOR_REGISTRY.get(job.job_type)

    if processor is None:
        raise ValueError(f"No processor registered for job type '{job.job_type.value}'")

    job.status = "running"
    job.updated_at = datetime.now(timezone.utc)

    processed_job = processor(job)

    processed_job.status = "completed"
    processed_job.updated_at = datetime.now(timezone.utc)

    return processed_job