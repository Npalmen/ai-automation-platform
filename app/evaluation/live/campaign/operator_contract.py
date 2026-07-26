"""Semi-automatic operator plan and secondary approval contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.evaluation.live.campaign.modes import CAMPAIGN_TYPE_REPLY_BUDGET
from app.evaluation.live.campaign.registry import list_campaign_scenarios
from app.evaluation.live.campaign.schemas import CampaignScenario
from app.evaluation.live.config import LiveEvalConfig

DEFAULT_SECONDARY_HANDOFF = "send_internal_handoff"
VALID_DECISIONS = frozenset({"approve", "reject"})
VALID_SECONDARY_STATES = frozenset({
    "remain_pending",
    "resolved_separately",
    "rejected",
    "not_materialized",
    "cancelled_by_job_completion",
})


@dataclass(frozen=True)
class OperatorPlanStep:
    action_type: str
    decision: str
    delivery_type: str | None = None
    expected_http_status: int | None = None
    expected_result: str | None = None

    @property
    def resolved_delivery_type(self) -> str:
        return self.delivery_type or self.action_type


@dataclass(frozen=True)
class SecondaryApprovalExpectation:
    action_type: str
    expected_final_state: str
    delivery_type: str | None = None

    @property
    def resolved_delivery_type(self) -> str:
        return self.delivery_type or self.action_type


@dataclass(frozen=True)
class SemiAutoOperatorContract:
    operator_plan: tuple[OperatorPlanStep, ...]
    secondary_approvals: tuple[SecondaryApprovalExpectation, ...]
    uses_legacy_operator_action: bool = False


def _parse_operator_plan_step(raw: dict[str, Any]) -> OperatorPlanStep:
    action_type = str(raw.get("action_type") or "").strip()
    if not action_type:
        raise ValueError("operator_plan step requires action_type")
    decision = str(raw.get("decision") or "").strip().lower()
    if decision not in VALID_DECISIONS:
        raise ValueError(f"operator_plan step has invalid decision {decision!r}")
    delivery_type = raw.get("delivery_type")
    expected_http_status = raw.get("expected_http_status")
    expected_result = raw.get("expected_result")
    return OperatorPlanStep(
        action_type=action_type,
        decision=decision,
        delivery_type=str(delivery_type).strip() if delivery_type else None,
        expected_http_status=int(expected_http_status) if expected_http_status is not None else None,
        expected_result=str(expected_result).strip() if expected_result else None,
    )


def _parse_secondary_expectation(raw: dict[str, Any]) -> SecondaryApprovalExpectation:
    action_type = str(raw.get("action_type") or "").strip()
    if not action_type:
        raise ValueError("secondary_approvals entry requires action_type")
    expected_final_state = str(raw.get("expected_final_state") or "").strip()
    if expected_final_state not in VALID_SECONDARY_STATES:
        raise ValueError(
            f"secondary_approvals has invalid expected_final_state {expected_final_state!r}"
        )
    delivery_type = raw.get("delivery_type")
    return SecondaryApprovalExpectation(
        action_type=action_type,
        expected_final_state=expected_final_state,
        delivery_type=str(delivery_type).strip() if delivery_type else None,
    )


def _legacy_operator_plan(approval: dict[str, Any]) -> tuple[OperatorPlanStep, ...]:
    operator_action = str(approval.get("operator_action") or "none").strip().lower()
    test_variant = str(approval.get("test_variant") or "normal").strip().lower()
    if operator_action == "none" or test_variant == "negative_hold":
        return ()
    target = str(approval.get("target_action_type") or "send_customer_auto_reply")
    if operator_action == "approve":
        steps = [
            OperatorPlanStep(
                action_type=target,
                decision="approve",
                expected_http_status=200,
            )
        ]
        if test_variant == "duplicate_approve":
            steps.append(
                OperatorPlanStep(
                    action_type=target,
                    decision="approve",
                    expected_result="idempotent",
                )
            )
        return tuple(steps)
    if operator_action == "reject":
        steps = [
            OperatorPlanStep(
                action_type=target,
                decision="reject",
                expected_http_status=200,
            )
        ]
        if test_variant == "stale_action":
            steps.append(
                OperatorPlanStep(
                    action_type=target,
                    decision="approve",
                    expected_http_status=409,
                )
            )
        return tuple(steps)
    return ()


def _default_secondary_for_semi_auto(
    approval: dict[str, Any],
    *,
    operator_plan: tuple[OperatorPlanStep, ...],
) -> tuple[SecondaryApprovalExpectation, ...]:
    explicit = approval.get("secondary_approvals")
    if explicit is not None:
        return tuple(_parse_secondary_expectation(row) for row in explicit)
    if not operator_plan:
        return ()
    target_types = {step.action_type for step in operator_plan}
    if DEFAULT_SECONDARY_HANDOFF not in target_types:
        return (
            SecondaryApprovalExpectation(
                action_type=DEFAULT_SECONDARY_HANDOFF,
                expected_final_state="remain_pending",
            ),
        )
    return ()


def parse_semi_auto_operator_contract(scenario: CampaignScenario) -> SemiAutoOperatorContract:
    approval = dict(scenario.expected_approval or {})
    raw_plan = approval.get("operator_plan")
    uses_legacy = False
    if raw_plan:
        operator_plan = tuple(_parse_operator_plan_step(row) for row in raw_plan)
    else:
        legacy_action = str(approval.get("operator_action") or "none").strip().lower()
        uses_legacy = legacy_action in ("approve", "reject")
        operator_plan = _legacy_operator_plan(approval)
    secondary_approvals = _default_secondary_for_semi_auto(
        approval,
        operator_plan=operator_plan,
    )
    return SemiAutoOperatorContract(
        operator_plan=operator_plan,
        secondary_approvals=secondary_approvals,
        uses_legacy_operator_action=uses_legacy and raw_plan is None,
    )


def build_semi_auto_operator_contract_matrix(
    *,
    campaign_type: str = "semi-auto-core",
) -> dict[str, Any]:
    from app.evaluation.live.campaign.semi_automatic_expected_outcomes import (
        resolve_semi_automatic_expected_outcome,
    )

    scenarios = list_campaign_scenarios(campaign_type=campaign_type)
    per_scenario: list[dict[str, Any]] = []
    for scenario in scenarios:
        contract = parse_semi_auto_operator_contract(scenario)
        outcome = resolve_semi_automatic_expected_outcome(scenario)
        per_scenario.append(
            {
                "scenario_id": scenario.scenario_id,
                "expected_materialized_approvals": (
                    0 if outcome.is_negative_hold else 2
                ),
                "operator_plan": [
                    {
                        "action_type": step.action_type,
                        "delivery_type": step.resolved_delivery_type,
                        "decision": step.decision,
                        "expected_http_status": step.expected_http_status,
                        "expected_result": step.expected_result,
                    }
                    for step in contract.operator_plan
                ],
                "secondary_approvals": [
                    {
                        "action_type": sec.action_type,
                        "delivery_type": sec.resolved_delivery_type,
                        "expected_final_state": sec.expected_final_state,
                    }
                    for sec in contract.secondary_approvals
                ],
                "expected_reply": outcome.expected_reply,
                "reply_budget": scenario.budgets.gmail_replies,
                "final_job_status": outcome.final_job_status,
                "uses_legacy_operator_action": contract.uses_legacy_operator_action,
            }
        )
    return {
        "campaign_type": campaign_type,
        "workflow_reply_budget": CAMPAIGN_TYPE_REPLY_BUDGET.get(campaign_type, 0),
        "per_scenario": per_scenario,
    }


def validate_semi_auto_operator_contract(
    *,
    campaign_type: str = "semi-auto-core",
    config: LiveEvalConfig | None = None,
) -> tuple[list[str], list[str], dict[str, Any]]:
    from app.evaluation.live.config import get_live_eval_config

    config = config or get_live_eval_config()
    matrix = build_semi_auto_operator_contract_matrix(campaign_type=campaign_type)
    issues: list[str] = []
    warnings: list[str] = []

    if campaign_type != "semi-auto-core":
        return issues, warnings, matrix

    for row in matrix["per_scenario"]:
        scenario_id = row["scenario_id"]
        plan = row["operator_plan"]
        secondary = row["secondary_approvals"]

        if scenario_id == "TBSM08_unknown_negative_hold":
            if plan:
                issues.append(f"{scenario_id}: negative hold must not define operator_plan")
            continue

        if not plan:
            issues.append(f"{scenario_id}: semi-auto scenario missing operator_plan")

        if row["uses_legacy_operator_action"]:
            warnings.append(
                f"{scenario_id}: uses legacy operator_action without operator_plan"
            )

        target_types = [step["action_type"] for step in plan]
        if len(target_types) != len(set(target_types)) and len(plan) > 1:
            dup_steps = [t for t in target_types if target_types.count(t) > 1]
            if len(set(dup_steps)) > 1:
                issues.append(
                    f"{scenario_id}: ambiguous operator_plan with multiple action_types"
                )

        for step in plan:
            if step["decision"] not in VALID_DECISIONS:
                issues.append(f"{scenario_id}: invalid operator decision")

        if plan and not secondary:
            issues.append(f"{scenario_id}: missing secondary_approvals expectations")

        for sec in secondary:
            if sec["expected_final_state"] not in VALID_SECONDARY_STATES:
                issues.append(f"{scenario_id}: invalid secondary expected_final_state")

        if row["expected_reply"] and row["reply_budget"] != 1:
            issues.append(f"{scenario_id}: reply scenario must have gmail_replies budget 1")
        if not row["expected_reply"] and row["reply_budget"] != 0:
            issues.append(f"{scenario_id}: no-reply scenario must have gmail_replies budget 0")

    if config.max_gmail_replies_per_run != 1:
        issues.append("LIVE_EVAL_MAX_GMAIL_REPLIES must be 1 per scenario for semi-auto campaigns")

    return issues, warnings, matrix
