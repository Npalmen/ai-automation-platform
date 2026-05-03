"""Next Best Action rules for leads."""
from __future__ import annotations

from app.lead.models import LeadScore, MissingInfoResult, NextAction


def decide_next_action(
    score: LeadScore,
    missing_info: MissingInfoResult,
    tenant_auto_actions: dict | None = None,
) -> NextAction:
    """Deterministic next-action decision.

    Rules (in priority order):
    1. completeness < 0.7            → ask_questions
    2. score >= 70 and complete      → create_offer_draft / ready_to_dispatch
    3. score 40-69                   → approval_required
    4. score < 40                    → manual_review
    """
    completeness = missing_info.completeness_score

    if completeness < 0.7:
        return "ask_questions"

    if score.score >= 70:
        # Check if tenant has enabled auto-dispatch for leads
        auto_actions = tenant_auto_actions or {}
        lead_auto = auto_actions.get("lead", False)
        if lead_auto is True or lead_auto == "auto":
            return "ready_to_dispatch"
        return "create_offer_draft"

    if score.score >= 40:
        return "approval_required"

    return "manual_review"
