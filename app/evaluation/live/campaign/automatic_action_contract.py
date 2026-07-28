"""Hard limits for automatic Gmail canary campaign qualification."""

from __future__ import annotations

from typing import Any

from app.evaluation.live.campaign.modes import (
    CAMPAIGN_TYPE_REPLY_BUDGET,
    CAMPAIGN_TYPE_SEND_BUDGET,
)
from app.evaluation.live.errors import LiveEvalSafetyError

AUTOMATIC_GMAIL_CANARY_CAMPAIGN_TYPE = "automatic-gmail-canary"
AUTOMATIC_GMAIL_CANARY_WORKFLOW_CONFIRMATION = "RUN_AUTOMATIC_GMAIL_CANARY"
AUTOMATIC_GMAIL_CANARY_SCENARIO_IDS: tuple[str, ...] = (
    "TBA01_safe_lead_auto_reply",
    "TBA02_unknown_auto_hold",
)
ALLOWED_AUTOMATIC_ACTION_TYPES = frozenset({"send_customer_auto_reply"})

CANARY_AUTO_ACTIONS: dict[str, str] = {
    "lead": "auto",
    "customer_inquiry": "manual",
    "invoice": "manual",
    "unknown": "manual",
}

QUALIFICATION_ERROR = "automatic_campaign_type_not_qualified"


class AutomaticCampaignNotQualified(LiveEvalSafetyError):
    """Raised when automatic campaign parameters fall outside E1 scope."""


def _qualification_issues(
    *,
    campaign_type: str,
    workflow_confirmation: str | None = None,
    scenario_ids: tuple[str, ...] | None = None,
) -> list[str]:
    issues: list[str] = []
    if campaign_type != AUTOMATIC_GMAIL_CANARY_CAMPAIGN_TYPE:
        issues.append(
            f"{QUALIFICATION_ERROR}: campaign_type must be "
            f"{AUTOMATIC_GMAIL_CANARY_CAMPAIGN_TYPE!r}, got {campaign_type!r}"
        )
    if workflow_confirmation is not None:
        if workflow_confirmation != AUTOMATIC_GMAIL_CANARY_WORKFLOW_CONFIRMATION:
            issues.append(
                f"{QUALIFICATION_ERROR}: workflow_confirmation must be "
                f"{AUTOMATIC_GMAIL_CANARY_WORKFLOW_CONFIRMATION!r}, "
                f"got {workflow_confirmation!r}"
            )
    if scenario_ids is not None:
        normalized = tuple(item.strip() for item in scenario_ids if str(item).strip())
        if normalized != AUTOMATIC_GMAIL_CANARY_SCENARIO_IDS:
            issues.append(
                f"{QUALIFICATION_ERROR}: scenario_ids must be exactly "
                f"{AUTOMATIC_GMAIL_CANARY_SCENARIO_IDS}, got {normalized!r}"
            )
    return issues


def validate_automatic_campaign_qualification(
    *,
    campaign_type: str,
    workflow_confirmation: str | None = None,
    scenario_ids: tuple[str, ...] | None = None,
    raise_on_failure: bool = True,
) -> list[str]:
    """Fail-closed qualification for automatic Gmail canary (bindande tillägg B)."""
    issues = _qualification_issues(
        campaign_type=campaign_type,
        workflow_confirmation=workflow_confirmation,
        scenario_ids=scenario_ids,
    )
    if issues and raise_on_failure:
        raise AutomaticCampaignNotQualified(issues[0])
    return issues


def validate_automatic_action_scope(
    scenario_action_types: list[str] | tuple[str, ...],
) -> list[str]:
    """Only send_customer_auto_reply is authorized in E1."""
    issues: list[str] = []
    for action_type in scenario_action_types:
        if action_type not in ALLOWED_AUTOMATIC_ACTION_TYPES:
            issues.append(
                f"{QUALIFICATION_ERROR}: action_type {action_type!r} is not allowlisted"
            )
    return issues


def validate_automatic_campaign_budgets(
    *,
    campaign_type: str = AUTOMATIC_GMAIL_CANARY_CAMPAIGN_TYPE,
    selected_scenario_ids: tuple[str, ...] | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """Validate exact send/reply/write budgets for automatic Gmail canary."""
    issues = validate_automatic_campaign_qualification(
        campaign_type=campaign_type,
        scenario_ids=selected_scenario_ids,
        raise_on_failure=False,
    )
    matrix: dict[str, Any] = {}
    try:
        from app.evaluation.live.campaign.scenario_budget import build_selected_scenario_budget

        budget = build_selected_scenario_budget(
            campaign_type=campaign_type,
            selected_scenario_ids=selected_scenario_ids,
        )
        matrix = budget.to_dict()
        if budget.inbound_send_budget != 2:
            issues.append(
                f"{QUALIFICATION_ERROR}: inbound_send_budget must be 2, "
                f"got {budget.inbound_send_budget}"
            )
        if budget.expected_reply_count != 1:
            issues.append(
                f"{QUALIFICATION_ERROR}: expected_reply_count must be 1, "
                f"got {budget.expected_reply_count}"
            )
        if budget.non_gmail_write_budget != 0:
            issues.append(
                f"{QUALIFICATION_ERROR}: non_gmail_write_budget must be 0, "
                f"got {budget.non_gmail_write_budget}"
            )
        send_ceiling = CAMPAIGN_TYPE_SEND_BUDGET.get(campaign_type, 0)
        reply_ceiling = CAMPAIGN_TYPE_REPLY_BUDGET.get(campaign_type, 0)
        if send_ceiling != 2 or reply_ceiling != 1:
            issues.append(
                f"{QUALIFICATION_ERROR}: campaign ceilings must be sends=2 replies=1"
            )
    except LiveEvalSafetyError as exc:
        issues.append(str(exc))
    return issues, matrix
