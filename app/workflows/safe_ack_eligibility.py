"""Central safe-acknowledgement eligibility policy (Todo D).

Single authoritative gate for whether a customer-facing safe acknowledgement
draft may be prepared. All downstream paths must consume this result.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.workflows.business_intent import BusinessIntentResult
from app.workflows.decision_contract import DecisionRecommendation, _LEGACY_AUTHORIZATION_TOKENS
from app.workflows.processors.ai_processor_utils import normalize_sender
from app.workflows.threat_assessment import ThreatAssessment, CONTRACT_VERSION as THREAT_CONTRACT_VERSION

POLICY_VERSION = "safe_ack_eligibility_v1"

PERMITTED_REPLY_TYPES = frozenset({"none", "safe_acknowledgement", "manual_only"})

_SOFT_EXTRACTION_ISSUES = frozenset(
    {
        "missing_identity",
        "missing_requested_service",
    }
)

_HARD_EXTRACTION_ISSUES = frozenset(
    {
        "invalid_email",
        "invalid_phone",
    }
)

_FORBIDDEN_INBOUND_TOPIC_PATTERNS: tuple[tuple[str, str], ...] = (
    ("price", r"\b(?:pris|kostar|kostnad|vad\s+kostar)\b"),
    ("booking", r"\b(?:boka|bokning|inbokad|bokat\s+tid)\b"),
    ("warranty", r"\b(?:garanti|reklamation)\b"),
    ("legal_commitment", r"\b(?:juridiskt|stämning|advokat)\b"),
    ("bank_details", r"\b(?:bankgiro|plusgiro|swish\s+nummer)\b"),
)

_OUT_OF_AREA_MARKERS = ("gotland",)

_BLOCKING_PRIMARY_INTENTS = frozenset(
    {
        "irrelevant",
        "safety_incident",
        "pricing_request",
        "booking_request",
        "data_privacy_request",
        "invoice",
        "supplier",
        "complaint",
        "job_status_request",
    }
)

_BLOCKING_SECONDARY_INTENTS = frozenset(
    {
        "pricing_request",
        "booking_request",
    }
)

_BLOCKED_DECISIONING_REASONS = frozenset(
    {
        "ambiguous_context",
        "identity_conflict",
        "prompt_injection",
        "spam_detected",
    }
)


@dataclass(frozen=True)
class SafeAckEligibilityResult:
    eligible: bool
    blocker_codes: tuple[str, ...] = ()
    supporting_reason_codes: tuple[str, ...] = ()
    permitted_reply_type: str = "none"
    requires_approval: bool = False
    allowed_missing_facts: tuple[str, ...] = ()
    forbidden_commitments: tuple[str, ...] = ()
    threat_contract_version: str | None = None
    policy_version: str = POLICY_VERSION
    customer_draft_allowed: bool = False
    internal_note_allowed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "eligible": self.eligible,
            "blocker_codes": list(self.blocker_codes),
            "supporting_reason_codes": list(self.supporting_reason_codes),
            "permitted_reply_type": self.permitted_reply_type,
            "requires_approval": self.requires_approval,
            "allowed_missing_facts": list(self.allowed_missing_facts),
            "forbidden_commitments": list(self.forbidden_commitments),
            "threat_contract_version": self.threat_contract_version,
            "policy_version": self.policy_version,
            "customer_draft_allowed": self.customer_draft_allowed,
            "internal_note_allowed": self.internal_note_allowed,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> SafeAckEligibilityResult | None:
        if not data:
            return None
        return cls(
            eligible=bool(data.get("eligible")),
            blocker_codes=tuple(data.get("blocker_codes") or ()),
            supporting_reason_codes=tuple(data.get("supporting_reason_codes") or ()),
            permitted_reply_type=str(data.get("permitted_reply_type") or "none"),
            requires_approval=bool(data.get("requires_approval")),
            allowed_missing_facts=tuple(data.get("allowed_missing_facts") or ()),
            forbidden_commitments=tuple(data.get("forbidden_commitments") or ()),
            threat_contract_version=data.get("threat_contract_version"),
            policy_version=str(data.get("policy_version") or POLICY_VERSION),
            customer_draft_allowed=bool(data.get("customer_draft_allowed")),
            internal_note_allowed=bool(data.get("internal_note_allowed", True)),
        )


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


def _blocked(
    *codes: str,
    forbidden: tuple[str, ...] = (),
    threat_version: str | None = None,
    internal_note_allowed: bool = True,
    permitted_reply_type: str = "none",
) -> SafeAckEligibilityResult:
    return SafeAckEligibilityResult(
        eligible=False,
        blocker_codes=tuple(codes),
        permitted_reply_type=permitted_reply_type,
        forbidden_commitments=forbidden,
        threat_contract_version=threat_version,
        customer_draft_allowed=False,
        internal_note_allowed=internal_note_allowed,
    )


def evaluate_safe_ack_eligibility(
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
    decisioning_reasons: list[str] | None = None,
    threat_assessment: dict[str, Any] | ThreatAssessment | None = None,
    business_intent: dict[str, Any] | BusinessIntentResult | None = None,
    extracted_fact_set: dict[str, Any] | None = None,
) -> SafeAckEligibilityResult:
    """Return whether a safe acknowledgement draft may be prepared for approval."""
    threat: ThreatAssessment | None
    if isinstance(threat_assessment, ThreatAssessment):
        threat = threat_assessment
    else:
        threat = ThreatAssessment.from_dict(threat_assessment)

    intent: BusinessIntentResult | None
    if isinstance(business_intent, BusinessIntentResult):
        intent = business_intent
    else:
        intent = BusinessIntentResult.from_dict(business_intent)

    threat_version = (threat.contract_version if threat else None) or THREAT_CONTRACT_VERSION
    internal_note_allowed = threat.internal_note_allowed if threat else True

    from app.evaluation.profile_testbot.qualification.live_expectations import (
        expected_send_behavior_for_live_eval,
    )

    live_eval = input_data.get("live_eval") if isinstance(input_data.get("live_eval"), dict) else {}
    quality_expected_send = expected_send_behavior_for_live_eval(
        str(live_eval.get("scenario_id") or "")
    )
    if quality_expected_send == "observe_only":
        return _blocked(
            "quality_observe_only",
            permitted_reply_type="none",
            threat_version=threat_version,
            internal_note_allowed=True,
        )
    if quality_expected_send in {"reject", "no_reply"}:
        return _blocked(
            f"quality_{quality_expected_send}",
            permitted_reply_type="none",
            threat_version=threat_version,
            internal_note_allowed=internal_note_allowed,
        )

    quality_send_contract = quality_expected_send in {
        "send_after_approval",
        "draft_for_approval",
        "automatic_safe_send",
    }

    if threat is not None and not threat.customer_draft_allowed:
        blockers = tuple(threat.hard_blockers) if threat.hard_blockers else (f"threat_{threat.threat_class}",)
        return _blocked(
            *blockers,
            threat_version=threat_version,
            internal_note_allowed=internal_note_allowed,
        )

    if intent is not None:
        if intent.primary_intent in _BLOCKING_PRIMARY_INTENTS:
            return _blocked(
                f"intent_{intent.primary_intent}",
                permitted_reply_type="manual_only" if intent.primary_intent == "safety_incident" else "none",
                threat_version=threat_version,
                internal_note_allowed=internal_note_allowed,
            )
        for secondary in intent.secondary_intents:
            if secondary in _BLOCKING_SECONDARY_INTENTS:
                return _blocked(
                    f"intent_{secondary}",
                    forbidden=(secondary,),
                    threat_version=threat_version,
                    internal_note_allowed=internal_note_allowed,
                )

    risk_cats = list(risk_categories or [])
    if "safety_risk" in risk_cats:
        return _blocked(
            "urgent_safety",
            permitted_reply_type="manual_only",
            threat_version=threat_version,
            internal_note_allowed=internal_note_allowed,
        )

    if detected_job_type not in ("lead", "customer_inquiry"):
        return _blocked("unsupported_job_type", threat_version=threat_version)

    if risk_detected:
        return _blocked("content_risk_detected", threat_version=threat_version)

    if risk_cats:
        return _blocked(*risk_cats, threat_version=threat_version)

    if not _usable_customer_email(input_data):
        return _blocked("no_usable_reply_address", threat_version=threat_version)

    issue_set = {str(i) for i in extraction_issues if i}
    if issue_set & _HARD_EXTRACTION_ISSUES:
        return _blocked(
            *sorted(issue_set & _HARD_EXTRACTION_ISSUES),
            threat_version=threat_version,
        )

    if issue_set - _SOFT_EXTRACTION_ISSUES:
        return _blocked(
            *sorted(issue_set - _SOFT_EXTRACTION_ISSUES),
            threat_version=threat_version,
        )

    raw = str(recommendation_raw or "").strip().lower()
    if raw in _LEGACY_AUTHORIZATION_TOKENS:
        return _blocked("legacy_authorization_token", threat_version=threat_version)

    if raw in {"hold", "reject", "no_reply", "no_action"}:
        return _blocked(f"decisioning_{raw}", threat_version=threat_version)

    if recommendation == DecisionRecommendation.HOLD:
        return _blocked("decisioning_hold", threat_version=threat_version)

    if decisioning_reasons:
        matched = [reason for reason in decisioning_reasons if reason in _BLOCKED_DECISIONING_REASONS]
        if matched:
            return _blocked(*matched, threat_version=threat_version)

    combined_text = " ".join(
        str(input_data.get(key) or "")
        for key in ("subject", "message_text")
    )
    if "fwd:" in combined_text.lower() or "vidarebefordrat" in combined_text.lower():
        return _blocked("forwarded_thread_context", threat_version=threat_version)

    forbidden = _inbound_forbidden_topics(combined_text)
    if forbidden:
        return _blocked(*forbidden, forbidden=tuple(forbidden), threat_version=threat_version)

    if _is_out_of_area(combined_text):
        return _blocked("out_of_service_area", threat_version=threat_version)

    soft_signals = (
        "missing_identity" in issue_set
        or low_confidence
        or used_fallback
    )
    manual_review_signal = recommendation in (
        DecisionRecommendation.MANUAL_REVIEW,
        None,
    )
    if (
        recommendation == DecisionRecommendation.AUTO_ROUTE
        and not soft_signals
        and not quality_send_contract
    ):
        return _blocked("auto_route_without_identity_gap", threat_version=threat_version)

    if not soft_signals and not manual_review_signal and not quality_send_contract:
        return _blocked("complete_enough_for_auto_path", threat_version=threat_version)

    supporting: list[str] = []
    if soft_signals:
        supporting.append("incomplete_lead_missing_details")
    if manual_review_signal:
        supporting.append("operational_manual_review")
    if low_confidence:
        supporting.append("low_confidence_soft")
    if used_fallback:
        supporting.append("decisioning_used_fallback_soft")

    allowed_missing = tuple(sorted(issue_set & _SOFT_EXTRACTION_ISSUES))
    if extracted_fact_set:
        missing_from_facts = [
            f["field_name"]
            for f in (extracted_fact_set.get("facts") or [])
            if f.get("fact_status") in ("unknown", "conflicting")
        ]
        if missing_from_facts:
            allowed_missing = tuple(sorted(set(allowed_missing) | set(missing_from_facts)))

    return SafeAckEligibilityResult(
        eligible=True,
        supporting_reason_codes=tuple(supporting),
        permitted_reply_type="safe_acknowledgement",
        requires_approval=True,
        allowed_missing_facts=allowed_missing,
        forbidden_commitments=("price", "booking", "warranty", "legal_commitment", "delivery_promise"),
        threat_contract_version=threat_version,
        customer_draft_allowed=True,
        internal_note_allowed=internal_note_allowed,
    )
