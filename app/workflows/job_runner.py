from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.core.audit_service import create_audit_event
from app.domain.workflows.models import Job
from app.domain.workflows.statuses import JobStatus
from app.workflows.job_router import get_job_type
from app.workflows.processor_registry import PROCESSOR_REGISTRY
from app.workflows.processors.unknown_processor import process_unknown_job
from app.workflows.processors.error_result_builder import build_error_result


def run_job(job: Job, db: Session) -> Job:
    try:
        create_audit_event(
            db=db,
            tenant_id=job.tenant_id,
            category="job",
            action="job_received",
            status="started",
            details={
                "job_id": job.job_id,
                "job_type": job.job_type.value,
            }
        )

        job.status = JobStatus.PROCESSING
        job.updated_at = datetime.now(timezone.utc)

        job_type = get_job_type(job)
        processor = PROCESSOR_REGISTRY.get(job_type)

        if processor is not None:
            job = processor(job)
        else:
            job = process_unknown_job(job, str(job_type))

        job.status = JobStatus.COMPLETED
        job.updated_at = datetime.now(timezone.utc)

        create_audit_event(
            db=db,
            tenant_id=job.tenant_id,
            category="job",
            action="job_completed",
            status="success",
            details={
                "job_id": job.job_id,
                "job_type": job.job_type.value,
                "final_status": job.status.value,
            }
        )

        return job

    except Exception as e:
        job.status = JobStatus.FAILED
        job.updated_at = datetime.now(timezone.utc)
        job.result = build_error_result(
            message="Job failed during execution",
            processed_for=job.tenant_id,
            detected_type=str(job.job_type),
            summary="Ett fel uppstod under körning.",
            error=str(e)
        )

        create_audit_event(
            db=db,
            tenant_id=job.tenant_id,
            category="job",
            action="job_failed",
            status="error",
            details={
                "job_id": job.job_id,
                "job_type": job.job_type.value,
                "error": str(e),
            }
        )

        return job