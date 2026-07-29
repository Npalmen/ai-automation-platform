"""P1 pre-activation readiness gates."""

from __future__ import annotations

from typing import Any

from app.production_pilot.config_snapshot import compute_snapshot_hash, verify_snapshot_hash
from app.production_pilot.constants import (
    P1_READINESS_SCHEMA_VERSION,
    PILOT_TENANT_ID,
    RELEASE_VERSION,
)
from app.production_pilot.status import PRODUCTION_PILOT_RELEASE_READY
from app.production_pilot.gates import (
    build_activation_snapshot,
    validate_approval_first_auto_actions,
    validate_blocked_integrations,
    validate_no_automatic_gmail_replies,
)
from app.production_pilot.p1_activation import build_p1_tenant_record, validate_p1_tenant_record
from app.production_pilot.release_manifest import build_release_manifest, validate_release_manifest
from app.production_pilot.stages import stage_capabilities


def _check(name: str, ok: bool, *, detail: str, blocker: bool = False) -> dict[str, Any]:
    if ok:
        return {"name": name, "status": "pass", "detail": detail}
    status = "fail" if blocker else "warn"
    return {"name": name, "status": status, "detail": detail, "blocker": blocker}


def build_p1_readiness(
    *,
    runtime_sha: str | None = None,
    backup_reference: str | None = None,
    p0_qualification_workflow: str = "30484065150",
    active_pilot_tenant_count: int = 1,
    oauth_valid: bool = True,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    blockers: list[str] = []

    manifest = build_release_manifest(
        activation_stage="P1",
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
    checks.append(
        _check(
            "p0_qualification_present",
            bool(p0_qualification_workflow),
            detail=f"{PRODUCTION_PILOT_RELEASE_READY}@{p0_qualification_workflow}",
            blocker=True,
        )
    )
    checks.append(
        _check(
            "single_pilot_tenant",
            active_pilot_tenant_count == 1,
            detail=f"active_pilot_tenants={active_pilot_tenant_count}",
            blocker=True,
        )
    )
    checks.append(
        _check(
            "pilot_tenant_id",
            PILOT_TENANT_ID == "TENANT_PRODUCTION_PILOT_01",
            detail=PILOT_TENANT_ID,
            blocker=True,
        )
    )
    checks.append(
        _check(
            "gmail_oauth_valid",
            oauth_valid,
            detail="pilot mailbox OAuth must be valid",
            blocker=not oauth_valid,
        )
    )
    checks.append(
        _check(
            "backup_reference_present",
            bool(backup_reference),
            detail=backup_reference or "missing backup reference",
            blocker=not bool(backup_reference),
        )
    )

    p1_record = build_p1_tenant_record()
    p1_failures = validate_p1_tenant_record(p1_record)
    checks.append(
        _check(
            "p1_config_valid",
            not p1_failures,
            detail="; ".join(p1_failures) if p1_failures else compute_snapshot_hash(p1_record["settings"])[:16],
            blocker=bool(p1_failures),
        )
    )

    settings = p1_record["settings"]
    for name, validator in (
        ("blocked_integrations", validate_blocked_integrations),
        ("approval_first_active", validate_approval_first_auto_actions),
        ("automatic_gmail_replies_disabled", validate_no_automatic_gmail_replies),
    ):
        ok = True
        detail = "ok"
        try:
            validator(settings)
        except Exception as exc:
            ok = False
            detail = str(exc)
        checks.append(_check(name, ok, detail=detail, blocker=True))

    caps = stage_capabilities("P1")
    checks.append(_check("shadow_promotion_off", not caps["shadow_promotion"], detail="shadow promotion OFF", blocker=True))
    checks.append(_check("approvals_off", not caps["approvals"], detail="approvals OFF", blocker=True))
    checks.append(_check("gmail_reply_budget_zero", caps["gmail_reply_budget"] == 0, detail="reply budget 0", blocker=True))
    checks.append(
        _check(
            "automatic_verify_link_merge_off",
            not caps["automatic_verify"] and not caps["automatic_customer_link"] and not caps["automatic_merge"],
            detail="verify/link/merge OFF",
            blocker=True,
        )
    )

    snapshot = settings.get("production_pilot", {}).get("config_snapshot")
    checks.append(
        _check(
            "config_snapshot_hash_valid",
            bool(snapshot and verify_snapshot_hash(snapshot)),
            detail="activation snapshot verified",
            blocker=not bool(snapshot and verify_snapshot_hash(snapshot)),
        )
    )

    for check in checks:
        if check.get("blocker") and check["status"] == "fail":
            blockers.append(check["name"])

    overall = "fail" if blockers else "ready_for_p1_activation"
    return {
        "report_schema_version": P1_READINESS_SCHEMA_VERSION,
        "release_version": RELEASE_VERSION,
        "runtime_sha": runtime_sha,
        "tenant_id": PILOT_TENANT_ID,
        "activation_stage": "P1",
        "activation_snapshot": build_activation_snapshot(tenant_id=PILOT_TENANT_ID, settings=settings),
        "config_hash": compute_snapshot_hash(settings),
        "release_manifest": manifest,
        "checks": checks,
        "blockers": blockers,
        "overall_status": overall,
    }
