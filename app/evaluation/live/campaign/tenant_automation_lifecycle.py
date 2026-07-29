"""Tenant automation lifecycle for automatic Gmail canary (harness only)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.evaluation.live.campaign.automatic_action_contract import CANARY_AUTO_ACTIONS
from app.repositories.postgres.database import SessionLocal
from app.repositories.postgres.tenant_config_models import TenantConfigRecord
from app.workflows.tenant_automation import FULL_AUTO, normalize_automation_mode

LIVE_EVAL_TENANT_ID = "TENANT_LIVE_EVAL"
DEFAULT_SNAPSHOT_PATH = Path("storage/ci-live-eval/automatic_canary_tenant_snapshot.json")


@dataclass(frozen=True)
class TenantAutomationSnapshot:
    tenant_id: str
    auto_actions: dict[str, Any]
    config_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "auto_actions": dict(self.auto_actions),
            "config_hash": self.config_hash,
        }


@dataclass(frozen=True)
class TenantLifecycleReport:
    pre_run_config_hash: str
    active_run_config_hash: str
    post_run_config_hash: str
    restoration_status: str
    pause_status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "pre_run_config_hash": self.pre_run_config_hash,
            "active_run_config_hash": self.active_run_config_hash,
            "post_run_config_hash": self.post_run_config_hash,
            "restoration_status": self.restoration_status,
            "pause_status": self.pause_status,
        }


def _canonical_json(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def hash_auto_actions(auto_actions: dict[str, Any] | None) -> str:
    normalized = dict(sorted((auto_actions or {}).items()))
    return hashlib.sha256(_canonical_json(normalized).encode("utf-8")).hexdigest()


def _read_auto_actions(tenant_id: str) -> dict[str, Any]:
    db = SessionLocal()
    try:
        row = db.get(TenantConfigRecord, tenant_id)
        if row is None:
            return {}
        return dict(row.auto_actions or {})
    finally:
        db.close()


def _write_auto_actions(tenant_id: str, auto_actions: dict[str, Any]) -> None:
    db = SessionLocal()
    try:
        row = db.get(TenantConfigRecord, tenant_id)
        if row is None:
            raise ValueError(f"tenant {tenant_id!r} not found")
        row.auto_actions = dict(auto_actions)
        db.commit()
    finally:
        db.close()


def verify_automation_not_broadly_enabled(
    auto_actions: dict[str, Any] | None,
) -> list[str]:
    """Fail if any job type already permits direct external execution."""
    issues: list[str] = []
    for job_type, raw in sorted((auto_actions or {}).items()):
        if normalize_automation_mode(raw) == FULL_AUTO:
            issues.append(
                f"automatic Gmail action already enabled for job_type={job_type!r}"
            )
    return issues


def verify_canary_automation_active(
    auto_actions: dict[str, Any] | None,
) -> list[str]:
    """Fail unless only lead is auto and all other canary job types are manual."""
    issues: list[str] = []
    actions = auto_actions or {}
    for job_type, expected in CANARY_AUTO_ACTIONS.items():
        actual = actions.get(job_type)
        if str(actual) != expected:
            issues.append(
                f"canary automation mismatch for {job_type!r}: "
                f"expected {expected!r}, got {actual!r}"
            )
    for job_type, raw in sorted(actions.items()):
        if job_type in CANARY_AUTO_ACTIONS:
            continue
        if normalize_automation_mode(raw) == FULL_AUTO:
            issues.append(
                f"unexpected automatic Gmail action enabled for job_type={job_type!r}"
            )
    return issues


def snapshot_tenant_config(
    tenant_id: str = LIVE_EVAL_TENANT_ID,
) -> TenantAutomationSnapshot:
    auto_actions = _read_auto_actions(tenant_id)
    return TenantAutomationSnapshot(
        tenant_id=tenant_id,
        auto_actions=auto_actions,
        config_hash=hash_auto_actions(auto_actions),
    )


def write_snapshot_file(
    snapshot: TenantAutomationSnapshot,
    path: Path | str = DEFAULT_SNAPSHOT_PATH,
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(snapshot.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def load_snapshot_file(path: Path | str) -> TenantAutomationSnapshot:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    auto_actions = dict(raw.get("auto_actions") or {})
    return TenantAutomationSnapshot(
        tenant_id=str(raw.get("tenant_id") or LIVE_EVAL_TENANT_ID),
        auto_actions=auto_actions,
        config_hash=str(raw.get("config_hash") or hash_auto_actions(auto_actions)),
    )


def activate_canary_automation(
    tenant_id: str = LIVE_EVAL_TENANT_ID,
) -> TenantAutomationSnapshot:
    _write_auto_actions(tenant_id, dict(CANARY_AUTO_ACTIONS))
    return snapshot_tenant_config(tenant_id)


def pause_automation(
    tenant_id: str = LIVE_EVAL_TENANT_ID,
) -> TenantAutomationSnapshot:
    paused = {job_type: "manual" for job_type in CANARY_AUTO_ACTIONS}
    _write_auto_actions(tenant_id, paused)
    return snapshot_tenant_config(tenant_id)


def restore_tenant_config(
    snapshot: TenantAutomationSnapshot,
    *,
    tenant_id: str | None = None,
) -> TenantAutomationSnapshot:
    target_tenant = tenant_id or snapshot.tenant_id
    _write_auto_actions(target_tenant, dict(snapshot.auto_actions))
    return snapshot_tenant_config(target_tenant)


def restore_from_snapshot_file(
    path: Path | str,
    *,
    tenant_id: str = LIVE_EVAL_TENANT_ID,
) -> TenantLifecycleReport:
    snapshot = load_snapshot_file(path)
    pre_hash = snapshot.config_hash
    restored = restore_tenant_config(snapshot, tenant_id=tenant_id)
    post_hash = restored.config_hash
    restoration_status = "restored" if post_hash == pre_hash else "failed"
    return TenantLifecycleReport(
        pre_run_config_hash=pre_hash,
        active_run_config_hash=hash_auto_actions(CANARY_AUTO_ACTIONS),
        post_run_config_hash=post_hash,
        restoration_status=restoration_status,
        pause_status="not_paused",
    )


def run_lifecycle_cleanup(
    snapshot_path: Path | str,
    *,
    tenant_id: str = LIVE_EVAL_TENANT_ID,
) -> TenantLifecycleReport:
    """Pause automation then restore original config (idempotent)."""
    snapshot = load_snapshot_file(snapshot_path)
    pre_hash = snapshot.config_hash
    pause_automation(tenant_id=tenant_id)
    restored = restore_tenant_config(snapshot, tenant_id=tenant_id)
    post_hash = restored.config_hash
    return TenantLifecycleReport(
        pre_run_config_hash=pre_hash,
        active_run_config_hash=hash_auto_actions(CANARY_AUTO_ACTIONS),
        post_run_config_hash=post_hash,
        restoration_status="restored" if post_hash == pre_hash else "failed",
        pause_status="paused",
    )
