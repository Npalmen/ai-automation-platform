"""Central action classification and authorization at the dispatch boundary."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.workflows.action_executor import SUPPORTED_ACTIONS
from app.workflows.tenant_automation import allows_direct_external_execution, resolve_automation_mode


class ActionEffect(str, Enum):
    EXTERNAL_WRITE = "external_write"
    INTERNAL_RECORD = "internal_record"
    INTERNAL_STUB = "internal_stub"


class ActionAuthorization(str, Enum):
    BLOCKED = "blocked"
    APPROVAL_REQUIRED = "approval_required"
    EXECUTION_ALLOWED = "execution_allowed"


@dataclass(frozen=True)
class ActionSpec:
    effect: ActionEffect
    integration: str | None = None


ACTION_REGISTRY: dict[str, ActionSpec] = {
    "send_customer_auto_reply": ActionSpec(effect=ActionEffect.EXTERNAL_WRITE, integration="google_mail"),
    "send_internal_handoff": ActionSpec(effect=ActionEffect.EXTERNAL_WRITE, integration="google_mail"),
    "send_email": ActionSpec(effect=ActionEffect.EXTERNAL_WRITE, integration="google_mail"),
    "create_monday_item": ActionSpec(effect=ActionEffect.EXTERNAL_WRITE, integration="monday"),
    "notify_slack": ActionSpec(effect=ActionEffect.EXTERNAL_WRITE, integration="slack"),
    "notify_teams": ActionSpec(effect=ActionEffect.INTERNAL_STUB, integration="teams"),
    "create_internal_task": ActionSpec(effect=ActionEffect.INTERNAL_RECORD, integration=None),
}


def classify_action(action_type: str | None) -> ActionSpec | None:
    if not action_type:
        return None
    return ACTION_REGISTRY.get(str(action_type))


def authorize_action(
    action_type: str | None,
    *,
    job_type: str,
    auto_actions: dict[str, Any] | None,
    risk_detected: bool,
    policy_decision: str | None,
    pre_authorized: bool = False,
) -> ActionAuthorization:
    """Authorize a single action at the final dispatch boundary."""
    spec = classify_action(action_type)
    if spec is None or action_type not in SUPPORTED_ACTIONS:
        return ActionAuthorization.BLOCKED

    if policy_decision in ("hold_for_review", "send_for_approval"):
        return ActionAuthorization.BLOCKED

    if spec.effect in (ActionEffect.INTERNAL_STUB, ActionEffect.INTERNAL_RECORD):
        return ActionAuthorization.EXECUTION_ALLOWED

    if pre_authorized:
        return ActionAuthorization.EXECUTION_ALLOWED

    if risk_detected:
        return ActionAuthorization.APPROVAL_REQUIRED

    mode = resolve_automation_mode(auto_actions, job_type)
    if allows_direct_external_execution(mode):
        return ActionAuthorization.EXECUTION_ALLOWED

    return ActionAuthorization.APPROVAL_REQUIRED


def apply_action_authorization(
    action: dict[str, Any],
    *,
    job_type: str,
    auto_actions: dict[str, Any] | None,
    risk_detected: bool,
    policy_decision: str | None,
    pre_authorized: bool = False,
) -> dict[str, Any]:
    """Return action dict annotated with authorization outcome for dispatch loop."""
    if action.get("_skip"):
        return action

    action_type = action.get("type")
    auth = authorize_action(
        action_type,
        job_type=job_type,
        auto_actions=auto_actions,
        risk_detected=risk_detected,
        policy_decision=policy_decision,
        pre_authorized=pre_authorized,
    )

    if auth == ActionAuthorization.BLOCKED:
        return {
            "type": action_type or "unknown",
            "_skip": True,
            "_skip_reason": "action_blocked",
        }

    if auth == ActionAuthorization.APPROVAL_REQUIRED:
        return {**action, "_needs_approval": True, "_authorization": auth.value}

    return {**action, "_authorization": auth.value}
