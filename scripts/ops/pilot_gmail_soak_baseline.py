#!/usr/bin/env python3
"""Secret-free Day-0 baseline for 7-day Gmail soak (T_NIKLAS_DEMO_001)."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from app.core.settings import get_settings
from app.integrations.google.oauth_token_resolver import PROVIDER, gmail_connection_status
from app.repositories.postgres.database import SessionLocal
from app.repositories.postgres.oauth_credential_repository import OAuthCredentialRepository
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

TENANT = "T_NIKLAS_DEMO_001"
API_KEY_CANDIDATES = [
    Path(f"/app/storage/tenant_keys/{TENANT}.api_key"),
    Path(f"/opt/krowolf/storage/tenant_keys/{TENANT}.api_key"),
]
OUT_CANDIDATES = [
    Path("/opt/krowolf/storage/status/gmail_soak_baseline.json"),
    Path("/app/storage/status/gmail_soak_baseline.json"),
]
API_BASE = "https://api.krowolf.se"


def load_api_key() -> str:
    for path in API_KEY_CANDIDATES:
        if path.is_file():
            return path.read_text().strip()
    raise FileNotFoundError("tenant API key not found")


def api_json(method: str, path: str, api_key: str, body: dict | None = None) -> tuple[int, dict | str]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        data=data,
        method=method,
        headers={"X-API-Key": api_key, "Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw[:300]


def scope_flags(scopes: str | None) -> dict:
    s = scopes or ""
    return {
        "gmail_readonly": "gmail.readonly" in s,
        "gmail_modify": "gmail.modify" in s,
        "gmail_send": "gmail.send" in s,
        "spreadsheets": "spreadsheets" in s,
    }


def main() -> int:
    api_key = load_api_key()
    settings = get_settings()
    db = SessionLocal()
    report: dict = {
        "report": "gmail_soak_baseline",
        "tenant": TENANT,
        "soak_day": 0,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        settings_row = TenantConfigRepository.get_settings(db, TENANT) or {}
        sched = settings_row.get("scheduler") or {}
        workflow_scan = settings_row.get("workflow_scan") or {}

        row = OAuthCredentialRepository.get(db, TENANT, PROVIDER)
        status = gmail_connection_status(db, TENANT, settings=settings)
        meta = (row.metadata_json or {}) if row else {}

        report["credential"] = {
            "oauth_row_exists": row is not None,
            "credential_source": status.get("credential_source"),
            "connection_state": status.get("connection_state"),
            "email_domain": (meta.get("email") or status.get("email") or "").split("@")[-1] or None,
            "expires_at": row.expires_at.isoformat() if row and row.expires_at else None,
            "access_token_set": bool(row and row.access_token),
            "refresh_token_set": bool(row and row.refresh_token),
            "scopes_flags": scope_flags(row.scopes if row else None),
            "connected_via": meta.get("connected_via"),
        }

        report["scheduler"] = {
            "run_mode": sched.get("run_mode"),
            "scheduler_enabled": sched.get("run_mode") not in (None, "", "paused", "manual"),
        }

        report["gmail_checkpoint"] = {
            "workflow_scan_status": workflow_scan.get("status"),
            "last_scan_at": workflow_scan.get("last_scan_at"),
            "systems_scanned": workflow_scan.get("systems_scanned"),
            "gmail_summary_status": ((workflow_scan.get("summary") or {}).get("gmail") or {}).get("status"),
            "label_scope": "krowolf-demo-niklas",
            "query": "label:krowolf-demo-niklas is:unread",
        }

        report["counts"] = {
            "jobs_by_type": {
                r[0]: r[1]
                for r in db.execute(
                    text("SELECT job_type, count(*) FROM jobs WHERE tenant_id=:t GROUP BY job_type"),
                    {"t": TENANT},
                )
            },
            "jobs_by_status": {
                r[0]: r[1]
                for r in db.execute(
                    text("SELECT status, count(*) FROM jobs WHERE tenant_id=:t GROUP BY status"),
                    {"t": TENANT},
                )
            },
            "jobs_total": db.execute(
                text("SELECT count(*) FROM jobs WHERE tenant_id=:t"), {"t": TENANT}
            ).scalar(),
            "approvals_by_state": {
                r[0]: r[1]
                for r in db.execute(
                    text("SELECT state, count(*) FROM approval_requests WHERE tenant_id=:t GROUP BY state"),
                    {"t": TENANT},
                )
            },
            "audit_events_total": db.execute(
                text("SELECT count(*) FROM audit_events WHERE tenant_id=:t"), {"t": TENANT}
            ).scalar(),
            "integration_events_total": db.execute(
                text("SELECT count(*) FROM integration_events WHERE tenant_id=:t"), {"t": TENANT}
            ).scalar(),
            "integration_errors": db.execute(
                text(
                    "SELECT count(*) FROM integration_events WHERE tenant_id=:t AND status = 'failed'"
                ),
                {"t": TENANT},
            ).scalar(),
        }

        try:
            report["counts"]["operator_alerts"] = {
                r[0]: r[1]
                for r in db.execute(
                    text("SELECT status, count(*) FROM operator_alerts WHERE tenant_id=:t GROUP BY status"),
                    {"t": TENANT},
                )
            }
        except Exception:
            db.rollback()
            report["counts"]["operator_alerts"] = None

        try:
            report["counts"]["incidents"] = {
                r[0]: r[1]
                for r in db.execute(
                    text(
                        "SELECT i.status, count(*) FROM incidents i "
                        "JOIN incident_tenants it ON i.incident_id = it.incident_id "
                        "WHERE it.tenant_id=:t GROUP BY i.status"
                    ),
                    {"t": TENANT},
                )
            }
        except Exception:
            db.rollback()
            report["counts"]["incidents"] = None

        report["counts"]["needs_help"] = None

        _, health = api_json("GET", "/integrations/health", api_key)
        if isinstance(health, dict):
            gmail_h = (health.get("systems") or {}).get("gmail") or {}
            report["integration_health_gmail"] = {
                "status": gmail_h.get("status"),
                "checks": [
                    {k: c.get(k) for k in ("key", "status", "description")}
                    for c in (gmail_h.get("checks") or [])
                ],
                "recent_errors_count": len(health.get("recent_errors") or []),
            }

        _, pending = api_json("GET", "/approvals/pending?limit=50", api_key)
        report["pending_approvals_api"] = pending.get("total") if isinstance(pending, dict) else None

        backup = {}
        for name in ("backup_status.json", "offsite_backup_status.json"):
            for base in (Path("/opt/krowolf/storage/status"), Path("/app/storage/status")):
                p = base / name
                if p.exists():
                    data = json.loads(p.read_text())
                    backup[name] = {
                        k: data.get(k)
                        for k in ("status", "completed_at", "offsite_status", "offsite_verified")
                        if k in data
                    }
                    break
        report["backup"] = backup

        report["soak_policy"] = {
            "gmail_send_disabled": True,
            "platform_env_not_used_for_tenant_gmail": status.get("credential_source") == "tenant_oauth",
            "scheduler_stays_paused": sched.get("run_mode") == "paused",
            "approval_first": settings_row.get("auto_actions") in (False, "semi", None, "false"),
            "allowed_scopes_in_use": ["gmail.readonly", "gmail.modify"],
            "stored_grant_note": "Google grant may include legacy gmail.send + spreadsheets; Krowolf must not invoke them.",
        }
    finally:
        db.close()

    out_path = next((p for p in OUT_CANDIDATES if p.parent.exists()), OUT_CANDIDATES[-1])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    print(json.dumps({"written": str(out_path), "credential_source": report.get("credential", {}).get("credential_source")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
