from app.ai.schemas import InvoiceAnalysisResponse
from app.domain.workflows.models import Job
from app.workflows.processors.ai_processor_utils import (
    get_latest_processor_payload,
    run_ai_step,
)
from app.workflows.validators.invoice_validator import validate_invoice_data


PROCESSOR_NAME = "invoice_processor"
PROMPT_NAME = "invoice_analysis"


def _build_source_context(job: Job) -> dict:
    input_data = job.input_data or {}
    sender = input_data.get("sender") or {}
    attachments = input_data.get("attachments") or []

    classification_payload = get_latest_processor_payload(job, "classification_processor")
    extraction_payload = get_latest_processor_payload(job, "entity_extraction_processor")

    return {
        "job_id": job.job_id,
        "tenant_id": job.tenant_id,
        "job_type": job.job_type.value,
        "input_data": {
            "subject": input_data.get("subject"),
            "message_text": input_data.get("message_text"),
            "sender": {
                "name": sender.get("name"),
                "email": sender.get("email"),
                "phone": sender.get("phone"),
            },
            "attachments": attachments,
        },
        "history": {
            "classification": classification_payload,
            "entity_extraction": extraction_payload,
        },
    }


def process_invoice_job(job: Job) -> Job:
    context = _build_source_context(job)

    def success_payload_builder(parsed):
        invoice_data = parsed.invoice_data.model_dump()
        validation = validate_invoice_data(invoice_data, job.processor_history)

        validation_status = parsed.validation_status
        approval_route = parsed.approval_route
        missing_critical = list(parsed.missing_critical)
        duplicate_suspected = bool(parsed.duplicate_suspected or validation["duplicate_suspected"])

        if not validation["is_valid"]:
            validation_status = "manual_review"
            approval_route = "manual_review"
            missing_critical = sorted(set(missing_critical + validation["issues"]))

        if duplicate_suspected:
            validation_status = "manual_review"
            approval_route = "manual_review"
            missing_critical = sorted(set(missing_critical + ["duplicate_invoice_detected"]))

        return {
            "processor_name": PROCESSOR_NAME,
            "invoice_data": validation["normalized_invoice_data"],
            "validation_status": validation_status,
            "duplicate_suspected": duplicate_suspected,
            "missing_critical": missing_critical,
            "approval_route": approval_route,
            "reasons": parsed.reasons,
            "confidence": parsed.confidence,
            "validation": {
                "is_valid": validation["is_valid"],
                "issues": validation["issues"],
            },
            "recommended_next_step": (
                "manual_review" if approval_route == "manual_review" else approval_route
            ),
        }

    def fallback_payload_builder(error_message: str):
        return {
            "processor_name": PROCESSOR_NAME,
            "invoice_data": {
                "supplier_name": None,
                "organization_number": None,
                "invoice_number": None,
                "invoice_date": None,
                "due_date": None,
                "currency": None,
                "amount_ex_vat": None,
                "vat_amount": None,
                "amount_inc_vat": None,
                "reference": None,
            },
            "validation_status": "manual_review",
            "duplicate_suspected": False,
            "missing_critical": ["invoice_analysis_failed"],
            "approval_route": "manual_review",
            "reasons": ["invoice_analysis_failed"],
            "confidence": 0.0,
            "validation": {
                "is_valid": False,
                "issues": ["invoice_analysis_failed"],
            },
            "error": error_message,
            "recommended_next_step": "manual_review",
        }

    updated_job = run_ai_step(
        job=job,
        processor_name=PROCESSOR_NAME,
        prompt_name = "invoice_analysis_v1",
        context=context,
        response_model=InvoiceAnalysisResponse,
        success_summary="Faktura analyserad med AI.",
        success_payload_builder=success_payload_builder,
        fallback_payload_builder=fallback_payload_builder,
    )

    payload = updated_job.result["payload"]
    validation = payload.get("validation", {})
    if not validation.get("is_valid", True) or payload.get("duplicate_suspected"):
        updated_job.result["requires_human_review"] = True

    return updated_job