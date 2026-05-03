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
LeadStatus = Literal[
    "new",
    "waiting_for_customer",
    "info_received",
    "offer_ready",
    "offer_sent",
    "won",
    "lost",
    "manual_review",
]


class LeadAnalysis:
    """Result of the rule-based lead analyzer."""

    __slots__ = (
        "lead_type", "intent", "urgency", "customer_type", "confidence",
        "tenant_context_used", "context_sources", "matched_service",
    )

    def __init__(
        self,
        lead_type: LeadType,
        intent: Intent,
        urgency: Urgency,
        customer_type: CustomerType,
        confidence: float,
        tenant_context_used: bool = False,
        context_sources: list[str] | None = None,
        matched_service: str | None = None,
    ) -> None:
        self.lead_type: LeadType = lead_type
        self.intent: Intent = intent
        self.urgency: Urgency = urgency
        self.customer_type: CustomerType = customer_type
        self.confidence: float = confidence
        self.tenant_context_used: bool = tenant_context_used
        self.context_sources: list[str] = context_sources or []
        self.matched_service: str | None = matched_service

    def to_dict(self) -> dict:
        return {
            "lead_type": self.lead_type,
            "intent": self.intent,
            "urgency": self.urgency,
            "customer_type": self.customer_type,
            "confidence": self.confidence,
            "tenant_context_used": self.tenant_context_used,
            "context_sources": self.context_sources,
            "matched_service": self.matched_service,
        }


class MissingInfoResult:
    """Result of the missing info engine."""

    __slots__ = (
        "required_fields", "present_fields", "missing_fields",
        "optional_fields", "completeness_score",
        "schema_source", "tenant_context_used", "context_sources",
    )

    def __init__(
        self,
        required_fields: list[str],
        present_fields: list[str],
        missing_fields: list[str],
        optional_fields: list[str],
        completeness_score: float,
        schema_source: str = "default",
        tenant_context_used: bool = False,
        context_sources: list[str] | None = None,
    ) -> None:
        self.required_fields = required_fields
        self.present_fields = present_fields
        self.missing_fields = missing_fields
        self.optional_fields = optional_fields
        self.completeness_score = completeness_score
        self.schema_source = schema_source
        self.tenant_context_used = tenant_context_used
        self.context_sources: list[str] = context_sources or []

    def to_dict(self) -> dict:
        return {
            "required_fields": self.required_fields,
            "present_fields": self.present_fields,
            "missing_fields": self.missing_fields,
            "optional_fields": self.optional_fields,
            "completeness_score": round(self.completeness_score, 3),
            "schema_source": self.schema_source,
            "tenant_context_used": self.tenant_context_used,
            "context_sources": self.context_sources,
        }


class LeadScore:
    """Result of the lead scoring engine."""

    __slots__ = ("score", "category", "reasons", "tenant_context_used", "business_fit_reason")

    def __init__(
        self,
        score: int,
        category: ScoreCategory,
        reasons: list[str],
        tenant_context_used: bool = False,
        business_fit_reason: str | None = None,
    ) -> None:
        self.score: int = score
        self.category: ScoreCategory = category
        self.reasons: list[str] = reasons
        self.tenant_context_used: bool = tenant_context_used
        self.business_fit_reason: str | None = business_fit_reason

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "category": self.category,
            "reasons": self.reasons,
            "tenant_context_used": self.tenant_context_used,
            "business_fit_reason": self.business_fit_reason,
        }


class OfferDraft:
    """Preliminary offer draft — not an exact quote."""

    __slots__ = (
        "summary",
        "recommended_next_step",
        "assumptions",
        "risk_points",
        "suggested_offer_sections",
        "estimated_price_range",
        "confidence",
        "tenant_context_used",
        "context_sources",
    )

    def __init__(
        self,
        summary: str,
        recommended_next_step: str,
        assumptions: list[str],
        suggested_offer_sections: list[str],
        estimated_price_range: str | None,
        confidence: float,
        risk_points: list[str] | None = None,
        tenant_context_used: bool = False,
        context_sources: list[str] | None = None,
    ) -> None:
        self.summary = summary
        self.recommended_next_step = recommended_next_step
        self.assumptions = assumptions
        self.risk_points = risk_points or []
        self.suggested_offer_sections = suggested_offer_sections
        self.estimated_price_range = estimated_price_range
        self.confidence = confidence
        self.tenant_context_used = tenant_context_used
        self.context_sources: list[str] = context_sources or []

    def to_dict(self) -> dict:
        return {
            "summary": self.summary,
            "recommended_next_step": self.recommended_next_step,
            "assumptions": self.assumptions,
            "risk_points": self.risk_points,
            "suggested_offer_sections": self.suggested_offer_sections,
            "estimated_price_range": self.estimated_price_range,
            "confidence": self.confidence,
            "disclaimer": "Preliminärt underlag — inte ett bindande erbjudande.",
            "tenant_context_used": self.tenant_context_used,
            "context_sources": self.context_sources,
        }
