"""Verify alert reopen after auto-resolve (Kapitel 10 lifecycle)."""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from app.core.settings import get_settings  # noqa: E402

BASE = "http://127.0.0.1:8000"
TENANT = "T_K10_REOPEN"
ORIGIN = "http://localhost:5173"


def main() -> int:
    settings = get_settings()
    h = {"X-Admin-API-Key": settings.ADMIN_API_KEY.strip(), "Origin": ORIGIN}
    engine = create_engine(settings.DATABASE_URL)
    Session = sessionmaker(bind=engine)
    db = Session()
    now = datetime.now(timezone.utc)
    stale_at = now - timedelta(hours=48)

    job_id = str(uuid.uuid4())
    approval_id = str(uuid.uuid4())
    stale_at = now - timedelta(hours=48)

    db.execute(
        text(
            """
            INSERT INTO tenant_configs (tenant_id, name, slug, status, settings, enabled_job_types, allowed_integrations, created_at, updated_at)
            VALUES (:tid, 'K10 Reopen', :slug, 'active', '{}', '[]', '[]', :now, :now)
            ON CONFLICT (tenant_id) DO NOTHING
            """
        ),
        {"tid": TENANT, "slug": TENANT.lower(), "now": now},
    )
    db.execute(
        text(
            """
            INSERT INTO approval_requests (approval_id, tenant_id, job_id, state, channel, next_on_approve, created_at, updated_at, request_payload)
            VALUES (:aid, :tid, :jid, 'pending', 'internal', 'email_send', :created, :now, '{}')
            """
        ),
        {"aid": approval_id, "tid": TENANT, "jid": job_id, "created": stale_at, "now": now},
    )
    db.commit()

    run1 = requests.post(
        f"{BASE}/admin/alert-evaluations/run",
        json={"scope": "platform"},
        headers=h,
        timeout=120,
    ).json()
    alerts = requests.get(
        f"{BASE}/admin/alerts",
        params={"tenant_id": TENANT, "alert_type": "job.approval_stale"},
        headers=h,
    ).json()
    items = alerts.get("items") or []
    if not items:
        print("FAIL reopen: no alert created")
        return 1
    alert_id = items[0]["id"]
    print(f"created alert {alert_id[:8]}")

    db.execute(
        text("UPDATE approval_requests SET state='approved', updated_at=:now WHERE approval_id=:aid"),
        {"aid": approval_id, "now": now},
    )
    db.commit()
    requests.post(
        f"{BASE}/admin/alert-evaluations/run",
        json={"scope": "platform"},
        headers=h,
        timeout=120,
    )
    resolved = requests.get(f"{BASE}/admin/alerts/{alert_id}", headers=h).json()
    if resolved["status"] != "resolved":
        print(f"FAIL reopen: expected resolved, got {resolved['status']}")
        return 1
    print("resolved OK")

    # Simulate problem returning after reopen grace (15 min policy on job.approval_stale).
    grace_cutoff = now - timedelta(minutes=20)
    db.execute(
        text(
            "UPDATE operator_alerts SET resolved_at=:cutoff WHERE id=:aid"
        ),
        {"aid": alert_id, "cutoff": grace_cutoff},
    )

    db.execute(
        text(
            "UPDATE approval_requests SET state='pending', updated_at=:stale WHERE approval_id=:aid"
        ),
        {"aid": approval_id, "stale": stale_at},
    )
    db.commit()
    requests.post(
        f"{BASE}/admin/alert-evaluations/run",
        json={"scope": "platform"},
        headers=h,
        timeout=120,
    )
    reopened = requests.get(f"{BASE}/admin/alerts/{alert_id}", headers=h).json()
    if reopened["status"] == "open":
        print(f"PASS reopen: status=open version={reopened['version']}")
        return 0
    print(f"FAIL reopen: status={reopened['status']}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
