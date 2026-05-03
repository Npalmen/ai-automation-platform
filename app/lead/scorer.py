"""Lead Scoring Engine.

Deterministic rule-based scoring (0–100). Returns score, category, and reasons.

When a TenantLeadContext is provided scoring also considers:
- priority_services / high_value_services
- geographic_area match
- ideal_customer_profile
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.lead.models import LeadAnalysis, LeadScore, MissingInfoResult, ScoreCategory

if TYPE_CHECKING:
    from app.lead.tenant_context import TenantLeadContext


_BUYING_KEYWORDS = [
    "offert", "pris", "installera", "boka", "köpa", "beställa",
    "när kan ni komma", "prisuppgift", "intresserad av att gå vidare",
]

_WEAK_KEYWORDS = [
    "funderar bara", "kanske", "tittar runt", "jämföra priser",
    "ingen brådska", "inga planer",
]


def _any_keyword(text: str, keywords: list[str]) -> bool:
    return any(re.search(r"\b" + re.escape(kw) + r"\b", text) for kw in keywords)


def _category(score: int) -> ScoreCategory:
    if score >= 70:
        return "hot"
    if score >= 40:
        return "warm"
    return "cold"


def _geographic_match(text: str, served_areas: list[str]) -> bool | None:
    """Return True if served, False if explicitly outside served areas, None if unknown."""
    if not served_areas:
        return None
    lower_areas = [a.lower() for a in served_areas]
    return any(re.search(r"\b" + re.escape(a) + r"\b", text) for a in lower_areas)


def score_lead(
    analysis: LeadAnalysis,
    missing_info: MissingInfoResult,
    entities: dict,
    input_data: dict,
    tenant_ctx: "TenantLeadContext | None" = None,
) -> LeadScore:
    subject = (input_data.get("subject") or "").lower()
    body = (input_data.get("message_text") or "").lower()
    text = f"{subject} {body}"

    points = 0
    reasons: list[str] = []
    business_fit_reason: str | None = None
    tenant_ctx_used = False

    # Intent
    if analysis.intent == "ready_to_buy":
        points += 25
        reasons.append("intent:ready_to_buy (+25)")
    elif analysis.intent == "comparing":
        points += 15
        reasons.append("intent:comparing (+15)")

    # Urgency
    if analysis.urgency == "high":
        points += 20
        reasons.append("urgency:high (+20)")
    elif analysis.urgency == "medium":
        points += 8
        reasons.append("urgency:medium (+8)")

    # Completeness
    if missing_info.completeness_score >= 0.8:
        points += 20
        reasons.append("completeness:>=0.8 (+20)")
    elif missing_info.completeness_score >= 0.5:
        points += 8
        reasons.append("completeness:>=0.5 (+8)")

    # Contact info
    contact_score = 0
    if entities.get("email"):
        contact_score += 4
    if entities.get("phone"):
        contact_score += 3
    if entities.get("address") or entities.get("city"):
        contact_score += 3
    if contact_score > 0:
        points += contact_score
        reasons.append(f"contact_info (+{contact_score})")

    # Strong buying keywords
    if _any_keyword(text, _BUYING_KEYWORDS):
        points += 10
        reasons.append("buying_keywords (+10)")

    # Weak/research language — penalty
    if _any_keyword(text, _WEAK_KEYWORDS):
        points -= 10
        reasons.append("weak_language (-10)")

    # Known lead_type adds credibility
    if analysis.lead_type != "unknown":
        points += 5
        reasons.append(f"lead_type:{analysis.lead_type} (+5)")

    # ── Tenant-aware bonuses ──────────────────────────────────────────────────
    if tenant_ctx and tenant_ctx.context_available:
        tenant_ctx_used = True

        # High-value service bonus
        ideal = tenant_ctx.ideal_customer
        high_value_services: list[str] = ideal.get("high_value_services") or []
        if analysis.lead_type in high_value_services:
            points += 10
            reasons.append(f"high_value_service:{analysis.lead_type} (+10)")
            business_fit_reason = f"Leadtyp '{analysis.lead_type}' är prioriterad tjänst hos tenanten."

        # Priority services
        priority_services: list[str] = ideal.get("priority_services") or []
        if analysis.lead_type in priority_services and analysis.lead_type not in high_value_services:
            points += 5
            reasons.append(f"priority_service:{analysis.lead_type} (+5)")
            if not business_fit_reason:
                business_fit_reason = f"Leadtyp '{analysis.lead_type}' matchar prioriterad tjänst."

        # Geographic match
        geo_match = _geographic_match(text, tenant_ctx.served_areas)
        if geo_match is True:
            points += 8
            reasons.append("geographic_match (+8)")
            if not business_fit_reason:
                business_fit_reason = "Lead är inom serverat geografiskt område."
        elif geo_match is False:
            points -= 15
            reasons.append("geographic_mismatch (-15)")
            business_fit_reason = "Lead kan vara utanför serverat geografiskt område."

        # Ideal customer type match
        ideal_types: list[str] = ideal.get("customer_types") or []
        if ideal_types and analysis.customer_type in ideal_types:
            points += 5
            reasons.append(f"ideal_customer_type:{analysis.customer_type} (+5)")

        # Lead not in offered services → penalty
        if not tenant_ctx.is_service_offered(analysis.lead_type) and analysis.lead_type != "unknown":
            points -= 20
            reasons.append(f"service_not_offered:{analysis.lead_type} (-20)")
            business_fit_reason = f"Tjänsten '{analysis.lead_type}' erbjuds inte av tenanten."

    score = max(0, min(100, points))
    return LeadScore(
        score=score,
        category=_category(score),
        reasons=reasons,
        tenant_context_used=tenant_ctx_used,
        business_fit_reason=business_fit_reason,
    )
