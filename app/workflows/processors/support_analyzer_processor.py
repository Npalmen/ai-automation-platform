"""Support Analyzer Processor.

Runs after entity_extraction for CUSTOMER_INQUIRY jobs. Produces:
- support_analysis
- support_missing_info
- support_priority
- support_next_action
- support_generated_question_message (optional)
- support_response_draft
- support_status

All deterministic — no LLM required.
When db is provided, loads TenantSupportContext for tenant-aware analysis.
"""
from __future__ import annotations

from app.domain.workflows.models import Job
from app.support.analyzer import analyze_support
from app.support.missing_info import compute_support_missing_info
from app.support.next_action import decide_support_next_action
from app.support.prioritizer import prioritize_support
from app.support.question_generator import generate_support_question_message, should_ask_questions
from app.support.response_draft import build_support_response_draft
from app.support.tenant_context import load_support_context_from_job
from app.workflows.processors.ai_processor_utils import (
    append_processor_result,
    get_latest_processor_payload,
)

PROCESSOR_NAME = "support_analyzer_processor"


def process_support_analyzer_job(job: Job, db=None) -> Job:
    input_data: dict = job.input_data or {}

    try:
        extraction_payload = get_latest_processor_payload(job, "entity_extraction_processor")
        entities: dict = extraction_payload.get("entities") or {}

        # Load tenant context (requires db; gracefully absent if not available)
        tenant_ctx = load_support_context_from_job(job, db)

        # Tenant auto_actions from processor history (fallback)
        tenant_auto_actions = _get_auto_actions(job)

        # 1. Analyze ticket type, category, urgency, sentiment
        analysis = analyze_support(input_data, entities, tenant_ctx)

        # 2. Compute missing info + completeness
        missing_info = compute_support_missing_info(
            analysis.ticket_type, input_data, entities, tenant_ctx
        )

        # 3. Prioritize
        priority = prioritize_support(analysis, missing_info, entities, input_data, tenant_ctx)

        # 4. Next action
        next_action = decide_support_next_action(
            analysis, missing_info, priority, tenant_auto_actions, tenant_ctx
        )

        # 5. Question message (if needed)
        question_message: str | None = None
        if should_ask_questions(missing_info.completeness_score):
            question_message = generate_support_question_message(
                missing_info.missing_fields,
                ticket_type=analysis.ticket_type,
                tenant_ctx=tenant_ctx,
                input_data=input_data,
            )

        # 6. Response draft
        response_draft = build_support_response_draft(
            analysis, missing_info, priority, entities, input_data, tenant_ctx
        )

        # 7. support_status — preserve if already set by operator
        support_status = input_data.get("support_status") or _infer_support_status(
            next_action.action, input_data
        )

        payload: dict = {
            "processor_name": PROCESSOR_NAME,
            "support_analysis": analysis.to_dict(),
            "support_missing_info": missing_info.to_dict(),
            "support_priority": priority.to_dict(),
            "support_next_action": next_action.to_dict(),
            "support_response_draft": response_draft.to_dict(),
            "support_status": support_status,
            "confidence": analysis.confidence,
        }

        if question_message:
            payload["support_generated_question_message"] = question_message

        requires_review = next_action.action in ("escalate", "manual_review", "create_task")

        result = {
            "status": "completed",
            "summary": _summary(next_action.action, priority.score, missing_info.completeness_score),
            "requires_human_review": requires_review,
            "payload": payload,
        }

    except Exception as exc:
        # Never block the pipeline — degrade gracefully to a skipped marker
        result = {
            "status": "skipped",
            "summary": f"Support-analys hoppades över: {exc}",
            "requires_human_review": False,
            "payload": {
                "processor_name": PROCESSOR_NAME,
                "skipped": True,
                "skip_reason": str(exc),
                "support_status": input_data.get("support_status") or "new",
            },
        }

    return append_processor_result(job, PROCESSOR_NAME, result)


def _summary(action: str, score: int, completeness: float) -> str:
    return (
        f"Supportärende analyserat: score={score}, completeness={completeness:.0%}, "
        f"next_action={action}."
    )


def _get_auto_actions(job: Job) -> dict:
    for item in reversed(job.processor_history):
        payload = (item.get("result") or {}).get("payload") or {}
        auto = payload.get("auto_actions")
        if isinstance(auto, dict):
            return auto
    return {}


def _infer_support_status(action: str, input_data: dict) -> str:
    """Infer support_status from pipeline result when not operator-set."""
    if input_data.get("conversation_messages") and len(input_data["conversation_messages"]) > 1:
        if action in ("suggest_solution", "ready_to_dispatch"):
            return "solution_suggested"
        return "in_review"
    if action == "ask_for_info":
        return "new"
    if action == "escalate":
        return "escalated"
    if action in ("suggest_solution", "ready_to_dispatch"):
        return "solution_suggested"
    return "new"
