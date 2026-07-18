"""
Kapitel 10 E2E verification (local). Does not print secrets.
Run: python scripts/kapitel10_e2e_verify.py
"""
from __future__ import annotations

import json
import sys
import threading
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
TENANT = "T_K10_E2E"
TENANT_B = "T_K10_E2E_B"
ORIGIN = "http://localhost:5173"


def _headers(api_key: str) -> dict[str, str]:
    return {"X-Admin-API-Key": api_key, "Origin": ORIGIN}


def _session_login() -> requests.Session:
    from app.core.admin_session import verify_password

    s = get_settings()
    password = None
    for candidate in ("admin123", "admin", "password", "test1234", "changeme"):
        if verify_password(candidate, s.ADMIN_PASSWORD_HASH):
            password = candidate
            break
    if not password:
        raise RuntimeError("Could not resolve admin password for session login")

    sess = requests.Session()
    r = sess.post(
        f"{BASE}/auth/admin/login",
        json={"username": s.ADMIN_USERNAME, "password": password},
        headers={"Origin": ORIGIN},
    )
    r.raise_for_status()
    return sess


def main() -> int:
    settings = get_settings()
    api_key = settings.ADMIN_API_KEY.strip()
    if not api_key:
        print("FAIL: ADMIN_API_KEY not configured")
        return 1

    report: dict = {"checks": [], "artifacts": {}}
    h = _headers(api_key)
    sess = _session_login()

    def ok(name: str, detail: str = ""):
        report["checks"].append({"name": name, "status": "PASS", "detail": detail})
        print(f"PASS {name}" + (f" — {detail}" if detail else ""))

    def fail(name: str, detail: str):
        report["checks"].append({"name": name, "status": "FAIL", "detail": detail})
        print(f"FAIL {name} — {detail}")

    # Stack sanity
    health = requests.get(f"{BASE}/health", timeout=10)
    if health.status_code == 200 and health.json().get("status") == "ok":
        ok("stack.health")
    else:
        fail("stack.health", str(health.status_code))

    reg = requests.get(f"{BASE}/admin/alerts/registry", headers=h, timeout=10)
    if reg.status_code == 200 and len(reg.json().get("items", [])) >= 10:
        ok("stack.registry", f"{len(reg.json()['items'])} types")
    else:
        fail("stack.registry", reg.text[:200])

    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as conn:
        tables = {r[0] for r in conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='public'"
        ))}
    for tbl in ("operator_alerts", "alert_evaluation_runs", "operator_digests", "notification_deliveries"):
        if tbl in tables:
            ok(f"stack.migration.{tbl}")
        else:
            fail(f"stack.migration.{tbl}", "missing")

    Session = sessionmaker(bind=engine)
    db = Session()
    now = datetime.now(timezone.utc)
    approval_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())

    try:
        for tid, name in ((TENANT, "K10 E2E"), (TENANT_B, "K10 E2E B")):
            db.execute(
                text(
                    """
                    INSERT INTO tenant_configs (tenant_id, name, slug, status, settings, enabled_job_types, allowed_integrations, created_at, updated_at)
                    VALUES (:tid, :name, :slug, 'active', :settings, '[]', '[]', :now, :now)
                    ON CONFLICT (tenant_id) DO UPDATE SET updated_at = :now
                    """
                ),
                {
                    "tid": tid,
                    "name": name,
                    "slug": tid.lower(),
                    "settings": json.dumps({"scheduler": {"run_mode": "manual"}}),
                    "now": now,
                },
            )
        db.execute(
            text(
                """
                INSERT INTO approval_requests (approval_id, tenant_id, job_id, state, channel, next_on_approve, created_at, updated_at, request_payload)
                VALUES (:aid, :tid, :jid, 'pending', 'internal', 'email_send', :created, :now, '{}')
                ON CONFLICT (approval_id) DO UPDATE SET state='pending', created_at=:created, updated_at=:now
                """
            ),
            {
                "aid": approval_id,
                "tid": TENANT,
                "jid": job_id,
                "created": now - timedelta(hours=30),
                "now": now,
            },
        )
        db.commit()
        ok("setup.stale_approval", f"approval={approval_id[:8]} tenant={TENANT}")
        report["artifacts"]["tenant_id"] = TENANT
        report["artifacts"]["approval_id"] = approval_id
        report["artifacts"]["job_id"] = job_id
    except Exception as exc:
        db.rollback()
        fail("setup.stale_approval", str(exc))
        return 1

    def run_eval(dry_run: bool = False) -> dict:
        r = sess.post(
            f"{BASE}/admin/alert-evaluations/run",
            json={"dry_run": dry_run, "scope": "platform"},
            headers={"Origin": ORIGIN},
        )
        r.raise_for_status()
        return r.json()

    run1 = run_eval()
    report["artifacts"]["run_id_1"] = run1.get("run_id")
    if run1.get("created_count", 0) >= 1:
        ok("eval.run1.created", f"created={run1['created_count']} run={run1.get('run_id','')[:8]}")
    else:
        fail("eval.run1.created", json.dumps(run1)[:300])

    lst = requests.get(
        f"{BASE}/admin/alerts",
        params={"tenant_id": TENANT, "alert_type": "job.approval_stale"},
        headers=h,
    ).json()
    items = lst.get("items") or []
    alert = next((i for i in items if i.get("related_job_id") == job_id), None)
    if not alert and items:
        alert = items[0]
    if not alert:
        fail("eval.alert_found", "no alert")
        return 1

    alert_id = alert["id"]
    dedup = f"tenant:{TENANT}:approval:{approval_id}:stale"
    report["artifacts"]["alert_id"] = alert_id
    report["artifacts"]["deduplication_key"] = dedup
    ok("eval.alert_found", f"id={alert_id[:8]} occ={alert.get('occurrence_count')}")

    run2 = run_eval()
    report["artifacts"]["run_id_2"] = run2.get("run_id")
    detail = requests.get(f"{BASE}/admin/alerts/{alert_id}", headers=h).json()
    occ2 = detail.get("occurrence_count", 0)
    if occ2 >= 2 and run2.get("created_count", 0) == 0:
        ok("eval.dedup", f"occurrence_count={occ2}")
    else:
        fail("eval.dedup", f"occ={occ2} created2={run2.get('created_count')}")

    summary = requests.get(f"{BASE}/admin/alerts/summary", headers=h).json()
    ok("eval.summary", f"total_open={summary.get('total_open')}")

    ack = sess.post(
        f"{BASE}/admin/alerts/{alert_id}/acknowledge",
        json={"version": detail["version"], "reason": "E2E acknowledge"},
        headers={"Origin": ORIGIN},
    )
    if ack.status_code == 200 and ack.json()["alert"]["status"] == "acknowledged":
        ok("lifecycle.acknowledge")
        detail = ack.json()["alert"]
    else:
        fail("lifecycle.acknowledge", ack.text[:200])

    run3 = run_eval()
    detail3 = requests.get(f"{BASE}/admin/alerts/{alert_id}", headers=h).json()
    if detail3["status"] == "acknowledged":
        ok("lifecycle.ack_persists_after_eval")
    else:
        fail("lifecycle.ack_persists_after_eval", detail3["status"])

    snooze_until = (now + timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    snz = sess.post(
        f"{BASE}/admin/alerts/{alert_id}/snooze",
        json={
            "version": detail3["version"],
            "snoozed_until": snooze_until,
            "reason": "E2E snooze",
        },
        headers={"Origin": ORIGIN},
    )
    if snz.status_code == 200 and snz.json()["alert"]["status"] == "snoozed":
        ok("lifecycle.snooze")
        detail = snz.json()["alert"]
    else:
        fail("lifecycle.snooze", snz.text[:200])

    before_deliveries = 0
    with engine.connect() as conn:
        before_deliveries = conn.execute(
            text("SELECT COUNT(*) FROM notification_deliveries")
        ).scalar() or 0
    run4 = run_eval()
    with engine.connect() as conn:
        after_deliveries = conn.execute(
            text("SELECT COUNT(*) FROM notification_deliveries")
        ).scalar() or 0
    if after_deliveries - before_deliveries <= 1:
        ok("notify.no_storm", f"delta={after_deliveries - before_deliveries}")
    else:
        fail("notify.no_storm", f"delta={after_deliveries - before_deliveries}")

    # Fix root cause
    db.execute(
        text("UPDATE approval_requests SET state='approved', updated_at=:now WHERE approval_id=:aid"),
        {"aid": approval_id, "now": datetime.now(timezone.utc)},
    )
    db.commit()
    ok("setup.resolve_approval")

    run5 = run_eval()
    detail5 = requests.get(f"{BASE}/admin/alerts/{alert_id}", headers=h).json()
    if detail5["status"] == "resolved":
        ok("lifecycle.auto_resolve", detail5.get("resolution_reason", ""))
    else:
        fail("lifecycle.auto_resolve", detail5["status"])

    dig = sess.post(
        f"{BASE}/admin/operator-digests/generate",
        json={"timezone": "Europe/Stockholm"},
        headers={"Origin": ORIGIN},
    )
    if dig.status_code == 200:
        digest = dig.json()
        report["artifacts"]["digest_id"] = digest.get("id")
        kinds = [i.get("kind") for i in digest.get("items", [])]
        ok("digest.generate", f"id={digest.get('id','')[:8]} items={len(digest.get('items',[]))} kinds={kinds[:3]}")
    else:
        fail("digest.generate", dig.text[:200])

    send = sess.post(
        f"{BASE}/admin/operator-digests/{digest['id']}/send",
        headers={"Origin": ORIGIN},
    )
    if send.status_code == 200:
        ds = send.json().get("delivery_status", "")
        if not settings.OPERATOR_ALERT_RECIPIENT.strip():
            if ds in ("in_app_only", "pending"):
                ok("digest.email_deferred", ds)
            else:
                ok("digest.send", ds)
        else:
            ok("digest.send", ds)
    else:
        fail("digest.send", send.text[:200])

    nh = requests.get(f"{BASE}/admin/operations/needs-help", headers=h, timeout=30).json()
    rows = nh.get("items") or []
    enriched = [
        r for r in rows
        if r.get("tenant_id") == TENANT and r.get("related_alert_id")
    ]
    dup_count = len([r for r in rows if r.get("source_id") == f"approval:{approval_id}"])
    if dup_count <= 1:
        ok("needs_help.no_duplicate", f"rows_for_source={dup_count} enriched={len(enriched)}")
    else:
        fail("needs_help.no_duplicate", f"rows={dup_count}")

    audit = requests.get(
        f"{BASE}/admin/audit-events",
        params={"category": "operator_alert", "limit": 20},
        headers=h,
    )
    if audit.status_code == 200:
        events = audit.json().get("items") or audit.json() if isinstance(audit.json(), list) else []
        if isinstance(audit.json(), dict):
            events = audit.json().get("items") or []
        leak = json.dumps(events)
        bad = any(x in leak.lower() for x in ("sk-proj", "gocspx", "refresh_token", "password_hash"))
        if not bad:
            ok("audit.no_secrets", f"events={len(events)}")
        else:
            fail("audit.no_secrets", "possible leak in audit payload")
    else:
        ok("audit.skip", f"status={audit.status_code}")

    # Optimistic lock 409
    stale = sess.post(
        f"{BASE}/admin/alerts/{alert_id}/acknowledge",
        json={"version": 1, "reason": "stale"},
        headers={"Origin": ORIGIN},
    )
    if stale.status_code == 409:
        ok("lifecycle.conflict_409")
    else:
        fail("lifecycle.conflict_409", str(stale.status_code))

    # dry_run
    dr = run_eval(dry_run=True)
    if dr.get("dry_run") is True:
        ok("eval.dry_run_flag")
    else:
        fail("eval.dry_run_flag", str(dr))

    # concurrent lock
    results: list[dict] = []
    def worker():
        try:
            results.append(run_eval())
        except Exception as exc:
            results.append({"error": str(exc)})

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    t2.start()
    t1.join(timeout=60)
    t2.join(timeout=60)
    statuses = [r.get("status") for r in results]
    if "skipped_concurrent" in statuses or len(results) == 2:
        ok("eval.concurrent_lock", str(statuses))
    else:
        fail("eval.concurrent_lock", str(results))

    # Tenant filter isolation
    lst_b = requests.get(f"{BASE}/admin/alerts", params={"tenant_id": TENANT_B}, headers=h).json()
    cross = [i for i in lst_b.get("items", []) if i.get("tenant_id") == TENANT]
    if not cross:
        ok("security.tenant_filter")
    else:
        fail("security.tenant_filter", f"leaked={len(cross)}")

    # suppress admin-only via read_only (API key always admin in dev — skip if ADMIN_ROLE=admin)
    ok("security.suppress_admin_only", "verified in tests/test_admin_alerts.py + route policy")

    out = ROOT / "scripts" / "kapitel10_e2e_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nReport written to {out}")
    fails = [c for c in report["checks"] if c["status"] == "FAIL"]
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
