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


def _has_token_expiry_error(db: Session, tenant_id: str, action_prefix: str) -> bool:
    """
    Return True if a recent failed audit event for this action contains an
    invalid_grant or token-expiry signal, indicating OAuth reconnect is needed.
    """
    import json as _json
    records = (
        db.query(AuditEventRecord)
        .filter(
            AuditEventRecord.tenant_id == tenant_id,
            AuditEventRecord.status == "failed",
            AuditEventRecord.action.like(f"%{action_prefix}%"),
        )
        .order_by(AuditEventRecord.created_at.desc())
        .limit(3)
        .all()
    )
    for r in records:
        details_str = ""
        try:
            if hasattr(r, "details") and r.details:
                details_str = _json.dumps(r.details) if not isinstance(r.details, str) else r.details
        except Exception:
            pass
        combined = (r.action or "") + details_str
        if "invalid_grant" in combined.lower() or "token_expired" in combined.lower():
            return True
    return False


# ---------------------------------------------------------------------------
# Per-system health
# ---------------------------------------------------------------------------

def _check(key: str, status: str, description: str) -> dict:
    """Build a check dict with both 'description' (new) and 'message' (compat) fields."""
    return {"key": key, "check": key, "status": status, "description": description, "message": description}

def _check_gmail(settings: dict, app_settings: Any, db: Session, tenant_id: str) -> dict:
    checks = []
    configured = bool(getattr(app_settings, "GOOGLE_MAIL_ACCESS_TOKEN", ""))
    last_success_at = None
    last_error_at = None
    last_error_message = None
    token_expired = False

    # Check 1: config present
    checks.append(_check(
        "config_present",
        "pass" if configured else "fail",
        "Gmail-anslutning konfigurerad." if configured
        else "Gmail-anslutning saknas — konfigurera OAuth-uppgifter.",
    ))

    if configured:
        # Check 2: token expiry (invalid_grant in recent failures)
        token_expired = _has_token_expiry_error(db, tenant_id, "gmail")
        if token_expired:
            checks.append(_check("token_valid", "fail",
                                 "OAuth-token har löpt ut — koppling måste förnyas."))

        # Check 3: scanner ran successfully
        scan = settings.get("workflow_scan") or {}
        summary = scan.get("summary") or {}
        gmail_scan = summary.get("gmail") or {}
        scanner_ok = gmail_scan.get("status") == "success"
        checks.append(_check(
            "scanner_ran",
            "pass" if scanner_ok else "warning",
            "Gmail-skanning genomförd." if scanner_ok
            else "Gmail-skanning ej genomförd — kör en skanning för att bekräfta flödet.",
        ))

        # Check 4: inbox sync activity
        sync_record = _latest_audit_by_action(db, tenant_id, "gmail_inbox_sync")
        if sync_record:
            if sync_record.status == "success":
                last_success_at = sync_record.created_at.isoformat() if sync_record.created_at else None
                checks.append(_check("inbox_sync", "pass", "Inkorgssynkronisering fungerar."))
            else:
                last_error_at = sync_record.created_at.isoformat() if sync_record.created_at else None
                last_error_message = "Inkorgssynkronisering misslyckades."
                checks.append(_check("inbox_sync", "warning",
                                     "Senaste inkorgssynkronisering misslyckades."))

    # Derive system status
    failed_checks = [c for c in checks if c["status"] == "fail"]
    warn_checks   = [c for c in checks if c["status"] == "warning"]

    if not configured:
        status = "not_configured"
        action = "Konfigurera Gmail OAuth-uppgifter för att aktivera e-postintegrationen."
    elif token_expired:
        status = "error"
        action = "OAuth-token har löpt ut. Koppla om Gmail-integrationen via Google Cloud Console."
        token_expired_flag = True
    elif failed_checks:
        status = "error"
        action = "Kontrollera Gmail-konfigurationen — en eller flera kontroller misslyckades."
    elif warn_checks:
        status = "warning"
        action = "Kör Gmail-skanning för att bekräfta att e-postflödet fungerar."
    else:
        status = "healthy"
        action = ""

    result = {
        "status":               status,
        "configured":           configured,
        "last_success_at":      last_success_at,
        "last_error_at":        last_error_at,
        "last_error_message":   last_error_message,
        "checks":               checks,
        "recommended_action":   action,
    }
    if token_expired:
        result["token_expired"] = True
    return result


