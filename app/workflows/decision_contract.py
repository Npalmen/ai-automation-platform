"""Canonical decision contract between AI recommendation and policy authorization."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.workflows.tenant_automation import (
    FULL_AUTO,
    resolve_automation_mode,
)


class DecisionRecommendation(str, Enum):
    AUTO_ROUTE = "auto_route"
    MANUAL_REVIEW = "manual_review"
    HOLD = "hold"


class PolicyAuthorization(str, Enum):
    HOLD_FOR_REVIEW = "hold_for_review"
    APPROVAL_REQUIRED = "approval_required"
    EXECUTION_ALLOWED = "execution_allowed"
    NO_ACTION = "no_action"


# Legacy authorization tokens stored on the wrong processor layer.
_LEGACY_AUTHORIZATION_TOKENS = frozenset({"auto_execute", "send_for_approval"})


@dataclass(frozen=True)
class PolicyAuthorizationResult:
    authorization: PolicyAuthorization
    reasons: tuple[str, ...]
    recommendation: DecisionRecommendation | None
    recommendation_raw: str | None


def normalize_decision_recommendation(
    raw: Any,
    *,
    used_fallback: bool = False,
) -> DecisionRecommendation | None:
    """Normalize AI-layer decision values. Legacy auth tokens fail closed."""
    if used_fallback:
        return DecisionRecommendation.MANUAL_REVIEW

    if raw is None:
        return None

    value = str(raw).strip().lower()
    if not value:
        return None

    if value in _LEGACY_AUTHORIZATION_TOKENS:
        return DecisionRecommendation.MANUAL_REVIEW

    if value in ("auto_route", "route"):
        return DecisionRecommendation.AUTO_ROUTE
    if value in ("manual_review", "request_human_review"):
        return DecisionRecommendation.MANUAL_REVIEW
    if value == "hold":
        return DecisionRecommendation.HOLD

    return None


def project_policy_decision(authorization: PolicyAuthorization) -> str:
    """Backward-compatible projection for orchestrator / approval consumers."""
    return {
        PolicyAuthorization.HOLD_FOR_REVIEW: "hold_for_review",
        PolicyAuthorization.APPROVAL_REQUIRED: "send_for_approval",
        PolicyAuthorization.EXECUTION_ALLOWED: "auto_execute",
        PolicyAuthorization.NO_ACTION: "hold_for_review",
    }[authorization]


def project_recommended_next_step(authorization: PolicyAuthorization) -> str:
    return {
        PolicyAuthorization.HOLD_FOR_REVIEW: "manual_review",
        PolicyAuthorization.APPROVAL_REQUIRED: "awaiting_approval",
        PolicyAuthorization.EXECUTION_ALLOWED: "action_dispatch",
        PolicyAuthorization.NO_ACTION: "manual_review",
    }[authorization]


def project_approval_route(authorization: PolicyAuthorization) -> str | None:
    if authorization == PolicyAuthorization.APPROVAL_REQUIRED:
        return "approval_required"
    if authorization == PolicyAuthorization.HOLD_FOR_REVIEW:
        return "manual_review"
    return None


def resolve_policy_authorization(
    *,
    detected_job_type: str,
    recommendation: DecisionRecommendation | None,
    recommendation_raw: str | None,
    auto_actions: dict[str, Any] | None,
    low_confidence: bool,
    used_fallback: bool,
    risk_detected: bool,
    force_approval_test: bool = False,
    invoice_has_issues: bool = False,
) -> PolicyAuthorizationResult:
    """Single resolver — risk and fail-closed rules cannot be bypassed."""
    reasons: list[str] = []

    if risk_detected:
        reasons.append("content_risk_detected")
        return PolicyAuthorizationResult(
            authorization=PolicyAuthorization.HOLD_FOR_REVIEW,
            reasons=tuple(reasons),
            recommendation=recommendation,
            recommendation_raw=recommendation_raw,
        )

    if detected_job_type == "invoice":
        return _resolve_invoice_authorization(
            reasons=reasons,
            recommendation=recommendation,
            recommendation_raw=recommendation_raw,
            invoice_has_issues=invoice_has_issues,
        )

    if detected_job_type not in ("lead", "customer_inquiry"):
        reasons.append("unknown_job_type")
        return PolicyAuthorizationResult(
            authorization=PolicyAuthorization.HOLD_FOR_REVIEW,
            reasons=tuple(reasons),
            recommendation=recommendation,
            recommendation_raw=recommendation_raw,
        )

    if force_approval_test:
        reasons.append("forced_approval_test")
        return PolicyAuthorizationResult(
            authorization=PolicyAuthorization.APPROVAL_REQUIRED,
            reasons=tuple(reasons),
            recommendation=recommendation,
            recommendation_raw=recommendation_raw,
        )

    if used_fallback or low_confidence or recommendation is None:
        if used_fallback:
            reasons.append("decisioning_used_fallback")
        if low_confidence:
            reasons.append(f"{detected_job_type}_low_confidence")
        if recommendation is None:
            reasons.append("missing_or_invalid_decision_recommendation")
        return PolicyAuthorizationResult(
            authorization=PolicyAuthorization.HOLD_FOR_REVIEW,
            reasons=tuple(reasons),
            recommendation=recommendation,
            recommendation_raw=recommendation_raw,
        )

    if recommendation in (DecisionRecommendation.HOLD, DecisionRecommendation.MANUAL_REVIEW):
        reasons.append(f"decisioning_{recommendation.value}")
        return PolicyAuthorizationResult(
            authorization=PolicyAuthorization.HOLD_FOR_REVIEW,
            reasons=tuple(reasons),
            recommendation=recommendation,
            recommendation_raw=recommendation_raw,
        )

    if recommendation == DecisionRecommendation.AUTO_ROUTE:
        mode = resolve_automation_mode(auto_actions, detected_job_type)
        if mode == FULL_AUTO:
            reasons.append("decisioning_auto_route_full_auto")
            return PolicyAuthorizationResult(
                authorization=PolicyAuthorization.EXECUTION_ALLOWED,
                reasons=tuple(reasons),
                recommendation=recommendation,
                recommendation_raw=recommendation_raw,
            )
        reasons.append("decisioning_auto_route_requires_approval")
        return PolicyAuthorizationResult(
            authorization=PolicyAuthorization.APPROVAL_REQUIRED,
            reasons=tuple(reasons),
            recommendation=recommendation,
            recommendation_raw=recommendation_raw,
        )

    reasons.append("unhandled_recommendation")
    return PolicyAuthorizationResult(
        authorization=PolicyAuthorization.HOLD_FOR_REVIEW,
        reasons=tuple(reasons),
        recommendation=recommendation,
        recommendation_raw=recommendation_raw,
    )


def _resolve_invoice_authorization(
    *,
    reasons: list[str],
    recommendation: DecisionRecommendation | None,
    recommendation_raw: str | None,
    invoice_has_issues: bool = False,
) -> PolicyAuthorizationResult:
    if invoice_has_issues:
        reasons.append("invoice_requires_review")
        return PolicyAuthorizationResult(
            authorization=PolicyAuthorization.HOLD_FOR_REVIEW,
            reasons=tuple(reasons),
            recommendation=recommendation,
            recommendation_raw=recommendation_raw,
        )
    reasons.append("invoice_clean_requires_approval")
    return PolicyAuthorizationResult(
        authorization=PolicyAuthorization.APPROVAL_REQUIRED,
        reasons=tuple(reasons),
        recommendation=recommendation,
        recommendation_raw=recommendation_raw,
    )


def is_force_approval_test_allowed(input_data: dict[str, Any], *, allow_flag: bool) -> bool:
    """force_approval_test is only honored when explicitly enabled server-side."""
    if not allow_flag:
        return False
    return input_data.get("force_approval_test") is True
