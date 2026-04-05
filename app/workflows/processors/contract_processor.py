from app.domain.workflows.models import Job
from app.workflows.processors.result_builder import build_processor_result


def process_contract_job(job: Job) -> Job:
    text = str(job.input_data.get("text", ""))

    job.result = build_processor_result(
        message="Contract job processed successfully",
        processed_for=job.tenant_id,
        detected_type="contract",
        summary="Avtal identifierat och redo för nästa steg.",
        extracted_data={
            "text_preview": text[:100],
            "character_count": len(text)
        }
    )
    return job