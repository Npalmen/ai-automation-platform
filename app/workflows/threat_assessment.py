"""Deterministic trust/threat assessment for inbox intake.

Runs before business classification. Deterministic hard blockers cannot be
lowered by downstream LLM interpretation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

CONTRACT_VERSION = "threat_assessment_v1"

THREAT_CLASSES = frozenset(
    {
        "trusted_business_content",
        "suspicious",
        "phishing",
        "prompt_injection",
        "spam",
        "credential_request",
        "payment_detail_change",
        "unknown",
    }
)

SEVERITIES = frozenset({"none", "low", "medium", "high", "critical"})

ROUTING_VALUES = frozenset({"continue", "manual_review", "security_review", "reject"})


@dataclass(frozen=True)
class ThreatAssessment:
    threat_class: str
    severity: str
    confidence: float
    evidence_spans: tuple[dict[str, Any], ...] = ()
    detected_signals: tuple[str, ...] = ()
    customer_draft_allowed: bool = True
    internal_note_allowed: bool = True
    required_routing: str = "continue"
    hard_blockers: tuple[str, ...] = ()
    contract_version: str = CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "threat_class": self.threat_class,
            "severity": self.severity,
            "confidence": self.confidence,
            "evidence_spans": list(self.evidence_spans),
            "detected_signals": list(self.detected_signals),
            "customer_draft_allowed": self.customer_draft_allowed,
            "internal_note_allowed": self.internal_note_allowed,
            "required_routing": self.required_routing,
            "hard_blockers": list(self.hard_blockers),
            "contract_version": self.contract_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ThreatAssessment | None:
        if not data:
            return None
        return cls(
            threat_class=str(data.get("threat_class") or "unknown"),
            severity=str(data.get("severity") or "none"),
            confidence=float(data.get("confidence") or 0.0),
            evidence_spans=tuple(data.get("evidence_spans") or ()),
            detected_signals=tuple(data.get("detected_signals") or ()),
            customer_draft_allowed=bool(data.get("customer_draft_allowed", True)),
            internal_note_allowed=bool(data.get("internal_note_allowed", True)),
            required_routing=str(data.get("required_routing") or "continue"),
            hard_blockers=tuple(data.get("hard_blockers") or ()),
            contract_version=str(data.get("contract_version") or CONTRACT_VERSION),
        )


# Deterministic signal patterns — order matters for primary threat_class selection.
_PHISHING_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("phishing_verify_account", re.compile(r"\bverify\s+your\s+account\b", re.I)),
    ("phishing_click_verify", re.compile(r"\bclick\s+here\s+to\s+verify\b", re.I)),
    ("phishing_urgent_account", re.compile(r"\burgent\s+account\s+verification\b", re.I)),
    ("phishing_account_suspended", re.compile(r"\baccount\s+(?:has\s+been\s+)?suspended\b", re.I)),
    ("phishing_confirm_identity", re.compile(r"\bconfirm\s+your\s+identity\b", re.I)),
)

_PROMPT_INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("prompt_ignore_previous", re.compile(r"\bignore\s+(?:all\s+)?previous\s+instructions\b", re.I)),
    ("prompt_disregard", re.compile(r"\bdisregard\s+(?:all\s+)?(?:prior|previous)\b", re.I)),
    ("prompt_system_override", re.compile(r"\b(?:you\s+are\s+now|act\s+as|pretend\s+to\s+be)\b", re.I)),
    ("prompt_send_price", re.compile(r"\bignore\b.*\bsend\s+price\b", re.I | re.S)),
)

_CREDENTIAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("credential_password", re.compile(r"\b(?:send|share|provide)\s+(?:your\s+)?password\b", re.I)),
    ("credential_login", re.compile(r"\blogin\s+credentials\b", re.I)),
    ("credential_reset_link", re.compile(r"\breset\s+your\s+password\s+(?:here|now)\b", re.I)),
)

_PAYMENT_CHANGE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("payment_bankgiro_change", re.compile(r"\b(?:ändra|byt(?:t)?|nytt)\s+bankgiro\b", re.I)),
    ("payment_plusgiro_change", re.compile(r"\b(?:ändra|byt|nytt)\s+plusgiro\b", re.I)),
    ("payment_wire_urgent", re.compile(r"\bwire\s+transfer\s+urgent\b", re.I)),
    ("payment_account_change", re.compile(r"\b(?:ändra|byt)\s+(?:vårt\s+)?(?:bank|betalnings)konto\b", re.I)),
)

_SPAM_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("spam_lottery", re.compile(r"\b(?:you\s+won|lottery|free\s+money)\b", re.I)),
    ("spam_casino", re.compile(r"\bcasino\s+bonus\b", re.I)),
    ("spam_seo", re.compile(r"\bseo\s+erbjudande\b", re.I)),
    ("spam_cold_outreach", re.compile(r"\bcold\s+outreach\b", re.I)),
)

_SUSPICIOUS_LINK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("suspicious_short_link", re.compile(r"\b(?:bit\.ly|tinyurl|t\.co)/\S+", re.I)),
)


def _find_matches(
    text: str,
    patterns: tuple[tuple[str, re.Pattern[str]], ...],
) -> list[tuple[str, str]]:
    """Return (signal_id, matched_text) for each pattern hit."""
    hits: list[tuple[str, str]] = []
    for signal_id, pattern in patterns:
        match = pattern.search(text)
        if match:
            hits.append((signal_id, match.group(0)))
    return hits


def _span(signal_id: str, matched_text: str, section: str = "current_message") -> dict[str, Any]:
    return {
        "signal": signal_id,
        "text": matched_text,
        "section": section,
    }


def assess_threat(
    *,
    subject: str = "",
    body: str = "",
    quoted_history: str = "",
) -> ThreatAssessment:
    """Run deterministic threat assessment on inbound message content.

    Current message (subject + body) is assessed with higher weight than quoted
    history. Quoted prompt injection alone does not block a legitimate new request
    unless combined with other high-risk signals in the current section.
    """
    current_text = f"{subject}\n{body}".strip()
    combined_text = f"{current_text}\n{quoted_history}".strip()

    if not combined_text:
        return ThreatAssessment(
            threat_class="unknown",
            severity="low",
            confidence=0.3,
            customer_draft_allowed=False,
            internal_note_allowed=True,
            required_routing="manual_review",
            hard_blockers=("empty_message",),
        )

    signals: list[str] = []
    spans: list[dict[str, Any]] = []
    hard_blockers: list[str] = []

    # Assess current message section first (authoritative for hard blocks).
    current_hits: list[tuple[str, str, str]] = []
    for category, patterns in (
        ("phishing", _PHISHING_PATTERNS),
        ("prompt_injection", _PROMPT_INJECTION_PATTERNS),
        ("credential_request", _CREDENTIAL_PATTERNS),
        ("payment_detail_change", _PAYMENT_CHANGE_PATTERNS),
        ("spam", _SPAM_PATTERNS),
        ("suspicious", _SUSPICIOUS_LINK_PATTERNS),
    ):
        for signal_id, matched in _find_matches(current_text, patterns):
            current_hits.append((category, signal_id, matched))
            signals.append(signal_id)
            spans.append(_span(signal_id, matched, "current_message"))
            hard_blockers.append(signal_id)

    # Quoted history: advisory only unless no current-message signals.
    quoted_hits: list[tuple[str, str, str]] = []
    if quoted_history.strip():
        for category, patterns in (
            ("prompt_injection", _PROMPT_INJECTION_PATTERNS),
            ("phishing", _PHISHING_PATTERNS),
        ):
            for signal_id, matched in _find_matches(quoted_history, patterns):
                quoted_hits.append((category, signal_id, matched))
                if not current_hits:
                    signals.append(f"quoted_{signal_id}")
                    spans.append(_span(signal_id, matched, "quoted_history"))

    # Determine primary threat class and severity.
    threat_class = "trusted_business_content"
    severity = "none"
    confidence = 0.85
    required_routing = "continue"
    customer_draft_allowed = True

    if current_hits:
        # Priority: phishing > prompt_injection > credential > payment > spam > suspicious
        priority = [
            "phishing",
            "prompt_injection",
            "credential_request",
            "payment_detail_change",
            "spam",
            "suspicious",
        ]
        for cat in priority:
            matching = [h for h in current_hits if h[0] == cat]
            if matching:
                threat_class = cat
                break

        if threat_class in ("phishing", "prompt_injection", "credential_request"):
            severity = "critical"
            confidence = 0.95
            required_routing = "security_review"
            customer_draft_allowed = False
        elif threat_class == "payment_detail_change":
            severity = "high"
            confidence = 0.9
            required_routing = "security_review"
            customer_draft_allowed = False
        elif threat_class == "spam":
            severity = "high"
            confidence = 0.9
            required_routing = "reject"
            customer_draft_allowed = False
        elif threat_class == "suspicious":
            severity = "medium"
            confidence = 0.75
            required_routing = "manual_review"
            customer_draft_allowed = False
    elif quoted_hits:
        threat_class = "suspicious"
        severity = "low"
        confidence = 0.6
        required_routing = "continue"
        customer_draft_allowed = True
        hard_blockers = []

    return ThreatAssessment(
        threat_class=threat_class,
        severity=severity,
        confidence=confidence,
        evidence_spans=tuple(spans),
        detected_signals=tuple(signals),
        customer_draft_allowed=customer_draft_allowed,
        internal_note_allowed=True,
        required_routing=required_routing,
        hard_blockers=tuple(hard_blockers),
    )


def merge_threat_assessment(
    deterministic: ThreatAssessment,
    llm_assessment: ThreatAssessment | None,
) -> ThreatAssessment:
    """Merge LLM threat hints with deterministic assessment.

    LLM may raise severity or add signals but cannot lower deterministic hard blockers.
    """
    if llm_assessment is None:
        return deterministic

    if deterministic.hard_blockers:
        return deterministic

    if llm_assessment.severity in ("high", "critical") and deterministic.severity in ("none", "low", "medium"):
        return ThreatAssessment(
            threat_class=llm_assessment.threat_class,
            severity=llm_assessment.severity,
            confidence=max(deterministic.confidence, llm_assessment.confidence),
            evidence_spans=deterministic.evidence_spans + llm_assessment.evidence_spans,
            detected_signals=deterministic.detected_signals + llm_assessment.detected_signals,
            customer_draft_allowed=llm_assessment.customer_draft_allowed,
            internal_note_allowed=True,
            required_routing=llm_assessment.required_routing,
            hard_blockers=llm_assessment.hard_blockers,
        )

    return deterministic
