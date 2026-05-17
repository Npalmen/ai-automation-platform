"""
Integration health service.

Computes per-system health signals from existing platform state.
All checks are deterministic and read-only — no external API calls.
No secrets are included in the response.

Systems checked: gmail, monday, fortnox
Overall status: healthy | warning | error

Signal sources (internal only):
  - env/settings config presence
  - workflow_scan status + systems_scanned
  - IntegrationEvent records (dispatch/export events)
  - AuditEventRecord records (inbox_sync, scheduler actions)
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository


# ---------------------------------------------------------------------------
# Internal query helpers
# ---------------------------------------------------------------------------

def _latest_dispatch_event(db: Session, tenant_id: str, system: str):
    """Return the most recent IntegrationEvent for this system, or None."""
    from app.domain.integrations.models import IntegrationEvent

    return (
        db.query(IntegrationEvent)
        .filter(
            IntegrationEvent.tenant_id == tenant_id,
            IntegrationEvent.integration_type == "controlled_dispatch",
        )
        .order_by(IntegrationEvent.created_at.desc())
        .first()
    )


def _latest_audit_by_action(db: Session, tenant_id: str, action: str):
    """Return the most recent AuditEventRecord for a given action, or None."""
    return (
        db.query(AuditEventRecord)
        .filter(
            AuditEventRecord.tenant_id == tenant_id,
            AuditEventRecord.action == action,
        )
        .order_by(AuditEventRecord.created_at.desc())
        .first()
    )


def _recent_errors(db: Session, tenant_id: str, limit: int = 5) -> list[dict]:
    """Return recent failed audit events for the tenant."""
    records = (
        db.query(AuditEventRecord)
        .filter(
            AuditEventRecord.tenant_id == tenant_id,
            AuditEventRecord.status == "failed",
        )
        .order_by(AuditEventRecord.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "action":     r.action,
            "category":   r.category,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in records
    ]


# ---------------------------------------------------------------------------
# Per-system health
# ---------------------------------------------------------------------------

def _check_gmail(settings: dict, app_settings: Any, db: Session, tenant_id: str) -> dict:
    checks = []
    configured = bool(getattr(app_settings, "GOOGLE_MAIL_ACCESS_TOKEN", ""))
    last_success_at = None
    last_error_at = None
    last_error_message = None

    # Check 1: config present
    checks.append({
        "key":     "config_present",
        "status":  "pass" if configured else "fail",
        "message": "GOOGLE_MAIL_ACCESS_TOKEN konfigurerat." if configured
                   else "GOOGLE_MAIL_ACCESS_TOKEN saknas.",
    })

    # Check 2: scanner ran successfully
    scan = settings.get("workflow_scan") or {}
    summary = scan.get("summary") or {}
    gmail_scan = summary.get("gmail") or {}
    scanner_ok = gmail_scan.get("status") == "success"
    checks.append({
        "key":     "scanner_ran",
        "status":  "pass" if scanner_ok else "warning",
        "message": "Gmail-skanning lyckades." if scanner_ok
                   else "Gmail-skanning har inte körts eller misslyckades.",
    })

    # Check 3: inbox sync activity
    sync_record = _latest_audit_by_action(db, tenant_id, "gmail_inbox_sync")
    if sync_record:
        if sync_record.status == "success":
            last_success_at = sync_record.created_at.isoformat() if sync_record.created_at else None
            checks.append({"key": "inbox_sync", "status": "pass",
                           "message": "Inkorgssynk lyckades."})
        else:
            last_error_at = sync_record.created_at.isoformat() if sync_record.created_at else None
            last_error_message = "Inkorgssynk misslyckades."
            checks.append({"key": "inbox_sync", "status": "warning",
                           "message": "Senaste inkorgssynk misslyckades."})

    # Derive system status
    failed_checks = [c for c in checks if c["status"] == "fail"]
    warn_checks   = [c for c in checks if c["status"] == "warning"]

    if not configured:
        status = "not_configured"
        action = "Konfigurera GOOGLE_MAIL_ACCESS_TOKEN i miljövariabler."
    elif failed_checks:
        status = "error"
        action = "Kontrollera Gmail-konfigurationen."
    elif warn_checks:
        status = "warning"
        action = "Kör Gmail-skanning för att verifiera anslutningen."
    else:
        status = "healthy"
        action = ""

    return {
        "status":               status,
        "configured":           configured,
        "last_success_at":      last_success_at,
        "last_error_at":        last_error_at,
        "last_error_message":   last_error_message,
        "checks":               checks,
        "recommended_action":   action,
    }


def _check_monday(settings: dict, app_settings: Any, db: Session, tenant_id: str) -> dict:
    checks = []
    configured = bool(getattr(app_settings, "MONDAY_API_KEY", ""))
    last_success_at = None
    last_error_at = None
    last_error_message = None

    # Check 1: config present
    checks.append({
        "key":     "config_present",
        "status":  "pass" if configured else "fail",
        "message": "MONDAY_API_KEY konfigurerat." if configured
                   else "MONDAY_API_KEY saknas.",
    })

    # Check 2: scanner ran
    scan = settings.get("workflow_scan") or {}
    summary = scan.get("summary") or {}
    monday_scan = summary.get("monday") or {}
    scanner_ok = monday_scan.get("status") == "success"
    checks.append({
        "key":     "scanner_ran",
        "status":  "pass" if scanner_ok else "warning",
        "message": "Monday-skanning lyckades." if scanner_ok
                   else "Monday-skanning har inte körts eller misslyckades.",
    })

    # Check 3: successful dispatch event
    dispatch = _latest_dispatch_event(db, tenant_id, "monday")
    if dispatch:
        if dispatch.status == "success":
            last_success_at = dispatch.created_at.isoformat() if dispatch.created_at else None
            checks.append({"key": "dispatch_success", "status": "pass",
                           "message": "Minst en lyckad dispatch till Monday."})
        elif dispatch.status == "failed":
            last_error_at = dispatch.created_at.isoformat() if dispatch.created_at else None
            last_error_message = "Senaste dispatch misslyckades."
            checks.append({"key": "dispatch_success", "status": "warning",
                           "message": "Senaste dispatch till Monday misslyckades."})

    # Derive system status
    failed_checks = [c for c in checks if c["status"] == "fail"]
    warn_checks   = [c for c in checks if c["status"] == "warning"]

    if not configured:
        status = "not_configured"
        action = "Konfigurera MONDAY_API_KEY och MONDAY_BOARD_ID i miljövariabler."
    elif failed_checks:
        status = "error"
        action = "Kontrollera Monday-konfigurationen."
    elif warn_checks:
        status = "warning"
        action = "Kör Monday-skanning och testa dispatch."
    else:
        status = "healthy"
        action = ""

    return {
        "status":               status,
        "configured":           configured,
        "last_success_at":      last_success_at,
        "last_error_at":        last_error_at,
        "last_error_message":   last_error_message,
        "checks":               checks,
        "recommended_action":   action,
    }


def _check_fortnox(settings: dict, app_settings: Any, db: Session, tenant_id: str) -> dict:
    checks = []
    access_token  = (getattr(app_settings, "FORTNOX_ACCESS_TOKEN",  "") or "").strip()
    client_secret = (getattr(app_settings, "FORTNOX_CLIENT_SECRET", "") or "").strip()
    configured = bool(access_token and client_secret)
    last_success_at = None
    last_error_at = None
    last_error_message = None

    # Check 1: both credentials present
    checks.append({
        "key":     "config_present",
        "status":  "pass" if configured else "fail",
        "message": "FORTNOX_ACCESS_TOKEN och FORTNOX_CLIENT_SECRET konfigurerade." if configured
                   else "FORTNOX_ACCESS_TOKEN eller FORTNOX_CLIENT_SECRET saknas.",
    })

    # Check 2: scanner ran
    scan = settings.get("workflow_scan") or {}
    summary = scan.get("summary") or {}
    fortnox_scan = summary.get("fortnox") or {}
    scanner_ok = fortnox_scan.get("status") == "success"
    checks.append({
        "key":     "scanner_ran",
        "status":  "pass" if scanner_ok else "warning",
        "message": "Fortnox-skanning lyckades." if scanner_ok
                   else "Fortnox-skanning har inte körts eller misslyckades.",
    })

    # Check 3: successful Fortnox integration event (export/preview)
    from app.domain.integrations.models import IntegrationEvent
    fortnox_event = (
        db.query(IntegrationEvent)
        .filter(
            IntegrationEvent.tenant_id == tenant_id,
            IntegrationEvent.integration_type.ilike("%fortnox%"),
        )
        .order_by(IntegrationEvent.created_at.desc())
        .first()
    )
    if fortnox_event:
        if fortnox_event.status == "success":
            last_success_at = fortnox_event.created_at.isoformat() if fortnox_event.created_at else None
            checks.append({"key": "export_success", "status": "pass",
                           "message": "Minst en lyckad Fortnox-export."})
        elif fortnox_event.status == "failed":
            last_error_at = fortnox_event.created_at.isoformat() if fortnox_event.created_at else None
            last_error_message = fortnox_event.last_error or "Senaste Fortnox-export misslyckades."
            checks.append({"key": "export_success", "status": "warning",
                           "message": "Senaste Fortnox-export misslyckades."})

    # Derive system status
    failed_checks = [c for c in checks if c["status"] == "fail"]
    warn_checks   = [c for c in checks if c["status"] == "warning"]

    if not configured:
        status = "not_configured"
        action = "Konfigurera FORTNOX_ACCESS_TOKEN och FORTNOX_CLIENT_SECRET i miljövariabler."
    elif failed_checks:
        status = "error"
        action = "Kontrollera Fortnox-konfigurationen."
    elif warn_checks:
        status = "warning"
        action = "Kör Fortnox-skanning och testa en export."
    else:
        status = "healthy"
        action = ""

    return {
        "status":               status,
        "configured":           configured,
        "last_success_at":      last_success_at,
        "last_error_at":        last_error_at,
        "last_error_message":   last_error_message,
        "checks":               checks,
        "recommended_action":   action,
    }


# ---------------------------------------------------------------------------
# Overall aggregation
# ---------------------------------------------------------------------------

def _overall_status(systems: dict) -> str:
    statuses = [v["status"] for v in systems.values()]
    if "error" in statuses:
        return "error"
    if "warning" in statuses or "not_configured" in statuses:
        return "warning"
    return "healthy"


def _build_runbook_signals(systems: dict[str, dict], recent_errors: list[dict]) -> list[dict]:
    """
    Build actionable runbook signals from health state.

    Signals are deterministic and free from secrets. They point operators
    to the first remediation step when pilot drift is detected.
    """
    signals: list[dict] = []

    gmail = systems.get("gmail") or {}
    monday = systems.get("monday") or {}

    if gmail.get("status") in {"error", "not_configured"}:
        signals.append({
            "severity": "critical",
            "area": "gmail",
            "title": "Gmail integration is unavailable",
            "action": "Configure OAuth env vars and rerun setup verification.",
            "runbook_ref": "docs/12-production-guide.md#gmail-integration",
        })
    elif gmail.get("status") == "warning":
        signals.append({
            "severity": "warning",
            "area": "gmail",
            "title": "Gmail integration needs validation",
            "action": "Run inbox sync and workflow scan to confirm mail flow.",
            "runbook_ref": "docs/12-production-guide.md#pre-launch-checklist",
        })

    if monday.get("status") in {"error", "not_configured"}:
        signals.append({
            "severity": "critical",
            "area": "monday",
            "title": "Monday integration is unavailable",
            "action": "Set MONDAY_API_KEY and MONDAY_BOARD_ID, then verify dispatch.",
            "runbook_ref": "docs/12-production-guide.md#mondaycom-integration",
        })
    elif monday.get("status") == "warning":
        signals.append({
            "severity": "warning",
            "area": "monday",
            "title": "Monday integration needs dispatch validation",
            "action": "Run a dispatch preview/live dispatch for a lead case.",
            "runbook_ref": "docs/12-production-guide.md#pre-launch-checklist",
        })

    fortnox = systems.get("fortnox") or {}
    if fortnox.get("status") in {"error"}:
        signals.append({
            "severity": "critical",
            "area": "fortnox",
            "title": "Fortnox integration error",
            "action": "Check FORTNOX_ACCESS_TOKEN, FORTNOX_CLIENT_SECRET, and rerun Fortnox scan.",
            "runbook_ref": "docs/12-production-guide.md#fortnox-integration",
        })
    elif fortnox.get("status") == "warning":
        signals.append({
            "severity": "warning",
            "area": "fortnox",
            "title": "Fortnox integration needs validation",
            "action": "Run Fortnox scan and verify a draft or export.",
            "runbook_ref": "docs/12-production-guide.md#pre-launch-checklist",
        })

    if recent_errors:
        signals.append({
            "severity": "warning",
            "area": "operations",
            "title": "Recent integration-related failures detected",
            "action": "Review /audit-events and resolve the latest failed actions before pilot traffic.",
            "runbook_ref": "docs/12-production-guide.md#error-behaviour",
        })

    return signals


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_integration_health(
    db: Session,
    tenant_id: str,
    *,
    app_settings: Any,
) -> dict[str, Any]:
    """
    Compute integration health for all supported systems.

    All checks are read-only and deterministic. No external API calls.
    No secret values appear in the response.
    """
    settings = TenantConfigRepository.get_settings(db, tenant_id)

    systems = {
        "gmail":   _check_gmail(settings, app_settings, db, tenant_id),
        "monday":  _check_monday(settings, app_settings, db, tenant_id),
        "fortnox": _check_fortnox(settings, app_settings, db, tenant_id),
    }
    recent_errors = _recent_errors(db, tenant_id)

    return {
        "tenant_id":      tenant_id,
        "overall_status": _overall_status(systems),
        "systems":        systems,
        "recent_errors":  recent_errors,
        "runbook_signals": _build_runbook_signals(systems, recent_errors),
    }
