"""Stage-aware safety gates for the production pilot tenant."""

from __future__ import annotations

from typing import Any

from app.production_pilot.constants import (
    BLOCKED_AUTO_MODES,
    BLOCKED_PILOT_INTEGRATIONS,
    PILOT_TENANT_ID,
)
from app.production_pilot.stages import current_activation_stage, stage_capabilities


class ProductionPilotGateViolation(ValueError):
    """Raised when production pilot policy blocks an action."""


def is_production_pilot_tenant(tenant_id: str) -> bool:
    return tenant_id == PILOT_TENANT_ID


def _scheduler_run_mode(settings: dict[str, Any] | None) -> str:
    scheduler = (settings or {}).get("scheduler") or {}
    operations = (settings or {}).get("operations") or {}
    if operations.get("paused"):
        return "paused"
    return str(scheduler.get("run_mode") or "manual")


def _auto_actions(settings: dict[str, Any] | None) -> dict[str, Any]:
    return dict((settings or {}).get("auto_actions") or {})


def _allowed_integrations(settings: dict[str, Any] | None) -> set[str]:
    return {str(item) for item in ((settings or {}).get("allowed_integrations") or [])}


def validate_blocked_integrations(settings: dict[str, Any] | None) -> None:
    blocked = _allowed_integrations(settings) & BLOCKED_PILOT_INTEGRATIONS
    if blocked:
        raise ProductionPilotGateViolation(
            f"blocked integrations for production pilot: {sorted(blocked)}"
        )


def validate_approval_first_auto_actions(settings: dict[str, Any] | None) -> None:
    for job_type, mode in _auto_actions(settings).items():
        if mode in BLOCKED_AUTO_MODES:
            raise ProductionPilotGateViolation(
                f"auto_actions[{job_type!r}] must not be full auto during production pilot"
            )


def validate_stage_scheduler(settings: dict[str, Any] | None) -> None:
    caps = stage_capabilities(current_activation_stage(settings))
    if caps["scheduler_automatic"] and _scheduler_run_mode(settings) == "scheduled":
        return
    if _scheduler_run_mode(settings) == "scheduled":
        raise ProductionPilotGateViolation(
            "scheduler must be manual or paused during production pilot"
        )


def validate_no_automatic_gmail_replies(settings: dict[str, Any] | None) -> None:
    caps = stage_capabilities(current_activation_stage(settings))
    if caps["automatic_gmail"]:
        return
    automation = (settings or {}).get("automation") or {}
    if automation.get("automatic_gmail_replies") is True:
        raise ProductionPilotGateViolation("automatic_gmail_replies must remain false")


def validate_gmail_intake_allowed(settings: dict[str, Any] | None, *, dry_run: bool) -> None:
    if dry_run:
        return
    caps = stage_capabilities(current_activation_stage(settings))
    intake_enabled = bool(((settings or {}).get("production_pilot_intake") or {}).get("enabled"))
    if not caps["gmail_intake"] and intake_enabled:
        raise ProductionPilotGateViolation(
            "gmail intake is disabled at current activation stage; enable only after P1 authorization"
        )
    if not caps["gmail_intake"]:
        raise ProductionPilotGateViolation(
            "gmail intake is disabled at current activation stage"
        )


def validate_approvals_allowed(settings: dict[str, Any] | None) -> None:
    caps = stage_capabilities(current_activation_stage(settings))
    if not caps["approvals"]:
        raise ProductionPilotGateViolation("approvals are disabled at current activation stage")


def validate_external_write_budget(
    settings: dict[str, Any] | None,
    *,
    gmail_replies: int = 0,
    non_gmail_writes: int = 0,
) -> None:
    caps = stage_capabilities(current_activation_stage(settings))
    reply_budget = caps.get("gmail_reply_budget")
    non_gmail_budget = caps.get("non_gmail_write_budget")
    if reply_budget is not None and gmail_replies > reply_budget:
        raise ProductionPilotGateViolation(
            f"gmail reply budget exceeded ({gmail_replies} > {reply_budget})"
        )
    if non_gmail_budget is not None and non_gmail_writes > non_gmail_budget:
        raise ProductionPilotGateViolation(
            f"non-gmail write budget exceeded ({non_gmail_writes} > {non_gmail_budget})"
        )


def enforce_production_pilot_inbox_gates(
    *,
    tenant_id: str,
    dry_run: bool,
    settings: dict[str, Any] | None,
) -> None:
    if not is_production_pilot_tenant(tenant_id):
        return
    validate_blocked_integrations(settings)
    validate_approval_first_auto_actions(settings)
    validate_no_automatic_gmail_replies(settings)
    validate_stage_scheduler(settings)
    validate_gmail_intake_allowed(settings, dry_run=dry_run)


def enforce_production_pilot_scheduler_sync(
    *,
    tenant_id: str,
    settings: dict[str, Any] | None,
) -> None:
    if not is_production_pilot_tenant(tenant_id):
        return
    validate_stage_scheduler(settings)
    caps = stage_capabilities(current_activation_stage(settings))
    if not caps["scheduler_automatic"]:
        raise ProductionPilotGateViolation(
            "scheduled inbox sync is forbidden for production pilot tenant"
        )


def build_activation_snapshot(
    *,
    tenant_id: str,
    settings: dict[str, Any] | None,
) -> dict[str, Any]:
    stage = current_activation_stage(settings)
    caps = stage_capabilities(stage)
    return {
        "tenant_id": tenant_id,
        "is_production_pilot_tenant": is_production_pilot_tenant(tenant_id),
        "activation_stage": stage,
        "capabilities": caps,
        "scheduler_run_mode": _scheduler_run_mode(settings),
        "automatic_gmail_replies": bool(
            ((settings or {}).get("automation") or {}).get("automatic_gmail_replies")
        ),
        "allowed_integrations": sorted(_allowed_integrations(settings)),
        "external_action_writes_allowed": caps["non_gmail_write_budget"] not in (0, None)
        or caps["gmail_reply_budget"] not in (0, None),
    }
