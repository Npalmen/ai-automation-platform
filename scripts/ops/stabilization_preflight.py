#!/usr/bin/env python3
"""Del A preflight — secret-free pilot stabilization checks."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

from sqlalchemy import func, text

from app.core.settings import get_settings
from app.integrations.google.oauth_token_resolver import PROVIDER, gmail_connection_status
from app.repositories.postgres.database import SessionLocal
from app.repositories.postgres.oauth_credential_repository import OAuthCredentialRepository
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
from app.repositories.postgres.tenant_config_models import TenantConfigRecord

TENANT = "T_NIKLAS_DEMO_001"
API_BASE = "https://api.krowolf.se"


def _backup_summary() -> dict:
    for base in (Path("/opt/krowolf/storage/status"), Path("/app/storage/status")):
        p = base / "backup_status.json"
        if p.is_file():
            d = json.loads(p.read_text(encoding="utf-8"))
            return {
                "status": d.get("status"),
                "completed_at": d.get("completed_at"),
                "offsite_status": d.get("offsite_status"),
                "offsite_verified": d.get("offsite_verified"),
                "backup_id": d.get("backup_id"),
                "checksum_prefix": (d.get("checksum_sha256") or "")[:16] or None,
            }
    return {"status": "missing"}


def main() -> int:
    settings = get_settings()
    db = SessionLocal()
    report: dict = {"tenant": TENANT}
    try:
        try:
            with urllib.request.urlopen(f"{API_BASE}/health", timeout=15) as resp:
                report["health_http"] = resp.status
        except Exception:
            report["health_http"] = 0

        tenants = [r[0] for r in db.query(TenantConfigRecord.tenant_id).order_by(TenantConfigRecord.tenant_id).all()]
        sched = TenantConfigRepository.get_settings(db, TENANT).get("scheduler") or {}
        status = gmail_connection_status(db, TENANT, settings=settings)
        row = OAuthCredentialRepository.get(db, TENANT, PROVIDER)
        pending = db.execute(
            text("SELECT count(*) FROM integration_events WHERE status='pending'")
        ).scalar()

        report.update(
            {
                "admin_role": settings.ADMIN_ROLE,
                "database_url_dbname": "ai_platform",
                "tenant_count": len(tenants),
                "tenants": tenants,
                "scheduler_run_mode": sched.get("run_mode"),
                "gmail_credential_source": status.get("credential_source"),
                "gmail_connected": status.get("connected"),
                "oauth_row_exists": row is not None,
                "pending_integration_events": int(pending or 0),
                "backup": _backup_summary(),
            }
        )
        blockers = []
        if report["health_http"] != 200:
            blockers.append("health")
        if report["tenant_count"] != 1 or tenants != [TENANT]:
            blockers.append("tenant_whitelist")
        if sched.get("run_mode") != "paused":
            blockers.append("scheduler")
        if status.get("credential_source") != "tenant_oauth":
            blockers.append("gmail_credential_source")
        if not row:
            blockers.append("oauth_row_missing")
        b = report["backup"]
        if not (b.get("status") == "success" and b.get("offsite_verified")):
            blockers.append("backup")
        if pending:
            blockers.append("pending_dispatch")
        report["blockers"] = blockers
        report["pass"] = not blockers
    finally:
        db.close()

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
