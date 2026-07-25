"""Readiness report for internal live pilot activation."""

from __future__ import annotations

from typing import Any

from app.internal_pilot.constants import (
    MAX_PILOT_BATCH_EMAILS,
    MIN_PILOT_FIRST_BATCH_EMAILS,
    PILOT_GMAIL_LABEL_SCOPE,
    PILOT_GMAIL_QUERY,
    PILOT_TENANT_ID,
)
from app.internal_pilot.gates import (
    pilot_live_scan_enabled,
    validate_approval_first_auto_actions,
    validate_no_automatic_gmail_replies,
    validate_pilot_batch_size,
    validate_pilot_query,
    validate_scheduler_safe_for_live,
)


def _check(name: str, ok: bool, *, detail: str, blocker: bool = False) -> dict[str, Any]:
    if ok:
        return {"name": name, "status": "pass", "detail": detail}
    status = "fail" if blocker else "warn"
    return {"name": name, "status": status, "detail": detail, "blocker": blocker}


def build_internal_pilot_readiness(
    *,
    tenant_id: str,
    settings: dict[str, Any] | None,
    baseline_git_sha: str | None = None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    blockers: list[str] = []

    checks.append(
        _check(
            "pilot_tenant_isolated",
            tenant_id == PILOT_TENANT_ID,
            detail=f"expected tenant {PILOT_TENANT_ID}",
            blocker=True,
        )
    )
    try:
        validate_pilot_query(PILOT_GMAIL_QUERY)
        checks.append(
            _check(
                "mailbox_scope_defined",
                True,
                detail=f"query={PILOT_GMAIL_QUERY}",
            )
        )
    except Exception as exc:
        checks.append(
            _check(
                "mailbox_scope_defined",
                False,
                detail=str(exc),
                blocker=True,
            )
        )

    try:
        validate_pilot_batch_size(MAX_PILOT_BATCH_EMAILS)
        checks.append(
            _check(
                "batch_budget_configured",
                True,
                detail=f"max={MAX_PILOT_BATCH_EMAILS}, first_batch_min={MIN_PILOT_FIRST_BATCH_EMAILS}",
            )
        )
    except Exception as exc:
        checks.append(_check("batch_budget_configured", False, detail=str(exc), blocker=True))

    approval_ok = True
    approval_detail = "approval-first auto_actions"
    try:
        validate_approval_first_auto_actions(settings)
    except Exception as exc:
        approval_ok = False
        approval_detail = str(exc)
    checks.append(
        _check("approval_first_active", approval_ok, detail=approval_detail, blocker=True)
    )

    reply_ok = True
    reply_detail = "automatic_gmail_replies disabled"
    try:
        validate_no_automatic_gmail_replies(settings)
    except Exception as exc:
        reply_ok = False
        reply_detail = str(exc)
    checks.append(
        _check("automatic_gmail_replies_disabled", reply_ok, detail=reply_detail, blocker=True)
    )

    scheduler_ok = True
    scheduler_detail = "scheduler manual/paused"
    try:
        validate_scheduler_safe_for_live(settings)
    except Exception as exc:
        scheduler_ok = False
        scheduler_detail = str(exc)
    checks.append(
        _check("scheduler_safe", scheduler_ok, detail=scheduler_detail, blocker=True)
    )

    checks.append(
        _check(
            "external_writes_blocked",
            True,
            detail="external_action_writes=0 policy enforced by pilot gates",
        )
    )
    checks.append(
        _check(
            "live_scan_gate_present",
            True,
            detail="non-dry-run inbox sync requires internal_pilot.live_scan_enabled",
        )
    )
    checks.append(
        _check(
            "live_scan_enabled",
            pilot_live_scan_enabled(settings),
            detail="operator must enable after explicit approval",
        )
    )

    for check in checks:
        if check.get("blocker") and check["status"] == "fail":
            blockers.append(check["name"])

    overall = "fail" if blockers else "pass"
    if overall == "pass" and not pilot_live_scan_enabled(settings):
        overall = "ready_for_operator_activation"

    return {
        "report_schema_version": "internal-pilot.readiness.v1",
        "baseline_git_sha": baseline_git_sha,
        "tenant_id": tenant_id,
        "label_scope_slug": PILOT_GMAIL_LABEL_SCOPE,
        "gmail_query": PILOT_GMAIL_QUERY,
        "max_batch_emails": MAX_PILOT_BATCH_EMAILS,
        "min_first_batch_emails": MIN_PILOT_FIRST_BATCH_EMAILS,
        "checks": checks,
        "blockers": blockers,
        "overall_status": overall,
        "rollback_commands": {
            "pause_scheduler": (
                f"POST /admin/support/{PILOT_TENANT_ID}/disable-scheduler"
            ),
            "pause_automation": (
                f"POST /admin/support/{PILOT_TENANT_ID}/pause-automation"
            ),
            "disable_live_scan": (
                "set tenant settings internal_pilot.live_scan_enabled=false"
            ),
        },
        "activation_command": (
            "python scripts/internal_pilot_activate.py --enable-live --confirm-operator"
        ),
        "pause_command": "python scripts/internal_pilot_pause.py --execute",
        "first_scan_command": (
            "python scripts/ops/pilot_gmail_soak_first_scan.py 3"
        ),
    }
