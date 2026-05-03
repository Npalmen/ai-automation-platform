"""Typed result structures for the support analysis layer."""
from __future__ import annotations

from typing import Literal


TicketType = Literal[
    "issue",
    "question",
    "complaint",
    "warranty",
    "invoice_question",
    "emergency",
    "scheduling",
    "other",
]

SupportCategory = Literal[
    "installation",
    "product",
    "scheduling",
    "invoice",
    "warranty",
    "service",
    "safety",
    "other",
]

SupportUrgency = Literal["low", "medium", "high", "critical"]
CustomerSentiment = Literal["neutral", "concerned", "frustrated", "angry"]
PriorityCategory = Literal["normal", "urgent", "critical"]
ResponseType = Literal[
    "ask_for_info",
    "suggested_solution",
    "acknowledgement",
    "escalation",
]
SupportNextActionType = Literal[
    "ask_for_info",
    "suggest_solution",
    "manual_review",
    "escalate",
    "create_task",
    "ready_to_dispatch",
]
SupportStatus = Literal[
    "new",
    "waiting_for_customer",
    "in_review",
    "escalated",
    "solution_suggested",
    "resolved",
    "closed",
]


class SupportAnalysis:
    """Result of the rule-based support analyzer."""

    __slots__ = (
        "ticket_type", "category", "matched_service", "urgency",
        "customer_sentiment", "requires_human", "confidence",
        "tenant_context_used", "context_sources",
    )

    def __init__(
        self,
        ticket_type: TicketType,
        category: SupportCategory,
        urgency: SupportUrgency,
        customer_sentiment: CustomerSentiment,
        requires_human: bool,
        confidence: float,
        matched_service: str | None = None,
        tenant_context_used: bool = False,
        context_sources: list[str] | None = None,
    ) -> None:
        self.ticket_type: TicketType = ticket_type
        self.category: SupportCategory = category
        self.matched_service: str | None = matched_service
        self.urgency: SupportUrgency = urgency
        self.customer_sentiment: CustomerSentiment = customer_sentiment
        self.requires_human: bool = requires_human
        self.confidence: float = confidence
        self.tenant_context_used: bool = tenant_context_used
        self.context_sources: list[str] = context_sources or []

    def to_dict(self) -> dict:
        return {
            "ticket_type": self.ticket_type,
            "category": self.category,
            "matched_service": self.matched_service,
            "urgency": self.urgency,
            "customer_sentiment": self.customer_sentiment,
            "requires_human": self.requires_human,
            "confidence": self.confidence,
            "tenant_context_used": self.tenant_context_used,
            "context_sources": self.context_sources,
        }


class SupportMissingInfoResult:
    """Result of the support missing info engine."""

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


class SupportPriority:
    """Result of the support prioritization engine."""

    __slots__ = (
        "score", "category", "reasons",
        "business_risk_reason", "tenant_context_used", "context_sources",
    )

    def __init__(
        self,
        score: int,
        category: PriorityCategory,
        reasons: list[str],
        business_risk_reason: str | None = None,
        tenant_context_used: bool = False,
        context_sources: list[str] | None = None,
    ) -> None:
        self.score: int = score
        self.category: PriorityCategory = category
        self.reasons: list[str] = reasons
        self.business_risk_reason: str | None = business_risk_reason
        self.tenant_context_used: bool = tenant_context_used
        self.context_sources: list[str] = context_sources or []

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "category": self.category,
            "reasons": self.reasons,
            "business_risk_reason": self.business_risk_reason,
            "tenant_context_used": self.tenant_context_used,
            "context_sources": self.context_sources,
        }


class SupportResponseDraft:
    """Safe preliminary support response — not a definitive resolution."""

    __slots__ = (
        "response_type", "subject", "body",
        "assumptions", "risk_points", "recommended_next_step",
        "confidence", "tenant_context_used", "context_sources",
    )

    def __init__(
        self,
        response_type: ResponseType,
        subject: str,
        body: str,
        assumptions: list[str],
        recommended_next_step: str,
        confidence: float,
        risk_points: list[str] | None = None,
        tenant_context_used: bool = False,
        context_sources: list[str] | None = None,
    ) -> None:
        self.response_type: ResponseType = response_type
        self.subject: str = subject
        self.body: str = body
        self.assumptions: list[str] = assumptions
        self.risk_points: list[str] = risk_points or []
        self.recommended_next_step: str = recommended_next_step
        self.confidence: float = confidence
        self.tenant_context_used: bool = tenant_context_used
        self.context_sources: list[str] = context_sources or []

    def to_dict(self) -> dict:
        return {
            "response_type": self.response_type,
            "subject": self.subject,
            "body": self.body,
            "assumptions": self.assumptions,
            "risk_points": self.risk_points,
            "recommended_next_step": self.recommended_next_step,
            "confidence": self.confidence,
            "disclaimer": "Preliminärt svar — granskas av handläggare innan utskick.",
            "tenant_context_used": self.tenant_context_used,
            "context_sources": self.context_sources,
        }


class SupportNextAction:
    """Determined next action for a support ticket."""

    __slots__ = (
        "action", "requires_approval", "reason",
        "tenant_context_used", "context_sources",
    )

    def __init__(
        self,
        action: SupportNextActionType,
        requires_approval: bool,
        reason: str,
        tenant_context_used: bool = False,
        context_sources: list[str] | None = None,
    ) -> None:
        self.action: SupportNextActionType = action
        self.requires_approval: bool = requires_approval
        self.reason: str = reason
        self.tenant_context_used: bool = tenant_context_used
        self.context_sources: list[str] = context_sources or []

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "requires_approval": self.requires_approval,
            "reason": self.reason,
            "tenant_context_used": self.tenant_context_used,
            "context_sources": self.context_sources,
        }
