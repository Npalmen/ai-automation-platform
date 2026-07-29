"""Hard limits for automatic Gmail core campaign qualification (E2)."""

from __future__ import annotations

from typing import Any

from app.evaluation.live.campaign.automatic_action_contract import (
    ALLOWED_AUTOMATIC_ACTION_TYPES,
    QUALIFICATION_ERROR,
    AutomaticCampaignNotQualified,
    validate_automatic_action_scope,
)
from app.evaluation.live.campaign.modes import (
    CAMPAIGN_TYPE_REPLY_BUDGET,
    CAMPAIGN_TYPE_SEND_BUDGET,
)
from app.evaluation.live.errors import LiveEvalSafetyError

AUTOMATIC_GMAIL_CORE_CAMPAIGN_TYPE = "automatic-gmail-core"
AUTOMATIC_GMAIL_CORE_WORKFLOW_CONFIRMATION = "RUN_AUTOMATIC_GMAIL_CORE"
AUTOMATIC_GMAIL_CORE_SCENARIO_IDS: tuple[str, ...] = (
    "TBA01_safe_lead_auto_reply",
    "TBA02_unknown_auto_hold",
    "TBA03_safe_general_inquiry_auto_reply",
    "TBA04_noisy_lead_auto_reply",
    "TBA05_invoice_auto_hold",
    "TBA06_support_complaint_auto_hold",
    "TBA07_price_booking_commitment_hold",
    "TBA08_sensitive_safety_hold",
)
AUTOMATIC_GMAIL_CORE_POSITIVE_SCENARIO_IDS: frozenset[str] = frozenset({
    "TBA01_safe_lead_auto_reply",
    "TBA03_safe_general_inquiry_auto_reply",
    "TBA04_noisy_lead_auto_reply",
})
AUTOMATIC_GMAIL_CORE_HOLD_SCENARIO_IDS: frozenset[str] = frozenset({
    "TBA02_unknown_auto_hold",
    "TBA05_invoice_auto_hold",
    "TBA06_support_complaint_auto_hold",
    "TBA07_price_booking_commitment_hold",
    "TBA08_sensitive_safety_hold",
})

CORE_AUTO_ACTIONS: dict[str, str] = {
    "lead": "auto",
    "customer_inquiry": "auto",
    "invoice": "manual",
    "unknown": "manual",
}

CORE_INBOUND_SEND_BUDGET = 8
CORE_EXPECTED_REPLY_COUNT = 3
CORE_NON_GMAIL_WRITE_BUDGET = 0


def _qualification_issues(
    *,
    campaign_type: str,
    workflow_confirmation: str | None = None,
    scenario_ids: tuple[str, ...] | None = None,
) -> list[str]:
    issues: list[str] = []
    if campaign_type != AUTOMATIC_GMAIL_CORE_CAMPAIGN_TYPE:
        issues.append(
            f"{QUALIFICATION_ERROR}: campaign_type must be "
            f"{AUTOMATIC_GMAIL_CORE_CAMPAIGN_TYPE!r}, got {campaign_type!r}"
        )
    if workflow_confirmation is not None:
        if workflow_confirmation != AUTOMATIC_GMAIL_CORE_WORKFLOW_CONFIRMATION:
            issues.append(
                f"{QUALIFICATION_ERROR}: workflow_confirmation must be "
                f"{AUTOMATIC_GMAIL_CORE_WORKFLOW_CONFIRMATION!r}, "
                f"got {workflow_confirmation!r}"
            )
    if scenario_ids is not None:
        normalized = tuple(item.strip() for item in scenario_ids if str(item).strip())
        if normalized != AUTOMATIC_GMAIL_CORE_SCENARIO_IDS:
            issues.append(
                f"{QUALIFICATION_ERROR}: scenario_ids must be exactly "
                f"{AUTOMATIC_GMAIL_CORE_SCENARIO_IDS}, got {normalized!r}"
            )
    return issues


def validate_automatic_core_campaign_qualification(
    *,
    campaign_type: str,
    workflow_confirmation: str | None = None,
    scenario_ids: tuple[str, ...] | None = None,
    raise_on_failure: bool = True,
) -> list[str]:
    issues = _qualification_issues(
        campaign_type=campaign_type,
        workflow_confirmation=workflow_confirmation,
        scenario_ids=scenario_ids,
    )
    if issues and raise_on_failure:
        raise AutomaticCampaignNotQualified(issues[0])
    return issues


