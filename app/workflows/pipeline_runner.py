from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.workflows.job_runner import run_job
from app.workflows.processor_registry import get_pipeline_for_job_type
from app.integrations.dispatcher import IntegrationDispatcher
from app.repositories.postgres.session import SessionLocal


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
        JobType.POLICY,
        JobType.HUMAN_HANDOFF,
    ],
    JobType.CUSTOMER_INQUIRY: [
        JobType.ENTITY_EXTRACTION,
        JobType.CUSTOMER_INQUIRY,
        JobType.POLICY,
        JobType.HUMAN_HANDOFF,
    ],
    JobType.UNKNOWN: [
        JobType.POLICY,
        JobType.HUMAN_HANDOFF,
    ],
}


def run_pipeline(job: Job, db):
    current_job = job

    # Kör intake + classification
    for step in BASE_PIPELINE:
        current_job.job_type = step
        current_job = run_job(current_job, db)

    # Läs classification-resultat
    classification_result = current_job.result or {}
    payload = classification_result.get("payload") or {}

    detected_type_str = payload.get("detected_job_type", "unknown")

    try:
        detected_type = JobType(detected_type_str)
    except ValueError:
        detected_type = JobType.UNKNOWN

    # Sätt affärstyp
    current_job.job_type = detected_type

    # Hämta pipeline
    next_steps = POST_CLASSIFICATION_PIPELINES.get(
        detected_type,
        POST_CLASSIFICATION_PIPELINES[JobType.UNKNOWN],
    )

    # Kör resterande steg utan att skriva över affärstyp permanent
    for step in next_steps:
        step_job = current_job.model_copy(deep=True)
        step_job.job_type = step
        step_result = run_job(step_job, db)

        current_job.result = step_result.result
        current_job.processor_history = step_result.processor_history
        current_job.status = step_result.status
        current_job.updated_at = step_result.updated_at

    return current_job


async def run_pipeline(job):
    pipeline = get_pipeline_for_job_type(job.job_type)

    for processor_name in pipeline:
        job = await run_job(job, processor_name)

    db = SessionLocal()
    try:
        dispatcher = IntegrationDispatcher(db)
        await dispatcher.dispatch(job)
    finally:
        db.close()

    return job