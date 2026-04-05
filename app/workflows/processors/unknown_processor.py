from app.domain.workflows.models import Job
from app.workflows.processors.result_builder import build_processor_result


def process_unknown_job(job: Job, job_type: str) -> Job:
    text = str(job.input_data.get("text", ""))

    job.result = build_processor_result(
        message="Unknown job type processed",
        processed_for=job.tenant_id,
        detected_type=job_type,
        summary="Ingen speciallogik hittades för denna jobbtyp ännu.",
        extracted_data={
            "text_preview": text[:100]
        }
    )
    return job