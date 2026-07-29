"""Release manifest builder and validator."""

from __future__ import annotations

import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.settings import get_settings
from app.evaluation.regression.feature_flags import RISK_FLAGS
from app.production_pilot.constants import (
    CAPABILITY_REGISTRY_VERSION,
    MANIFEST_SCHEMA_VERSION,
    MIGRATION_HEAD,
    PILOT_TENANT_ID,
    QUALIFICATION_REGISTRY_VERSION,
    RELEASE_VERSION,
)


def canonical_json_bytes(payload: Any) -> bytes:
    import json

    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def _frontend_build_hash() -> str | None:
    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist" / "assets"
    if not dist.is_dir():
        return None
    parts = sorted(path.name for path in dist.iterdir() if path.is_file())
    if not parts:
        return None
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def feature_flag_defaults() -> dict[str, bool]:
    settings = get_settings()
    return {flag: bool(getattr(settings, flag, False)) for flag in RISK_FLAGS}


def build_release_manifest(
    *,
    activation_stage: str = "P0",
    docker_image_digest: str | None = None,
    rollback_target: str | None = None,
    backup_reference: str | None = None,
    operator_approval_id: str | None = None,
    commit_sha: str | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "release_version": RELEASE_VERSION,
        "commit_sha": commit_sha or _git_sha(),
        "migration_head": MIGRATION_HEAD,
        "docker_image_digest": docker_image_digest,
        "frontend_build_hash": _frontend_build_hash(),
        "capability_registry_version": CAPABILITY_REGISTRY_VERSION,
        "qualification_registry_version": QUALIFICATION_REGISTRY_VERSION,
        "feature_flag_defaults": feature_flag_defaults(),
        "pilot_tenant_id": PILOT_TENANT_ID,
        "allowed_integrations": ["google_mail"],
        "activation_level": activation_stage,
        "rollback_target": rollback_target or RELEASE_VERSION,
        "backup_reference": backup_reference,
        "operator_approval_id": operator_approval_id,
        "release_timestamp": now,
        "qualifications_required": [
            "FULL_FUNCTION_MATRIX_PASS",
            "CONTINUOUS_REGRESSION_QUALIFIED",
            "TESTBOT_SYSTEM_CLOSED",
        ],
    }
    payload["manifest_hash"] = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return payload


def validate_release_manifest(manifest: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    required = (
        "manifest_schema_version",
        "release_version",
        "commit_sha",
        "migration_head",
        "feature_flag_defaults",
        "pilot_tenant_id",
        "activation_level",
        "rollback_target",
        "release_timestamp",
        "manifest_hash",
    )
    for key in required:
        if key not in manifest:
            failures.append(f"missing manifest field: {key}")
    if manifest.get("pilot_tenant_id") != PILOT_TENANT_ID:
        failures.append("pilot_tenant_id mismatch")
    if manifest.get("activation_level") not in {"P0", "P1", "P2", "P3"}:
        failures.append("invalid activation_level")
    for flag, value in (manifest.get("feature_flag_defaults") or {}).items():
        if value is True:
            failures.append(f"risk flag {flag} must default false")
    stored_hash = manifest.get("manifest_hash")
    if stored_hash:
        copy_manifest = dict(manifest)
        copy_manifest.pop("manifest_hash", None)
        actual = hashlib.sha256(canonical_json_bytes(copy_manifest)).hexdigest()
        if actual != stored_hash:
            failures.append("manifest_hash mismatch")
    return failures
