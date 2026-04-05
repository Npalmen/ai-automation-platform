from app.domain.workflows.models import Job
from app.workflows.processors.result_builder import build_processor_result


def process_email_job(job: Job) -> Job:
    text = str(job.input_data.get("text", ""))

    job.result = build_processor_result(
        message="Email job processed successfully",
        processed_for=job.tenant_id,
        detected_type="email",
        summary="E-post identifierad och redo för nästa steg.",
        extracted_data={
            "text_preview": text[:100],
            "contains_question": "?" in text
        }
    )
    return job