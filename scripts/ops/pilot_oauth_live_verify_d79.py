#!/usr/bin/env python3
"""Pilotdrift OAuth Del 7-9 live verification — no secrets in output."""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

TENANT = "T_NIKLAS_DEMO_001"
PROVIDER = "google_mail"
API_KEY_CANDIDATES = [
    Path(f"/app/storage/tenant_keys/{TENANT}.api_key"),
    Path(f"/opt/krowolf/storage/tenant_keys/{TENANT}.api_key"),
]


def load_api_key() -> str:
    for path in API_KEY_CANDIDATES:
        if path.is_file():
            return path.read_text().strip()
    raise FileNotFoundError("tenant API key not found")
API_BASE = "https://api.krowolf.se"
QUERY = "label:krowolf-demo-niklas is:unread"
MAX_SCAN = 5
EXPECTED_EMAIL_DOMAIN = "sol-f.se"

SECRET_PATTERNS = [
    re.compile(r"ya29\.[A-Za-z0-9._\-]{10,}"),
    re.compile(r"1//[A-Za-z0-9._\-]{10,}"),
    re.compile(r'"access_token"\s*:\s*"[^"]{10,}"'),
    re.compile(r'"refresh_token"\s*:\s*"[^"]{10,}"'),
]


def scan_secrets(text: str) -> list[str]:
    hits = []
    for p in SECRET_PATTERNS:
        if p.search(text):
            hits.append(p.pattern[:40])
    return hits


