from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.domain.workflows.statuses import JobStatus
from app.workflows.processor_registry import get_processor


@dataclass(slots=True)
class WorkflowStepExecutionError(Exception):
    step: JobType
    message: str

    def __str__(self) -> str:
        return f"Workflow step '{self.step.value}' failed: {self.message}"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def run_job(job: Job, db=None) -> Job:
    """
    Executes exactly one workflow step based on job.job_type.

    The db argument is accepted for compatibility with existing callers,
    but persistence is handled by the pipeline/orchestrator layer.
    """
    step = job.job_type
    processor = get_processor(step)

    working_job = job.model_copy(deep=True)
    working_job.status = JobStatus.PROCESSING
    working_job.updated_at = _utcnow()

    try:
        processed_job = processor(working_job)
    except Exception as exc:
        raise WorkflowStepExecutionError(step=step, message=str(exc)) from exc

    processed_job.updated_at = _utcnow()
    return processed_job


def run_job_step(job: Job, step: JobType) -> Job:
    """
    Explicit step execution helper for future orchestrator use.
    """
    working_job = job.model_copy(deep=True)
    working_job.job_type = step
    return run_job(working_job)