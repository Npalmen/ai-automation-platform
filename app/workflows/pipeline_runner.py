from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.workflows.runner import run_job


BASE_PIPELINE = [
    JobType.INTAKE,
    JobType.CLASSIFICATION,
]


POST_CLASSIFICATION_PIPELINES = {
    JobType.INVOICE: [
        JobType.ENTITY_EXTRACTION,
        JobType.POLICY,
        JobType.HUMAN_HANDOFF,
    ],
    JobType.LEAD: [
        JobType.ENTITY_EXTRACTION,
        JobType.POLICY,
        JobType.HUMAN_HANDOFF,
    ],
    JobType.CUSTOMER_INQUIRY: [
        JobType.ENTITY_EXTRACTION,
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

    # Kör intake + classification först
    for step in BASE_PIPELINE:
        current_job.job_type = step
        current_job = run_job(current_job, db)

    # Hämta resultat från classification
    classification_result = current_job.result or {}
    payload = classification_result.get("payload") or {}

    detected_type_str = payload.get("detected_job_type", "unknown")

    try:
        detected_type = JobType(detected_type_str)
    except ValueError:
        detected_type = JobType.UNKNOWN

    # Hämta rätt pipeline
    next_steps = POST_CLASSIFICATION_PIPELINES.get(
        detected_type,
        POST_CLASSIFICATION_PIPELINES[JobType.UNKNOWN],
    )

    # Kör resten
    for step in next_steps:
        current_job.job_type = step
        current_job = run_job(current_job, db)

    return current_job