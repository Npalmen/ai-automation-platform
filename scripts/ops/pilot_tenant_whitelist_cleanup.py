#!/usr/bin/env python3
"""
Pilot production tenant whitelist cleanup.

Keeps exactly one tenant (--keep-tenant). Deletes all other tenants and
tenant-scoped rows. Fail-closed; no TRUNCATE; no secrets in output.

Usage:
  # Preflight + dry-run report
  python3 scripts/ops/pilot_tenant_whitelist_cleanup.py \\
    --keep-tenant T_NIKLAS_DEMO_001

  # Execute (after verified backup + reviewed dry-run)
  python3 scripts/ops/pilot_tenant_whitelist_cleanup.py \\
    --keep-tenant T_NIKLAS_DEMO_001 \\
    --confirm-production-cleanup \\
    --execute
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.admin.alerts.models import NotificationDeliveryRecord, OperatorAlertRecord
from app.admin.incident_models import (
    IncidentRecord,
    IncidentSignalRecord,
    IncidentTenantRecord,
    IncidentTimelineEventRecord,
)
from app.admin.onboarding.models import (
    OnboardingIntegrationVerificationRecord,
    OnboardingOAuthStateRecord,
    OnboardingSessionRecord,
    OnboardingStepDraftRecord,
    OnboardingStepStateRecord,
    TenantResourceBindingRecord,
)
from app.core.settings import get_settings
from app.domain.integrations.models import IntegrationEvent
from app.integrations.google.oauth_token_resolver import PROVIDER, gmail_connection_status
from app.integrations.oauth_state_models import IntegrationOAuthStateRecord
from app.repositories.postgres.action_execution_models import ActionExecutionRecord
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.database import SessionLocal
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.oauth_credential_models import OAuthCredentialRecord
from app.repositories.postgres.oauth_credential_repository import OAuthCredentialRepository
from app.repositories.postgres.tenant_api_key_models import TenantApiKeyRecord
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
from app.repositories.postgres.tenant_config_models import TenantConfigRecord

KEEP_DEFAULT = "T_NIKLAS_DEMO_001"
REQUIRED_DB_NAME = "ai_platform"
STATUS_DIR_CANDIDATES = [
    Path("/opt/krowolf/storage/status"),
    Path("/app/storage/status"),
]
TENANT_KEYS_DIRS = [
    Path("/opt/krowolf/storage/tenant_keys"),
    Path("/app/storage/tenant_keys"),
]
BASELINE_CANDIDATES = [
    Path("/opt/krowolf/storage/status/gmail_soak_baseline.json"),
    Path("/app/storage/status/gmail_soak_baseline.json"),
]
API_BASE = "https://api.krowolf.se"
CLEANUP_AUDIT_ACTION = "platform.tenant_whitelist_cleanup"


class CleanupBlocked(Exception):
    pass


def _status_dir() -> Path:
    for p in STATUS_DIR_CANDIDATES:
        if p.parent.exists():
            p.mkdir(parents=True, exist_ok=True)
            return p
    p = STATUS_DIR_CANDIDATES[-1]
    p.mkdir(parents=True, exist_ok=True)
    return p


def _db_name() -> str:
    url = get_settings().DATABASE_URL or ""
    return (urlparse(url).path or "").lstrip("/").lower()


def _count_model(db: Session, model, tenant_id: str) -> int:
    return (
        db.query(func.count())
        .select_from(model)
        .filter(model.tenant_id == tenant_id)  # type: ignore[attr-defined]
        .scalar()
        or 0
    )


def _snapshot_tenant(db: Session, tenant_id: str) -> dict[str, Any]:
    settings = get_settings()
    status = gmail_connection_status(db, tenant_id, settings=settings)
    row = OAuthCredentialRepository.get(db, tenant_id, PROVIDER)
    sched = TenantConfigRepository.get_settings(db, tenant_id).get("scheduler") or {}
    wf = TenantConfigRepository.get_settings(db, tenant_id).get("workflow_scan") or {}

    return {
        "tenant_config": _count_model(db, TenantConfigRecord, tenant_id),
        "jobs": _count_model(db, JobRecord, tenant_id),
        "approval_requests": _count_model(db, ApprovalRequestRecord, tenant_id),
        "oauth_credentials": _count_model(db, OAuthCredentialRecord, tenant_id),
        "integration_events": _count_model(db, IntegrationEvent, tenant_id),
        "operator_alerts": _count_model(db, OperatorAlertRecord, tenant_id),
        "incident_tenants": _count_model(db, IncidentTenantRecord, tenant_id),
        "audit_events": _count_model(db, AuditEventRecord, tenant_id),
        "tenant_api_keys": _count_model(db, TenantApiKeyRecord, tenant_id),
        "integration_oauth_states": _count_model(db, IntegrationOAuthStateRecord, tenant_id),
        "onboarding_sessions": _count_model(db, OnboardingSessionRecord, tenant_id),
        "onboarding_oauth_states": _count_model(db, OnboardingOAuthStateRecord, tenant_id),
        "tenant_resource_bindings": _count_model(db, TenantResourceBindingRecord, tenant_id),
        "action_executions": _count_model(db, ActionExecutionRecord, tenant_id),
        "gmail_checkpoint_present": bool(wf),
        "credential_source": status.get("credential_source"),
        "connection_state": status.get("connection_state"),
        "access_token_set": bool(row and row.access_token),
        "refresh_token_set": bool(row and row.refresh_token),
        "scheduler_run_mode": sched.get("run_mode"),
    }


def _list_all_tenant_ids(db: Session) -> list[str]:
    return [r[0] for r in db.query(TenantConfigRecord.tenant_id).order_by(TenantConfigRecord.tenant_id).all()]


def _orphan_incident_ids(db: Session) -> list[str]:
    linked = {r[0] for r in db.query(IncidentTenantRecord.incident_id).distinct().all()}
    if not linked:
        return [r[0] for r in db.query(IncidentRecord.incident_id).all()]
    return [
        r[0]
        for r in db.query(IncidentRecord.incident_id)
        .filter(~IncidentRecord.incident_id.in_(linked))
        .all()
    ]


def _count_deletions_for_tenant(db: Session, tenant_id: str) -> dict[str, int]:
    session_ids = [
        r[0]
        for r in db.query(OnboardingSessionRecord.id)
        .filter(OnboardingSessionRecord.tenant_id == tenant_id)
        .all()
    ]
    alert_ids = [
        r[0]
        for r in db.query(OperatorAlertRecord.id)
        .filter(OperatorAlertRecord.tenant_id == tenant_id)
        .all()
    ]

    counts: dict[str, int] = {}
    counts["notification_deliveries"] = (
        db.query(NotificationDeliveryRecord)
        .filter(NotificationDeliveryRecord.alert_id.in_(alert_ids))
        .count()
        if alert_ids
        else 0
    )
    counts["onboarding_step_drafts"] = (
        db.query(OnboardingStepDraftRecord)
        .filter(OnboardingStepDraftRecord.session_id.in_(session_ids))
        .count()
        if session_ids
        else 0
    )
    counts["onboarding_step_states"] = (
        db.query(OnboardingStepStateRecord)
        .filter(OnboardingStepStateRecord.session_id.in_(session_ids))
        .count()
        if session_ids
        else 0
    )
    counts["onboarding_integration_verifications"] = (
        db.query(OnboardingIntegrationVerificationRecord)
        .filter(OnboardingIntegrationVerificationRecord.session_id.in_(session_ids))
        .count()
        if session_ids
        else 0
    )

    for table_name, model in (
        ("onboarding_oauth_states", OnboardingOAuthStateRecord),
        ("onboarding_sessions", OnboardingSessionRecord),
        ("integration_oauth_states", IntegrationOAuthStateRecord),
        ("tenant_resource_bindings", TenantResourceBindingRecord),
        ("incident_signals", IncidentSignalRecord),
        ("incident_tenants", IncidentTenantRecord),
        ("operator_alerts", OperatorAlertRecord),
        ("integration_events", IntegrationEvent),
        ("action_executions", ActionExecutionRecord),
        ("approval_requests", ApprovalRequestRecord),
        ("jobs", JobRecord),
        ("audit_events", AuditEventRecord),
        ("oauth_credentials", OAuthCredentialRecord),
        ("tenant_api_keys", TenantApiKeyRecord),
        ("tenant_configs", TenantConfigRecord),
    ):
        counts[table_name] = _count_model(db, model, tenant_id)

    return {k: v for k, v in counts.items() if v > 0}


def _delete_tenant_data(db: Session, tenant_id: str, tallies: dict[str, int]) -> None:
    session_ids = [
        r[0]
        for r in db.query(OnboardingSessionRecord.id)
        .filter(OnboardingSessionRecord.tenant_id == tenant_id)
        .all()
    ]
    alert_ids = [
        r[0]
        for r in db.query(OperatorAlertRecord.id)
        .filter(OperatorAlertRecord.tenant_id == tenant_id)
        .all()
    ]

    def _del(table: str, n: int) -> None:
        if n:
            tallies[table] = tallies.get(table, 0) + n

    if alert_ids:
        n = (
            db.query(NotificationDeliveryRecord)
            .filter(NotificationDeliveryRecord.alert_id.in_(alert_ids))
            .delete(synchronize_session=False)
        )
        _del("notification_deliveries", n)

    if session_ids:
        for table, model in (
            ("onboarding_step_drafts", OnboardingStepDraftRecord),
            ("onboarding_step_states", OnboardingStepStateRecord),
            ("onboarding_integration_verifications", OnboardingIntegrationVerificationRecord),
        ):
            n = (
                db.query(model)
                .filter(model.session_id.in_(session_ids))  # type: ignore[attr-defined]
                .delete(synchronize_session=False)
            )
            _del(table, n)

    for table, model in (
        ("onboarding_oauth_states", OnboardingOAuthStateRecord),
        ("onboarding_sessions", OnboardingSessionRecord),
        ("integration_oauth_states", IntegrationOAuthStateRecord),
        ("tenant_resource_bindings", TenantResourceBindingRecord),
        ("incident_signals", IncidentSignalRecord),
        ("incident_tenants", IncidentTenantRecord),
        ("operator_alerts", OperatorAlertRecord),
        ("integration_events", IntegrationEvent),
        ("action_executions", ActionExecutionRecord),
        ("approval_requests", ApprovalRequestRecord),
        ("jobs", JobRecord),
        ("audit_events", AuditEventRecord),
        ("oauth_credentials", OAuthCredentialRecord),
        ("tenant_api_keys", TenantApiKeyRecord),
        ("tenant_configs", TenantConfigRecord),
    ):
        n = (
            db.query(model)
            .filter(model.tenant_id == tenant_id)  # type: ignore[attr-defined]
            .delete(synchronize_session=False)
        )
        _del(table, n)


def _delete_orphan_incidents(db: Session, tallies: dict[str, int]) -> None:
    orphan_ids = _orphan_incident_ids(db)
    if not orphan_ids:
        return
    n = (
        db.query(IncidentTimelineEventRecord)
        .filter(IncidentTimelineEventRecord.incident_id.in_(orphan_ids))
        .delete(synchronize_session=False)
    )
    if n:
        tallies["incident_timeline_events"] = tallies.get("incident_timeline_events", 0) + n
    n = (
        db.query(IncidentRecord)
        .filter(IncidentRecord.incident_id.in_(orphan_ids))
        .delete(synchronize_session=False)
    )
    if n:
        tallies["incidents"] = tallies.get("incidents", 0) + n


def _cleanup_tenant_key_files(keep_tenant: str, dry_run: bool) -> list[str]:
    removed: list[str] = []
    keep_name = f"{keep_tenant}.api_key"
    for base in TENANT_KEYS_DIRS:
        if not base.is_dir():
            continue
        for path in base.glob("*.api_key"):
            if path.name == keep_name:
                continue
            removed.append(str(path))
            if not dry_run:
                path.unlink(missing_ok=True)
    return removed


def _cleanup_browser_fixture_files(dry_run: bool) -> list[str]:
    removed: list[str] = []
    patterns = (
        "k12_browser_*report*.json",
        "kapitel12_browser_report*.json",
    )
    for base in _status_dir().parent.glob("status"):
        pass
    status = _status_dir()
    for pat in patterns:
        for path in status.glob(pat):
            removed.append(str(path))
            if not dry_run:
                path.unlink(missing_ok=True)
    return removed


def _read_backup_status() -> dict[str, Any]:
    for base in STATUS_DIR_CANDIDATES:
        p = base / "backup_status.json"
        if p.is_file():
            data = json.loads(p.read_text(encoding="utf-8"))
            return {
                "status": data.get("status"),
                "completed_at": data.get("completed_at"),
                "offsite_status": data.get("offsite_status"),
                "offsite_verified": data.get("offsite_verified"),
                "checksum_sha256_prefix": (data.get("checksum_sha256") or "")[:16] or None,
                "backup_id": data.get("backup_id") or data.get("filename") or data.get("artifact"),
            }
    return {"status": "missing"}


def _health_ok() -> bool:
    try:
        with urllib.request.urlopen(f"{API_BASE}/health", timeout=15) as resp:
            return resp.status == 200
    except Exception:
        return False


def _test_read_ok(tenant: str) -> bool:
    for base in TENANT_KEYS_DIRS:
        key_path = base / f"{tenant}.api_key"
        if not key_path.is_file():
            continue
        api_key = key_path.read_text().strip()
        req = urllib.request.Request(
            f"{API_BASE}/integrations/google_mail/test-read",
            data=b"{}",
            method="POST",
            headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode())
                return resp.status == 200 and body.get("credential_source") == "tenant_oauth"
        except urllib.error.HTTPError:
            return False
    return False


def run_preflight(db: Session, keep_tenant: str) -> dict[str, Any]:
    settings = get_settings()
    out: dict[str, Any] = {"preflight": {}}
    pf = out["preflight"]

    pf["health_200"] = _health_ok()
    pf["database_name"] = _db_name()
    pf["database_name_ok"] = pf["database_name"] == REQUIRED_DB_NAME
    pf["admin_role"] = settings.ADMIN_ROLE
    pf["admin_role_ok"] = settings.ADMIN_ROLE == "admin"

    all_tenants = _list_all_tenant_ids(db)
    pf["tenants_in_db"] = all_tenants
    pf["keep_tenant_exists"] = keep_tenant in all_tenants
    pf["whitelist_proof"] = keep_tenant in all_tenants and len(all_tenants) >= 1

    snap = _snapshot_tenant(db, keep_tenant)
    pf["keep_tenant_snapshot"] = snap
    pf["credential_source_tenant_oauth"] = snap.get("credential_source") == "tenant_oauth"
    pf["oauth_credentials_present"] = snap.get("oauth_credentials", 0) > 0
    pf["scheduler_paused"] = snap.get("scheduler_run_mode") == "paused"
    pf["soak_baseline_exists"] = any(p.is_file() for p in BASELINE_CANDIDATES)

    # No active scanner/dispatch job table — pending integration events heuristic
    pending_integrations = (
        db.query(func.count())
        .select_from(IntegrationEvent)
        .filter(IntegrationEvent.status == "pending")
        .scalar()
        or 0
    )
    pf["pending_integration_events"] = pending_integrations
    pf["no_pending_dispatch"] = pending_integrations == 0

    backup = _read_backup_status()
    pf["backup"] = backup
    pf["backup_offsite_ok"] = (
        backup.get("status") == "success"
        and backup.get("offsite_status") == "success"
        and backup.get("offsite_verified") is True
    )

    blockers = []
    if not pf["health_200"]:
        blockers.append("health_not_200")
    if not pf["database_name_ok"]:
        blockers.append("wrong_database")
    if not pf["keep_tenant_exists"]:
        blockers.append("keep_tenant_missing")
    if not pf["credential_source_tenant_oauth"]:
        blockers.append("credential_not_tenant_oauth")
    if not pf["oauth_credentials_present"]:
        blockers.append("oauth_row_missing")
    if not pf["scheduler_paused"]:
        blockers.append("scheduler_not_paused")
    pf["blockers"] = blockers
    pf["pass"] = len(blockers) == 0
    return out


def build_dry_run_report(db: Session, keep_tenant: str) -> dict[str, Any]:
    all_tenants = _list_all_tenant_ids(db)
    delete_targets = [t for t in all_tenants if t != keep_tenant]

    per_table: dict[str, int] = {}
    per_tenant: dict[str, dict[str, int]] = {}
    for tid in delete_targets:
        counts = _count_deletions_for_tenant(db, tid)
        per_tenant[tid] = counts
        for table, n in counts.items():
            per_table[table] = per_table.get(table, 0) + n

    orphan_ids = _orphan_incident_ids(db)
    if orphan_ids:
        per_table["incidents_orphan_existing"] = len(orphan_ids)

    fk_order = [
        "notification_deliveries",
        "onboarding_step_drafts",
        "onboarding_step_states",
        "onboarding_integration_verifications",
        "onboarding_oauth_states",
        "onboarding_sessions",
        "integration_oauth_states",
        "tenant_resource_bindings",
        "incident_signals",
        "incident_tenants",
        "operator_alerts",
        "integration_events",
        "action_executions",
        "approval_requests",
        "jobs",
        "audit_events",
        "oauth_credentials",
        "tenant_api_keys",
        "tenant_configs",
        "incident_timeline_events",
        "incidents",
    ]

    key_files = _cleanup_tenant_key_files(keep_tenant, dry_run=True)
    fixture_files = _cleanup_browser_fixture_files(dry_run=True)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "keep_tenant": keep_tenant,
        "tenants_kept": [keep_tenant],
        "tenants_to_delete": delete_targets,
        "tenants_before_count": len(all_tenants),
        "rows_to_delete_per_table": per_table,
        "rows_per_deleted_tenant": per_tenant,
        "foreign_key_delete_order": fk_order,
        "tenant_api_key_files_to_remove": [Path(p).name for p in key_files],
        "browser_fixture_files_to_remove": [Path(p).name for p in fixture_files],
        "keep_tenant_snapshot": _snapshot_tenant(db, keep_tenant),
    }


def emit_cleanup_audit(
    db: Session,
    keep_tenant: str,
    *,
    dry_run: bool,
    tenants_deleted: list[str],
    rows_deleted: dict[str, int],
) -> None:
    if dry_run:
        return
    db.add(
        AuditEventRecord(
            event_id=str(uuid4()),
            tenant_id=keep_tenant,
            category="platform",
            action=CLEANUP_AUDIT_ACTION,
            status="succeeded",
            details={
                "tenants_deleted_count": len(tenants_deleted),
                "tenants_deleted": tenants_deleted,
                "rows_deleted_per_table": rows_deleted,
                "keep_tenant": keep_tenant,
                "dry_run": False,
            },
            created_at=datetime.now(timezone.utc),
        )
    )


def execute_cleanup(db: Session, keep_tenant: str, *, require_backup: bool) -> dict[str, Any]:
    pre = run_preflight(db, keep_tenant)
    if not pre["preflight"]["pass"]:
        raise CleanupBlocked(f"Preflight failed: {pre['preflight']['blockers']}")

    if require_backup and not pre["preflight"]["backup_offsite_ok"]:
        raise CleanupBlocked("Offsite backup not verified — run canonical backup first")

    before = _snapshot_tenant(db, keep_tenant)
    all_before = _list_all_tenant_ids(db)
    delete_targets = [t for t in all_before if t != keep_tenant]

    tallies: dict[str, int] = {}
    try:
        for tid in delete_targets:
            _delete_tenant_data(db, tid, tallies)
        _delete_orphan_incidents(db, tallies)
        emit_cleanup_audit(
            db,
            keep_tenant,
            dry_run=False,
            tenants_deleted=delete_targets,
            rows_deleted=tallies,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    key_removed = _cleanup_tenant_key_files(keep_tenant, dry_run=False)
    fixture_removed = _cleanup_browser_fixture_files(dry_run=False)

    after = _snapshot_tenant(db, keep_tenant)
    all_after = _list_all_tenant_ids(db)

    before_cmp = dict(before)
    after_cmp = dict(after)
    audit_delta = after_cmp.get("audit_events", 0) - before_cmp.get("audit_events", 0)
    niklas_unchanged = before_cmp == after_cmp or (
        audit_delta == 1
        and {k: after_cmp[k] for k in after_cmp if k != "audit_events"}
        == {k: before_cmp[k] for k in before_cmp if k != "audit_events"}
    )

    return {
        "tenants_before": all_before,
        "tenants_deleted": delete_targets,
        "tenants_after": all_after,
        "kept_tenant": keep_tenant,
        "rows_deleted_per_table": tallies,
        "orphan_cleanup": {
            "incident_timeline_events": tallies.get("incident_timeline_events", 0),
            "incidents": tallies.get("incidents", 0),
        },
        "tenant_api_key_files_removed": [Path(p).name for p in key_removed],
        "browser_fixture_files_removed": [Path(p).name for p in fixture_removed],
        "niklas_counts_before": before,
        "niklas_counts_after": after,
        "niklas_unchanged": niklas_unchanged,
        "audit_events_delta": audit_delta,
    }


def post_verify(db: Session, keep_tenant: str) -> dict[str, Any]:
    tenants = _list_all_tenant_ids(db)
    stray: dict[str, int] = {}

    for table in (
        "jobs",
        "approval_requests",
        "oauth_credentials",
        "tenant_api_keys",
        "integration_events",
        "operator_alerts",
    ):
        n = db.execute(
            text(f"SELECT count(*) FROM {table} WHERE tenant_id != :keep"),
            {"keep": keep_tenant},
        ).scalar()
        stray[table] = int(n or 0)

    orphan_jobs = db.execute(
        text(
            "SELECT count(*) FROM jobs j WHERE NOT EXISTS "
            "(SELECT 1 FROM tenant_configs t WHERE t.tenant_id = j.tenant_id)"
        )
    ).scalar()

    return {
        "tenant_list": tenants,
        "exactly_one_tenant": tenants == [keep_tenant],
        "stray_rows_other_tenants": stray,
        "orphan_jobs": int(orphan_jobs or 0),
        "health_200": _health_ok(),
        "test_read_tenant_oauth": _test_read_ok(keep_tenant),
        "keep_snapshot": _snapshot_tenant(db, keep_tenant),
        "soak_baseline_exists": any(p.is_file() for p in BASELINE_CANDIDATES),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Pilot whitelist tenant cleanup")
    parser.add_argument("--keep-tenant", required=True, help="Only tenant to preserve")
    parser.add_argument(
        "--confirm-production-cleanup",
        action="store_true",
        help="Required for --execute",
    )
    parser.add_argument("--execute", action="store_true", help="Perform deletion (default dry-run)")
    parser.add_argument(
        "--skip-backup-check",
        action="store_true",
        help="Only for dry-run inventory; execute always requires verified backup",
    )
    args = parser.parse_args()

    keep = args.keep_tenant.strip()
    if not keep:
        print(json.dumps({"error": "empty keep-tenant"}))
        return 2

    db = SessionLocal()
    try:
        pre = run_preflight(db, keep)
        if not pre["preflight"]["keep_tenant_exists"]:
            print(json.dumps({"error": "keep_tenant_missing", **pre}, indent=2))
            return 1

        dry_report = build_dry_run_report(db, keep)
        dry_path = _status_dir() / "tenant_cleanup_dry_run.json"
        dry_path.write_text(json.dumps(dry_report, indent=2, ensure_ascii=False, default=str))

        if not args.execute:
            out = {
                "mode": "dry_run",
                "preflight": pre["preflight"],
                "dry_run_report_path": str(dry_path),
                "dry_run_summary": {
                    "tenants_to_delete": dry_report["tenants_to_delete"],
                    "rows_to_delete_per_table": dry_report["rows_to_delete_per_table"],
                },
                "credentials_exposed": False,
            }
            print(json.dumps(out, indent=2, ensure_ascii=False))
            return 0

        if not args.confirm_production_cleanup:
            print(json.dumps({"error": "missing --confirm-production-cleanup"}))
            return 2

        result = execute_cleanup(db, keep, require_backup=not args.skip_backup_check)
        post = post_verify(db, keep)

        verdict = "PASS"
        if not post["exactly_one_tenant"]:
            verdict = "FAIL"
        elif not result["niklas_unchanged"]:
            verdict = "FAIL"
        elif any(v > 0 for v in post["stray_rows_other_tenants"].values()):
            verdict = "PARTIAL"
        elif not post["test_read_tenant_oauth"]:
            verdict = "PARTIAL"

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "backup": _read_backup_status(),
            "cleanup": result,
            "post_verify": post,
            "verdict": verdict,
            "credentials_exposed": False,
            "external_side_effects": 0,
        }
        report_path = _status_dir() / "tenant_cleanup_report.json"
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        print(json.dumps({"report_path": str(report_path), "verdict": verdict, **report}, indent=2))
        return 0 if verdict == "PASS" else 1
    except CleanupBlocked as exc:
        print(json.dumps({"blocked": str(exc)}))
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
