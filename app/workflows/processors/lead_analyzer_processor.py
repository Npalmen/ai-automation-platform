"""Lead Analyzer Processor.

Runs after entity_extraction for LEAD jobs. Produces lead_analysis,
missing_info, lead_score, offer_draft, next_action, and optionally
a generated_question_message. All deterministic — no LLM required.

When db is provided, loads TenantLeadContext to make analysis tenant-aware.
"""
from __future__ import annotations

from app.domain.workflows.models import Job
from app.lead.analyzer import analyze_lead
from app.lead.missing_info import compute_missing_info
from app.lead.next_action import decide_next_action
from app.lead.offer_draft import build_offer_draft
from app.lead.question_generator import generate_question_message, should_ask_questions
from app.lead.scorer import score_lead
from app.lead.tenant_context import load_tenant_context_from_job
from app.workflows.processors.ai_processor_utils import (
    append_processor_result,
    get_latest_processor_payload,
)

PROCESSOR_NAME = "lead_analyzer_processor"


def process_lead_analyzer_job(job: Job, db=None) -> Job:
    extraction_payload = get_latest_processor_payload(job, "entity_extraction_processor")
    entities: dict = extraction_payload.get("entities") or {}
    input_data: dict = job.input_data or {}

    # Load tenant context (requires db; gracefully absent if not available)
    tenant_ctx = load_tenant_context_from_job(job, db)

    # Tenant auto_actions from processor history (fallback)
    tenant_auto_actions = _get_auto_actions(job)

    # 1. Analyze lead type, intent, urgency, customer_type
    analysis = analyze_lead(input_data, entities, tenant_ctx)

    # 2. Compute missing info + completeness (tenant schema if available)
    missing_info = compute_missing_info(analysis.lead_type, input_data, entities, tenant_ctx)

    # 3. Score lead (tenant-aware bonuses/penalties)
    lead_score = score_lead(analysis, missing_info, entities, input_data, tenant_ctx)

    # 4. Next action
    next_action = decide_next_action(lead_score, missing_info, tenant_auto_actions, tenant_ctx)

    # 5. Question message (if needed)
    question_message: str | None = None
    if should_ask_questions(missing_info.completeness_score):
        question_message = generate_question_message(
            missing_info.missing_fields, tenant_ctx, analysis.lead_type
        )

    # 6. Offer draft (only if complete enough)
    offer_draft_dict: dict | None = None
    draft = build_offer_draft(analysis, missing_info, entities, tenant_ctx)
    if draft:
        offer_draft_dict = draft.to_dict()

    # 7. lead_status — preserve if already set by operator
    lead_status = input_data.get("lead_status") or _infer_lead_status(next_action, input_data)

    payload: dict = {
        "processor_name": PROCESSOR_NAME,
        "lead_analysis": analysis.to_dict(),
        "missing_info": missing_info.to_dict(),
        "lead_score": lead_score.to_dict(),
        "next_action": next_action,
        "lead_status": lead_status,
        "confidence": analysis.confidence,
    }

    if question_message:
        payload["generated_question_message"] = question_message

    if offer_draft_dict:
        payload["offer_draft"] = offer_draft_dict

    requires_review = next_action in ("manual_review", "approval_required")

    result = {
        "status": "completed",
        "summary": _summary(next_action, lead_score.score, missing_info.completeness_score),
        "requires_human_review": requires_review,
        "payload": payload,
    }

    return append_processor_result(job, PROCESSOR_NAME, result)


def _summary(next_action: str, score: int, completeness: float) -> str:
    return (
        f"Lead analyserad: score={score}, completeness={completeness:.0%}, "
        f"next_action={next_action}."
    )


def _get_auto_actions(job: Job) -> dict:
    """Extract auto_actions from processor history if tenant config was loaded."""
    for item in reversed(job.processor_history):
        payload = (item.get("result") or {}).get("payload") or {}
        auto = payload.get("auto_actions")
        if isinstance(auto, dict):
            return auto
    return {}


def _infer_lead_status(next_action: str, input_data: dict) -> str:
    """Infer lead_status from pipeline result when not operator-set."""
    # If this is a continuation (customer replied), move to info_received
    if input_data.get("conversation_messages") and len(input_data["conversation_messages"]) > 1:
        if next_action in ("create_offer_draft", "ready_to_dispatch"):
            return "offer_ready"
        return "info_received"
    # Fresh lead
    if next_action == "ask_questions":
        return "new"
    if next_action in ("create_offer_draft", "ready_to_dispatch"):
        return "offer_ready"
    return "new"
