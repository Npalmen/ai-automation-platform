#!/usr/bin/env python3
"""Chapter 2: controlled Visma sandbox E2E on production. Safe metadata only on stdout."""
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
STATE_PATH = "/tmp/krowolf_visma_ch2_state.json"


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


def save_state(data: dict) -> None:
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f)


def load_state() -> dict:
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def summarize_preview(body: dict) -> dict:
    draft = body.get("draft") or {}
    payload = body.get("visma_payload") or {}
    invoice = payload.get("invoice") or {}
    rows = invoice.get("Rows") or invoice.get("rows") or []
    return {
        "payload_valid": body.get("status") in ("preview", "dry_run"),
        "line_count": len(rows),
        "amount_ex_vat": draft.get("amount_ex_vat"),
        "amount_inc_vat": draft.get("amount_inc_vat"),
        "currency": draft.get("currency", "SEK"),
        "synthetic_customer": "sandbox" in str(draft.get("supplier_name", "")).lower()
        or "krowolf" in str(draft.get("supplier_name", "")).lower(),
        "write_performed": False,
    }


def phase_create_job() -> dict:
    code = f'''
import json
import uuid
from datetime import datetime, timezone
from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.domain.workflows.statuses import JobStatus
from app.repositories.postgres.database import SessionLocal
from app.repositories.postgres.job_repository import JobRepository
from app.core.audit_service import create_audit_event

tenant_id = "{TENANT}"
now = datetime.now(timezone.utc)
input_data = {{
    "subject": "SANDBOX: Krowolf Visma verifiering",
    "message_text": (
        "Belopp exkl moms 100 kr. Moms 25 kr. Totalt 125 kr. "
        "Krowolf Visma sandbox verifiering."
    ),
    "sender": {{
        "name": "Krowolf Sandbox Kund",
        "email": "sandbox-verifiering@test.krowolf.internal",
        "phone": None,
    }},
    "visma_sandbox_test": True,
    "sandbox_test_marker": "krowolf_visma_chapter2_v6",
}}
processor_history = [
    {{
        "processor": "invoice_processor",
        "result": {{
            "status": "completed",
            "payload": {{
                "invoice_data": {{
                    "invoice_number": "SANDBOX-VISMA-CH2",
                    "due_date": "2026-08-31",
                    "customer_name": "Krowolf Sandbox Kund",
                    "description": "Krowolf Visma sandbox verifiering",
                    "quantity": 1,
                    "unit_price": 100.0,
                    "amount_ex_vat": 100.0,
                    "vat_amount": 25.0,
                    "amount_inc_vat": 125.0,
                    "currency": "SEK",
                }}
            }},
        }},
    }}
]
job = Job(
    job_id=str(uuid.uuid4()),
    tenant_id=tenant_id,
    job_type=JobType.INVOICE,
    status=JobStatus.MANUAL_REVIEW,
    input_data=input_data,
    result={{"sandbox": True, "chapter": "visma_ch2"}},
    processor_history=processor_history,
    created_at=now,
    updated_at=now,
)
db = SessionLocal()
try:
    saved = JobRepository.create_job(db, job)
    create_audit_event(
        db=db,
        tenant_id=tenant_id,
        category="workflow",
        action="visma_sandbox_test_job_created",
        status="success",
        details={{"job_id": saved.job_id, "job_type": "invoice", "sandbox": True}},
    )
    print(json.dumps({{
        "job_id": saved.job_id,
        "job_type": saved.job_type.value if hasattr(saved.job_type, "value") else str(saved.job_type),
        "status": saved.status.value if hasattr(saved.status, "value") else str(saved.status),
        "method": "JobRepository.create_job_no_pipeline",
        "external_action": False,
    }}))
finally:
    db.close()
'''
    return docker_python(code)


def phase_enable_visma() -> dict:
    tenant = api("GET", "/tenant")["body"]
    enabled_types = tenant.get("enabled_job_types") or []
    if "invoice" not in enabled_types:
        enabled_types = list(enabled_types) + ["invoice"]
    body = {
        "enabled_job_types": enabled_types,
        "allowed_integrations": ["google_mail", "google_sheets", "visma"],
        "auto_actions": {
            "lead": False,
            "customer_inquiry": False,
            "invoice": False,
        },
    }
    resp = api("PUT", "/tenant/config", body)
    audit = docker_python(
        f'''
import json
from app.repositories.postgres.database import SessionLocal
from app.core.audit_service import create_audit_event
db = SessionLocal()
try:
    create_audit_event(
        db=db,
        tenant_id="{TENANT}",
        category="tenant",
        action="tenant_integrations_updated",
        status="success",
        details={{"allowed_integrations": ["google_mail", "google_sheets", "visma"], "visma_enabled": True, "chapter": "visma_ch2"}},
    )
    print(json.dumps({{"audited": True}}))
finally:
    db.close()
'''
    )
    settings = docker_python(
        f'''
import json
from app.repositories.postgres.database import SessionLocal
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
db = SessionLocal()
try:
    s = TenantConfigRepository.get_settings(db, "{TENANT}")
    print(json.dumps({{"scheduler_mode": (s.get("scheduler") or {{}}).get("mode"), "demo_mode": s.get("demo_mode")}}))
finally:
    db.close()
'''
    )
    return {"http": resp["http"], "audit": audit, "settings": settings}


