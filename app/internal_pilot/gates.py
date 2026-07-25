"""Safety gates for the internal live pilot inbox scope."""

from __future__ import annotations

from typing import Any

from app.admin.onboarding.integration_fingerprint import build_gmail_label_query
from app.internal_pilot.constants import (
    MAX_PILOT_BATCH_EMAILS,
    PILOT_GMAIL_LABEL_SCOPE,
    PILOT_GMAIL_QUERY,
    PILOT_TENANT_ID,
)


class PilotGateViolation(ValueError):
    """Raised when an inbox sync request violates internal pilot policy."""


def is_pilot_tenant(tenant_id: str) -> bool:
    return tenant_id == PILOT_TENANT_ID


def _pilot_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    return dict((settings or {}).get("internal_pilot") or {})


def pilot_live_scan_enabled(settings: dict[str, Any] | None) -> bool:
    return bool(_pilot_settings(settings).get("live_scan_enabled"))


def _scheduler_run_mode(settings: dict[str, Any] | None) -> str:
    scheduler = (settings or {}).get("scheduler") or {}
    operations = (settings or {}).get("operations") or {}
    if operations.get("paused"):
        return "paused"
    return str(scheduler.get("run_mode") or "manual")


def _auto_actions(settings: dict[str, Any] | None) -> dict[str, Any]:
    return dict((settings or {}).get("auto_actions") or {})


def validate_pilot_query(query: str | None) -> str:
    if not query or not str(query).strip():
        raise PilotGateViolation("pilot inbox sync requires an explicit scoped Gmail query")
    normalized = " ".join(str(query).strip().split())
    expected = PILOT_GMAIL_QUERY
    if normalized != expected:
        required_prefix = f"label:krowolf-{PILOT_GMAIL_LABEL_SCOPE}"
        if required_prefix not in normalized.lower():
            raise PilotGateViolation(
                f"pilot inbox sync query must use scoped label {required_prefix!r}"
            )
        if "is:unread" not in normalized.lower():
            raise PilotGateViolation("pilot inbox sync query must include is:unread")
    return normalized


def validate_pilot_batch_size(max_results: int) -> None:
    if max_results < 1:
        raise PilotGateViolation("max_results must be at least 1")
    if max_results > MAX_PILOT_BATCH_EMAILS:
        raise PilotGateViolation(
            f"max_results {max_results} exceeds pilot batch limit {MAX_PILOT_BATCH_EMAILS}"
        )


def validate_approval_first_auto_actions(settings: dict[str, Any] | None) -> None:
    for job_type, mode in _auto_actions(settings).items():
        if mode in (True, "auto", "full_auto"):
            raise PilotGateViolation(
                f"auto_actions[{job_type!r}] must not be full auto during internal pilot"
            )


def validate_no_automatic_gmail_replies(settings: dict[str, Any] | None) -> None:
    automation = (settings or {}).get("automation") or {}
    if automation.get("automatic_gmail_replies") is True:
        raise PilotGateViolation("automatic_gmail_replies must remain false during internal pilot")


def validate_scheduler_safe_for_live(settings: dict[str, Any] | None) -> None:
    mode = _scheduler_run_mode(settings)
    if mode == "scheduled":
        raise PilotGateViolation("scheduler must be manual or paused before pilot live scan")


def build_pilot_activation_snapshot(
    *,
    tenant_id: str,
    settings: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "is_pilot_tenant": is_pilot_tenant(tenant_id),
        "gmail_label_scope": PILOT_GMAIL_LABEL_SCOPE,
        "gmail_query": PILOT_GMAIL_QUERY,
        "max_batch_emails": MAX_PILOT_BATCH_EMAILS,
        "live_scan_enabled": pilot_live_scan_enabled(settings),
        "scheduler_run_mode": _scheduler_run_mode(settings),
        "auto_actions": _auto_actions(settings),
        "automatic_gmail_replies": bool(
            ((settings or {}).get("automation") or {}).get("automatic_gmail_replies")
        ),
        "external_action_writes_allowed": False,
        "approval_first_required": True,
    }


def enforce_pilot_inbox_gates(
    *,
    tenant_id: str,
    query: str | None,
    max_results: int,
    dry_run: bool,
    settings: dict[str, Any] | None,
) -> str | None:
    """Return normalized query for pilot tenant; no-op for other tenants."""
    if not is_pilot_tenant(tenant_id):
        return query

    normalized_query = validate_pilot_query(query)
    validate_pilot_batch_size(max_results)
    validate_approval_first_auto_actions(settings)
    validate_no_automatic_gmail_replies(settings)

    if dry_run:
        return normalized_query

    if not pilot_live_scan_enabled(settings):
        raise PilotGateViolation(
            "pilot live inbox sync is disabled; enable via internal_pilot.live_scan_enabled "
            "after operator approval"
        )
    validate_scheduler_safe_for_live(settings)
    return normalized_query


def enforce_pilot_scheduler_sync(
    *,
    tenant_id: str,
    settings: dict[str, Any] | None,
) -> None:
    if not is_pilot_tenant(tenant_id):
        return
    raise PilotGateViolation(
        "scheduled inbox sync is forbidden for internal pilot tenant; use manual scoped scan"
    )


def expected_label_query_for_scope(label_scope_slug: str) -> str:
    return build_gmail_label_query(label_scope_slug)
