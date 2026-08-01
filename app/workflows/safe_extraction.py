"""Safe extraction with provenance and untrusted-span exclusion.

AI instructions and prompt-injection spans must never become authoritative
business facts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.workflows.threat_assessment import ThreatAssessment

CONTRACT_VERSION = "safe_extraction_v1"

FACT_STATUSES = frozenset({"explicit", "inferred", "conflicting", "unknown", "excluded"})

SENSITIVITY_CLASSES = frozenset({"public", "contact", "location", "financial", "identity", "restricted"})

# Spans matching these patterns are excluded from authoritative fact extraction.
_UNTRUSTED_SPAN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bignore\s+(?:all\s+)?previous\s+instructions\b.*", re.I | re.S),
    re.compile(r"\bdisregard\s+(?:all\s+)?(?:prior|previous)\b.*", re.I | re.S),
    re.compile(r"\b(?:send|provide|give)\s+(?:me\s+)?(?:a\s+)?price\s+quote\b", re.I),
    re.compile(r"\bact\s+as\b.*", re.I | re.S),
    re.compile(r"\byou\s+are\s+now\b.*", re.I | re.S),
)


@dataclass
class ExtractedFact:
    field_name: str
    normalized_value: str | None
    source_text: str | None = None
    source_section: str = "current_message"
    fact_status: str = "explicit"
    confidence: float = 0.0
    sensitivity_class: str = "public"
    extraction_version: str = CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_name": self.field_name,
            "normalized_value": self.normalized_value,
            "source_text": self.source_text,
            "source_section": self.source_section,
            "fact_status": self.fact_status,
            "confidence": self.confidence,
            "sensitivity_class": self.sensitivity_class,
            "extraction_version": self.extraction_version,
        }


@dataclass
class ExtractedFactSet:
    facts: list[ExtractedFact] = field(default_factory=list)
    excluded_spans: list[dict[str, Any]] = field(default_factory=list)
    contract_version: str = CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "facts": [f.to_dict() for f in self.facts],
            "excluded_spans": self.excluded_spans,
            "contract_version": self.contract_version,
        }

    def fact_map(self) -> dict[str, str | None]:
        return {f.field_name: f.normalized_value for f in self.facts if f.fact_status != "excluded"}


def identify_untrusted_spans(
    text: str,
    threat: ThreatAssessment | None = None,
) -> list[dict[str, Any]]:
    """Return untrusted text spans that must not become business facts."""
    spans: list[dict[str, Any]] = []

    for pattern in _UNTRUSTED_SPAN_PATTERNS:
        for match in pattern.finditer(text or ""):
            spans.append(
                {
                    "text": match.group(0),
                    "reason": "prompt_injection_pattern",
                    "start": match.start(),
                    "end": match.end(),
                }
            )

    if threat:
        for evidence in threat.evidence_spans:
            if evidence.get("signal", "").startswith("prompt_") or evidence.get("signal", "").startswith("phishing_"):
                spans.append(
                    {
                        "text": evidence.get("text", ""),
                        "reason": evidence.get("signal", "threat_evidence"),
                        "section": evidence.get("section", "current_message"),
                    }
                )

    return spans


def _value_from_untrusted_span(value: str | None, untrusted_spans: list[dict[str, Any]]) -> bool:
    if not value:
        return False
    lowered = value.lower().strip()
    for span in untrusted_spans:
        span_text = str(span.get("text") or "").lower()
        if span_text and (lowered in span_text or span_text in lowered):
            return True
    return False


def sanitize_entities(
    entities: dict[str, Any],
    *,
    subject: str = "",
    body: str = "",
    threat: ThreatAssessment | None = None,
    extraction_confidence: float = 0.0,
) -> tuple[dict[str, Any], ExtractedFactSet]:
    """Filter entity dict and build provenance-aware ExtractedFactSet."""
    combined = f"{subject}\n{body}"
    untrusted = identify_untrusted_spans(combined, threat)
    fact_set = ExtractedFactSet(excluded_spans=untrusted)

    sanitized: dict[str, Any] = dict(entities)
    sensitivity_map = {
        "customer_name": "identity",
        "email": "contact",
        "phone": "contact",
        "address": "location",
        "city": "location",
        "requested_service": "public",
        "company_name": "identity",
    }

    for field_name, raw_value in entities.items():
        if raw_value is None or raw_value == "":
            continue

        str_value = str(raw_value).strip()
        excluded = _value_from_untrusted_span(str_value, untrusted)

        if excluded:
            sanitized[field_name] = None
            fact_set.facts.append(
                ExtractedFact(
                    field_name=field_name,
                    normalized_value=None,
                    source_text=str_value,
                    fact_status="excluded",
                    confidence=extraction_confidence,
                    sensitivity_class=sensitivity_map.get(field_name, "public"),
                )
            )
        else:
            fact_set.facts.append(
                ExtractedFact(
                    field_name=field_name,
                    normalized_value=str_value,
                    source_text=str_value,
                    fact_status="explicit" if extraction_confidence >= 0.5 else "unknown",
                    confidence=extraction_confidence,
                    sensitivity_class=sensitivity_map.get(field_name, "public"),
                )
            )

    return sanitized, fact_set
