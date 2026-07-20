"""Tests for canonical decision contract and fail-closed normalization."""

from __future__ import annotations

import pytest

from app.workflows.decision_contract import (
    DecisionRecommendation,
    PolicyAuthorization,
    normalize_decision_recommendation,
    project_policy_decision,
    resolve_policy_authorization,
)


class TestNormalizeDecisionRecommendation:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("auto_route", DecisionRecommendation.AUTO_ROUTE),
            ("hold", DecisionRecommendation.HOLD),
            ("manual_review", DecisionRecommendation.MANUAL_REVIEW),
            ("auto_execute", DecisionRecommendation.MANUAL_REVIEW),
            ("send_for_approval", DecisionRecommendation.MANUAL_REVIEW),
            (None, None),
            ("garbage", None),
        ],
    )
    def test_normalization(self, raw, expected):
        assert normalize_decision_recommendation(raw) == expected

    def test_used_fallback_forces_manual_review(self):
        assert normalize_decision_recommendation("auto_route", used_fallback=True) == DecisionRecommendation.MANUAL_REVIEW


class TestLegacyAutoExecuteFailClosed:
    def test_legacy_auto_execute_never_execution_allowed_alone(self):
        result = resolve_policy_authorization(
            detected_job_type="lead",
            recommendation=normalize_decision_recommendation("auto_execute"),
            recommendation_raw="auto_execute",
            auto_actions={"lead": "full_auto"},
            low_confidence=False,
            used_fallback=False,
            risk_detected=False,
        )
        assert result.authorization != PolicyAuthorization.EXECUTION_ALLOWED
        assert result.authorization == PolicyAuthorization.HOLD_FOR_REVIEW

    def test_auto_route_requires_tenant_full_auto_for_execution(self):
        allowed = resolve_policy_authorization(
            detected_job_type="lead",
            recommendation=DecisionRecommendation.AUTO_ROUTE,
            recommendation_raw="auto_route",
            auto_actions={"lead": "full_auto"},
            low_confidence=False,
            used_fallback=False,
            risk_detected=False,
        )
        assert allowed.authorization == PolicyAuthorization.EXECUTION_ALLOWED
        assert project_policy_decision(allowed.authorization) == "auto_execute"

        blocked = resolve_policy_authorization(
            detected_job_type="lead",
            recommendation=DecisionRecommendation.AUTO_ROUTE,
            recommendation_raw="auto_route",
            auto_actions={},
            low_confidence=False,
            used_fallback=False,
            risk_detected=False,
        )
        assert blocked.authorization == PolicyAuthorization.APPROVAL_REQUIRED


class TestRiskOverridesForceApproval:
    def test_risk_blocks_force_approval_test(self):
        result = resolve_policy_authorization(
            detected_job_type="lead",
            recommendation=DecisionRecommendation.AUTO_ROUTE,
            recommendation_raw="auto_route",
            auto_actions={"lead": "full_auto"},
            low_confidence=False,
            used_fallback=False,
            risk_detected=True,
            force_approval_test=True,
        )
        assert result.authorization == PolicyAuthorization.HOLD_FOR_REVIEW
        assert "content_risk_detected" in result.reasons
