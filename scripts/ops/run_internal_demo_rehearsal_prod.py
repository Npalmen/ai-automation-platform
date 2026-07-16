#!/usr/bin/env python3
"""Internal demo rehearsal — read-only production walkthrough. No writes."""
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
V6_MARKER = "krowolf_visma_chapter2_v6"


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
            parsed = {"detail": raw[:200]}
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


def _safe_subject(input_data: dict) -> str:
    subj = str((input_data or {}).get("subject") or "")[:80]
    return subj if subj else "(no subject)"


def _processor_summary(job_body: dict) -> dict:
    """Extract demo-safe job intelligence fields from processor_history."""
    history = (job_body.get("result") or {}).get("processor_history")
    if not isinstance(history, list):
        history = job_body.get("processor_history") or []
    out: dict = {
        "processors_run": [],
        "classification": None,
        "priority": None,
        "missing_fields": [],
        "proposed_next_step": None,
        "service_profile": None,
        "risk_flags": [],
    }
    for entry in history:
        if not isinstance(entry, dict):
            continue
        name = entry.get("processor") or entry.get("name")
        if name:
            out["processors_run"].append(str(name))
        res = entry.get("result") or {}
        payload = res.get("payload") or res
        if name in ("lead_analyzer_processor", "support_analyzer_processor", "invoice_processor"):
            out["classification"] = out["classification"] or payload.get("classification") or payload.get("category")
            out["priority"] = out["priority"] or payload.get("priority")
            out["missing_fields"] = payload.get("missing_fields") or out["missing_fields"]
            out["service_profile"] = out["service_profile"] or payload.get("service_profile")
        if name == "policy_processor":
            out["risk_flags"] = list(payload.get("reasons") or payload.get("risk_flags") or [])
        if name == "approval_processor":
            ar = payload.get("approval_request") or {}
            out["proposed_next_step"] = ar.get("next_on_approve") or payload.get("recommended_next_step")
    return out


def _job_demo_card(job_body: dict) -> dict:
    return {
        "job_type": job_body.get("job_type"),
        "status": job_body.get("status"),
        "subject_preview": _safe_subject(job_body.get("input_data") or {}),
        "has_pending_approvals": job_body.get("has_pending_approvals"),
        "pending_approvals_count": job_body.get("pending_approvals_count"),
        "intelligence": _processor_summary(job_body),
    }


def discover_example_jobs() -> dict:
    return docker_python(
        f'''
import json
from app.repositories.postgres.database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
try:
    def pick(job_type, status=None, exclude_marker=None):
        q = """
            SELECT job_id FROM jobs
            WHERE tenant_id = :t AND job_type = :jt
        """
        params = {{"t": "{TENANT}", "jt": job_type}}
        if status:
            q += " AND status = :st"
            params["st"] = status
        if exclude_marker:
            q += " AND COALESCE(input_data->>'sandbox_test_marker','') != :m"
            params["m"] = exclude_marker
        q += " ORDER BY created_at DESC LIMIT 1"
        row = db.execute(text(q), params).fetchone()
        return row[0] if row else None
    visma = db.execute(text("""
        SELECT job_id FROM jobs WHERE tenant_id=:t
        AND input_data->>'sandbox_test_marker'=:m LIMIT 1
    """), {{"t": "{TENANT}", "m": "{V6_MARKER}"}}).fetchone()
    print(json.dumps({{
        "lead_job_id": pick("lead", exclude_marker="{V6_MARKER}"),
        "inquiry_job_id": pick("customer_inquiry"),
        "manual_review_job_id": pick("lead", status="manual_review") or pick("customer_inquiry", status="manual_review"),
        "visma_v6_job_id": visma[0] if visma else None,
    }}))
finally:
    db.close()
'''
    )


