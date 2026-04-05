from app.core.audit_service import create_audit_event
from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.repositories.postgres.job_repository import JobRepository
from app.workflows.job_runner import run_job


BASE_PIPELINE = [
    JobType.INTAKE,
    JobType.CLASSIFICATION,
]


POST_CLASSIFICATION_PIPELINES = {
    JobType.INVOICE: [
        JobType.ENTITY_EXTRACTION,
        JobType.INVOICE,
        JobType.POLICY,
        JobType.HUMAN_HANDOFF,
    ],
    JobType.LEAD: [
        JobType.ENTITY_EXTRACTION,
        JobType.LEAD,
        JobType.DECISIONING,
        JobType.POLICY,
        JobType.ACTION_DISPATCH,
        JobType.HUMAN_HANDOFF,
    ],
    JobType.CUSTOMER_INQUIRY: [
        JobType.ENTITY_EXTRACTION,
        JobType.CUSTOMER_INQUIRY,
        JobType.DECISIONING,
        JobType.POLICY,
        JobType.ACTION_DISPATCH,
        JobType.HUMAN_HANDOFF,
    ],
    JobType.UNKNOWN: [
        JobType.POLICY,
        JobType.HUMAN_HANDOFF,
    ],
}


def _persist(job: Job, db) -> Job:
    if db is None:
        return job

    return JobRepository.update_job(db, job)


def _audit(job: Job, step: JobType, db):
    if db is None:
        return

    result = job.result or {}
    payload = result.get("payload") or {}

    create_audit_event(
        db=db,
        tenant_id=job.tenant_id,
        category="workflow",
        action="processor_step_completed",
        status="success",
        details={
            "job_id": job.job_id,
            "step": step.value,
            "processor_name": payload.get("processor_name"),
            "prompt_name": payload.get("prompt_name"),
            "used_fallback": payload.get("used_fallback", False),
            "confidence": payload.get("confidence"),
            "low_confidence": payload.get("low_confidence", False),
            "requires_human_review": result.get("requires_human_review"),
            "decision": payload.get("decision"),
            "routing": payload.get("routing"),
            "target_queue": payload.get("target_queue"),
            "approval_route": payload.get("approval_route"),
            "validation_status": payload.get("validation_status"),
            "next": payload.get("recommended_next_step"),
        },
    )


def _run_step(job: Job, step: JobType, db):
    job.job_type = step
    job = run_job(job, db)

    job = _persist(job, db)
    _audit(job, step, db)

    return job


def run_pipeline(job: Job, db):
    current = job

    for step in BASE_PIPELINE:
        current = _run_step(current, step, db)

    payload = (current.result or {}).get("payload") or {}
    detected = payload.get("detected_job_type", JobType.UNKNOWN.value)

    try:
        detected_type = JobType(detected)
    except ValueError:
        detected_type = JobType.UNKNOWN

    next_steps = POST_CLASSIFICATION_PIPELINES.get(
        detected_type,
        POST_CLASSIFICATION_PIPELINES[JobType.UNKNOWN],
    )

    for step in next_steps:
        current = _run_step(current, step, db)

    return current