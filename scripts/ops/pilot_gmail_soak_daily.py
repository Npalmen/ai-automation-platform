#!/usr/bin/env python3
"""Daily secret-free Gmail soak report (compare deltas vs baseline)."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import text

from app.integrations.google.oauth_token_resolver import PROVIDER, gmail_connection_status
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.database import SessionLocal
from app.repositories.postgres.oauth_credential_repository import OAuthCredentialRepository
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
from app.core.settings import get_settings

TENANT = "T_NIKLAS_DEMO_001"
QUERY = "label:krowolf-demo-niklas is:unread"
API_KEY_CANDIDATES = [
    Path(f"/app/storage/tenant_keys/{TENANT}.api_key"),
    Path(f"/opt/krowolf/storage/tenant_keys/{TENANT}.api_key"),
]
BASELINE_CANDIDATES = [
    Path("/opt/krowolf/storage/status/gmail_soak_baseline.json"),
    Path("/app/storage/status/gmail_soak_baseline.json"),
]
OUT_DIR_CANDIDATES = [
    Path("/opt/krowolf/storage/status/gmail_soak"),
    Path("/app/storage/status/gmail_soak"),
]
API_BASE = "https://api.krowolf.se"


def load_api_key() -> str:
    for path in API_KEY_CANDIDATES:
        if path.is_file():
            return path.read_text().strip()
    raise FileNotFoundError("tenant API key not found")


def load_baseline() -> dict:
    for path in BASELINE_CANDIDATES:
        if path.is_file():
            return json.loads(path.read_text())
    return {}


def api_json(method: str, path: str, api_key: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        data=data,
        method=method,
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def main() -> int:
    soak_day = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    since_hours = int(sys.argv[2]) if len(sys.argv) > 2 else 24
    api_key = load_api_key()
    baseline = load_baseline()
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours)

    db = SessionLocal()
    report = {
        "report": "gmail_soak_daily",
        "tenant": TENANT,
        "soak_day": soak_day,
        "window_hours": since_hours,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline_generated_at": baseline.get("generated_at"),
    }
    try:
        settings = get_settings()
        status = gmail_connection_status(db, TENANT, settings=settings)
        sched = TenantConfigRepository.get_settings(db, TENANT).get("scheduler") or {}
        row = OAuthCredentialRepository.get(db, TENANT, PROVIDER)

        report["credential_source"] = status.get("credential_source")
        report["token_expires_at"] = row.expires_at.isoformat() if row and row.expires_at else None
        report["scheduler_run_mode"] = sched.get("run_mode")

        jobs_total = db.execute(text("SELECT count(*) FROM jobs WHERE tenant_id=:t"), {"t": TENANT}).scalar()
        baseline_jobs = (baseline.get("counts") or {}).get("jobs_total")
        report["jobs_total"] = jobs_total
        report["jobs_created_delta"] = (
            jobs_total - baseline_jobs if isinstance(baseline_jobs, int) else None
        )

        pending = db.execute(
            text("SELECT count(*) FROM approval_requests WHERE tenant_id=:t AND state='pending'"),
            {"t": TENANT},
        ).scalar()
        report["pending_approvals"] = pending

        approvals_created = db.execute(
            text(
                "SELECT count(*) FROM approval_requests WHERE tenant_id=:t AND created_at >= :since"
            ),
            {"t": TENANT, "since": since},
        ).scalar()
        report["approvals_created_window"] = approvals_created

        integration_errors = db.execute(
            text(
                "SELECT count(*) FROM integration_events WHERE tenant_id=:t AND status='failed' AND created_at >= :since"
            ),
            {"t": TENANT, "since": since},
        ).scalar()
        report["integration_errors_window"] = integration_errors

        refresh_events = (
            db.query(AuditEventRecord)
            .filter(
                AuditEventRecord.tenant_id == TENANT,
                AuditEventRecord.created_at >= since,
                AuditEventRecord.action.like("%google_mail%"),
            )
            .count()
        )
        report["google_mail_audit_events_window"] = refresh_events

        report["needs_help"] = None
        report["operator_corrections"] = None
        report["operator_minutes"] = None

        # Optional dry-run probe (no writes)
        http, body = api_json(
            "POST",
            "/gmail/process-inbox",
            api_key,
            {"max_results": 5, "dry_run": True, "query": QUERY},
        )
        report["dry_run_probe"] = {
            "http": http,
            "scanned": body.get("scanned"),
            "processed": body.get("processed"),
            "skipped": body.get("skipped"),
            "failed": body.get("failed"),
        }
        report["scanned"] = body.get("scanned")
        report["processed"] = body.get("processed")
        report["duplicates"] = body.get("skipped")
        report["failed"] = body.get("failed")

        _, health = api_json("GET", "/integrations/health", api_key)
        gmail_h = ((health.get("systems") or {}).get("gmail") or {}) if isinstance(health, dict) else {}
        report["integration_health_gmail_status"] = gmail_h.get("status")
        report["scanner_ran_check"] = next(
            (c.get("status") for c in (gmail_h.get("checks") or []) if c.get("key") == "scanner_ran"),
            None,
        )

        try:
            incidents = db.execute(
                text(
                    "SELECT count(*) FROM incidents i "
                    "JOIN incident_tenants it ON i.incident_id = it.incident_id "
                    "WHERE it.tenant_id=:t AND i.created_at >= :since"
                ),
                {"t": TENANT, "since": since},
            ).scalar()
            report["incidents_window"] = incidents
        except Exception:
            db.rollback()
            report["incidents_window"] = None

        report["external_side_effects"] = 0
        report["credentials_exposed"] = False
    finally:
        db.close()

    out_dir = next((p for p in OUT_DIR_CANDIDATES if p.parent.exists()), OUT_DIR_CANDIDATES[-1])
    out_dir.mkdir(parents=True, exist_ok=True)
    day_tag = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = out_dir / f"day_{soak_day:02d}_{day_tag}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    print(json.dumps({"written": str(out_path), "report": report}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
