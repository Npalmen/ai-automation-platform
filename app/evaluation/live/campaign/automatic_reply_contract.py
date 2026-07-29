"""Automatic Gmail campaign reply contract validation."""

from __future__ import annotations

from typing import Any

from app.evaluation.live.campaign.automatic_action_contract import (
    AUTOMATIC_GMAIL_CANARY_CAMPAIGN_TYPE,
    AUTOMATIC_GMAIL_CANARY_SCENARIO_IDS,
    validate_automatic_campaign_budgets,
    validate_automatic_campaign_qualification,
)
from app.evaluation.live.campaign.automatic_action_contract_core import (
    AUTOMATIC_GMAIL_CORE_CAMPAIGN_TYPE,
    AUTOMATIC_GMAIL_CORE_SCENARIO_IDS,
    CORE_EXPECTED_REPLY_COUNT,
    validate_automatic_core_campaign_budgets,
    validate_automatic_core_campaign_qualification,
)
from app.evaluation.live.campaign.automatic_expected_outcomes import (
    resolve_automatic_expected_outcome,
)
from app.evaluation.live.config import LiveEvalConfig, get_live_eval_config


def _default_scenario_ids(campaign_type: str) -> tuple[str, ...]:
    if campaign_type == AUTOMATIC_GMAIL_CORE_CAMPAIGN_TYPE:
        return AUTOMATIC_GMAIL_CORE_SCENARIO_IDS
    return AUTOMATIC_GMAIL_CANARY_SCENARIO_IDS


def _validate_budgets(
    *,
    campaign_type: str,
    selected_scenario_ids: tuple[str, ...] | None,
) -> tuple[list[str], dict[str, Any]]:
    if campaign_type == AUTOMATIC_GMAIL_CORE_CAMPAIGN_TYPE:
        return validate_automatic_core_campaign_budgets(
            campaign_type=campaign_type,
            selected_scenario_ids=selected_scenario_ids,
        )
    return validate_automatic_campaign_budgets(
        campaign_type=campaign_type,
        selected_scenario_ids=selected_scenario_ids,
    )


def _validate_qualification(
    *,
    campaign_type: str,
    selected_scenario_ids: tuple[str, ...] | None,
) -> list[str]:
    if campaign_type == AUTOMATIC_GMAIL_CORE_CAMPAIGN_TYPE:
        return validate_automatic_core_campaign_qualification(
            campaign_type=campaign_type,
            scenario_ids=selected_scenario_ids,
            raise_on_failure=False,
        )
    return validate_automatic_campaign_qualification(
        campaign_type=campaign_type,
        scenario_ids=selected_scenario_ids,
        raise_on_failure=False,
    )


def build_automatic_reply_contract_matrix(
    *,
    campaign_type: str = AUTOMATIC_GMAIL_CANARY_CAMPAIGN_TYPE,
    config: LiveEvalConfig | None = None,
    selected_scenario_ids: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Build contract matrix for automatic reply budgets (offline, no Gmail send)."""
    from app.evaluation.live.campaign.registry import get_campaign_scenario

    config = config or get_live_eval_config()
    scenario_ids = selected_scenario_ids or _default_scenario_ids(campaign_type)
    budget_issues, budget_matrix = _validate_budgets(
        campaign_type=campaign_type,
        selected_scenario_ids=scenario_ids,
    )

    per_scenario: list[dict[str, Any]] = []
    scenario_expected_total = 0
    for scenario_id in scenario_ids:
        scenario = get_campaign_scenario(scenario_id)
        outcome = resolve_automatic_expected_outcome(scenario)
        expected_replies = 1 if outcome.expected_reply else 0
        scenario_expected_total += expected_replies
        per_scenario.append(
            {
                "scenario_id": scenario.scenario_id,
                "expected_reply": outcome.expected_reply,
                "budget_gmail_replies": scenario.budgets.gmail_replies,
                "test_variant": outcome.test_variant,
            }
        )

    return {
        "campaign_type": campaign_type,
        "qualification_issues": budget_issues,
        "selected_scenario_budget": budget_matrix,
        "scenario_expected_reply_total": scenario_expected_total,
        "max_gmail_replies_per_run": config.max_gmail_replies_per_run,
        "per_scenario": per_scenario,
    }


def validate_automatic_reply_contract(
    *,
    campaign_type: str = AUTOMATIC_GMAIL_CANARY_CAMPAIGN_TYPE,
    config: LiveEvalConfig | None = None,
    selected_scenario_ids: tuple[str, ...] | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """Validate automatic Gmail reply contract (readiness gate)."""
    config = config or get_live_eval_config()
    issues = _validate_qualification(
        campaign_type=campaign_type,
        selected_scenario_ids=selected_scenario_ids,
    )
    budget_issues, _ = _validate_budgets(
        campaign_type=campaign_type,
        selected_scenario_ids=selected_scenario_ids,
    )
    issues.extend(budget_issues)

    matrix = build_automatic_reply_contract_matrix(
        campaign_type=campaign_type,
        config=config,
        selected_scenario_ids=selected_scenario_ids,
    )

    expected_replies = (
        CORE_EXPECTED_REPLY_COUNT
        if campaign_type == AUTOMATIC_GMAIL_CORE_CAMPAIGN_TYPE
        else 1
    )
    min_replies_env = 1 if campaign_type == AUTOMATIC_GMAIL_CANARY_CAMPAIGN_TYPE else expected_replies

    if config.max_gmail_replies_per_run < min_replies_env:
        issues.append(
            f"LIVE_EVAL_MAX_GMAIL_REPLIES must be >= {min_replies_env} for {campaign_type}"
        )
    if matrix["scenario_expected_reply_total"] != expected_replies:
        issues.append(
            f"{campaign_type} requires exactly {expected_replies} expected replies "
            f"across scenarios, got {matrix['scenario_expected_reply_total']}"
        )

    return issues, matrix
