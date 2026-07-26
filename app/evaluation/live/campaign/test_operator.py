"""Fail-closed test operator for semi-automatic live-eval campaigns."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from app.evaluation.live.campaign.operator_contract import OperatorPlanStep
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
    action_type: str
    delivery_type: str
    action_operation_id: str | None
    recipient_redacted: str
    created_at: str | None = None


@dataclass(frozen=True)
class OperatorActionResult:
    action: str
    approval_id: str
    action_type: str
    action_operation_id: str | None
    http_status: int
    changed: bool | None
    idempotent: bool
    conflict: bool
    body: dict[str, Any]


@dataclass
class OperatorExecutionContext:
    results: list[OperatorActionResult] = field(default_factory=list)
    target_action_operation_id: str | None = None
    target_approval_id: str | None = None
    target_action_type: str | None = None
    secondary_operation_ids: dict[str, str] = field(default_factory=dict)
    touched_approval_ids: list[str] = field(default_factory=list)


def _headers(*, admin_api_key: str, tenant_id: str) -> dict[str, str]:
    return {
        "X-Admin-API-Key": admin_api_key,
        "X-Tenant-ID": tenant_id,
    }


def _redact_recipient(value: str) -> str:
    text = (value or "").strip()
    if "@" not in text:
        return text or "(none)"
    local, domain = text.split("@", 1)
    if len(local) <= 2:
        masked_local = "*"
    else:
        masked_local = f"{local[:2]}***"
    return f"{masked_local}@{domain}"


def _parse_pending_approval(row: dict[str, Any]) -> PendingApproval:
    request_payload = dict(row.get("request_payload") or {})
    delivery_payload = dict(row.get("delivery_payload") or {})
    action_type = str(
        request_payload.get("action_type")
        or delivery_payload.get("type")
        or ""
    )
    delivery_type = str(delivery_payload.get("type") or action_type)
    recipient = str(
        delivery_payload.get("to")
        or delivery_payload.get("item_name")
        or delivery_payload.get("channel")
        or ""
    )
    return PendingApproval(
        approval_id=str(row.get("approval_id") or ""),
        state=str(row.get("state") or ""),
        next_on_approve=row.get("next_on_approve"),
        action_type=action_type,
        delivery_type=delivery_type,
        action_operation_id=request_payload.get("action_operation_id"),
        recipient_redacted=_redact_recipient(recipient),
        created_at=row.get("created_at"),
    )


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
    if not outcome.operator_plan:
        raise LiveEvalSafetyError(
            f"test operator blocked: scenario {scenario.scenario_id!r} missing operator_plan"
        )


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
    return [_parse_pending_approval(row) for row in items]


def match_target_approval(
    pending: list[PendingApproval],
    step: OperatorPlanStep,
    *,
    locked_operation_id: str | None = None,
) -> PendingApproval:
    """Match exactly one pending approval for an operator plan step."""
    if locked_operation_id:
        locked_rows = [
            row for row in pending
            if row.action_operation_id == locked_operation_id
            and row.action_type == step.action_type
            and row.delivery_type == step.resolved_delivery_type
        ]
        if locked_rows:
            by_approval_id: dict[str, PendingApproval] = {}
            for row in locked_rows:
                existing = by_approval_id.get(row.approval_id)
                if existing is None or existing.state == "pending":
                    by_approval_id[row.approval_id] = row
            locked_rows = list(by_approval_id.values())
        if len(locked_rows) == 1:
            return locked_rows[0]
        if len(locked_rows) > 1:
            raise LiveEvalSafetyError("ambiguous_target_approval")

    candidates = [
        row for row in pending
        if row.state == "pending"
        and row.next_on_approve in ("action_execute", "email_send")
        and row.action_type == step.action_type
        and row.delivery_type == step.resolved_delivery_type
    ]
    if locked_operation_id:
        locked_pending = [
            row for row in candidates
            if row.action_operation_id == locked_operation_id
        ]
        if len(locked_pending) == 1:
            return locked_pending[0]
        if len(locked_pending) > 1:
            raise LiveEvalSafetyError("ambiguous_target_approval")
        if candidates and all(row.action_operation_id != locked_operation_id for row in candidates):
            raise LiveEvalSafetyError("target_approval_not_found")
    if not candidates:
        raise LiveEvalSafetyError("target_approval_not_found")
    if len(candidates) > 1:
        raise LiveEvalSafetyError("ambiguous_target_approval")
    return candidates[0]


def _parse_action_result(
    *,
    action: str,
    approval: PendingApproval,
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
        approval_id=approval.approval_id,
        action_type=approval.action_type,
        action_operation_id=approval.action_operation_id,
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
    approval: PendingApproval,
    reason: str = "testbot semi-auto approve",
    timeout: float = 60.0,
) -> OperatorActionResult:
    response = httpx.post(
        f"{base_url.rstrip('/')}/approvals/{approval.approval_id}/approve",
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
    return _parse_action_result(action="approve", approval=approval, response=response)


def reject_approval(
    *,
    base_url: str,
    admin_api_key: str,
    tenant_id: str,
    approval: PendingApproval,
    reason: str = "testbot semi-auto reject",
    timeout: float = 60.0,
) -> OperatorActionResult:
    response = httpx.post(
        f"{base_url.rstrip('/')}/approvals/{approval.approval_id}/reject",
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
    return _parse_action_result(action="reject", approval=approval, response=response)


def _expected_statuses_for_step(step: OperatorPlanStep) -> set[int]:
    if step.expected_http_status is not None:
        return {step.expected_http_status}
    if step.expected_result == "idempotent":
        return {200, 201, 409}
    if step.decision == "approve":
        return {200, 201}
    return {200, 201}


def assert_secondary_approvals(
    *,
    approvals: list[PendingApproval],
    outcome: SemiAutomaticExpectedOutcome,
    touched_approval_ids: set[str],
    decision_records: list[dict[str, Any]],
) -> list[str]:
    violations: list[str] = []
    for secondary in outcome.secondary_approvals:
        matches = [
            row for row in approvals
            if row.action_type == secondary.action_type
            and row.delivery_type == secondary.resolved_delivery_type
        ]
        if not matches:
            if secondary.expected_final_state == "not_materialized":
                continue
            violations.append(
                f"secondary approval {secondary.action_type!r} not found"
            )
            continue
        if len(matches) > 1:
            violations.append(
                f"ambiguous secondary approval {secondary.action_type!r}"
            )
            continue
        row = matches[0]
        if row.approval_id in touched_approval_ids:
            violations.append(
                f"test operator touched secondary approval {secondary.action_type!r}"
            )
        if secondary.expected_final_state == "remain_pending":
            if row.state != "pending":
                violations.append(
                    f"secondary {secondary.action_type!r} expected remain_pending, "
                    f"got state={row.state!r}"
                )
            op_id = row.action_operation_id
            if op_id:
                for record_type in (
                    "action_approval_resolution",
                    "execution_intent",
                    "execution_outcome",
                ):
                    count = sum(
                        1
                        for rec in decision_records
                        if rec.get("record_type") == record_type
                        and rec.get("action_operation_id") == op_id
                    )
                    if count:
                        violations.append(
                            f"secondary {secondary.action_type!r} must not have "
                            f"{record_type}, got {count}"
                        )
    return violations


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
) -> OperatorExecutionContext:
    """Run contract-authorized operator actions for a semi-auto scenario."""
    ctx = OperatorExecutionContext()
    if outcome.is_negative_hold or not outcome.allow_operator_action:
        return ctx

    _validate_operator_guards(
        tenant_id=tenant_id,
        scenario=scenario,
        evaluation_run_id=evaluation_run_id,
        outcome=outcome,
        expected_sender=expected_sender,
        reply_budget_remaining=reply_budget_remaining,
    )

    locked_operation_id: str | None = None
    locked_approval_id: str | None = None

    for index, step in enumerate(outcome.operator_plan):
        pending = [
            row for row in list_job_approvals(
                base_url=base_url,
                admin_api_key=admin_api_key,
                tenant_id=tenant_id,
                job_id=job_id,
            )
            if row.state == "pending" or (
                locked_approval_id and row.approval_id == locked_approval_id
            )
        ]
        if index == 0:
            target = match_target_approval(pending, step)
            locked_operation_id = target.action_operation_id
            locked_approval_id = target.approval_id
            ctx.target_action_operation_id = locked_operation_id
            ctx.target_approval_id = locked_approval_id
            ctx.target_action_type = target.action_type
            for sec in outcome.secondary_approvals:
                sec_rows = [
                    row for row in pending
                    if row.action_type == sec.action_type
                    and row.delivery_type == sec.resolved_delivery_type
                ]
                if len(sec_rows) == 1 and sec_rows[0].action_operation_id:
                    ctx.secondary_operation_ids[sec.action_type] = (
                        sec_rows[0].action_operation_id
                    )
        else:
            if not locked_operation_id or not locked_approval_id:
                raise LiveEvalSafetyError("operator plan missing locked target operation")
            target = match_target_approval(
                pending,
                step,
                locked_operation_id=locked_operation_id,
            )
            if target.approval_id != locked_approval_id:
                raise LiveEvalSafetyError(
                    "duplicate/stale step must reuse same target approval"
                )

        if step.decision == "approve":
            result = approve_approval(
                base_url=base_url,
                admin_api_key=admin_api_key,
                tenant_id=tenant_id,
                approval=target,
                reason=(
                    "testbot duplicate approve"
                    if step.expected_result == "idempotent"
                    else "testbot semi-auto approve"
                ),
            )
        elif step.decision == "reject":
            result = reject_approval(
                base_url=base_url,
                admin_api_key=admin_api_key,
                tenant_id=tenant_id,
                approval=target,
            )
        else:
            raise LiveEvalSafetyError(f"unsupported operator decision {step.decision!r}")

        ctx.results.append(result)
        ctx.touched_approval_ids.append(target.approval_id)

        allowed = _expected_statuses_for_step(step)
        if result.http_status not in allowed:
            raise LiveEvalSafetyError(
                f"test operator {step.decision} failed: status={result.http_status}, "
                f"expected one of {sorted(allowed)}"
            )
        if step.expected_result == "idempotent" and not (
            result.idempotent or result.conflict
        ):
            raise LiveEvalSafetyError("duplicate approve must be idempotent or conflict-safe")
        if step.expected_http_status == 409 and not result.conflict:
            raise LiveEvalSafetyError("stale approve must return conflict")

    return ctx