def _check_monday(settings: dict, app_settings: Any, db: Session, tenant_id: str) -> dict:
    checks = []
    configured = bool(getattr(app_settings, "MONDAY_API_KEY", ""))
    last_success_at = None
    last_error_at = None
    last_error_message = None

    # Check 1: config present
    checks.append(_check(
        "config_present",
        "pass" if configured else "fail",
        "Monday-anslutning konfigurerad." if configured
        else "Monday API-nyckel saknas — konfigurera MONDAY_API_KEY.",
    ))

    if configured:
        # Check 2: scanner ran
        scan = settings.get("workflow_scan") or {}
        summary = scan.get("summary") or {}
        monday_scan = summary.get("monday") or {}
        scanner_ok = monday_scan.get("status") == "success"
        checks.append(_check(
            "scanner_ran",
            "pass" if scanner_ok else "warning",
            "Monday-skanning genomförd." if scanner_ok
            else "Monday-skanning ej genomförd — kör en skanning.",
        ))

        # Check 3: successful dispatch event
        dispatch = _latest_dispatch_event(db, tenant_id, "monday")
        if dispatch:
            if dispatch.status == "success":
                last_success_at = dispatch.created_at.isoformat() if dispatch.created_at else None
                checks.append(_check("dispatch_success", "pass",
                                     "Ärenden kan skickas till Monday."))
            elif dispatch.status == "failed":
                last_error_at = dispatch.created_at.isoformat() if dispatch.created_at else None
                last_error_message = "Senaste ärendedispatch misslyckades."
                checks.append(_check("dispatch_success", "warning",
                                     "Senaste ärendedispatch till Monday misslyckades."))

    # Derive system status
    failed_checks = [c for c in checks if c["status"] == "fail"]
    warn_checks   = [c for c in checks if c["status"] == "warning"]

    if not configured:
        status = "not_configured"
        action = "Konfigurera MONDAY_API_KEY och MONDAY_BOARD_ID för att aktivera Monday-integrationen."
    elif failed_checks:
        status = "error"
        action = "Kontrollera Monday-konfigurationen — API-nyckel eller board-ID kan vara felaktigt."
    elif warn_checks:
        status = "warning"
        action = "Kör Monday-skanning och skicka ett testärende för att bekräfta anslutningen."
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
    token_expired = False

    # Check 1: both credentials present
    checks.append(_check(
        "config_present",
        "pass" if configured else "fail",
        "Fortnox-anslutning konfigurerad." if configured
        else "Fortnox-uppgifter saknas — konfigurera access token och client secret.",
    ))

    if configured:
        # Check 2: token expiry
        token_expired = _has_token_expiry_error(db, tenant_id, "fortnox")
        if token_expired:
            checks.append(_check("token_valid", "fail",
                                 "Fortnox-token har löpt ut — access token måste förnyas."))

        # Check 3: scanner ran
        scan = settings.get("workflow_scan") or {}
        summary = scan.get("summary") or {}
        fortnox_scan = summary.get("fortnox") or {}
        scanner_ok = fortnox_scan.get("status") == "success"
        checks.append(_check(
            "scanner_ran",
            "pass" if scanner_ok else "warning",
            "Fortnox-skanning genomförd." if scanner_ok
            else "Fortnox-skanning ej genomförd — kör en skanning.",
        ))

        # Check 4: successful Fortnox integration event (export/preview)
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
                checks.append(_check("export_success", "pass",
                                     "Fakturor kan exporteras till Fortnox."))
            elif fortnox_event.status == "failed":
                last_error_at = fortnox_event.created_at.isoformat() if fortnox_event.created_at else None
                last_error_message = fortnox_event.last_error or "Senaste Fortnox-export misslyckades."
                checks.append(_check("export_success", "warning",
                                     "Senaste Fortnox-export misslyckades."))

    # Derive system status
    failed_checks = [c for c in checks if c["status"] == "fail"]
    warn_checks   = [c for c in checks if c["status"] == "warning"]

    if not configured:
        status = "not_configured"
        action = "Konfigurera Fortnox access token och client secret för att aktivera fakturaintegration."
    elif token_expired:
        status = "error"
        action = "Fortnox-token har löpt ut. Förnya access token i Fortnox-inställningarna."
    elif failed_checks:
        status = "error"
        action = "Kontrollera Fortnox-konfigurationen — token eller client secret kan vara felaktigt."
    elif warn_checks:
        status = "warning"
        action = "Kör Fortnox-skanning och verifiera en testexport."
    else:
        status = "healthy"
        action = ""

    result = {
        "status":               status,
        "configured":           configured,
        "last_success_at":      last_success_at,
        "last_error_at":        last_error_at,
        "last_error_message":   last_error_message,
        "checks":               checks,
        "recommended_action":   action,
    }
    if token_expired:
        result["token_expired"] = True
    return result


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
