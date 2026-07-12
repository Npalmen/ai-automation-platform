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
from app.service_profiles import select_profile, compute_profile_missing_info
from app.service_profiles.qualification import compute_playbook_questions
from app.service_profiles.context import detect_service_context
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

    # 2. Select service profile — drives service-specific questions, routing and completeness
    _combined = f"{input_data.get('subject', '')} {input_data.get('message_text', '')}".strip()
    _tenant_ctx_for_profile = tenant_ctx if tenant_ctx.context_available else None
    service_profile = select_profile(
        "lead",
        lead_type=analysis.lead_type,
        text=_combined,
        tenant_ctx=_tenant_ctx_for_profile,
    )

    # 3. Compute profile-specific missing info (service profile required fields + tenant schema)
    profile_missing_info = compute_profile_missing_info(
        service_profile, input_data, entities,
        tenant_ctx=_tenant_ctx_for_profile,
    )

    # 4. Compute generic missing info + completeness (backward-compat; used for scoring/next_action)
    missing_info = compute_missing_info(analysis.lead_type, input_data, entities, tenant_ctx)

    # 5. Score lead (tenant-aware bonuses/penalties)
    lead_score = score_lead(analysis, missing_info, entities, input_data, tenant_ctx)

    # 6. Next action
    next_action = decide_next_action(lead_score, missing_info, tenant_auto_actions, tenant_ctx)

    # 7. Question message (if needed) — uses playbook-aware selection
    # Detect service context first so playbook can suppress/prioritize per context.
    _service_context = detect_service_context(_combined)
    _playbook_result: dict = {}

    question_message: str | None = None
    if should_ask_questions(missing_info.completeness_score):
        # Compute playbook-based questions: respects context-specific suppress/priority rules
        # e.g. battery add-on suppresses property_type and prioritizes inverter/backup/main_fuse
        _playbook_result = compute_playbook_questions(
            service_profile, input_data, entities,
            service_context=_service_context,
            max_questions=4,
        )
        q_fields = _playbook_result.get("selected_fields") or []

        # Fall back to basic profile missing fields if playbook returns empty
        if not q_fields:
            q_fields = profile_missing_info["missing_fields"] or missing_info.missing_fields

        question_message = generate_question_message(
            q_fields, tenant_ctx, analysis.lead_type,
            service_profile=service_profile,
        )

    # 8. Offer draft (only if complete enough)
    offer_draft_dict: dict | None = None
    draft = build_offer_draft(analysis, missing_info, entities, tenant_ctx)
    if draft:
        offer_draft_dict = draft.to_dict()

    # 9. lead_status — preserve if already set by operator
    lead_status = input_data.get("lead_status") or _infer_lead_status(next_action, input_data)

    payload: dict = {
        "processor_name": PROCESSOR_NAME,
        "lead_analysis": analysis.to_dict(),
        "missing_info": missing_info.to_dict(),
        "lead_score": lead_score.to_dict(),
        "next_action": next_action,
        "lead_status": lead_status,
        "confidence": analysis.confidence,
        "service_profile_type": service_profile.service_type,
        "profile_missing_fields": profile_missing_info["missing_fields"],
        "profile_completeness_score": profile_missing_info["completeness_score"],
        "service_context": _service_context,
        "fact_states": _playbook_result.get("fact_states") or {},
        "suppressed_fields": _playbook_result.get("suppressed_fields") or [],
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
