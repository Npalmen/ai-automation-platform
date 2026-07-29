"""Read-only production runtime readiness for P1 operational restart."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.canonical_commit import resolve_canonical_commit
from app.production_pilot.config_snapshot import compute_snapshot_hash
from app.production_pilot.constants import MIGRATION_HEAD, PILOT_TENANT_ID, RELEASE_VERSION
from app.production_pilot.observability.constants import P1_RUNTIME_READINESS_SCHEMA_VERSION
from app.production_pilot.p1_activation import build_p1_tenant_record, validate_p1_tenant_record
from app.production_pilot.p1_readiness import build_p1_readiness
from app.production_pilot.stages import stage_capabilities
from app.repositories.postgres.oauth_credential_models import OAuthCredentialRecord
from app.repositories.postgres.tenant_config_models import TenantConfigRecord


def _check(name: str, ok: bool, *, detail: str, blocker: bool = False) -> dict[str, Any]:
    if ok:
        return {"name": name, "status": "pass", "detail": detail}
    status = "fail" if blocker else "warn"
    return {"name": name, "status": status, "detail": detail, "blocker": blocker}


def build_p1_runtime_readiness(
    db: Session,
    *,
    tenant_id: str,
    expected_runtime_sha: str | None = None,
    backup_reference: str | None = None,
    release_manifest_path: str = "storage/status/production-pilot/release-manifest.json",
    active_pilot_tenant_count: int = 1,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    blockers: list[str] = []
    runtime_sha = resolve_canonical_commit(explicit=expected_runtime_sha) or resolve_canonical_commit()

    manifest = {}
    manifest_path = Path(release_manifest_path)
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    checks.append(
        _check(
            "single_pilot_tenant",
            tenant_id == PILOT_TENANT_ID and active_pilot_tenant_count == 1,
            detail=f"tenant={tenant_id} active_count={active_pilot_tenant_count}",
            blocker=True,
        )
    )

    if expected_runtime_sha and runtime_sha:
        sha_ok = runtime_sha.startswith(expected_runtime_sha[:7]) or expected_runtime_sha.startswith(runtime_sha[:7])
        checks.append(
            _check(
                "runtime_sha_matches_release",
                sha_ok,
                detail=f"expected={expected_runtime_sha} actual={runtime_sha}",
                blocker=True,
            )
        )

    if manifest:
        checks.append(
            _check(
                "release_manifest_present",
                True,
                detail=manifest.get("release_version") or RELEASE_VERSION,
            )
        )
        checks.append(
            _check(
                "migration_head_matches",
                manifest.get("migration_head") == MIGRATION_HEAD,
                detail=f"manifest={manifest.get('migration_head')} code={MIGRATION_HEAD}",
                blocker=True,
            )
        )

    tenant_row = db.query(TenantConfigRecord).filter(TenantConfigRecord.tenant_id == tenant_id).first()
    settings = (tenant_row.settings if tenant_row else None) or build_p1_tenant_record()["settings"]
    record = build_p1_tenant_record()
    if tenant_row is not None:
        record = {
            "tenant_id": tenant_id,
            "settings": settings,
            "allowed_integrations": tenant_row.allowed_integrations or ["google_mail"],
            "activation_stage": (settings.get("production_pilot") or {}).get("activation_stage", "P1"),
        }
    p1_failures = validate_p1_tenant_record(record)
    checks.append(
        _check(
            "p1_config_valid",
            not p1_failures,
            detail="; ".join(p1_failures) if p1_failures else compute_snapshot_hash(settings)[:16],
            blocker=bool(p1_failures),
        )
    )

    oauth_row = (
        db.query(OAuthCredentialRecord)
        .filter(
            OAuthCredentialRecord.tenant_id == tenant_id,
            OAuthCredentialRecord.provider == "google_mail",
        )
        .first()
    )
    checks.append(
        _check(
            "gmail_oauth_present",
            oauth_row is not None,
            detail="credential row present (token not exposed)",
            blocker=oauth_row is None,
        )
    )

    caps = stage_capabilities("P1")
    checks.append(_check("gmail_reply_off", caps["gmail_reply_budget"] == 0, detail="reply budget 0", blocker=True))
    checks.append(_check("shadow_promotion_off", not caps["shadow_promotion"], detail="promotion OFF", blocker=True))
    checks.append(
        _check(
            "automatic_verify_link_merge_off",
            not caps["automatic_verify"] and not caps["automatic_customer_link"] and not caps["automatic_merge"],
            detail="verify/link/merge OFF",
            blocker=True,
        )
    )
    checks.append(_check("approvals_off", not caps["approvals"], detail="approvals OFF", blocker=True))
    checks.append(_check("sheets_monday_visma_off", not caps["sheets_monday_visma"], detail="blocked integrations", blocker=True))

    readiness = build_p1_readiness(runtime_sha=runtime_sha, backup_reference=backup_reference)
    checks.append(
        _check(
            "hermetic_p1_readiness",
            readiness.get("overall_status") == "ready_for_p1_activation",
            detail=readiness.get("overall_status", "unknown"),
            blocker=readiness.get("overall_status") != "ready_for_p1_activation",
        )
    )

    for check in checks:
        if check.get("blocker") and check["status"] == "fail":
            blockers.append(check["name"])

    return {
        "report_schema_version": P1_RUNTIME_READINESS_SCHEMA_VERSION,
        "tenant_id": tenant_id,
        "runtime_sha": runtime_sha,
        "expected_runtime_sha": expected_runtime_sha,
        "release_manifest_version": manifest.get("release_version") or RELEASE_VERSION,
        "config_hash": compute_snapshot_hash(settings),
        "backup_reference": backup_reference or manifest.get("backup_reference"),
        "rollback_target": manifest.get("rollback_target") or RELEASE_VERSION,
        "checks": checks,
        "blockers": blockers,
        "overall_status": "ready_for_operational_attach" if not blockers else "blocked",
        "oauth_token_exposed": False,
    }
