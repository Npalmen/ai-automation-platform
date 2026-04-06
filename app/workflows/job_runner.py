from __future__ import annotations

import inspect
from datetime import datetime, timezone

from app.domain.workflows.models import Job
from app.workflows.processor_registry import PROCESSOR_REGISTRY


class WorkflowStepExecutionError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def run_job(job: Job, db=None) -> Job:
    processor = PROCESSOR_REGISTRY.get(job.job_type)
    if processor is None:
        raise ValueError(f"No processor registered for job type '{job.job_type.value}'")

    job.status = "running"
    job.updated_at = datetime.now(timezone.utc)

    try:
        signature = inspect.signature(processor)
        if "db" in signature.parameters:
            processed_job = processor(job, db=db)
        else:
            processed_job = processor(job)
    except WorkflowStepExecutionError:
        raise
    except Exception as exc:
        raise WorkflowStepExecutionError(str(exc)) from exc

    processed_job.status = "completed"
    processed_job.updated_at = datetime.now(timezone.utc)
    return processed_job