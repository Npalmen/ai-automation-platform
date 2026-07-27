"""Semi-automatic campaign reply contract validation."""

from __future__ import annotations

from typing import Any

from app.evaluation.live.campaign.modes import CAMPAIGN_TYPE_REPLY_BUDGET
from app.evaluation.live.campaign.semi_automatic_expected_outcomes import (
    resolve_semi_automatic_expected_outcome,
)
from app.evaluation.live.config import LiveEvalConfig


def build_semi_auto_reply_contract_matrix(
    *,
    campaign_type: str = "semi-auto-core",
    config: LiveEvalConfig | None = None,
    selected_scenario_ids: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Build contract matrix for semi-auto reply budgets (offline, no Gmail send)."""
    from app.evaluation.live.config import get_live_eval_config
    from app.evaluation.live.campaign.scenario_budget import build_selected_scenario_budget

    config = config or get_live_eval_config()
    selected_budget = build_selected_scenario_budget(
        campaign_type=campaign_type,
        selected_scenario_ids=selected_scenario_ids,
    )
    workflow_reply_budget = selected_budget.campaign_type_reply_ceiling

    per_scenario: list[dict[str, Any]] = []
    scenario_expected_total = 0
    scenario_budget_total = 0

    for scenario_id in selected_budget.selected_scenario_ids:
        from app.evaluation.live.campaign.registry import get_campaign_scenario

        scenario = get_campaign_scenario(scenario_id)
        outcome = resolve_semi_automatic_expected_outcome(scenario)
        expected_replies = 1 if outcome.expected_reply else 0
        budget_replies = scenario.budgets.gmail_replies
        scenario_expected_total += expected_replies
        scenario_budget_total += budget_replies
        per_scenario.append(
            {
                "scenario_id": scenario.scenario_id,
                "expected_reply": outcome.expected_reply,
                "budget_gmail_replies": budget_replies,
                "test_variant": outcome.test_variant,
            }
        )

    tbsm06 = next(
        (row for row in per_scenario if row["scenario_id"] == "TBSM06_duplicate_approve"),
        None,
    )

    return {
        "campaign_type": campaign_type,
        "workflow_reply_budget": workflow_reply_budget,
        "selected_scenario_budget": selected_budget.to_dict(),
        "scenario_expected_reply_total": scenario_expected_total,
        "scenario_budget_reply_total": scenario_budget_total,
        "max_gmail_replies_per_run": config.max_gmail_replies_per_run,
        "per_scenario": per_scenario,
        "tbsm06_expected_reply": (
            tbsm06.get("expected_reply") if tbsm06 is not None else None
        ),
        "tbsm06_budget_gmail_replies": (
            tbsm06.get("budget_gmail_replies") if tbsm06 is not None else None
        ),
    }


def validate_semi_auto_reply_contract(
    *,
    campaign_type: str = "semi-auto-core",
    config: LiveEvalConfig | None = None,
    selected_scenario_ids: tuple[str, ...] | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """Return issues and contract matrix; blocks readiness when budgets diverge."""
    from app.evaluation.live.config import get_live_eval_config

    config = config or get_live_eval_config()
    matrix = build_semi_auto_reply_contract_matrix(
        campaign_type=campaign_type,
        config=config,
        selected_scenario_ids=selected_scenario_ids,
    )
    issues: list[str] = []

    if campaign_type != "semi-auto-core":
        return issues, matrix

    workflow_budget = matrix["workflow_reply_budget"]
    expected_total = matrix["scenario_expected_reply_total"]
    budget_total = matrix["scenario_budget_reply_total"]
    selected_budget = matrix["selected_scenario_budget"]
    selected_expected = selected_budget["expected_reply_count"]
    selected_authorized = selected_budget["max_reply_count"]

    if workflow_budget != 4 and selected_scenario_ids in (None, ()):
        issues.append(
            f"semi-auto workflow reply budget must be 4, got {workflow_budget}"
        )
    if selected_scenario_ids in (None, ()) and expected_total != 4:
        issues.append(
            f"semi-auto scenario expected_reply total must be 4, got {expected_total}"
        )
    if selected_scenario_ids in (None, ()) and budget_total != 4:
        issues.append(
            f"semi-auto scenario gmail_replies budget total must be 4, got {budget_total}"
        )
    if selected_scenario_ids in (None, ()) and workflow_budget != expected_total:
        issues.append(
            "workflow reply budget does not match scenario expected_reply total "
            f"({workflow_budget} != {expected_total})"
        )
    if selected_scenario_ids in (None, ()) and workflow_budget != budget_total:
        issues.append(
            "workflow reply budget does not match summed scenario gmail_replies "
            f"({workflow_budget} != {budget_total})"
        )
    if selected_expected != expected_total:
        issues.append(
            "selected scenario expected replies do not match per-scenario sum "
            f"({selected_expected} != {expected_total})"
        )
    if selected_authorized > workflow_budget:
        issues.append(
            "selected scenario authorized reply budget exceeds campaign ceiling "
            f"({selected_authorized} > {workflow_budget})"
        )
    if config.max_gmail_replies_per_run != 1:
        issues.append(
            "LIVE_EVAL_MAX_GMAIL_REPLIES must be 1 per scenario for semi-auto campaigns"
        )

    for row in matrix["per_scenario"]:
        if row["budget_gmail_replies"] > 1:
            issues.append(
                f"scenario {row['scenario_id']!r} gmail_replies budget exceeds 1"
            )

    tbsm06 = matrix.get("tbsm06_expected_reply")
    if selected_scenario_ids in (None, ()) or "TBSM06_duplicate_approve" in (
        selected_scenario_ids or ()
    ):
        if tbsm06 is not True and selected_scenario_ids in (None, ()):
            issues.append("TBSM06_duplicate_approve expected_reply must be true")
        if (
            matrix.get("tbsm06_budget_gmail_replies") != 1
            and selected_scenario_ids in (None, ())
        ):
            issues.append("TBSM06_duplicate_approve gmail_replies budget must be 1")

    return issues, matrix
