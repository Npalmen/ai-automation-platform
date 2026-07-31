"""Safe acknowledgement path for incomplete but low-risk leads.

Separates operational routing (manual_review) from communication authorization
(send_for_approval) so a bounded customer reply can be drafted and gated by approval.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.workflows.decision_contract import DecisionRecommendation, _LEGACY_AUTHORIZATION_TOKENS
from app.workflows.processors.ai_processor_utils import normalize_sender

# Extraction validation issues that may coexist with a safe acknowledgement draft.
_SOFT_EXTRACTION_ISSUES = frozenset(
    {
        "missing_identity",
        "missing_requested_service",
    }
)

# Hard blockers — never create a customer draft.
_HARD_EXTRACTION_ISSUES = frozenset(
    {
        "invalid_email",
        "invalid_phone",
    }
)

# Inbound topics that require hold without customer draft (no price/booking promises).
_FORBIDDEN_INBOUND_TOPIC_PATTERNS: tuple[tuple[str, str], ...] = (
    ("price", r"\b(?:pris|kostar|kostnad|vad\s+kostar)\b"),
    ("booking", r"\b(?:boka|bokning|inbokad|bokat\s+tid)\b"),
    ("warranty", r"\b(?:garanti|reklamation)\b"),
    ("legal_commitment", r"\b(?:juridiskt|stämning|advokat)\b"),
    ("bank_details", r"\b(?:bankgiro|plusgiro|swish\s+nummer)\b"),
)

_OUT_OF_AREA_MARKERS = (
    "gotland",
)


@dataclass(frozen=True)
class SafeAcknowledgementEligibility:
    eligible: bool
    reasons: tuple[str, ...] = ()


def _usable_customer_email(input_data: dict[str, Any]) -> str:
    sender = normalize_sender(input_data)
    email = str(sender.get("email") or "").strip().lower()
    if email and "no-reply" not in email and "noreply" not in email:
        return email
    for key in ("customer_email", "reply_to_email", "email"):
        candidate = str(input_data.get(key) or "").strip().lower()
        if candidate and "no-reply" not in candidate and "noreply" not in candidate:
            return candidate
    return ""


def _inbound_forbidden_topics(text: str) -> list[str]:
    lowered = (text or "").lower()
    found: list[str] = []
    for topic, pattern in _FORBIDDEN_INBOUND_TOPIC_PATTERNS:
        if re.search(pattern, lowered, re.IGNORECASE):
            found.append(topic)
    return found


def _is_out_of_area(text: str) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in _OUT_OF_AREA_MARKERS)


def evaluate_safe_acknowledgement_eligibility(
    *,
    detected_job_type: str,
    risk_detected: bool,
    risk_categories: list[str] | None,
    extraction_issues: list[str],
    input_data: dict[str, Any],
    recommendation: DecisionRecommendation | None,
    recommendation_raw: str | None,
    low_confidence: bool,
    used_fallback: bool,
) -> SafeAcknowledgementEligibility:
    """Return whether a safe acknowledgement draft may be prepared for approval."""
    reasons: list[str] = []

    if detected_job_type not in ("lead", "customer_inquiry"):
        return SafeAcknowledgementEligibility(False, ("unsupported_job_type",))

    if risk_detected:
        return SafeAcknowledgementEligibility(False, ("content_risk_detected",))

    if risk_categories:
        return SafeAcknowledgementEligibility(False, tuple(risk_categories))

    if not _usable_customer_email(input_data):
        return SafeAcknowledgementEligibility(False, ("no_usable_reply_address",))

    issue_set = {str(i) for i in extraction_issues if i}
    if issue_set & _HARD_EXTRACTION_ISSUES:
        return SafeAcknowledgementEligibility(
            False,
            tuple(sorted(issue_set & _HARD_EXTRACTION_ISSUES)),
        )

    if issue_set - _SOFT_EXTRACTION_ISSUES:
        return SafeAcknowledgementEligibility(
            False,
            tuple(sorted(issue_set - _SOFT_EXTRACTION_ISSUES)),
        )

    raw = str(recommendation_raw or "").strip().lower()
    if raw in _LEGACY_AUTHORIZATION_TOKENS:
        return SafeAcknowledgementEligibility(False, ("legacy_authorization_token",))

    if raw in {"hold", "reject", "no_reply", "no_action"}:
        return SafeAcknowledgementEligibility(False, (f"decisioning_{raw}",))

    if recommendation == DecisionRecommendation.HOLD:
        return SafeAcknowledgementEligibility(False, ("decisioning_hold",))

    combined_text = " ".join(
        str(input_data.get(key) or "")
        for key in ("subject", "message_text")
    )
    forbidden = _inbound_forbidden_topics(combined_text)
    if forbidden:
        return SafeAcknowledgementEligibility(False, tuple(forbidden))

    if _is_out_of_area(combined_text):
        return SafeAcknowledgementEligibility(False, ("out_of_service_area",))

    # Incomplete-but-comprehensible: missing identity/service only, or manual review routing.
    soft_signals = bool(issue_set) or low_confidence or used_fallback
    manual_review_signal = recommendation in (
        DecisionRecommendation.MANUAL_REVIEW,
        None,
    )
    if not soft_signals and not manual_review_signal:
        return SafeAcknowledgementEligibility(False, ("complete_enough_for_auto_path",))

    if soft_signals:
        reasons.append("incomplete_lead_missing_details")
    if manual_review_signal:
        reasons.append("operational_manual_review")
    if low_confidence:
        reasons.append("low_confidence_soft")
    if used_fallback:
        reasons.append("decisioning_used_fallback_soft")

    return SafeAcknowledgementEligibility(True, tuple(reasons))


def build_safe_acknowledgement_body(
    *,
    greeting: str,
    service_hint: str,
    missing_fields: list[str],
    signature_name: str,
) -> str:
    """Build a bounded acknowledgement that requests missing information only."""
    ack = "Tack för din förfrågan. Vi tittar på den och återkommer."
    service_line = ""
    if service_hint:
        service_line = f"\n\nVi ser att du vill ha hjälp med {service_hint}."

    prompts: list[str] = []
    if "customer_name" in missing_fields or "name" in missing_fields:
        prompts.append("Ditt namn")
    if "phone" in missing_fields:
        prompts.append("Telefonnummer")
    if "address" in missing_fields or "location" in missing_fields:
        prompts.append("Adress eller ort")
    if "requested_service" in missing_fields or "service_type" in missing_fields:
        prompts.append("Vilken tjänst det gäller")
    if not prompts:
        prompts = ["Namn", "Telefonnummer", "Adress"]

    question_block = "\n".join(f"- {item}" for item in prompts)
    closing = f"\n\nVänliga hälsningar\n{signature_name}" if signature_name else ""
    return (
        f"{greeting}\n\n"
        f"{ack}"
        f"{service_line}\n\n"
        "För att vi ska kunna gå vidare behöver vi:\n"
        f"{question_block}\n\n"
        "Förfrågan granskas av oss innan vi återkommer."
        f"{closing}"
    )
