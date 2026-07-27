"""Selected-scenario budget for full-system testbot campaigns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.evaluation.live.campaign.modes import (
    CAMPAIGN_TYPE_REPLY_BUDGET,
    CAMPAIGN_TYPE_SEND_BUDGET,
)
from app.evaluation.live.campaign.registry import get_campaign_scenario, list_campaign_scenarios
from app.evaluation.live.campaign.semi_automatic_expected_outcomes import (
    resolve_semi_automatic_expected_outcome,
)
from app.evaluation.live.errors import LiveEvalSafetyError


@dataclass(frozen=True)
class SelectedScenarioBudget:
    campaign_type: str
    selected_scenario_ids: tuple[str, ...]
    selected_scenario_count: int
    inbound_send_budget: int
    expected_reply_count: int
    max_reply_count: int
    per_scenario_reply_budget: dict[str, int]
    non_gmail_write_budget: int
    campaign_type_reply_ceiling: int
    campaign_type_send_ceiling: int

    @property
    def selected_scenario_expected_replies(self) -> int:
        return self.expected_reply_count

    @property
    def selected_scenario_authorized_reply_budget(self) -> int:
        return self.max_reply_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "campaign_type": self.campaign_type,
            "selected_scenario_ids": list(self.selected_scenario_ids),
            "selected_scenario_count": self.selected_scenario_count,
            "inbound_send_budget": self.inbound_send_budget,
            "expected_reply_count": self.expected_reply_count,
            "max_reply_count": self.max_reply_count,
            "per_scenario_reply_budget": dict(self.per_scenario_reply_budget),
            "non_gmail_write_budget": self.non_gmail_write_budget,
            "campaign_type_reply_ceiling": self.campaign_type_reply_ceiling,
            "campaign_type_send_ceiling": self.campaign_type_send_ceiling,
            "selected_scenario_expected_replies": self.selected_scenario_expected_replies,
            "selected_scenario_authorized_reply_budget": (
                self.selected_scenario_authorized_reply_budget
            ),
        }


def _normalize_selected_scenario_ids(
    selected_scenario_ids: tuple[str, ...] | list[str] | None,
) -> tuple[str, ...]:
    if not selected_scenario_ids:
        return ()
    normalized = tuple(item.strip() for item in selected_scenario_ids if str(item).strip())
    if not normalized:
        return ()
    if len(normalized) != len(set(normalized)):
        raise LiveEvalSafetyError("duplicate scenario ids in selection are not allowed")
    return normalized


def build_selected_scenario_budget(
    *,
    campaign_type: str,
    selected_scenario_ids: tuple[str, ...] | list[str] | None = None,
) -> SelectedScenarioBudget:
    """Compute reply/send budgets for the exact scenarios in this run."""
    if selected_scenario_ids is not None and len(selected_scenario_ids) == 0:
        raise LiveEvalSafetyError("empty scenario selection is not allowed")
    explicit_ids = _normalize_selected_scenario_ids(selected_scenario_ids)
    if explicit_ids:
        scenarios = []
        for scenario_id in explicit_ids:
            try:
                scenarios.append(get_campaign_scenario(scenario_id))
            except LiveEvalSafetyError as exc:
                raise LiveEvalSafetyError(
                    f"unknown or unavailable campaign scenario: {scenario_id}"
                ) from exc
            if scenarios[-1].campaign_type != campaign_type:
                raise LiveEvalSafetyError(
                    f"scenario {scenario_id!r} is not part of campaign_type={campaign_type!r}"
                )
        selected_ids = explicit_ids
    else:
        scenarios = list_campaign_scenarios(campaign_type=campaign_type)
        selected_ids = tuple(scenario.scenario_id for scenario in scenarios)

    if not selected_ids:
        raise LiveEvalSafetyError("empty scenario selection is not allowed")

    reply_ceiling = CAMPAIGN_TYPE_REPLY_BUDGET.get(campaign_type, 0)
    send_ceiling = CAMPAIGN_TYPE_SEND_BUDGET.get(campaign_type, 0)

    per_scenario_reply_budget: dict[str, int] = {}
    expected_reply_count = 0
    non_gmail_write_budget = 0
    for scenario in scenarios:
        outcome = resolve_semi_automatic_expected_outcome(scenario)
        reply_budget = scenario.budgets.gmail_replies
        per_scenario_reply_budget[scenario.scenario_id] = reply_budget
        expected_reply_count += 1 if outcome.expected_reply else 0
        non_gmail_write_budget += scenario.budgets.external_writes

    inbound_send_budget = len(scenarios)
    max_reply_count = expected_reply_count

    if reply_ceiling and max_reply_count > reply_ceiling:
        raise LiveEvalSafetyError(
            "selected scenario reply budget exceeds campaign ceiling "
            f"({max_reply_count} > {reply_ceiling})"
        )
    if send_ceiling and inbound_send_budget > send_ceiling:
        raise LiveEvalSafetyError(
            "selected scenario send budget exceeds campaign ceiling "
            f"({inbound_send_budget} > {send_ceiling})"
        )

    return SelectedScenarioBudget(
        campaign_type=campaign_type,
        selected_scenario_ids=selected_ids,
        selected_scenario_count=len(selected_ids),
        inbound_send_budget=inbound_send_budget,
        expected_reply_count=expected_reply_count,
        max_reply_count=max_reply_count,
        per_scenario_reply_budget=per_scenario_reply_budget,
        non_gmail_write_budget=non_gmail_write_budget,
        campaign_type_reply_ceiling=reply_ceiling,
        campaign_type_send_ceiling=send_ceiling,
    )
