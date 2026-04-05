from app.domain.workflows.models import Job
from app.integrations.enums import IntegrationType
from app.integrations.factory import get_integration_adapter
from app.integrations.service import get_integration_connection_config


PROCESSOR_NAME = "action_dispatch_processor"


def get_last_payload(job: Job, processor_name: str) -> dict:
    for item in reversed(job.processor_history):
        if item["processor"] == processor_name:
            return item["result"]["payload"]
    return {}


def process_action_dispatch_job(job: Job) -> Job:
    decision = get_last_payload(job, "decisioning_processor")
    policy = get_last_payload(job, "policy_processor")
    extraction = get_last_payload(job, "entity_extraction_processor")
    lead = get_last_payload(job, "lead_processor")
    inquiry = get_last_payload(job, "customer_inquiry_processor")
    invoice = get_last_payload(job, "invoice_processor")

    action_flags = decision.get("action_flags", {})
    target_queue = decision.get("target_queue")
    allow_auto = policy.get("decision") == "allow_auto"

    actions_executed: list[str] = []
    dispatch_errors: list[str] = []

    if allow_auto:
        try:
            if action_flags.get("create_crm_lead"):
                connection_config = get_integration_connection_config(
                    job.tenant_id,
                    IntegrationType.CRM,
                )
                adapter = get_integration_adapter(
                    IntegrationType.CRM,
                    connection_config=connection_config,
                )

                adapter.execute_action(
                    action="create_lead",
                    payload={
                        "job_id": job.job_id,
                        "tenant_id": job.tenant_id,
                        "target_queue": target_queue,
                        "input_data": job.input_data,
                        "entities": extraction.get("entities", {}),
                        "lead_score": lead.get("lead_score"),
                        "priority": lead.get("priority"),
                        "routing": lead.get("routing"),
                        "processor_history": job.processor_history,
                    },
                )

                actions_executed.append("crm_lead_created")

            if invoice and invoice.get("approval_route") == "auto_approve":
                actions_executed.append("invoice_ready_for_accounting")

            if target_queue in {"support_queue", "billing_queue", "case_queue", "sales_queue"}:
                actions_executed.append(f"routed_to_{target_queue}")

            if inquiry.get("routing") == "manual_review":
                dispatch_errors.append("inquiry_requires_manual_review")

        except Exception as exc:
            dispatch_errors.append(str(exc))

    requires_human_review = len(dispatch_errors) > 0

    result = {
        "status": "completed",
        "summary": "Actions dispatched." if not dispatch_errors else "Action dispatch failed.",
        "requires_human_review": requires_human_review,
        "payload": {
            "processor_name": PROCESSOR_NAME,
            "actions_executed": actions_executed,
            "dispatch_errors": dispatch_errors,
            "target_queue": target_queue,
            "recommended_next_step": "manual_review" if requires_human_review else target_queue,
        },
    }

    job.result = result
    job.processor_history.append(
        {
            "processor": PROCESSOR_NAME,
            "result": result,
        }
    )

    job.status = "completed"
    return job