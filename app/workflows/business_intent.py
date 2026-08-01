"""Business intent classification contract.

Separates business intention from trust/threat assessment. Classification runs
on threat-annotated representation, not raw untrusted instruction spans.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CONTRACT_VERSION = "business_intent_v1"

INTENT_CATEGORIES = frozenset(
    {
        "lead",
        "existing_customer_support",
        "job_status_request",
        "booking_request",
        "pricing_request",
        "complaint",
        "invoice",
        "supplier",
        "safety_incident",
        "data_privacy_request",
        "irrelevant",
        "unknown",
        "mixed",
        # Legacy taxonomy aliases mapped at boundary
        "customer_inquiry",
        "partnership",
        "newsletter",
        "internal",
        "spam",
    }
)

_LEGACY_TYPE_MAP: dict[str, str] = {
    "customer_inquiry": "existing_customer_support",
    "partnership": "irrelevant",
    "newsletter": "irrelevant",
    "internal": "irrelevant",
    "spam": "irrelevant",
}


@dataclass(frozen=True)
class BusinessIntentResult:
    primary_intent: str
    secondary_intents: tuple[str, ...] = ()
    confidence: float = 0.0
    evidence_spans: tuple[dict[str, Any], ...] = ()
    ambiguity_flags: tuple[str, ...] = ()
    conflict_flags: tuple[str, ...] = ()
    contract_version: str = CONTRACT_VERSION
    source_job_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary_intent": self.primary_intent,
            "secondary_intents": list(self.secondary_intents),
            "confidence": self.confidence,
            "evidence_spans": list(self.evidence_spans),
            "ambiguity_flags": list(self.ambiguity_flags),
            "conflict_flags": list(self.conflict_flags),
            "contract_version": self.contract_version,
            "source_job_type": self.source_job_type,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> BusinessIntentResult | None:
        if not data:
            return None
        return cls(
            primary_intent=str(data.get("primary_intent") or "unknown"),
            secondary_intents=tuple(data.get("secondary_intents") or ()),
            confidence=float(data.get("confidence") or 0.0),
            evidence_spans=tuple(data.get("evidence_spans") or ()),
            ambiguity_flags=tuple(data.get("ambiguity_flags") or ()),
            conflict_flags=tuple(data.get("conflict_flags") or ()),
            contract_version=str(data.get("contract_version") or CONTRACT_VERSION),
            source_job_type=data.get("source_job_type"),
        )


def normalize_intent_category(raw: str | None) -> str:
    value = str(raw or "unknown").strip().lower()
    return _LEGACY_TYPE_MAP.get(value, value)


def _is_job_status_request(subject: str, body: str) -> bool:
    return False


def build_business_intent_from_classification(
    *,
    detected_job_type: str,
    confidence: float,
    reasons: list[str] | None = None,
    threat_blocks_business: bool = False,
    subject: str = "",
    body: str = "",
) -> BusinessIntentResult:
    """Build BusinessIntentResult from classification processor output."""
    primary = normalize_intent_category(detected_job_type)
    ambiguity: list[str] = []
    conflicts: list[str] = []

    if threat_blocks_business:
        primary = "unknown"
        ambiguity.append("threat_blocked_business_classification")
        confidence = min(confidence, 0.35)

    if confidence < 0.5:
        ambiguity.append("low_confidence")

    if reasons:
        if "deterministic_fallback" in reasons:
            ambiguity.append("deterministic_fallback")
        if "llm_unavailable" in reasons:
            ambiguity.append("llm_unavailable")

    # Map pricing/booking from reasons or job type hints
    reason_text = " ".join(reasons or []).lower()
    secondary: list[str] = []
    if "price" in reason_text or primary == "lead" and "pris" in reason_text:
        secondary.append("pricing_request")
    if "booking" in reason_text or "boka" in reason_text:
        secondary.append("booking_request")

    if len(secondary) > 1:
        conflicts.append("mixed_intent_signals")

    return BusinessIntentResult(
        primary_intent=primary,
        secondary_intents=tuple(secondary),
        confidence=confidence,
        ambiguity_flags=tuple(ambiguity),
        conflict_flags=tuple(conflicts),
        source_job_type=detected_job_type,
    )