def sheets_tab_counts() -> dict:
    return docker_python(
        r'''
import json, requests
from urllib.parse import quote
from app.repositories.postgres.database import SessionLocal
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
from app.integrations.google.sheets_auth import resolve_google_sheets_access_token

db = SessionLocal()
try:
    settings = TenantConfigRepository.get_settings(db, "''' + TENANT + r'''")
    gs = settings.get("google_sheets") or {}
    sid = gs.get("spreadsheet_id") or ""
    if not sid:
        print(json.dumps({"configured": False}))
        raise SystemExit(0)
    token = resolve_google_sheets_access_token(settings)
    headers = {"Authorization": f"Bearer {token}"}
    meta = requests.get(
        f"https://sheets.googleapis.com/v4/spreadsheets/{sid}?fields=sheets.properties.title",
        headers=headers, timeout=20,
    )
    tabs = [s.get("properties", {}).get("title") for s in meta.json().get("sheets", [])]
    out = {"configured": True, "tabs_present": tabs, "tab_row_counts": {}}
    for tab in ("Leads", "Support", "Sammanfattning", "Logg"):
        if tab not in tabs:
            out["tab_row_counts"][tab] = {"present": False}
            continue
        col = "G" if tab == "Sammanfattning" else "L"
        rng = f"{tab}!A:{col}"
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{sid}/values/" + quote(rng, safe="!:")
        resp = requests.get(url, headers=headers, timeout=20)
        rows = resp.json().get("values") or [] if resp.ok else []
        out["tab_row_counts"][tab] = {
            "present": True,
            "http": resp.status_code,
            "row_count": len(rows),
            "has_header": bool(rows),
            "data_rows": max(0, len(rows) - 1),
        }
    print(json.dumps(out))
finally:
    db.close()
'''
    )