def main() -> int:
    phase = (sys.argv[1] if len(sys.argv) > 1 else "all").lower()
    out: dict = {"phase": phase, "tenant": TENANT, "at": datetime.now(timezone.utc).isoformat()}

    if phase in ("create", "all"):
        created = phase_create_job()
        out["create_job"] = created
        if not created.get("ok"):
            print(json.dumps(out, indent=2))
            return 1
        save_state({"job_id": created.get("job_id")})

    state = load_state()
    job_id = state.get("job_id")
    if not job_id and phase != "create":
        print(json.dumps({"error": "missing job_id in state"}, indent=2))
        return 1
    out["job_id_present"] = bool(job_id)

    if phase in ("disabled", "all") and job_id:
        prev = api("POST", f"/finance/invoices/{job_id}/visma/preview")
        exp = api("POST", f"/finance/invoices/{job_id}/visma/export", {})
        out["disabled_preview"] = {
            "http": prev["http"],
            "status": prev["body"].get("status"),
            "summary": summarize_preview(prev["body"]) if prev["http"] == 200 else None,
        }
        out["disabled_export"] = {
            "http": exp["http"],
            "detail": exp["body"].get("detail"),
            "status": exp["body"].get("status"),
        }
        out["disabled_counts"] = {
            "visma_integration_events": psql_count(
                "SELECT count(*) FROM integration_events WHERE integration_type='visma';"
            ),
            "visma_success_events": psql_count(
                "SELECT count(*) FROM integration_events WHERE integration_type='visma' AND status='success';"
            ),
        }

    if phase in ("enable", "all"):
        out["enable_visma"] = phase_enable_visma()
        st = api("GET", "/integrations/visma/status")
        tr = api("POST", "/integrations/visma/test-read")
        out["visma_status"] = {
            "http": st["http"],
            "connected": st["body"].get("connected"),
        }
        out["visma_test_read"] = {
            "http": tr["http"],
            "api_readable": tr["body"].get("api_readable"),
        }

    if phase in ("enabled_preview", "all") and job_id:
        prev2 = api("POST", f"/finance/invoices/{job_id}/visma/preview")
        out["enabled_preview"] = {
            "http": prev2["http"],
            **summarize_preview(prev2["body"]),
        }

    if phase in ("export", "all") and job_id:
        exp2 = api("POST", f"/finance/invoices/{job_id}/visma/export", {})
        body = exp2["body"]
        out["export_request"] = {
            "http": exp2["http"],
            "status": body.get("status"),
            "approval_id_present": bool(body.get("approval_id")),
        }
        save_state({**state, "approval_id": body.get("approval_id")})

    if phase in ("approve", "all"):
        state = load_state()
        approval_id = state.get("approval_id") or f"finance_visma_export:{TENANT}:{job_id}"
        pre = docker_python(
            f'''
import json
from app.repositories.postgres.database import SessionLocal
from app.repositories.postgres.approval_repository import ApprovalRequestRepository
db = SessionLocal()
try:
    rec = ApprovalRequestRepository.get_by_approval_id(db, "{TENANT}", "{approval_id}")
    if rec is None:
        print(json.dumps({{"found": False}}))
    else:
        p = rec.request_payload or {{}}
        print(json.dumps({{
            "found": True,
            "state": p.get("state"),
            "next_on_approve": p.get("next_on_approve"),
            "job_id": rec.job_id,
        }}))
finally:
    db.close()
'''
        )
        out["approval_precheck"] = pre
        success_before = psql_count(
            "SELECT count(*) FROM integration_events WHERE integration_type='visma' AND status='success';"
        )
        recon_before = psql_count(
            "SELECT count(*) FROM integration_events WHERE integration_type='visma' AND status='reconciliation_required';"
        )
        if recon_before > 0:
            out["approve_skipped"] = "reconciliation_required_exists"
        elif pre.get("state") != "pending":
            out["approve_skipped"] = f"approval_state_{pre.get('state')}"
        else:
            appr = api(
                "POST",
                f"/approvals/{approval_id}/approve",
                {"actor": "operator", "channel": "dashboard", "note": "Visma sandbox chapter 2 one-shot approval"},
            )
            out["approve"] = {
                "http": appr["http"],
                "status": appr["body"].get("status"),
                "export_status": (appr["body"].get("export_result") or {}).get("status"),
                "external_id_stored": bool(
                    (appr["body"].get("export_result") or {}).get("external_invoice_id")
                ),
            }
            if appr["http"] >= 500 or appr["body"].get("export_result") is None and appr["http"] == 200:
                out["approve_warning"] = "uncertain_outcome_do_not_retry"
        out["integration_events_after_approve"] = {
            "success": psql_count(
                "SELECT count(*) FROM integration_events WHERE integration_type='visma' AND status='success';"
            ),
            "reconciliation_required": psql_count(
                "SELECT count(*) FROM integration_events WHERE integration_type='visma' AND status='reconciliation_required';"
            ),
            "success_before": success_before,
        }

    if phase in ("idempotency", "all") and job_id:
        exp3 = api("POST", f"/finance/invoices/{job_id}/visma/export", {})
        out["second_export"] = {
            "http": exp3["http"],
            "status": exp3["body"].get("status"),
        }
        state = load_state()
        approval_id = state.get("approval_id") or f"finance_visma_export:{TENANT}:{job_id}"
        appr2 = api(
            "POST",
            f"/approvals/{approval_id}/approve",
            {"actor": "operator", "channel": "dashboard", "note": "duplicate approve check"},
        )
        out["second_approve"] = {
            "http": appr2["http"],
            "status": appr2["body"].get("status"),
            "export_status": (appr2["body"].get("export_result") or {}).get("status"),
        }

    if phase in ("safety", "all"):
        tenant = api("GET", "/tenant")["body"]
        out["safety"] = {
            "visma_in_allowlist": "visma" in (tenant.get("allowed_integrations") or []),
            "auto_actions_all_false": all(not v for v in (tenant.get("auto_actions") or {}).values()),
            "visma_cred_count": psql_count(
                "SELECT count(*) FROM oauth_credentials WHERE provider='visma';"
            ),
            "visma_success_events": psql_count(
                "SELECT count(*) FROM integration_events WHERE integration_type='visma' AND status='success';"
            ),
            "reconciliation_required": psql_count(
                "SELECT count(*) FROM integration_events WHERE integration_type='visma' AND status='reconciliation_required';"
            ),
            "pending_finance_visma_approvals": psql_count(
                "SELECT count(*) FROM approval_requests WHERE tenant_id='"
                + TENANT
                + "' AND approval_id LIKE 'finance_visma_export:%' AND (request_payload->>'state')='pending';"
            ),
        }
        audit = docker_python(
            '''
import json
from app.repositories.postgres.database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
try:
    rows = db.execute(text("""
        SELECT action, status, count(*) AS n
        FROM audit_events
        WHERE tenant_id = :t
          AND action IN (
            'visma_sandbox_test_job_created',
            'tenant_integrations_updated',
            'finance_visma_export'
          )
        GROUP BY action, status
        ORDER BY action, status
    """), {"t": "''' + TENANT + '''"}).fetchall()
    print(json.dumps({"audit_counts": [{"action": r[0], "status": r[1], "count": r[2]} for r in rows]}))
finally:
    db.close()
'''
        )
        out["audit_summary"] = audit
        sandbox = docker_python(
            '''
import json
import requests
from app.repositories.postgres.database import SessionLocal
from app.integrations.visma.token_resolver import resolve_visma_access_token
from app.integrations.visma.client import VismaClient
from app.core.settings import get_settings

db = SessionLocal()
try:
    token = resolve_visma_access_token(db, "''' + TENANT + '''", check_allowlist=False)
    client = VismaClient(token, api_url=get_settings().VISMA_API_URL)
    # Read-only: count recent customer invoices (metadata only)
    resp = requests.get(
        client.api_url.rstrip("/") + "/customerinvoices?$pagesize=5",
        headers=client._headers(),
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    items = data if isinstance(data, list) else data.get("Data") or data.get("items") or []
    sandbox_rows = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        text_blob = " ".join(str(v) for v in item.values() if isinstance(v, (str, int, float))).lower()
        if "krowolf" in text_blob or "sandbox" in text_blob:
            sandbox_rows += 1
    print(json.dumps({
        "read_only": True,
        "recent_invoice_page_count": len(items) if isinstance(items, list) else 0,
        "sandbox_marked_in_page": sandbox_rows,
    }))
except Exception as exc:
    print(json.dumps({"read_only": True, "error_type": type(exc).__name__}))
finally:
    db.close()
'''
        )
        out["sandbox_readonly"] = sandbox

    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
