from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.domain.workflows.statuses import JobStatus
from app.domain.workflows.models import Job
from app.workflows.processor_registry import PROCESSOR_REGISTRY


def run_job(job: Job, db: Session) -> Job:
    processor = PROCESSOR_REGISTRY.get(job.job_type)

    if not processor:
        job.status = JobStatus.FAILED
        job.result = {
            "status": "failed",
            "summary": f"No processor registered for job_type={job.job_type}",
            "requires_human_review": True,
            "payload": {},
        }
        job.updated_at = datetime.now(timezone.utc)
        return job

    try:
        job = processor(job)
        job.status = JobStatus.COMPLETED
    except Exception as e:
        job.status = JobStatus.FAILED
        job.result = {
            "status": "failed",
            "summary": "Processor execution failed.",
            "requires_human_review": True,
            "payload": {
                "error": str(e),
                "processor": str(job.job_type),
            },
        }

    job.updated_at = datetime.now(timezone.utc)
    return job