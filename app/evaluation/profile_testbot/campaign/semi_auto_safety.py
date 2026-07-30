"""Fail-fast safety checks for profile semi-auto campaigns."""

from __future__ import annotations

from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.profile_testbot.campaign.semi_auto_contract import ContractSemiAutoBackend
from app.evaluation.profile_testbot.constants import (
    BLOCKED_TENANTS,
    LIVE_EVAL_TENANT_ID,
    SEMI_AUTO_SCENARIO_TARGET,
    SEMI_AUTO_SEND_AFTER_APPROVAL_MIN,
)
from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario


def validate_campaign_budgets(
    *,
    scenario_count: int,
    send_after_count: int,
    send_budget_used: int,
) -> list[str]:
    issues: list[str] = []
    if scenario_count != SEMI_AUTO_SCENARIO_TARGET:
        issues.append(f"scenario count {scenario_count} != {SEMI_AUTO_SCENARIO_TARGET}")
    if send_after_count < SEMI_AUTO_SEND_AFTER_APPROVAL_MIN:
        issues.append(
            f"send_after_approval count {send_after_count} < {SEMI_AUTO_SEND_AFTER_APPROVAL_MIN}"
        )
    if send_budget_used > SEMI_AUTO_SEND_AFTER_APPROVAL_MIN:
        issues.append(
            f"send budget exceeded: {send_budget_used} > {SEMI_AUTO_SEND_AFTER_APPROVAL_MIN}"
        )
    return issues


def assert_tenant_isolated(tenant_id: str) -> None:
    if tenant_id != LIVE_EVAL_TENANT_ID:
        raise LiveEvalSafetyError(f"tenant must be {LIVE_EVAL_TENANT_ID}")
    if tenant_id in BLOCKED_TENANTS:
        raise LiveEvalSafetyError(f"tenant {tenant_id!r} is blocked")


def assert_no_external_writes(backend: ContractSemiAutoBackend) -> None:
    for integration, count in backend.external_writes.items():
        if count:
            raise LiveEvalSafetyError(f"external write blocked: {integration}={count}")
    if backend.automatic_verify_link_merge:
        raise LiveEvalSafetyError("automatic verify/link/merge blocked")


def assert_hold_scenario_no_send(
    *,
    scenario: ProfileScenario,
    sends: int,
    adapter_invocations: int,
) -> None:
    if scenario.expected_send_behavior in {"hold", "reject", "no_reply"}:
        if sends or adapter_invocations:
            raise LiveEvalSafetyError(
                f"unexpected send on {scenario.expected_send_behavior} scenario {scenario.scenario_id}"
            )


def abort_campaign(message: str) -> LiveEvalSafetyError:
    return LiveEvalSafetyError(message)
