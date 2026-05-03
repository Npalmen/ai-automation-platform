"""Support Response Draft Engine.

Produces a safe preliminary response when completeness >= 0.7.
Never sends — operator reviews before any outbound action.

Response types:
- ask_for_info: completeness < 0.7 (question_generator handles text)
- acknowledgement: high urgency/critical — confirm receipt, promise fast follow-up
- suggested_solution: low risk + common issue matched in tenant FAQ
- escalation: critical/emergency/angry — escalate to human immediately

Safety rules:
- No definitive technical diagnosis for electrical/safety issues.
- Safety disclaimer always injected for emergency/safety categories.
- For critical urgency: always escalation, not suggested_solution.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.support.models import (
    SupportAnalysis,
    SupportMissingInfoResult,
    SupportPriority,
    SupportResponseDraft,
    ResponseType,
)

if TYPE_CHECKING:
    from app.support.tenant_context import TenantSupportContext

_SAFETY_DISCLAIMER = (
    "⚠️ Om det finns direkt fara, bryt strömmen om det kan göras säkert "
    "och kontakta behörig hjälp eller jourtjänst omedelbart."
)

_SAFETY_CATEGORIES = ("safety", "installation")
_SAFETY_TICKET_TYPES = ("emergency",)


def _company_prefix(tenant_ctx: "TenantSupportContext | None") -> str:
    if tenant_ctx and tenant_ctx.context_available and tenant_ctx.company_name:
        return f"Vi på {tenant_ctx.company_name} "
    return "Vi "


def _is_safety_relevant(analysis: SupportAnalysis, input_data: dict) -> bool:
    if analysis.ticket_type in _SAFETY_TICKET_TYPES:
        return True
    if analysis.category == "safety":
        return True
    text = (
        (input_data.get("subject") or "")
        + " "
        + (input_data.get("message_text") or "")
    ).lower()
    import re
    safety_kws = ["el ", "ström", "kortslutning", "brand", "rök", "läck", "stöt", "gnistor"]
    return any(re.search(r"\b" + re.escape(kw) + r"\b", text) for kw in safety_kws)


def build_support_response_draft(
    analysis: SupportAnalysis,
    missing_info: SupportMissingInfoResult,
    priority: SupportPriority,
    entities: dict,
    input_data: dict,
    tenant_ctx: "TenantSupportContext | None" = None,
) -> SupportResponseDraft:
    """Return a SupportResponseDraft. Always returns (unlike offer_draft which returns None)."""
    prefix = _company_prefix(tenant_ctx)
    is_safety = _is_safety_relevant(analysis, input_data)
    risk_points: list[str] = []
    if is_safety:
        risk_points.append(_SAFETY_DISCLAIMER)

    tenant_ctx_used = bool(tenant_ctx and tenant_ctx.context_available)
    ctx_sources = list(tenant_ctx.sources_used) if tenant_ctx_used else []
    company_name = (tenant_ctx.company_name if tenant_ctx_used else None) or "vi"

    # ── Choose response type ──────────────────────────────────────────────────
    response_type: ResponseType

    if analysis.urgency == "critical" or analysis.ticket_type == "emergency":
        response_type = "escalation"
    elif analysis.customer_sentiment == "angry":
        response_type = "escalation"
    elif missing_info.completeness_score < 0.7:
        response_type = "ask_for_info"
    elif tenant_ctx and tenant_ctx.context_available:
        # Check if common_issue matches
        text_combined = (
            (input_data.get("subject") or "").lower()
            + " "
            + (input_data.get("message_text") or "").lower()
        )
        matched_issue = tenant_ctx.matching_common_issue(text_combined)
        if matched_issue and analysis.urgency in ("low", "medium") and not analysis.requires_human:
            response_type = "suggested_solution"
        else:
            response_type = "acknowledgement"
    else:
        response_type = "acknowledgement"

    # ── Build subject ─────────────────────────────────────────────────────────
    ticket_labels = {
        "emergency": "AKUT",
        "complaint": "Klagomål",
        "warranty": "Garantiärende",
        "invoice_question": "Fakturafråga",
        "scheduling": "Tidsbokning",
        "issue": "Supportärende",
        "question": "Fråga",
        "other": "Ärende",
    }
    ticket_label = ticket_labels.get(analysis.ticket_type, "Ärende")
    subject = f"Re: {ticket_label} — {analysis.matched_service or 'ditt ärende'}"

    # ── Build body ────────────────────────────────────────────────────────────
    assumptions: list[str] = []
    recommended_next_step: str

    if response_type == "escalation":
        body_parts = [
            f"{prefix}har tagit emot ditt ärende och eskalerar det omedelbart till rätt person.",
            "",
            "Du kan förvänta dig att höra från oss inom kort.",
        ]
        if is_safety:
            body_parts.append("")
            body_parts.append(_SAFETY_DISCLAIMER)
        body = "\n".join(body_parts)
        recommended_next_step = "Eskalera till handläggare/tekniker omgående."
        assumptions.append("Ärendet kräver mänsklig uppföljning.")

    elif response_type == "suggested_solution":
        matched_issue = None
        if tenant_ctx and tenant_ctx.context_available:
            text_combined = (
                (input_data.get("subject") or "").lower()
                + " "
                + (input_data.get("message_text") or "").lower()
            )
            matched_issue = tenant_ctx.matching_common_issue(text_combined)

        steps: list[str] = []
        if matched_issue:
            steps = matched_issue.get("solution_steps") or []
            assumptions.append("Baserat på liknande ärenden i kundens FAQ.")

        if steps:
            steps_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps))
            body = (
                f"{prefix}har tagit emot ditt ärende och har ett förslag på lösning:\n\n"
                f"{steps_text}\n\n"
                f"Om problemet kvarstår, hör av dig så följer vi upp."
            )
        else:
            body = (
                f"{prefix}har tagit emot ditt ärende. "
                f"Vi granskar det och återkommer med en lösning."
            )
        recommended_next_step = "Skicka svarsförslaget till kund efter granskning."

    elif response_type == "ask_for_info":
        body = (
            f"{prefix}har tagit emot ditt ärende. "
            f"För att hjälpa dig behöver vi lite mer information "
            f"(se separat meddelande)."
        )
        recommended_next_step = "Skicka frågemeddelandet till kund."
        assumptions.append("Kompletterande frågor genereras separat.")

    else:  # acknowledgement
        urgency_text = ""
        if analysis.urgency in ("high", "critical"):
            urgency_text = " Vi behandlar det som prioriterat."

        body = (
            f"{prefix}har tagit emot ditt ärende och återkommer inom kort.{urgency_text}\n\n"
            f"Om du behöver snabb hjälp, kontakta oss direkt."
        )
        recommended_next_step = "Granska ärendet och tilldela handläggare."

    # ── Confidence ────────────────────────────────────────────────────────────
    confidence = 0.5
    if response_type == "suggested_solution":
        confidence = 0.75
    elif response_type == "escalation":
        confidence = 0.85
    elif response_type == "acknowledgement":
        confidence = 0.65
    if tenant_ctx_used:
        confidence = min(confidence + 0.05, 0.95)

    # Geographic risk from priority
    if priority.business_risk_reason and "serviceområde" in priority.business_risk_reason:
        risk_points.append("Kontrollera att adressen är inom serviceområdet.")

    return SupportResponseDraft(
        response_type=response_type,
        subject=subject,
        body=body,
        assumptions=assumptions,
        risk_points=risk_points,
        recommended_next_step=recommended_next_step,
        confidence=round(confidence, 3),
        tenant_context_used=tenant_ctx_used,
        context_sources=ctx_sources,
    )