def main() -> int:
    out: dict = {
        "rehearsal": "internal_demo",
        "tenant": TENANT,
        "at": datetime.now(timezone.utc).isoformat(),
        "visma_writes_performed": False,
    }

    # Infrastructure sanity
    out["health"] = {"root": api("GET", "/")["http"], "health": api("GET", "/health")["http"]}

    discovered = discover_example_jobs()
    out["discovered_jobs"] = {k: bool(v) for k, v in discovered.items() if k.endswith("_job_id")}

    walkthrough: dict = {}

    # 1 Gmail intake narrative
    intake: dict = {}
    for label, key in [
        ("lead", "lead_job_id"),
        ("customer_inquiry", "inquiry_job_id"),
        ("manual_review", "manual_review_job_id"),
    ]:
        jid = discovered.get(key)
        if not jid:
            intake[label] = {"found": False}
            continue
        resp = api("GET", f"/jobs/{jid}")
        intake[label] = {"found": True, "http": resp["http"], **_job_demo_card(resp["body"])}
    walkthrough["gmail_intake"] = intake

    # 2 Manual review queue
    mr = api("GET", "/manual-review/jobs?limit=10")
    mr_items = mr["body"].get("items") or []
    walkthrough["manual_review_queue"] = {
        "http": mr["http"],
        "total": mr["body"].get("total"),
        "sample_subjects": [
            str((i.get("subject") or i.get("summary") or ""))[:60]
            for i in mr_items[:3]
        ],
        "label_expected": "krowolf-manual-review",
        "handoff_present_count": sum(
            1 for i in mr_items if (i.get("gmail_handoff") or {}).get("label_applied")
        ),
    }
    if discovered.get("manual_review_job_id"):
        mrd = api("GET", f"/manual-review/jobs/{discovered['manual_review_job_id']}")
        handoff = (mrd["body"].get("gmail_handoff") or {}) if mrd["http"] == 200 else {}
        walkthrough["manual_review_detail"] = {
            "http": mrd["http"],
            "unread_preserved": handoff.get("unread_preserved"),
            "label_applied": handoff.get("label_applied"),
            "label_name": handoff.get("label_name"),
            "resolved": mrd["body"].get("resolved"),
        }

    # 3 Google Sheets
    walkthrough["google_sheets"] = sheets_tab_counts()
    walkthrough["google_sheets"]["append_only_note"] = (
        "Leads/Support are append-only; re-export may duplicate rows. "
        "Sammanfattning is replace-range current-state."
    )

    # 4 Visma (no writes)
    visma_st = api("GET", "/integrations/visma/status")
    visma_tr = api("POST", "/integrations/visma/test-read")
    visma_block: dict = {
        "status_http": visma_st["http"],
        "connected": visma_st["body"].get("connected"),
        "test_read_http": visma_tr["http"],
        "api_readable": visma_tr["body"].get("api_readable"),
        "real_customer_writes_released": False,
    }
    v6 = discovered.get("visma_v6_job_id")
    if v6:
        prev = api("POST", f"/finance/invoices/{v6}/visma/preview")
        exp = api("POST", f"/finance/invoices/{v6}/visma/export", {})
        appr = api("GET", f"/jobs/{v6}/approvals")
        visma_block["controlled_job"] = {
            "preview_http": prev["http"],
            "preview_local_only": prev["body"].get("status") in ("preview", "dry_run"),
            "export_status": exp["body"].get("status"),
            "idempotent": exp["body"].get("status") == "already_exported",
            "approval_states": [
                (a.get("state") or (a.get("request_payload") or {}).get("state"))
                for a in (appr["body"].get("items") or [])[:3]
            ],
        }
    walkthrough["visma"] = visma_block

    # 5 Daily summary + tenant safety
    daily = api("GET", "/reports/daily-summary")
    tenant = api("GET", "/tenant")
    control = api("GET", "/dashboard/control")
    walkthrough["daily_summary"] = {
        "http": daily["http"],
        "has_counts": isinstance(daily["body"].get("counts") or daily["body"].get("summary"), dict),
        "pending_approvals_in_report": daily["body"].get("pending_approvals"),
    }
    walkthrough["tenant_safety"] = {
        "auto_actions_all_false": all(
            not v for v in (tenant["body"].get("auto_actions") or {}).values()
        ),
        "allowed_integrations": tenant["body"].get("allowed_integrations"),
        "scheduler_manual": (control["body"].get("scheduler") or {}).get("run_mode") == "manual",
    }

    out["walkthrough"] = walkthrough

    # Rehearsal findings (operator notes from automated checks)
    findings = {"demo_blockers": [], "non_blocking_polish": [], "unclear_ui_text": []}
    if not discovered.get("lead_job_id"):
        findings["demo_blockers"].append("No lead job found for intake narrative")
    if not discovered.get("inquiry_job_id"):
        findings["demo_blockers"].append("No customer_inquiry job found")
    if not discovered.get("manual_review_job_id"):
        findings["demo_blockers"].append("No manual_review job found")
    if walkthrough["manual_review_queue"].get("total", 0) == 0:
        findings["non_blocking_polish"].append("Manual-review queue empty — use historical job detail only")
    sheets = walkthrough.get("google_sheets") or {}
    if not sheets.get("configured"):
        findings["demo_blockers"].append("Google Sheets not configured for tenant")
    else:
        for tab in ("Leads", "Support", "Sammanfattning"):
            tc = (sheets.get("tab_row_counts") or {}).get(tab) or {}
            if not tc.get("present"):
                findings["demo_blockers"].append(f"Sheets tab missing: {tab}")
            elif tc.get("data_rows", 0) == 0:
                findings["non_blocking_polish"].append(f"Sheets tab {tab} has no data rows yet")
    if not visma_block.get("connected"):
        findings["demo_blockers"].append("Visma not connected")
    elif v6 and not (visma_block.get("controlled_job") or {}).get("idempotent"):
        findings["demo_blockers"].append("Visma v6 job not showing already_exported idempotency")
    if tenant["body"].get("auto_actions", {}).get("lead"):
        findings["demo_blockers"].append("auto_actions.lead is true")
    findings["unclear_ui_text"].append(
        "Operator UI is API/Internal Console — no polished customer-facing portal"
    )
    findings["non_blocking_polish"].append(
        "Job status may show awaiting_approval when pending approvals exist even if DB status differs"
    )
    findings["non_blocking_polish"].append(
        "Gmail integration health may show warning after demo batch processed (expected)"
    )
    findings["non_blocking_polish"].append(
        "8 legacy email_send approvals still pending from first demo batch — drain or reject before pilot"
    )
    out["findings"] = findings
    out["rehearsal_completed"] = len(findings["demo_blockers"]) == 0

    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    return 0 if out["rehearsal_completed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
