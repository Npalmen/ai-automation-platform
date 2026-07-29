"""Production pilot readiness and P0 release-ready status."""

from __future__ import annotations

from typing import Any

from app.core.settings import get_settings
from app.production_pilot.config_snapshot import compute_snapshot_hash, verify_snapshot_hash
from app.production_pilot.constants import (
    PILOT_TENANT_ID,
    READINESS_SCHEMA_VERSION,
    RELEASE_VERSION,
)
from app.production_pilot.gates import (
    build_activation_snapshot,
    validate_approval_first_auto_actions,
    validate_blocked_integrations,
    validate_no_automatic_gmail_replies,
    validate_stage_scheduler,
)
from app.production_pilot.kill_switches import apply_p0_baseline
from app.production_pilot.release_manifest import build_release_manifest, validate_release_manifest
from app.production_pilot.stages import current_activation_stage


def _check(name: str, ok: bool, *, detail: str, blocker: bool = False) -> dict[str, Any]:
    if ok:
        return {"name": name, "status": "pass", "detail": detail}
    status = "fail" if blocker else "warn"
    return {"name": name, "status": status, "detail": detail, "blocker": blocker}


def build_production_pilot_readiness(
    *,
    tenant_id: str,
    settings: dict[str, Any] | None,
    runtime_sha: str | None = None,
    backup_reference: str | None = None,
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

    stage = current_activation_stage(settings)
    checks.append(
        _check(
            "activation_stage_p0",
            stage == "P0",
            detail=f"stage={stage}",
            blocker=True,
        )
    )

    for name, validator in (
        ("blocked_integrations", validate_blocked_integrations),
        ("approval_first_active", validate_approval_first_auto_actions),
        ("automatic_gmail_replies_disabled", validate_no_automatic_gmail_replies),
        ("scheduler_paused", validate_stage_scheduler),
    ):
        ok = True
        detail = "ok"
        try:
            validator(settings)
        except Exception as exc:
            ok = False
            detail = str(exc)
        checks.append(_check(name, ok, detail=detail, blocker=True))

    intake_enabled = bool(((settings or {}).get("production_pilot_intake") or {}).get("enabled"))
    checks.append(
        _check(
            "gmail_intake_disabled",
            not intake_enabled,
            detail="P0 requires gmail intake OFF",
            blocker=True,
        )
    )

    app_settings = get_settings()
    checks.append(
        _check(
            "global_scheduler_pause_available",
            hasattr(app_settings, "PRODUCTION_PILOT_GLOBAL_SCHEDULER_PAUSE"),
            detail="global scheduler pause env flag present",
        )
    )
    checks.append(
        _check(
            "backup_reference_present",
            bool(backup_reference),
            detail=backup_reference or "backup reference required before migration/deploy",
            blocker=not bool(backup_reference),
        )
    )

    manifest = build_release_manifest(
        activation_stage="P0",
        backup_reference=backup_reference,
        commit_sha=runtime_sha,
    )
    manifest_failures = validate_release_manifest(manifest)
    checks.append(
        _check(
            "release_manifest_valid",
            not manifest_failures,
            detail="; ".join(manifest_failures) if manifest_failures else manifest["manifest_hash"][:16],
            blocker=bool(manifest_failures),
        )
    )

    snapshot = ((settings or {}).get("production_pilot") or {}).get("config_snapshot")
    snapshot_ok = bool(snapshot and verify_snapshot_hash(snapshot))
    checks.append(
        _check(
            "config_snapshot_hash_valid",
            snapshot_ok,
            detail="baseline snapshot hash verified" if snapshot_ok else "missing or invalid snapshot",
            blocker=not snapshot_ok,
        )
    )

    for check in checks:
        if check.get("blocker") and check["status"] == "fail":
            blockers.append(check["name"])

    overall = "fail" if blockers else "ready_for_p0_preflight"
    return {
        "report_schema_version": READINESS_SCHEMA_VERSION,
        "release_version": RELEASE_VERSION,
        "runtime_sha": runtime_sha,
        "tenant_id": tenant_id,
        "activation_stage": stage,
        "activation_snapshot": build_activation_snapshot(tenant_id=tenant_id, settings=settings),
        "config_hash": compute_snapshot_hash(settings),
        "release_manifest": manifest,
        "checks": checks,
        "blockers": blockers,
        "overall_status": overall,
        "kill_switches": list(
            (
                "global_scheduler_pause",
                "pause_tenant_automation",
                "disable_scheduler",
                "disable_gmail_replies",
                "disable_shadow_intake",
                "disable_shadow_matching",
                "disable_shadow_promotion",
                "disable_gmail_intake",
                "enable_read_only_operator_mode",
                "deployment_rollback",
                "database_restore",
            )
        ),
        "rollback_commands": {
            "pause_automation": f"POST /admin/support/{PILOT_TENANT_ID}/pause-automation",
            "disable_scheduler": f"POST /admin/support/{PILOT_TENANT_ID}/disable-scheduler",
            "restore_snapshot": "python scripts/production_pilot/restore_baseline.py --execute",
        },
    }


def p0_baseline_settings() -> dict[str, Any]:
    return apply_p0_baseline()