def validate_automatic_core_campaign_budgets(
    *,
    campaign_type: str = AUTOMATIC_GMAIL_CORE_CAMPAIGN_TYPE,
    selected_scenario_ids: tuple[str, ...] | None = None,
) -> tuple[list[str], dict[str, Any]]:
    issues = validate_automatic_core_campaign_qualification(
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
        if budget.inbound_send_budget != CORE_INBOUND_SEND_BUDGET:
            issues.append(
                f"{QUALIFICATION_ERROR}: inbound_send_budget must be "
                f"{CORE_INBOUND_SEND_BUDGET}, got {budget.inbound_send_budget}"
            )
        if budget.expected_reply_count != CORE_EXPECTED_REPLY_COUNT:
            issues.append(
                f"{QUALIFICATION_ERROR}: expected_reply_count must be "
                f"{CORE_EXPECTED_REPLY_COUNT}, got {budget.expected_reply_count}"
            )
        if budget.non_gmail_write_budget != CORE_NON_GMAIL_WRITE_BUDGET:
            issues.append(
                f"{QUALIFICATION_ERROR}: non_gmail_write_budget must be "
                f"{CORE_NON_GMAIL_WRITE_BUDGET}, got {budget.non_gmail_write_budget}"
            )
        send_ceiling = CAMPAIGN_TYPE_SEND_BUDGET.get(campaign_type, 0)
        reply_ceiling = CAMPAIGN_TYPE_REPLY_BUDGET.get(campaign_type, 0)
        if send_ceiling != CORE_INBOUND_SEND_BUDGET or reply_ceiling != CORE_EXPECTED_REPLY_COUNT:
            issues.append(
                f"{QUALIFICATION_ERROR}: campaign ceilings must be "
                f"sends={CORE_INBOUND_SEND_BUDGET} replies={CORE_EXPECTED_REPLY_COUNT}"
            )
        for scenario_id, reply_budget in budget.per_scenario_reply_budget.items():
            if reply_budget > 1:
                issues.append(
                    f"{QUALIFICATION_ERROR}: max reply per scenario is 1, "
                    f"got {reply_budget} for {scenario_id!r}"
                )
    except LiveEvalSafetyError as exc:
        issues.append(str(exc))
    return issues, matrix


def resolve_automatic_campaign_qualification(
    *,
    campaign_type: str,
    workflow_confirmation: str | None = None,
    scenario_ids: tuple[str, ...] | None = None,
    raise_on_failure: bool = True,
) -> list[str]:
    """Dispatch qualification validation to canary or core contract."""
    from app.evaluation.live.campaign.automatic_action_contract import (
        AUTOMATIC_GMAIL_CANARY_CAMPAIGN_TYPE,
        validate_automatic_campaign_qualification,
    )

    if campaign_type == AUTOMATIC_GMAIL_CANARY_CAMPAIGN_TYPE:
        return validate_automatic_campaign_qualification(
            campaign_type=campaign_type,
            workflow_confirmation=workflow_confirmation,
            scenario_ids=scenario_ids,
            raise_on_failure=raise_on_failure,
        )
    if campaign_type == AUTOMATIC_GMAIL_CORE_CAMPAIGN_TYPE:
        return validate_automatic_core_campaign_qualification(
            campaign_type=campaign_type,
            workflow_confirmation=workflow_confirmation,
            scenario_ids=scenario_ids,
            raise_on_failure=raise_on_failure,
        )
    issues = [
        f"{QUALIFICATION_ERROR}: unsupported automatic campaign_type {campaign_type!r}"
    ]
    if issues and raise_on_failure:
        raise AutomaticCampaignNotQualified(issues[0])
    return issues


__all__ = [
    "ALLOWED_AUTOMATIC_ACTION_TYPES",
    "AUTOMATIC_GMAIL_CORE_CAMPAIGN_TYPE",
    "AUTOMATIC_GMAIL_CORE_HOLD_SCENARIO_IDS",
    "AUTOMATIC_GMAIL_CORE_POSITIVE_SCENARIO_IDS",
    "AUTOMATIC_GMAIL_CORE_SCENARIO_IDS",
    "AUTOMATIC_GMAIL_CORE_WORKFLOW_CONFIRMATION",
    "CORE_AUTO_ACTIONS",
    "CORE_EXPECTED_REPLY_COUNT",
    "CORE_INBOUND_SEND_BUDGET",
    "resolve_automatic_campaign_qualification",
    "validate_automatic_core_campaign_budgets",
    "validate_automatic_core_campaign_qualification",
]
