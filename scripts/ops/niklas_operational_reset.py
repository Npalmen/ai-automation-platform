#!/usr/bin/env python3
"""
Del I — Niklas operational reset (single tenant test data only).

Clears jobs, approvals, alerts, incidents, integration events, action executions,
and tenant audit history while preserving tenant config, OAuth, API keys, Gmail
checkpoint/dedupe metadata, and scheduler paused state.

Usage:
  python3 scripts/ops/niklas_operational_reset.py --dry-run
  python3 scripts/ops/niklas_operational_reset.py --confirm-production-cleanup --execute
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
from app.core.settings import get_settings
from app.domain.integrations.models import IntegrationEvent
from app.integrations.google.oauth_token_resolver import PROVIDER, gmail_connection_status
from app.repositories.postgres.action_execution_models import ActionExecutionRecord
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.database import SessionLocal
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.oauth_credential_repository import OAuthCredentialRepository
from app.repositories.postgres.tenant_api_key_models import TenantApiKeyRecord
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
from app.repositories.postgres.tenant_config_models import TenantConfigRecord

TENANT_DEFAULT = "T_NIKLAS_DEMO_001"
REQUIRED_DB_NAME = "ai_platform"
API_BASE = "https://api.krowolf.se"
RESET_AUDIT_ACTION = "platform.niklas_operational_reset"
STATUS_DIRS = [
    Path("/opt/krowolf/storage/status"),
    Path("/app/storage/status"),
]
TENANT_KEY_DIRS = [
    Path("/opt/krowolf/storage/tenant_keys"),
    Path("/app/storage/tenant_keys"),
]
SOAK_GLOBS = ("gmail_soak/day_*.json", "gmail_soak_baseline.json")


class ResetBlocked(Exception):
    pass


def _status_dir() -> Path:
    for p in STATUS_DIRS:
        if p.parent.exists():
            p.mkdir(parents=True, exist_ok=True)
            return p
    p = STATUS_DIRS[-1]
    p.mkdir(parents=True, exist_ok=True)
    return p


def _db_name() -> str:
    return (urlparse(get_settings().DATABASE_URL or "").path or "").lstrip("/").lower()


def _count(db: Session, model, tenant_id: str) -> int:
    return (
        db.query(func.count())
        .select_from(model)
        .filter(model.tenant_id == tenant_id)  # type: ignore[attr-defined]
        .scalar()
        or 0
    )


def _snapshot(db: Session, tenant_id: str) -> dict[str, Any]:
    settings = get_settings()
    gmail = gmail_connection_status(db, tenant_id, settings=settings)
    oauth = OAuthCredentialRepository.get(db, tenant_id, PROVIDER)
    sched = TenantConfigRepository.get_settings(db, tenant_id).get("scheduler") or {}
    wf = TenantConfigRepository.get_settings(db, tenant_id).get("workflow_scan") or {}
    incident_ids = [
        r[0]
        for r in db.query(IncidentTenantRecord.incident_id)
        .filter(IncidentTenantRecord.tenant_id == tenant_id)
        .all()
    ]
    return {
        "jobs": _count(db, JobRecord, tenant_id),
        "approvals": _count(db, ApprovalRequestRecord, tenant_id),
        "operator_alerts": _count(db, OperatorAlertRecord, tenant_id),
        "integration_events": _count(db, IntegrationEvent, tenant_id),
        "action_executions": _count(db, ActionExecutionRecord, tenant_id),
        "audit_events": _count(db, AuditEventRecord, tenant_id),
        "incident_links": len(incident_ids),
        "tenant_config": _count(db, TenantConfigRecord, tenant_id),
        "tenant_api_keys": _count(db, TenantApiKeyRecord, tenant_id),
        "oauth_google_mail": 1 if oauth else 0,
        "scheduler_run_mode": sched.get("run_mode"),
        "gmail_credential_source": gmail.get("credential_source"),
        "workflow_scan_status": wf.get("status"),
        "workflow_scan_last_scan_at": wf.get("last_scan_at"),
    }


def _orphan_incident_ids(db: Session) -> list[str]:
    linked = {r[0] for r in db.query(IncidentTenantRecord.incident_id).all()}
    all_ids = {r[0] for r in db.query(IncidentRecord.incident_id).all()}
    return sorted(all_ids - linked)


def _delete_operational_rows(db: Session, tenant_id: str) -> dict[str, int]:
    tallies: dict[str, int] = {}
    alert_ids = [
        r[0]
        for r in db.query(OperatorAlertRecord.id)
        .filter(OperatorAlertRecord.tenant_id == tenant_id)
        .all()
    ]
    if alert_ids:
        n = (
            db.query(NotificationDeliveryRecord)
            .filter(NotificationDeliveryRecord.alert_id.in_(alert_ids))
            .delete(synchronize_session=False)
        )
        if n:
            tallies["notification_deliveries"] = n

    incident_ids = [
        r[0]
        for r in db.query(IncidentTenantRecord.incident_id)
        .filter(IncidentTenantRecord.tenant_id == tenant_id)
        .all()
    ]
    if incident_ids:
        n = (
            db.query(IncidentTimelineEventRecord)
            .filter(IncidentTimelineEventRecord.incident_id.in_(incident_ids))
            .delete(synchronize_session=False)
        )
        if n:
            tallies["incident_timeline_events"] = n

    for table, model in (
        ("incident_signals", IncidentSignalRecord),
        ("incident_tenants", IncidentTenantRecord),
        ("operator_alerts", OperatorAlertRecord),
        ("integration_events", IntegrationEvent),
        ("action_executions", ActionExecutionRecord),
        ("approval_requests", ApprovalRequestRecord),
        ("jobs", JobRecord),
        ("audit_events", AuditEventRecord),
    ):
        n = (
            db.query(model)
            .filter(model.tenant_id == tenant_id)  # type: ignore[attr-defined]
            .delete(synchronize_session=False)
        )
        if n:
            tallies[table] = n

    orphan_ids = _orphan_incident_ids(db)
    if orphan_ids:
        n = (
            db.query(IncidentTimelineEventRecord)
            .filter(IncidentTimelineEventRecord.incident_id.in_(orphan_ids))
            .delete(synchronize_session=False)
        )
        if n:
            tallies["orphan_incident_timeline_events"] = tallies.get("orphan_incident_timeline_events", 0) + n
        n = (
            db.query(IncidentRecord)
            .filter(IncidentRecord.incident_id.in_(orphan_ids))
            .delete(synchronize_session=False)
        )
        if n:
            tallies["orphan_incidents"] = n

    return tallies


def _cleanup_status_artifacts(dry_run: bool) -> list[str]:
    removed: list[str] = []
    status = _status_dir()
    patterns = (
        "k12_browser_*report*.json",
        "kapitel12_browser_report*.json",
        "tenant_cleanup_*.json",
    )
    for pat in patterns:
        for path in status.glob(pat):
            removed.append(str(path))
            if not dry_run:
                path.unlink(missing_ok=True)
    soak_dir = status / "gmail_soak"
    if soak_dir.is_dir():
        for path in soak_dir.glob("day_*.json"):
            removed.append(str(path))
            if not dry_run:
                path.unlink(missing_ok=True)
    return removed


def _health_ok() -> bool:
    try:
        with urllib.request.urlopen(f"{API_BASE}/health", timeout=15) as resp:
            return resp.status == 200
    except Exception:
        return False


def _test_read_ok(tenant: str) -> bool:
    for base in TENANT_KEY_DIRS:
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


def _preflight(db: Session, tenant_id: str) -> dict[str, Any]:
    settings = get_settings()
    tenants = [r[0] for r in db.query(TenantConfigRecord.tenant_id).all()]
    sched = TenantConfigRepository.get_settings(db, tenant_id).get("scheduler") or {}
    gmail = gmail_connection_status(db, tenant_id, settings=settings)
    pending = int(
        db.execute(text("SELECT count(*) FROM integration_events WHERE status='pending'")).scalar() or 0
    )
    pf = {
        "health_200": _health_ok(),
        "database_name_ok": _db_name() == REQUIRED_DB_NAME,
        "admin_role_ok": settings.ADMIN_ROLE == "admin",
        "tenant_count": len(tenants),
        "tenant_whitelist_ok": tenants == [tenant_id],
        "scheduler_paused": sched.get("run_mode") == "paused",
        "gmail_tenant_oauth": gmail.get("credential_source") == "tenant_oauth",
        "oauth_row_exists": OAuthCredentialRepository.get(db, tenant_id, PROVIDER) is not None,
        "pending_integration_events": pending,
        "test_read_ok": _test_read_ok(tenant_id),
    }
    pf["pass"] = all(
        [
            pf["health_200"],
            pf["database_name_ok"],
            pf["admin_role_ok"],
            pf["tenant_whitelist_ok"],
            pf["scheduler_paused"],
            pf["gmail_tenant_oauth"],
            pf["oauth_row_exists"],
            pf["pending_integration_events"] == 0,
        ]
    )
    return pf


def _write_audit(db: Session, tenant_id: str, before: dict[str, Any], deleted: dict[str, int]) -> None:
    db.add(
        AuditEventRecord(
            event_id=str(uuid4()),
            tenant_id=tenant_id,
            category="platform",
            action=RESET_AUDIT_ACTION,
            status="succeeded",
            details={
                "before": before,
                "deleted": deleted,
                "preserved": [
                    "tenant_config",
                    "oauth_credentials",
                    "tenant_api_keys",
                    "workflow_scan_checkpoint",
                    "scheduler_paused",
                ],
            },
            created_at=datetime.now(timezone.utc),
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Niklas operational reset (Del I)")
    parser.add_argument("--tenant", default=TENANT_DEFAULT)
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-production-cleanup", action="store_true")
    args = parser.parse_args()
    dry_run = not args.execute
    if args.execute and not args.confirm_production_cleanup:
        print("ERROR: --execute requires --confirm-production-cleanup", file=sys.stderr)
        return 2

    db = SessionLocal()
    report: dict[str, Any] = {
        "report": "niklas_operational_reset",
        "tenant": args.tenant,
        "dry_run": dry_run,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        pf = _preflight(db, args.tenant)
        report["preflight"] = pf
        if not pf["pass"]:
            report["blocked"] = True
            print(json.dumps(report, indent=2, ensure_ascii=False))
            return 1

        before = _snapshot(db, args.tenant)
        report["before"] = before
        report["files_to_remove"] = _cleanup_status_artifacts(dry_run=True)

        if dry_run:
            report["would_delete"] = {
                k: before[k]
                for k in (
                    "jobs",
                    "approvals",
                    "operator_alerts",
                    "integration_events",
                    "action_executions",
                    "audit_events",
                )
                if before.get(k)
            }
            report["after_expected"] = {**before, **{k: 0 for k in report["would_delete"]}}
            report["after_expected"]["audit_events"] = 1
            out = _status_dir() / "niklas_operational_reset_dry_run.json"
            out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
            report["written"] = str(out)
            print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
            return 0

        deleted = _delete_operational_rows(db, args.tenant)
        _write_audit(db, args.tenant, before, deleted)
        db.commit()
        removed_files = _cleanup_status_artifacts(dry_run=False)
        after = _snapshot(db, args.tenant)
        report["deleted"] = deleted
        report["files_removed"] = removed_files
        report["after"] = after
        report["pass"] = (
            after["jobs"] == 0
            and after["approvals"] == 0
            and after["operator_alerts"] == 0
            and after["integration_events"] == 0
            and after["action_executions"] == 0
            and after["tenant_config"] == 1
            and after["oauth_google_mail"] == 1
            and after["scheduler_run_mode"] == "paused"
            and after["gmail_credential_source"] == "tenant_oauth"
        )
        out = _status_dir() / "niklas_operational_reset_report.json"
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        report["written"] = str(out)
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        return 0 if report["pass"] else 1
    except Exception as exc:
        db.rollback()
        report["error"] = type(exc).__name__
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