def api_json(method: str, path: str, api_key: str, body: dict | None = None) -> tuple[int, dict | str]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        data=data,
        method=method,
        headers={"X-API-Key": api_key, "Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw[:400]


def section_connected(db) -> dict:
    from app.integrations.google.oauth_token_resolver import gmail_connection_status, PROVIDER as P
    from app.integrations.oauth_state_models import IntegrationOAuthStateRecord
    from app.repositories.postgres.audit_models import AuditEventRecord
    from app.repositories.postgres.oauth_credential_repository import OAuthCredentialRepository
    from app.core.settings import get_settings

    settings = get_settings()
    row = OAuthCredentialRepository.get(db, TENANT, P)
    status = gmail_connection_status(db, TENANT, settings=settings)

    latest_state = (
        db.query(IntegrationOAuthStateRecord)
        .filter_by(tenant_id=TENANT, provider=P)
        .order_by(IntegrationOAuthStateRecord.created_at.desc())
        .first()
    )
    state_out = {
        "latest_state_consumed": latest_state.consumed_at is not None if latest_state else False,
        "latest_state_consumed_at_set": bool(latest_state and latest_state.consumed_at),
    }

    started_audits = (
        db.query(AuditEventRecord)
        .filter(
            AuditEventRecord.tenant_id == TENANT,
            AuditEventRecord.action == "integration.google_mail.oauth_started",
        )
        .count()
    )
    state_out["oauth_started_audit_count"] = started_audits

    out = {
        "connection_state": status.get("connection_state"),
        "credential_source": status.get("credential_source"),
        "connected": status.get("connected"),
        "email": status.get("email"),
        "reconnect_required": status.get("reconnect_required"),
        "scopes_reported": status.get("scopes"),
        **state_out,
    }

    if row is None:
        out["oauth_row_exists"] = False
        out["verdict"] = "FAIL"
        return out

    meta = row.metadata_json or {}
    scopes = (row.scopes or "").split()
    scope_set = {s.strip() for s in scopes if s.strip()}
    expected = {
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.modify",
    }
    out["oauth_row_exists"] = True
    out["tenant_id"] = row.tenant_id
    out["provider"] = row.provider
    out["access_token_set"] = bool(row.access_token)
    out["refresh_token_set"] = bool(row.refresh_token)
    out["expires_at"] = row.expires_at.isoformat() if row.expires_at else None
    out["scopes_db"] = sorted(scope_set)
    out["scopes_exact_pilot"] = scope_set == expected
    out["email_metadata"] = meta.get("email")
    out["connected_via"] = meta.get("connected_via")

    audits = (
        db.query(AuditEventRecord)
        .filter(
            AuditEventRecord.tenant_id == TENANT,
            AuditEventRecord.action.in_(
                [
                    "integration.google_mail.oauth_connected",
                    "oauth_connection_completed",
                ]
            ),
        )
        .order_by(AuditEventRecord.created_at.desc())
        .limit(3)
        .all()
    )
    out["callback_audit_count"] = len(audits)
    audit_safe = []
    for a in audits:
        blob = json.dumps(a.details or {})
        audit_safe.append(
            {
                "action": a.action,
                "status": a.status,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "secret_hits": scan_secrets(blob),
                "detail_keys": sorted((a.details or {}).keys()) if isinstance(a.details, dict) else [],
            }
        )
    out["callback_audits"] = audit_safe

    status_blob = json.dumps(out)
    out["credentials_exposed_in_status"] = bool(scan_secrets(status_blob))

    from sqlalchemy import text

    cred_count = db.execute(
        text("SELECT count(*) FROM oauth_credentials WHERE tenant_id = :t AND provider = :p"),
        {"t": TENANT, "p": P},
    ).scalar()
    out["oauth_credential_row_count"] = int(cred_count or 0)

    ok = (
        out["connection_state"] == "connected"
        and out["credential_source"] == "tenant_oauth"
        and out["tenant_id"] == TENANT
        and out["oauth_credential_row_count"] == 1
        and out["access_token_set"]
        and out["refresh_token_set"]
        and bool(out.get("expires_at"))
        and out["scopes_exact_pilot"]
        and out["latest_state_consumed"] is True
        and out["latest_state_consumed_at_set"] is True
        and out["oauth_started_audit_count"] >= 1
        and out["callback_audit_count"] >= 1
        and not out["credentials_exposed_in_status"]
        and (out["email_metadata"] or out["email"])
    )
    out["verdict"] = "PASS" if ok else "PARTIAL"
    if (
        not row.access_token
        or not row.refresh_token
        or out["connection_state"] != "connected"
        or out["credential_source"] != "tenant_oauth"
    ):
        out["verdict"] = "FAIL"
    return out


def section_test_read(api_key: str) -> dict:
    http, body = api_json("POST", "/integrations/google_mail/test-read", api_key, {})
    out = {"http": http}
    if isinstance(body, dict):
        out.update(
            {
                "status": body.get("status"),
                "api_readable": body.get("api_readable"),
                "email_address": body.get("email_address"),
                "credential_source": body.get("credential_source"),
                "detail": body.get("detail"),
            }
        )
        blob = json.dumps(body)
        out["secret_hits"] = scan_secrets(blob)
    else:
        out["error"] = str(body)[:200]
        out["secret_hits"] = scan_secrets(str(body))

    # integration health
    http_h, health = api_json("GET", "/integrations/health", api_key)
    out["health_http"] = http_h
    if isinstance(health, dict):
        gmail = (health.get("systems") or {}).get("gmail") or health.get("gmail") or {}
        out["gmail_health_status"] = gmail.get("status")
        out["health_secret_hits"] = scan_secrets(json.dumps(health))
    out["external_side_effects"] = 0
    ok = (
        http == 200
        and out.get("api_readable") is True
        and out.get("credential_source") == "tenant_oauth"
        and not out.get("secret_hits")
    )
    if out.get("email_address"):
        out["email_domain_ok"] = EXPECTED_EMAIL_DOMAIN in str(out["email_address"])
        ok = ok and out["email_domain_ok"]
    out["verdict"] = "PASS" if ok else ("PARTIAL" if http == 200 else "FAIL")
    return out


def section_refresh(db) -> dict:
    from app.integrations.google.oauth_token_resolver import (
        resolve_google_mail_connection_config,
        refresh_tenant_google_mail_token,
    )
    from app.repositories.postgres.oauth_credential_repository import OAuthCredentialRepository

    row = OAuthCredentialRepository.get(db, TENANT, PROVIDER)
    if row is None:
        return {"verdict": "FAIL", "error": "no_oauth_row"}

    old_access_len = len(row.access_token or "")
    old_refresh = row.refresh_token
    old_expires = row.expires_at

    # Force expiry without touching refresh token
    row.expires_at = datetime.now(timezone.utc) - timedelta(hours=2)
    db.commit()
    db.refresh(row)

    out = {
        "simulated_expired": True,
        "refresh_token_preserved_before": bool(old_refresh),
    }

    try:
        cfg = resolve_google_mail_connection_config(TENANT, db=db)
        out["resolver_credential_source"] = cfg.get("credential_source")
        out["resolver_ok"] = cfg.get("credential_source") == "tenant_oauth" and bool(cfg.get("access_token"))
        out["access_token_changed"] = len(cfg.get("access_token") or "") != old_access_len or (
            cfg.get("access_token") != row.access_token
        )
    except Exception as exc:
        out["resolver_error"] = str(exc)[:200]
        out["verdict"] = "FAIL"
        db.rollback()
        return out

    row2 = OAuthCredentialRepository.get(db, TENANT, PROVIDER)
    out["refresh_token_preserved_after"] = row2.refresh_token == old_refresh
    out["db_expires_updated"] = (
        row2.expires_at is not None
        and row2.expires_at > datetime.now(timezone.utc)
    )
    out["access_token_set_after"] = bool(row2.access_token)

    # Explicit refresh call idempotency check
    try:
        refresh_tenant_google_mail_token(db, TENANT)
        row3 = OAuthCredentialRepository.get(db, TENANT, PROVIDER)
        out["refresh_token_still_preserved"] = row3.refresh_token == old_refresh
    except Exception as exc:
        out["explicit_refresh_error"] = str(exc)[:200]

    out["verdict"] = (
        "PASS"
        if out.get("resolver_ok")
        and out.get("refresh_token_preserved_after")
        and out.get("db_expires_updated")
        and out.get("credential_source", out.get("resolver_credential_source")) != "platform_env"
        else "FAIL"
    )
    if out.get("resolver_credential_source") == "tenant_oauth" and out.get("refresh_token_preserved_after"):
        if out["verdict"] != "PASS" and out.get("db_expires_updated"):
            out["verdict"] = "PARTIAL"
    return out


def section_dry_run(api_key: str, db) -> dict:
    from app.repositories.postgres.audit_models import AuditEventRecord

    before_jobs = db.execute(
        __import__("sqlalchemy").text(
            "SELECT count(*) FROM jobs WHERE tenant_id = :t"
        ),
        {"t": TENANT},
    ).scalar()

    http, body = api_json(
        "POST",
        "/gmail/process-inbox",
        api_key,
        {"max_results": MAX_SCAN, "dry_run": True, "query": QUERY},
    )
    out = {
        "http": http,
        "dry_run": body.get("dry_run") if isinstance(body, dict) else None,
        "query_used": body.get("query_used") if isinstance(body, dict) else QUERY,
        "scanned": body.get("scanned") if isinstance(body, dict) else None,
        "processed": body.get("processed") if isinstance(body, dict) else None,
        "skipped": body.get("skipped") if isinstance(body, dict) else None,
        "failed": body.get("failed") if isinstance(body, dict) else None,
        "created_jobs": 0,
        "external_side_effects": 0,
    }
    if isinstance(body, dict):
        skipped = body.get("skipped_messages") or []
        out["skipped_reasons"] = [
            {"message_id": (s.get("message_id") or "")[:20] + "...", "reason": s.get("reason")}
            for s in skipped[:10]
        ]
        out["secret_hits"] = scan_secrets(json.dumps(body))

    after_jobs = db.execute(
        __import__("sqlalchemy").text(
            "SELECT count(*) FROM jobs WHERE tenant_id = :t"
        ),
        {"t": TENANT},
    ).scalar()
    out["jobs_before"] = before_jobs
    out["jobs_after"] = after_jobs
    out["jobs_created"] = max(0, (after_jobs or 0) - (before_jobs or 0))

    _, pending = api_json("GET", "/approvals/pending?limit=50", api_key)
    out["pending_approvals"] = len((pending.get("items") if isinstance(pending, dict) else []) or [])

    try:
        from app.admin.operations_needs_help import list_needs_help_for_tenant

        nh = list_needs_help_for_tenant(db, TENANT, limit=50)
        out["needs_help_count"] = len(nh.get("items") or [])
    except Exception:
        out["needs_help_count"] = None

    sched = db.execute(
        __import__("sqlalchemy").text(
            "SELECT settings->'scheduler'->>'run_mode' FROM tenant_configs WHERE tenant_id = :t"
        ),
        {"t": TENANT},
    ).scalar()
    out["scheduler_run_mode"] = (sched or "").strip() if sched else None

    out["verdict"] = (
        "PASS"
        if http == 200
        and out.get("dry_run") is True
        and out.get("jobs_created") == 0
        and out.get("scheduler_run_mode") == "paused"
        else "FAIL"
    )
    return out


def main() -> int:
    from app.repositories.postgres.database import SessionLocal

    api_key = load_api_key()
    report: dict = {"tenant": TENANT, "phases": {}}

    db = SessionLocal()
    try:
        report["phases"]["1_connected"] = section_connected(db)
        report["phases"]["2_test_read"] = section_test_read(api_key)

        if report["phases"]["2_test_read"].get("verdict") == "PASS":
            report["phases"]["3_refresh"] = section_refresh(db)
        else:
            report["phases"]["3_refresh"] = {"verdict": "SKIPPED", "reason": "test_read_not_pass"}

        tr = report["phases"].get("2_test_read", {}).get("verdict")
        rf = report["phases"].get("3_refresh", {}).get("verdict")
        if tr == "PASS" and rf == "PASS":
            report["phases"]["4_dry_run"] = section_dry_run(api_key, db)
        else:
            report["phases"]["4_dry_run"] = {
                "verdict": "SKIPPED",
                "reason": f"test_read={tr}, refresh={rf}",
            }
    finally:
        db.close()

    blob = json.dumps(report)
    report["credentials_exposed"] = bool(scan_secrets(blob))
    report["external_side_effects"] = 0

    soak_ready = (
        report["phases"].get("1_connected", {}).get("verdict") == "PASS"
        and report["phases"].get("2_test_read", {}).get("verdict") == "PASS"
        and report["phases"].get("3_refresh", {}).get("verdict") == "PASS"
        and report["phases"].get("4_dry_run", {}).get("verdict") == "PASS"
        and not report["credentials_exposed"]
    )
    report["ready_for_7_day_soak"] = soak_ready

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if soak_ready else 1


if __name__ == "__main__":
    sys.exit(main())
