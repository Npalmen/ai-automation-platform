#!/usr/bin/env python3
"""Chapter 3: stale approval cleanup, sandbox inspection, production verification.

Safe metadata only on stdout. No Visma writes.
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

TENANT = "T_NIKLAS_DEMO_001"
API_KEY_PATH = f"/opt/krowolf/storage/tenant_keys/{TENANT}.api_key"
BASE = "https://api.krowolf.se"
REJECT_NOTE = "Stängt efter misslyckat Visma sandbox-test före ArticleId-fix."
SUCCESS_MARKER = "krowolf_visma_chapter2_v6"


def api(method: str, path: str, body: dict | None = None) -> dict:
    key = open(API_KEY_PATH, encoding="utf-8").read().strip()
    headers = {"X-API-Key": key, "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode()
            return {"http": resp.status, "body": json.loads(raw) if raw else {}}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"detail": raw[:300]}
        return {"http": exc.code, "body": parsed}


def psql_count(sql: str) -> int:
    proc = subprocess.run(
        [
            "sudo", "docker", "exec", "krowolf-db-1", "psql",
            "-U", "postgres", "-d", "ai_platform", "-t", "-A", "-c", sql,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return int((proc.stdout or "0").strip() or "0")


def docker_python(code: str) -> dict:
    proc = subprocess.run(
        ["sudo", "docker", "exec", "-w", "/app", "krowolf-app-1", "python", "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return {"ok": False, "stderr": proc.stderr[:500]}
    try:
        return {"ok": True, **json.loads(proc.stdout.strip())}
    except json.JSONDecodeError:
        return {"ok": True, "raw": proc.stdout[:500]}


def git_head() -> str:
    proc = subprocess.run(
        ["sudo", "git", "-C", "/opt/krowolf", "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return (proc.stdout or "").strip()


def list_pending_visma_approvals() -> dict:
    return docker_python(
        f'''
import json
from app.repositories.postgres.database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
try:
    rows = db.execute(text("""
        SELECT ar.approval_id, ar.job_id,
               ar.request_payload->>'state' AS state,
               ar.request_payload->>'next_on_approve' AS next_on_approve,
               j.input_data->>'sandbox_test_marker' AS marker,
               (SELECT count(*) FROM integration_events ie
                WHERE ie.tenant_id = ar.tenant_id AND ie.job_id = ar.job_id
                  AND ie.integration_type = 'visma' AND ie.status = 'success') AS success_events,
               (SELECT count(*) FROM integration_events ie
                WHERE ie.tenant_id = ar.tenant_id AND ie.job_id = ar.job_id
                  AND ie.integration_type = 'visma' AND ie.status = 'reconciliation_required') AS recon_events
        FROM approval_requests ar
        LEFT JOIN jobs j ON j.job_id = ar.job_id AND j.tenant_id = ar.tenant_id
        WHERE ar.tenant_id = :tenant
          AND ar.approval_id LIKE 'finance_visma_export:%'
          AND (ar.request_payload->>'state') = 'pending'
        ORDER BY ar.approval_id
    """), {{"tenant": "{TENANT}"}}).fetchall()
    items = []
    for r in rows:
        items.append({{
            "approval_id_suffix_present": bool(r[0]),
            "job_marker": r[4],
            "is_v6_success_job": r[4] == "{SUCCESS_MARKER}",
            "success_events": int(r[5] or 0),
            "recon_events": int(r[6] or 0),
            "next_on_approve": r[3],
            "state": r[2],
        }})
    print(json.dumps({{"count": len(items), "items": items}}))
finally:
    db.close()
'''
    )


def reject_stale_approvals() -> dict:
    pre = list_pending_visma_approvals()
    if not pre.get("ok"):
        return {"error": "list_failed", "pre": pre}
    items = pre.get("items") or []
    stale = [i for i in items if not i.get("is_v6_success_job")]
    v6_pending = [i for i in items if i.get("is_v6_success_job")]
    results = []
    rejected = 0
    skipped = 0
    for item in stale:
        if item.get("is_v6_success_job"):
            skipped += 1
            continue
        if item.get("success_events", 0) > 0:
            skipped += 1
            results.append({"action": "skipped_has_success", "marker": item.get("job_marker")})
            continue
        if item.get("recon_events", 0) > 0:
            skipped += 1
            results.append({"action": "skipped_recon", "marker": item.get("job_marker")})
            continue
        if item.get("next_on_approve") != "finance_visma_export":
            skipped += 1
            results.append({"action": "skipped_wrong_action", "marker": item.get("job_marker")})
            continue
        # Resolve approval_id from DB without printing full id in loop output
        lookup = docker_python(
            f'''
import json
from app.repositories.postgres.database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
try:
    row = db.execute(text("""
        SELECT approval_id FROM approval_requests
        WHERE tenant_id = :tenant
          AND approval_id LIKE 'finance_visma_export:%'
          AND (request_payload->>'state') = 'pending'
          AND job_id IN (
            SELECT job_id FROM jobs
            WHERE tenant_id = :tenant
              AND COALESCE(input_data->>'sandbox_test_marker','') = :marker
            LIMIT 1
          )
        LIMIT 1
    """), {{"tenant": "{TENANT}", "marker": "{item.get('job_marker') or ''}"}}).fetchone()
    print(json.dumps({{"approval_id": row[0] if row else None}}))
finally:
    db.close()
'''
        )
        approval_id = (lookup.get("approval_id") if lookup.get("ok") else None)
        if not approval_id:
            skipped += 1
            results.append({"action": "skipped_not_found", "marker": item.get("job_marker")})
            continue
        resp = api(
            "POST",
            f"/approvals/{approval_id}/reject",
            {
                "actor": "operator",
                "channel": "dashboard",
                "note": REJECT_NOTE,
            },
        )
        ok = resp["http"] == 200 and resp["body"].get("status") == "rejected"
        if ok:
            rejected += 1
        results.append({
            "action": "rejected" if ok else "reject_failed",
            "http": resp["http"],
            "status": resp["body"].get("status"),
            "marker": item.get("job_marker"),
            "export_result_null": resp["body"].get("export_result") is None,
        })
    post = list_pending_visma_approvals()
    approved_v6 = docker_python(
        f'''
import json
from app.repositories.postgres.database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
try:
    row = db.execute(text("""
        SELECT request_payload->>'state' AS state
        FROM approval_requests ar
        JOIN jobs j ON j.job_id = ar.job_id AND j.tenant_id = ar.tenant_id
        WHERE ar.tenant_id = :tenant
          AND ar.approval_id LIKE 'finance_visma_export:%'
          AND j.input_data->>'sandbox_test_marker' = :marker
        LIMIT 1
    """), {{"tenant": "{TENANT}", "marker": "{SUCCESS_MARKER}"}}).fetchone()
    print(json.dumps({{"v6_approval_state": row[0] if row else None}}))
finally:
    db.close()
'''
    )
    success_after = psql_count(
        "SELECT count(*) FROM integration_events WHERE integration_type='visma' AND status='success';"
    )
    return {
        "stale_found": len(stale),
        "v6_still_pending": len(v6_pending),
        "rejected": rejected,
        "skipped": skipped,
        "results": results,
        "pending_after": post.get("count"),
        "v6_approval": approved_v6,
        "visma_success_events_after": success_after,
    }


def inspect_sandbox_artifacts() -> dict:
    return docker_python(
        f'''
import json, requests
from app.repositories.postgres.database import SessionLocal
from app.integrations.visma.token_resolver import resolve_visma_access_token
from app.core.settings import get_settings

db = SessionLocal()
try:
    token = resolve_visma_access_token(db, "{TENANT}", check_allowlist=False)
    base = get_settings().VISMA_API_URL.rstrip("/")
    h = {{"Authorization": f"Bearer {{token}}", "Accept": "application/json"}}
    out = {{"customers": [], "invoices": [], "deletion_via_api": False}}
    cr = requests.get(
        f"{{base}}/customers?$filter=contains(Name,'Krowolf Sandbox')&$pagesize=10",
        headers=h, timeout=30,
    )
    customers = cr.json() if cr.ok else []
    if isinstance(customers, dict):
        customers = customers.get("Data") or []
    for c in customers:
        if not isinstance(c, dict):
            continue
        created = str(c.get("CreatedUtc") or "")
        email = str(c.get("Email") or "")
        out["customers"].append({{
            "name_match": "krowolf sandbox" in str(c.get("Name") or "").lower(),
            "has_sandbox_email": "sandbox-verifiering@test.krowolf.internal" in email.lower(),
            "created_utc_prefix": created[:10] if created else None,
            "is_private_person": c.get("IsPrivatePerson"),
        }})
    ir = requests.get(
        f"{{base}}/customerinvoices?$filter=contains(CustomerName,'Krowolf')&$pagesize=10",
        headers=h, timeout=30,
    )
    invoices = ir.json() if ir.ok else []
    if isinstance(invoices, dict):
        invoices = invoices.get("Data") or []
    for inv in invoices:
        if not isinstance(inv, dict):
            continue
        ref = str(inv.get("YourReference") or inv.get("YourOrderReference") or "")
        note = str(inv.get("NoteText") or "")
        out["invoices"].append({{
            "total": inv.get("TotalAmount") or inv.get("Total"),
            "currency": inv.get("CurrencyCode"),
            "reference_has_ch2": "ch2" in ref.lower() or "sandbox" in ref.lower(),
            "reference_has_diag": "diag" in ref.lower(),
            "note_has_job_marker": "chapter2" in note.lower() or "sandbox" in note.lower(),
            "sent": bool(inv.get("Sent") or inv.get("IsSent")),
            "created_utc_prefix": str(inv.get("CreatedUtc") or "")[:10] or None,
        }})
    out["customer_count"] = len(out["customers"])
    out["invoice_count"] = len(out["invoices"])
    # Visma eAccounting API generally does not expose safe programmatic delete for invoices.
    out["operator_cleanup_recommended"] = (
        "Manual deletion in Visma sandbox UI if available; do not use production API delete."
    )
    print(json.dumps(out))
finally:
    db.close()
'''
    )


def production_verification() -> dict:
    root = api("GET", "/")
    health = api("GET", "/health")
    tenant = api("GET", "/tenant")
    visma_st = api("GET", "/integrations/visma/status")
    visma_tr = api("POST", "/integrations/visma/test-read")
    gmail_st = api("GET", "/integrations/google_mail/status")
    sheets_cfg = docker_python(
        f'''
import json
from app.repositories.postgres.database import SessionLocal
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
db = SessionLocal()
try:
    s = TenantConfigRepository.get_settings(db, "{TENANT}")
    gs = s.get("google_sheets") or {{}}
    print(json.dumps({{
        "sheets_configured": bool(gs.get("spreadsheet_id") or gs.get("leads_sheet") or gs.get("support_sheet")),
        "scheduler_mode": (s.get("scheduler") or {{}}).get("mode"),
    }}))
finally:
    db.close()
'''
    )
    tbody = tenant["body"]
    logs = subprocess.run(
        [
            "sudo", "docker", "logs", "krowolf-app-1", "--tail", "80",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    log_text = logs.stdout or ""
    risky = any(
        p in log_text
        for p in ("Traceback", "ERROR", "500 Internal", "reconciliation_required")
    )
    containers = subprocess.run(
        ["sudo", "docker", "ps", "--format", "{{.Names}} {{.Status}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "head": git_head(),
        "root_http": root["http"],
        "health_http": health["http"],
        "tenant": {
            "allowed_integrations": tbody.get("allowed_integrations"),
            "auto_actions": tbody.get("auto_actions"),
            "auto_all_false": all(not v for v in (tbody.get("auto_actions") or {}).values()),
        },
        "visma_status": {
            "http": visma_st["http"],
            "connected": visma_st["body"].get("connected"),
        },
        "visma_test_read": {
            "http": visma_tr["http"],
            "api_readable": visma_tr["body"].get("api_readable"),
        },
        "gmail_status": {
            "http": gmail_st["http"],
            "connected": gmail_st["body"].get("connected"),
        },
        "sheets": sheets_cfg,
        "visma_cred_count": psql_count(
            "SELECT count(*) FROM oauth_credentials WHERE provider='visma';"
        ),
        "visma_success_events": psql_count(
            "SELECT count(*) FROM integration_events WHERE integration_type='visma' AND status='success';"
        ),
        "visma_recon_events": psql_count(
            "SELECT count(*) FROM integration_events WHERE integration_type='visma' AND status='reconciliation_required';"
        ),
        "visma_failed_events": psql_count(
            "SELECT count(*) FROM integration_events WHERE integration_type='visma' AND status='failed';"
        ),
        "pending_visma_approvals": psql_count(
            "SELECT count(*) FROM approval_requests WHERE tenant_id='"
            + TENANT
            + "' AND approval_id LIKE 'finance_visma_export:%' "
            + "AND (request_payload->>'state')='pending';"
        ),
        "approved_visma_approvals": psql_count(
            "SELECT count(*) FROM approval_requests WHERE tenant_id='"
            + TENANT
            + "' AND approval_id LIKE 'finance_visma_export:%' "
            + "AND (request_payload->>'state')='approved';"
        ),
        "rejected_visma_approvals": psql_count(
            "SELECT count(*) FROM approval_requests WHERE tenant_id='"
            + TENANT
            + "' AND approval_id LIKE 'finance_visma_export:%' "
            + "AND (request_payload->>'state')='rejected';"
        ),
        "containers_running": "krowolf-app-1" in (containers.stdout or "")
            and "krowolf-db-1" in (containers.stdout or "")
            and "krowolf-caddy" in (containers.stdout or ""),
        "app_log_risky_tail": risky,
    }


def golden_path_readonly() -> dict:
    api_key = open(API_KEY_PATH, encoding="utf-8").read().strip()
    daily = api("GET", "/reports/daily-summary")
    pending = api("GET", "/approvals/pending?limit=50")
    control = api("GET", "/dashboard/control")
    manual = api("GET", "/manual-review/jobs?limit=20")
    # Visma idempotency read-only check on v6 job
    v6_job = docker_python(
        f'''
import json
from app.repositories.postgres.database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
try:
    row = db.execute(text("""
        SELECT job_id FROM jobs
        WHERE tenant_id = :tenant
          AND input_data->>'sandbox_test_marker' = :marker
        ORDER BY created_at DESC LIMIT 1
    """), {{"tenant": "{TENANT}", "marker": "{SUCCESS_MARKER}"}}).fetchone()
    print(json.dumps({{"has_v6_job": bool(row)}}))
finally:
    db.close()
'''
    )
    idem = {}
    if v6_job.get("has_v6_job"):
        lookup = docker_python(
            f'''
import json
from app.repositories.postgres.database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
try:
    row = db.execute(text("""
        SELECT job_id FROM jobs WHERE tenant_id=:t AND input_data->>'sandbox_test_marker'=:m LIMIT 1
    """), {{"t": "{TENANT}", "m": "{SUCCESS_MARKER}"}}).fetchone()
    print(json.dumps({{"job_id": row[0] if row else None}}))
finally:
    db.close()
'''
        )
        jid = lookup.get("job_id")
        if jid:
            prev = api("POST", f"/finance/invoices/{jid}/visma/preview")
            exp = api("POST", f"/finance/invoices/{jid}/visma/export", {})
            idem = {
                "preview_http": prev["http"],
                "preview_local_only": prev["body"].get("status") in ("preview", "dry_run"),
                "export_http": exp["http"],
                "export_status": exp["body"].get("status"),
            }
    dbody = daily["body"]
    return {
        "daily_http": daily["http"],
        "daily_has_priority_rows": bool((dbody.get("priority_items") or dbody.get("priority_rows") or [])),
        "daily_has_counters": isinstance(dbody.get("counts") or dbody.get("summary"), dict),
        "pending_approvals_total": pending["body"].get("total"),
        "manual_review_http": manual["http"],
        "manual_review_total": manual["body"].get("total"),
        "scheduler_manual": (control["body"].get("scheduler") or {}).get("run_mode") == "manual",
        "visma_idempotency_check": idem,
        "v6_job_present": v6_job.get("has_v6_job"),
    }


def main() -> int:
    phase = (sys.argv[1] if len(sys.argv) > 1 else "all").lower()
    out: dict = {
        "chapter": 3,
        "tenant": TENANT,
        "at": datetime.now(timezone.utc).isoformat(),
        "phase": phase,
    }
    if phase in ("reject", "all"):
        out["cleanup"] = reject_stale_approvals()
    if phase in ("sandbox", "all"):
        out["sandbox"] = inspect_sandbox_artifacts()
    if phase in ("production", "all"):
        out["production"] = production_verification()
    if phase in ("golden", "all"):
        out["golden"] = golden_path_readonly()
    if phase == "list":
        out["pending"] = list_pending_visma_approvals()
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
