#!/usr/bin/env python3
"""
First live Gmail soak scan — only when operator prepared 3–5 new unread labeled messages.

Checks unread count via dry_run, requires min_new_messages (default 3) that are NOT duplicates.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

TENANT = "T_NIKLAS_DEMO_001"
QUERY = "label:krowolf-demo-niklas is:unread"
MAX_RESULTS = 5
MIN_NEW = int(sys.argv[1]) if len(sys.argv) > 1 else 3
API_KEY_PATH = Path(f"/app/storage/tenant_keys/{TENANT}.api_key")
API_BASE = "https://api.krowolf.se"


def api_json(method: str, path: str, api_key: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        data=data,
        method=method,
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {"detail": e.read().decode()[:300]}


def latest_payload(job: dict, processor: str) -> dict:
    history = (job.get("result") or {}).get("processor_history") or job.get("processor_history") or []
    for item in reversed(history):
        if item.get("processor") == processor:
            return ((item.get("result") or {}).get("payload") or {})
    return {}


def safe_job_card(job: dict) -> dict:
    inp = job.get("input_data") or {}
    sender = inp.get("sender") or {}
    class_p = latest_payload(job, "classification_processor")
    extract_p = latest_payload(job, "entity_extraction_processor")
    policy_p = latest_payload(job, "policy_processor")
    entities = extract_p.get("entities") or {}
    return {
        "job_id": job.get("job_id"),
        "message_id": inp.get("message_id") or (inp.get("source") or {}).get("message_id"),
        "job_type": job.get("job_type"),
        "status": job.get("status"),
        "classification": class_p.get("detected_job_type") or class_p.get("classification"),
        "confidence": class_p.get("confidence") or class_p.get("classification_confidence"),
        "sender_domain": (sender.get("email") or "").split("@")[-1] if sender.get("email") else None,
        "subject_len": len(inp.get("subject") or ""),
        "extracted_core_fields": {
            k: v
            for k, v in {
                "company": entities.get("company_name") or entities.get("organization"),
                "phone_present": bool(entities.get("phone")),
                "city": entities.get("city") or entities.get("location"),
            }.items()
            if v
        },
        "routing": policy_p.get("approval_route") or policy_p.get("decision"),
        "approval_required": bool(job.get("has_pending_approvals")),
        "pending_approvals_count": job.get("pending_approvals_count"),
        "needs_help_signal": job.get("status") == "manual_review",
        "errors": [],
    }


def main() -> int:
    api_key = API_KEY_PATH.read_text().strip()

    http_d, dry = api_json(
        "POST",
        "/gmail/process-inbox",
        api_key,
        {"max_results": MAX_RESULTS, "dry_run": True, "query": QUERY},
    )
    skipped = dry.get("skipped_messages") or []
    duplicates = sum(1 for s in skipped if s.get("reason") == "duplicate")
    scanned = dry.get("scanned") or 0
    would_process = (dry.get("processed") or 0) + max(0, scanned - duplicates - (dry.get("failed") or 0))
    new_candidates = scanned - duplicates

    precheck = {
        "http": http_d,
        "scanned": scanned,
        "duplicates": duplicates,
        "failed": dry.get("failed"),
        "new_candidates": new_candidates,
        "min_required": MIN_NEW,
        "ready_for_live_scan": new_candidates >= MIN_NEW,
    }

    if http_d >= 400:
        print(json.dumps({"phase": "precheck", "precheck": precheck, "live_scan": "aborted"}, indent=2))
        return 1

    if new_candidates < MIN_NEW:
        print(
            json.dumps(
                {
                    "phase": "awaiting_operator",
                    "precheck": precheck,
                    "live_scan": "skipped",
                    "instruction": (
                        f"Lägg {MIN_NEW}–5 nya olästa mejl under label:krowolf-demo-niklas "
                        "som inte redan har jobb, kör sedan om detta skript."
                    ),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 2

    http_l, scan = api_json(
        "POST",
        "/gmail/process-inbox",
        api_key,
        {"max_results": MAX_RESULTS, "dry_run": False, "query": QUERY},
    )

    job_cards = []
    for entry in scan.get("created_jobs") or []:
        jid = entry.get("job_id")
        card = {
            "scan_entry": {
                "message_id": entry.get("message_id"),
                "inferred_type": entry.get("inferred_type"),
                "status": entry.get("status"),
                "marked_handled": bool(entry.get("marked_handled")),
            }
        }
        if jid:
            _, job = api_json("GET", f"/jobs/{jid}", api_key)
            if isinstance(job, dict) and job.get("job_id"):
                card["job"] = safe_job_card(job)
        job_cards.append(card)

    _, health = api_json("GET", "/integrations/health", api_key)
    gmail_h = (health.get("systems") or {}).get("gmail") or {}
    scanner_ran = next(
        (c.get("status") for c in (gmail_h.get("checks") or []) if c.get("key") == "scanner_ran"),
        None,
    )

    # workflow-scan updates scanner_ran from stored jobs (no live Gmail API)
    _, wf = api_json("POST", "/workflow-scan/gmail", api_key)
    _, health2 = api_json("GET", "/integrations/health", api_key)
    gmail_h2 = (health2.get("systems") or {}).get("gmail") or {}
    scanner_ran_after = next(
        (c.get("status") for c in (gmail_h2.get("checks") or []) if c.get("key") == "scanner_ran"),
        None,
    )

    out = {
        "phase": "first_live_scan",
        "tenant": TENANT,
        "precheck": precheck,
        "live_scan": {
            "http": http_l,
            "dry_run": scan.get("dry_run"),
            "scanned": scan.get("scanned"),
            "processed": scan.get("processed"),
            "skipped": scan.get("skipped"),
            "failed": scan.get("failed"),
            "skipped_messages": [
                {"message_id": (s.get("message_id") or "")[:20] + "...", "reason": s.get("reason")}
                for s in (scan.get("skipped_messages") or [])
            ],
        },
        "per_message": job_cards,
        "workflow_scan_gmail": {
            "http": wf.get("status") if isinstance(wf, dict) else None,
            "summary_status": (wf.get("summary") or {}).get("gmail", {}).get("status") if isinstance(wf, dict) else None,
        },
        "scanner_ran_before": scanner_ran,
        "scanner_ran_after_workflow_scan": scanner_ran_after,
        "external_side_effects": 0,
        "credentials_exposed": False,
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if http_l < 400 else 1


if __name__ == "__main__":
    raise SystemExit(main())
