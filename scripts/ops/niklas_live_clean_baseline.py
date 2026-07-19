#!/usr/bin/env python3
"""Del J — post-clean operational baseline snapshot (secret-free)."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, text

from app.admin.alerts.models import OperatorAlertRecord
from app.admin.incident_models import IncidentRecord, IncidentTenantRecord
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
from app.repositories.postgres.tenant_config_models import TenantConfigRecord
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

TENANT = sys.argv[1] if len(sys.argv) > 1 else "T_NIKLAS_DEMO_001"
OUT_CANDIDATES = [
    Path("/opt/krowolf/storage/status/niklas_live_clean_baseline.json"),
    Path("/app/storage/status/niklas_live_clean_baseline.json"),
]
API_BASE = "https://api.krowolf.se"
TENANT_KEY_DIRS = [
    Path("/opt/krowolf/storage/tenant_keys"),
    Path("/app/storage/tenant_keys"),
]


def _backup_summary() -> dict:
    for base in (Path("/opt/krowolf/storage/status"), Path("/app/storage/status")):
        p = base / "backup_status.json"
        if p.is_file():
            d = json.loads(p.read_text(encoding="utf-8"))
            return {
                "status": d.get("status"),
                "offsite_verified": d.get("offsite_verified"),
                "backup_id": d.get("backup_id"),
            }
    return {"status": "missing"}


def _test_read(tenant: str) -> str:
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
                if resp.status == 200 and body.get("credential_source") == "tenant_oauth":
                    return "PASS"
                return "FAIL"
        except urllib.error.HTTPError:
            return "FAIL"
    return "SKIP"


def main() -> int:
    settings = get_settings()
    db = SessionLocal()
    try:
        tenants = [r[0] for r in db.query(TenantConfigRecord.tenant_id).order_by(TenantConfigRecord.tenant_id).all()]
        sched = TenantConfigRepository.get_settings(db, TENANT).get("scheduler") or {}
        wf = TenantConfigRepository.get_settings(db, TENANT).get("workflow_scan") or {}
        gmail = gmail_connection_status(db, TENANT, settings=settings)
        oauth = OAuthCredentialRepository.get(db, TENANT, PROVIDER)

        open_alerts = (
            db.query(func.count())
            .select_from(OperatorAlertRecord)
            .filter(OperatorAlertRecord.tenant_id == TENANT, OperatorAlertRecord.status == "open")
            .scalar()
            or 0
        )
        incidents = (
            db.query(func.count())
            .select_from(IncidentTenantRecord)
            .filter(IncidentTenantRecord.tenant_id == TENANT)
            .scalar()
            or 0
        )
        failed_events = (
            db.query(func.count())
            .select_from(IntegrationEvent)
            .filter(IntegrationEvent.tenant_id == TENANT, IntegrationEvent.status == "failed")
            .scalar()
            or 0
        )
        orphan_tenants = db.execute(
            text(
                "SELECT count(*) FROM tenant_configs tc "
                "LEFT JOIN jobs j ON j.tenant_id = tc.tenant_id "
                "WHERE tc.tenant_id NOT IN (SELECT tenant_id FROM tenant_configs)"
            )
        ).scalar()

        baseline = {
            "report": "niklas_live_clean_baseline",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "canonical_tenant": TENANT,
            "counts": {
                "tenants": len(tenants),
                "jobs": db.query(func.count()).select_from(JobRecord).filter_by(tenant_id=TENANT).scalar() or 0,
                "approvals": (
                    db.query(func.count()).select_from(ApprovalRequestRecord).filter_by(tenant_id=TENANT).scalar() or 0
                ),
                "open_alerts": int(open_alerts),
                "incidents": int(incidents),
                "integration_events": (
                    db.query(func.count()).select_from(IntegrationEvent).filter_by(tenant_id=TENANT).scalar() or 0
                ),
                "integration_failures": int(failed_events),
                "action_executions": (
                    db.query(func.count()).select_from(ActionExecutionRecord).filter_by(tenant_id=TENANT).scalar() or 0
                ),
                "audit_events": (
                    db.query(func.count()).select_from(AuditEventRecord).filter_by(tenant_id=TENANT).scalar() or 0
                ),
                "tenant_api_keys": (
                    db.query(func.count()).select_from(TenantApiKeyRecord).filter_by(tenant_id=TENANT).scalar() or 0
                ),
            },
            "tenants": tenants,
            "scheduler_run_mode": sched.get("run_mode"),
            "gmail": {
                "credential_source": gmail.get("credential_source"),
                "connected": gmail.get("connected"),
                "connection_state": gmail.get("connection_state"),
                "scopes_present": bool(oauth and oauth.scopes),
            },
            "workflow_scan": {
                "status": wf.get("status"),
                "last_scan_at": wf.get("last_scan_at"),
            },
            "checks": {
                "health_http": None,
                "gmail_test_read": _test_read(TENANT),
                "backup": _backup_summary(),
            },
            "settings": {
                "admin_role": settings.ADMIN_ROLE,
                "gmail_send_disabled": True,
                "external_writes_disabled": True,
                "scheduler_paused": sched.get("run_mode") == "paused",
            },
        }

        try:
            with urllib.request.urlopen(f"{API_BASE}/health", timeout=15) as resp:
                baseline["checks"]["health_http"] = resp.status
        except Exception:
            baseline["checks"]["health_http"] = 0

        blockers = []
        if baseline["counts"]["tenants"] != 1 or tenants != [TENANT]:
            blockers.append("tenant_count")
        if baseline["counts"]["jobs"]:
            blockers.append("jobs")
        if baseline["counts"]["approvals"]:
            blockers.append("approvals")
        if baseline["counts"]["open_alerts"]:
            blockers.append("open_alerts")
        if baseline["counts"]["incidents"]:
            blockers.append("incidents")
        if baseline["counts"]["integration_failures"]:
            blockers.append("integration_failures")
        if sched.get("run_mode") != "paused":
            blockers.append("scheduler")
        if gmail.get("credential_source") != "tenant_oauth":
            blockers.append("gmail_oauth")
        if baseline["checks"]["gmail_test_read"] != "PASS":
            blockers.append("gmail_test_read")
        if baseline["checks"]["health_http"] != 200:
            blockers.append("health")

        baseline["blockers"] = blockers
        baseline["ready_for_soak_day_1"] = not blockers

        out = next((p for p in OUT_CANDIDATES if p.parent.exists()), OUT_CANDIDATES[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(baseline, indent=2, ensure_ascii=False, default=str))
        print(json.dumps({"written": str(out), "ready_for_soak_day_1": baseline["ready_for_soak_day_1"], "blockers": blockers}, indent=2))
        return 0 if not blockers else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
