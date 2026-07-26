"""Fail-closed test operator for semi-automatic live-eval campaigns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.evaluation.live.campaign.schemas import CampaignScenario
from app.evaluation.live.campaign.semi_automatic_expected_outcomes import (
    SemiAutomaticExpectedOutcome,
)
from app.evaluation.live.errors import LiveEvalSafetyError

TESTBOT_OPERATOR_ACTOR = "testbot-operator"
TESTBOT_OPERATOR_CHANNEL = "live_eval_test_operator"


@dataclass(frozen=True)
class PendingApproval:
    approval_id: str
    state: str
    next_on_approve: str | None


@dataclass(frozen=True)
class OperatorActionResult:
    action: str
    approval_id: str
    http_status: int
    changed: bool | None
    idempotent: bool
    conflict: bool
    body: dict[str, Any]


def _headers(*, admin_api_key: str, tenant_id: str) -> dict[str, str]:
    return {
        "X-Admin-API-Key": admin_api_key,
        "X-Tenant-ID": tenant_id,
    }


def _validate_operator_guards(
    *,
    tenant_id: str,
    scenario: CampaignScenario,
    evaluation_run_id: str,
    outcome: SemiAutomaticExpectedOutcome,
    expected_sender: str,
    reply_budget_remaining: int,
) -> None:
    if tenant_id != "TENANT_LIVE_EVAL":
        raise LiveEvalSafetyError(f"test operator blocked: tenant {tenant_id!r}")
    if not evaluation_run_id:
        raise LiveEvalSafetyError("test operator blocked: missing evaluation_run_id")
    if outcome.is_negative_hold or not outcome.allow_operator_action:
        raise LiveEvalSafetyError(
            f"test operator blocked: scenario {scenario.scenario_id!r} forbids operator action"
        )
    if outcome.expected_reply and reply_budget_remaining <= 0:
        raise LiveEvalSafetyError("test operator blocked: reply budget exhausted")
    if not expected_sender:
        raise LiveEvalSafetyError("test operator blocked: missing expected_sender allowlist")


def list_job_approvals(
    *,
    base_url: str,
    admin_api_key: str,
    tenant_id: str,
    job_id: str,
    timeout: float = 30.0,
) -> list[PendingApproval]:
    response = httpx.get(
        f"{base_url.rstrip('/')}/jobs/{job_id}/approvals",
        headers=_headers(admin_api_key=admin_api_key, tenant_id=tenant_id),
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    items = payload.get("items") or []
    return [
        PendingApproval(
            approval_id=str(row.get("approval_id") or ""),
            state=str(row.get("state") or ""),
            next_on_approve=row.get("next_on_approve"),
        )
        for row in items
    ]


def _parse_action_result(
    *,
    action: str,
    approval_id: str,
    response: httpx.Response,
) -> OperatorActionResult:
    body: dict[str, Any] = {}
    try:
        body = response.json()
    except ValueError:
        body = {}

    conflict = response.status_code in (409, 400)
    idempotent = bool(body.get("idempotent")) if isinstance(body, dict) else False
    changed = body.get("changed") if isinstance(body, dict) else None

    return OperatorActionResult(
        action=action,
        approval_id=approval_id,
        http_status=response.status_code,
        changed=changed if isinstance(changed, bool) else None,
        idempotent=idempotent,
        conflict=conflict,
        body=body,
    )


def approve_approval(
    *,
    base_url: str,
    admin_api_key: str,
    tenant_id: str,
    approval_id: str,
    reason: str = "testbot semi-auto approve",
    timeout: float = 60.0,
) -> OperatorActionResult:
    response = httpx.post(
        f"{base_url.rstrip('/')}/approvals/{approval_id}/approve",
        headers=_headers(admin_api_key=admin_api_key, tenant_id=tenant_id),
        json={
            "actor": TESTBOT_OPERATOR_ACTOR,
            "channel": TESTBOT_OPERATOR_CHANNEL,
            "note": reason,
        },
        timeout=timeout,
    )
    if response.status_code >= 500:
        response.raise_for_status()
    return _parse_action_result(action="approve", approval_id=approval_id, response=response)


def reject_approval(
    *,
    base_url: str,
    admin_api_key: str,
    tenant_id: str,
    approval_id: str,
    reason: str = "testbot semi-auto reject",
    timeout: float = 60.0,
) -> OperatorActionResult:
    response = httpx.post(
        f"{base_url.rstrip('/')}/approvals/{approval_id}/reject",
        headers=_headers(admin_api_key=admin_api_key, tenant_id=tenant_id),
        json={
            "actor": TESTBOT_OPERATOR_ACTOR,
            "channel": TESTBOT_OPERATOR_CHANNEL,
            "note": reason,
        },
        timeout=timeout,
    )
    if response.status_code >= 500:
        response.raise_for_status()
    return _parse_action_result(action="reject", approval_id=approval_id, response=response)


def execute_test_operator_actions(
    *,
    base_url: str,
    admin_api_key: str,
    tenant_id: str,
    scenario: CampaignScenario,
    evaluation_run_id: str,
    job_id: str,
    outcome: SemiAutomaticExpectedOutcome,
    expected_sender: str,
    reply_budget_remaining: int,
) -> list[OperatorActionResult]:
    """Run contract-authorized operator actions for a semi-auto scenario."""
    if outcome.is_negative_hold or not outcome.allow_operator_action:
        return []

    _validate_operator_guards(
        tenant_id=tenant_id,
        scenario=scenario,
        evaluation_run_id=evaluation_run_id,
        outcome=outcome,
        expected_sender=expected_sender,
        reply_budget_remaining=reply_budget_remaining,
    )

    pending = [
        row for row in list_job_approvals(
            base_url=base_url,
            admin_api_key=admin_api_key,
            tenant_id=tenant_id,
            job_id=job_id,
        )
        if row.state == "pending"
    ]
    if not pending:
        raise LiveEvalSafetyError(
            f"test operator blocked: no pending approval for job {job_id!r}"
        )
    if len(pending) != 1:
        raise LiveEvalSafetyError(
            f"test operator blocked: expected exactly one pending approval, got {len(pending)}"
        )

    approval_id = pending[0].approval_id
    results: list[OperatorActionResult] = []

    if outcome.operator_action == "approve":
        first = approve_approval(
            base_url=base_url,
            admin_api_key=admin_api_key,
            tenant_id=tenant_id,
            approval_id=approval_id,
        )
        results.append(first)
        if first.http_status not in (200, 201):
            raise LiveEvalSafetyError(
                f"test operator approve failed: status={first.http_status}"
            )
        if outcome.expect_duplicate_idempotent:
            second = approve_approval(
                base_url=base_url,
                admin_api_key=admin_api_key,
                tenant_id=tenant_id,
                approval_id=approval_id,
                reason="testbot duplicate approve",
            )
            results.append(second)
            if second.http_status not in (200, 201, 409):
                raise LiveEvalSafetyError(
                    f"duplicate approve unexpected status={second.http_status}"
                )
        return results

    if outcome.operator_action == "reject":
        first = reject_approval(
            base_url=base_url,
            admin_api_key=admin_api_key,
            tenant_id=tenant_id,
            approval_id=approval_id,
        )
        results.append(first)
        if first.http_status not in (200, 201):
            raise LiveEvalSafetyError(
                f"test operator reject failed: status={first.http_status}"
            )
        if outcome.expect_stale_conflict:
            stale = approve_approval(
                base_url=base_url,
                admin_api_key=admin_api_key,
                tenant_id=tenant_id,
                approval_id=approval_id,
                reason="testbot stale approve attempt",
            )
            results.append(stale)
            if not stale.conflict and not stale.idempotent:
                raise LiveEvalSafetyError(
                    "stale approve must be denied without action"
                )
        return results

    raise LiveEvalSafetyError(
        f"unsupported operator_action {outcome.operator_action!r}"
    )
