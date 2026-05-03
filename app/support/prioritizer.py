"""Support Priority / Scoring Engine.

Deterministic rule-based scoring (0–100). Returns score, category, and reasons.

When a TenantSupportContext is provided scoring also considers:
- SLA critical_keywords / urgent_categories
- priority_rules / high_value_keywords
- Geographic area constraints
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.support.models import SupportAnalysis, SupportMissingInfoResult, SupportPriority, PriorityCategory

if TYPE_CHECKING:
    from app.support.tenant_context import TenantSupportContext


def _category(score: int) -> PriorityCategory:
    if score >= 70:
        return "critical"
    if score >= 40:
        return "urgent"
    return "normal"


def prioritize_support(
    analysis: SupportAnalysis,
    missing_info: SupportMissingInfoResult,
    entities: dict,
    input_data: dict,
    tenant_ctx: "TenantSupportContext | None" = None,
) -> SupportPriority:
    """Compute priority score 0–100 for a support ticket."""
    points = 0
    reasons: list[str] = []
    business_risk_reason: str | None = None
    tenant_ctx_used = False

    # ── Urgency ───────────────────────────────────────────────────────────────
    if analysis.urgency == "critical":
        points += 50
        reasons.append("urgency:critical (+50)")
    elif analysis.urgency == "high":
        points += 25
        reasons.append("urgency:high (+25)")
    elif analysis.urgency == "medium":
        points += 10
        reasons.append("urgency:medium (+10)")

    # ── Sentiment ─────────────────────────────────────────────────────────────
    if analysis.customer_sentiment == "angry":
        points += 20
        reasons.append("sentiment:angry (+20)")
    elif analysis.customer_sentiment == "frustrated":
        points += 10
        reasons.append("sentiment:frustrated (+10)")
    elif analysis.customer_sentiment == "concerned":
        points += 5
        reasons.append("sentiment:concerned (+5)")

    # ── Ticket type risk ──────────────────────────────────────────────────────
    if analysis.ticket_type == "emergency":
        points += 15
        reasons.append("ticket_type:emergency (+15)")
    elif analysis.ticket_type in ("complaint", "warranty"):
        points += 10
        reasons.append(f"ticket_type:{analysis.ticket_type} (+10)")

    # ── Category safety risk ──────────────────────────────────────────────────
    if analysis.category == "safety":
        points += 10
        reasons.append("category:safety (+10)")

    # ── requires_human ────────────────────────────────────────────────────────
    if analysis.requires_human:
        points += 5
        reasons.append("requires_human (+5)")

    # ── Completeness risk ─────────────────────────────────────────────────────
    # Emergency missing phone/address is extra risk
    if analysis.ticket_type == "emergency":
        if "phone" in missing_info.missing_fields:
            points += 5
            reasons.append("emergency_missing_phone (+5)")
        if "address" in missing_info.missing_fields:
            points += 5
            reasons.append("emergency_missing_address (+5)")

    # ── Tenant-aware bonuses ──────────────────────────────────────────────────
    if tenant_ctx and tenant_ctx.context_available:
        tenant_ctx_used = True
        text = (
            (input_data.get("subject") or "").lower()
            + " "
            + (input_data.get("message_text") or "").lower()
        )

        # SLA critical override
        if tenant_ctx.is_critical_by_sla(text):
            points += 20
            reasons.append("tenant_sla_critical (+20)")
            business_risk_reason = "Ärendet matchar tenant-definierade kritiska SLA-ord."

        # Urgent category
        if tenant_ctx.is_urgent_category(analysis.category):
            points += 15
            reasons.append(f"tenant_urgent_category:{analysis.category} (+15)")
            if not business_risk_reason:
                business_risk_reason = f"Kategori '{analysis.category}' är definierad som urgent av tenanten."

        # High-value customer keywords from priority_rules
        hv_kws = (tenant_ctx.priority_rules.get("high_value_keywords") or [])
        if any(re.search(r"\b" + re.escape(kw.lower()) + r"\b", text) for kw in hv_kws):
            points += 10
            reasons.append("tenant_high_value_match (+10)")
            if not business_risk_reason:
                business_risk_reason = "Ärendet matchar tenant-definierade högt värderade kunder."

        # Geographic mismatch — note as risk but don't add points
        if tenant_ctx.served_areas:
            combined = text + " " + (entities.get("city") or "") + " " + (entities.get("address") or "")
            in_area = any(
                re.search(r"\b" + re.escape(a.lower()) + r"\b", combined.lower())
                for a in tenant_ctx.served_areas
            )
            if not in_area and (entities.get("city") or entities.get("address")):
                reasons.append("geographic_outside_area (risk)")
                if not business_risk_reason:
                    business_risk_reason = "Ärendet kan vara utanför serviceområdet."

    score = max(0, min(100, points))
    return SupportPriority(
        score=score,
        category=_category(score),
        reasons=reasons,
        business_risk_reason=business_risk_reason,
        tenant_context_used=tenant_ctx_used,
        context_sources=list(tenant_ctx.sources_used) if tenant_ctx_used else [],
    )
