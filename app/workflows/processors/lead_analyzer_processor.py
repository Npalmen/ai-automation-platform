"""Lead Analyzer Processor.

Runs after entity_extraction for LEAD jobs. Produces lead_analysis,
missing_info, lead_score, offer_draft, next_action, and optionally
a generated_question_message. All deterministic — no LLM required.
"""
from __future__ import annotations

from app.domain.workflows.models import Job
from app.lead.analyzer import analyze_lead
from app.lead.missing_info import compute_missing_info
from app.lead.next_action import decide_next_action
from app.lead.offer_draft import build_offer_draft
from app.lead.question_generator import generate_question_message, should_ask_questions
from app.lead.scorer import score_lead
from app.workflows.processors.ai_processor_utils import (
    append_processor_result,
    get_latest_processor_payload,
)

PROCESSOR_NAME = "lead_analyzer_processor"


def process_lead_analyzer_job(job: Job) -> Job:
    extraction_payload = get_latest_processor_payload(job, "entity_extraction_processor")
    entities: dict = extraction_payload.get("entities") or {}
    input_data: dict = job.input_data or {}

    # Retrieve tenant auto_actions from tenant config (if available via job metadata)
    tenant_auto_actions = _get_auto_actions(job)

    # 1. Analyze lead type, intent, urgency, customer_type
    analysis = analyze_lead(input_data, entities)

    # 2. Compute missing info + completeness
    missing_info = compute_missing_info(analysis.lead_type, input_data, entities)

    # 3. Score lead
    lead_score = score_lead(analysis, missing_info, entities, input_data)

    # 4. Next action
    next_action = decide_next_action(lead_score, missing_info, tenant_auto_actions)

    # 5. Question message (if needed)
    question_message: str | None = None
    if should_ask_questions(missing_info.completeness_score):
        question_message = generate_question_message(missing_info.missing_fields)

    # 6. Offer draft (only if complete enough)
    offer_draft_dict: dict | None = None
    draft = build_offer_draft(analysis, missing_info, entities)
    if draft:
        offer_draft_dict = draft.to_dict()

    payload: dict = {
        "processor_name": PROCESSOR_NAME,
        "lead_analysis": analysis.to_dict(),
        "missing_info": missing_info.to_dict(),
        "lead_score": lead_score.to_dict(),
        "next_action": next_action,
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
