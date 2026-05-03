"""Typed result structures for the lead analysis layer."""
from __future__ import annotations

from typing import Literal


LeadType = Literal[
    "solar_installation",
    "ev_charger",
    "roof_cleaning",
    "roof_painting",
    "electrical_work",
    "battery_storage",
    "unknown",
]

Intent = Literal["researching", "comparing", "ready_to_buy"]
Urgency = Literal["low", "medium", "high"]
CustomerType = Literal["private", "company", "brf", "unknown"]
ScoreCategory = Literal["hot", "warm", "cold"]
NextAction = Literal[
    "ask_questions",
    "create_offer_draft",
    "manual_review",
    "approval_required",
    "ready_to_dispatch",
]


class LeadAnalysis:
    """Result of the rule-based lead analyzer."""

    __slots__ = ("lead_type", "intent", "urgency", "customer_type", "confidence")

    def __init__(
        self,
        lead_type: LeadType,
        intent: Intent,
        urgency: Urgency,
        customer_type: CustomerType,
        confidence: float,
    ) -> None:
        self.lead_type: LeadType = lead_type
        self.intent: Intent = intent
        self.urgency: Urgency = urgency
        self.customer_type: CustomerType = customer_type
        self.confidence: float = confidence

    def to_dict(self) -> dict:
        return {
            "lead_type": self.lead_type,
            "intent": self.intent,
            "urgency": self.urgency,
            "customer_type": self.customer_type,
            "confidence": self.confidence,
        }


class MissingInfoResult:
    """Result of the missing info engine."""

    __slots__ = ("required_fields", "present_fields", "missing_fields", "optional_fields", "completeness_score")

    def __init__(
        self,
        required_fields: list[str],
        present_fields: list[str],
        missing_fields: list[str],
        optional_fields: list[str],
        completeness_score: float,
    ) -> None:
        self.required_fields = required_fields
        self.present_fields = present_fields
        self.missing_fields = missing_fields
        self.optional_fields = optional_fields
        self.completeness_score = completeness_score

    def to_dict(self) -> dict:
        return {
            "required_fields": self.required_fields,
            "present_fields": self.present_fields,
            "missing_fields": self.missing_fields,
            "optional_fields": self.optional_fields,
            "completeness_score": round(self.completeness_score, 3),
        }


class LeadScore:
    """Result of the lead scoring engine."""

    __slots__ = ("score", "category", "reasons")

    def __init__(self, score: int, category: ScoreCategory, reasons: list[str]) -> None:
        self.score: int = score
        self.category: ScoreCategory = category
        self.reasons: list[str] = reasons

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "category": self.category,
            "reasons": self.reasons,
        }


class OfferDraft:
    """Preliminary offer draft — not an exact quote."""

    __slots__ = (
        "summary",
        "recommended_next_step",
        "assumptions",
        "suggested_offer_sections",
        "estimated_price_range",
        "confidence",
    )

    def __init__(
        self,
        summary: str,
        recommended_next_step: str,
        assumptions: list[str],
        suggested_offer_sections: list[str],
        estimated_price_range: str | None,
        confidence: float,
    ) -> None:
        self.summary = summary
        self.recommended_next_step = recommended_next_step
        self.assumptions = assumptions
        self.suggested_offer_sections = suggested_offer_sections
        self.estimated_price_range = estimated_price_range
        self.confidence = confidence

    def to_dict(self) -> dict:
        return {
            "summary": self.summary,
            "recommended_next_step": self.recommended_next_step,
            "assumptions": self.assumptions,
            "suggested_offer_sections": self.suggested_offer_sections,
            "estimated_price_range": self.estimated_price_range,
            "confidence": self.confidence,
            "disclaimer": "Preliminärt underlag — inte ett bindande erbjudande.",
        }
