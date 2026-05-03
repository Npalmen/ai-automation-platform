"""Next Best Action rules for leads."""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.lead.models import LeadScore, MissingInfoResult, NextAction

if TYPE_CHECKING:
    from app.lead.tenant_context import TenantLeadContext


def decide_next_action(
    score: LeadScore,
    missing_info: MissingInfoResult,
    tenant_auto_actions: dict | None = None,
    tenant_ctx: "TenantLeadContext | None" = None,
) -> NextAction:
    """Deterministic next-action decision.

    Priority order:
    1. completeness < 0.7              → ask_questions
    2. service not offered (score penalised) → manual_review if score low
    3. score >= 70 and complete         → ready_to_dispatch / create_offer_draft
    4. score 40-69                      → approval_required
    5. score < 40                       → manual_review
    """
    completeness = missing_info.completeness_score

    if completeness < 0.7:
        return "ask_questions"

    # Geographic mismatch or service not offered → manual review regardless of score
    if score.business_fit_reason and score.score < 40:
        return "manual_review"

    if score.score >= 70:
        auto_actions = tenant_auto_actions or {}
        lead_auto = auto_actions.get("lead", False)
        if lead_auto is True or lead_auto == "auto":
            return "ready_to_dispatch"
        return "create_offer_draft"

    if score.score >= 40:
        return "approval_required"

    return "manual_review"
