"""
Integration health service.

Computes per-system health signals from existing platform state.
All checks are deterministic and read-only — no external API calls.
No secrets are included in the response.

Tenant health uses canonical integration keys (google_mail, monday, fortnox).
Platform capabilities are reported separately and never become tenant warnings
when an integration is not selected for the tenant.

Signal sources (internal only):
  - env/settings config presence
  - workflow_scan status + systems_scanned
  - IntegrationEvent records (dispatch/export events)
  - AuditEventRecord records (inbox_sync, scheduler actions)
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.admin.integrations.selection_resolver import (
    IntegrationSelectionView,
    derive_integration_selection,
    should_evaluate_tenant_health,
)
from app.integrations.keys import (
    TENANT_HEALTH_INTEGRATION_KEYS,
    display_name_sv,
    normalize_integration_key,
)
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


def _not_applicable_block(
    integration_key: str,
    selection: IntegrationSelectionView,
) -> dict[str, Any]:
    label = display_name_sv(integration_key)
    return {
        "status": "not_applicable",
        "selection_status": selection.selection_status,
        "configured": False,
        "last_success_at": None,
        "last_error_at": None,
        "last_error_message": None,
        "checks": [],
        "recommended_action": "",
        "description": f"{label} är inte vald för denna kund.",
    }


def _not_connected_block(
    integration_key: str,
    selection: IntegrationSelectionView,
) -> dict[str, Any]:
    label = display_name_sv(integration_key)
    return {
        "status": "not_connected",
        "selection_status": selection.selection_status,
        "configured": False,
        "last_success_at": None,
        "last_error_at": None,
        "last_error_message": None,
        "checks": [],
        "recommended_action": "",
        "description": f"{label} är vald men inte ansluten.",
    }


def _check_google_mail(settings: dict, app_settings: Any, db: Session, tenant_id: str) -> dict:
    from app.repositories.postgres.oauth_credential_repository import OAuthCredentialRepository

    checks = []
    oauth_row = OAuthCredentialRepository.get(db, tenant_id, "google_mail")
    platform_token = bool(getattr(app_settings, "GOOGLE_MAIL_ACCESS_TOKEN", ""))
    configured = oauth_row is not None or platform_token
    last_success_at = None
    last_error_at = None
    last_error_message = None
    token_expired = False

    checks.append(_check(
        "config_present",
        "pass" if configured else "fail",
        "Gmail-anslutning konfigurerad." if configured
        else "Gmail-anslutning saknas — anslut Google via operatörspanelen.",
    ))

    if configured:
        if oauth_row is not None and oauth_row.expires_at is not None:
            from datetime import datetime, timezone, timedelta

            expires = oauth_row.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires <= datetime.now(timezone.utc) + timedelta(minutes=5) and oauth_row.refresh_token:
                checks.append(_check(
                    "token_valid",
                    "warning",
                    "Access token nära utgång — förnyas automatiskt vid nästa anrop.",
                ))
        token_expired = _has_token_expiry_error(db, tenant_id, "gmail")
        if token_expired:
            checks.append(_check("token_valid", "fail",
                                 "OAuth-token har löpt ut — koppling måste förnyas."))

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

    failed_checks = [c for c in checks if c["status"] == "fail"]
    warn_checks   = [c for c in checks if c["status"] == "warning"]

    if not configured:
        status = "not_configured"
        action = "Konfigurera Gmail OAuth-uppgifter för att aktivera e-postintegrationen."
    elif token_expired:
        status = "error"
        action = "OAuth-token har löpt ut. Koppla om Gmail-integrationen via Google Cloud Console."
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


# Backward-compatible alias for tests importing _check_gmail.
_check_gmail = _check_google_mail


def _check_monday(settings: dict, app_settings: Any, db: Session, tenant_id: str) -> dict:
    checks = []
    configured = bool(getattr(app_settings, "MONDAY_API_KEY", ""))
    last_success_at = None
    last_error_at = None
    last_error_message = None

    checks.append(_check(
        "config_present",
        "pass" if configured else "fail",
        "Monday-anslutning konfigurerad." if configured
        else "Monday API-nyckel saknas — konfigurera MONDAY_API_KEY.",
    ))

    if configured:
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


def _check_fortnox_platform(app_settings: Any) -> dict[str, Any]:
    access_token = (getattr(app_settings, "FORTNOX_ACCESS_TOKEN", "") or "").strip()
    client_secret = (getattr(app_settings, "FORTNOX_CLIENT_SECRET", "") or "").strip()
    configured = bool(access_token and client_secret)
    return {
        "integration_key": "fortnox",
        "status": "configured" if configured else "not_configured",
        "configured": configured,
        "description": (
            "Fortnox-plattformskonfiguration finns."
            if configured
            else "Fortnox-plattformskonfiguration saknas."
        ),
    }


def _check_fortnox_tenant(settings: dict, app_settings: Any, db: Session, tenant_id: str) -> dict:
    checks = []
    access_token  = (getattr(app_settings, "FORTNOX_ACCESS_TOKEN",  "") or "").strip()
    client_secret = (getattr(app_settings, "FORTNOX_CLIENT_SECRET", "") or "").strip()
    configured = bool(access_token and client_secret)
    last_success_at = None
    last_error_at = None
    last_error_message = None
    token_expired = False

    checks.append(_check(
        "config_present",
        "pass" if configured else "fail",
        "Fortnox-anslutning konfigurerad." if configured
        else "Fortnox-uppgifter saknas — konfigurera access token och client secret.",
    ))

    if configured:
        token_expired = _has_token_expiry_error(db, tenant_id, "fortnox")
        if token_expired:
            checks.append(_check("token_valid", "fail",
                                 "Fortnox-token har löpt ut — access token måste förnyas."))

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


# Backward-compatible alias for tests importing _check_fortnox.
_check_fortnox = _check_fortnox_tenant

_TENANT_CHECKERS = {
    "google_mail": _check_google_mail,
    "monday": _check_monday,
    "fortnox": _check_fortnox_tenant,
}


def _apply_selection_to_health(
    integration_key: str,
    selection: IntegrationSelectionView,
    raw_health: dict[str, Any],
) -> dict[str, Any]:
    if selection.selection_status == "not_selected":
        return _not_applicable_block(integration_key, selection)

    result = dict(raw_health)
    result["selection_status"] = selection.selection_status

    if (
        selection.selection_status == "selected_optional"
        and raw_health.get("status") == "not_configured"
    ):
        return _not_connected_block(integration_key, selection)

    return result


# ---------------------------------------------------------------------------
# Overall aggregation
# ---------------------------------------------------------------------------

def _overall_status(systems: dict) -> str:
    statuses = [
        v["status"]
        for v in systems.values()
        if v.get("status") not in ("not_applicable", "not_connected")
    ]
    if not statuses:
        return "healthy"
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

    google_mail = systems.get("google_mail") or {}
    monday = systems.get("monday") or {}

    if google_mail.get("status") in {"error", "not_configured"}:
        signals.append({
            "severity": "critical",
            "area": "google_mail",
            "title": "Gmail integration is unavailable",
            "action": "Configure OAuth env vars and rerun setup verification.",
            "runbook_ref": "docs/12-production-guide.md#gmail-integration",
        })
    elif google_mail.get("status") == "warning":
        signals.append({
            "severity": "warning",
            "area": "google_mail",
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


def get_platform_integration_capabilities(
    app_settings: Any,
) -> dict[str, dict[str, Any]]:
    """Platform-level integration capability — never tenant-specific warnings."""
    return {
        "google_mail": {
            "integration_key": "google_mail",
            "status": "configured" if getattr(app_settings, "GOOGLE_MAIL_ACCESS_TOKEN", "") else "not_configured",
            "configured": bool(getattr(app_settings, "GOOGLE_MAIL_ACCESS_TOKEN", "")),
        },
        "monday": {
            "integration_key": "monday",
            "status": "configured" if getattr(app_settings, "MONDAY_API_KEY", "") else "not_configured",
            "configured": bool(getattr(app_settings, "MONDAY_API_KEY", "")),
        },
        "fortnox": _check_fortnox_platform(app_settings),
    }


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
    Compute integration health for tenant-selected systems.

    All checks are read-only and deterministic. No external API calls.
    No secret values appear in the response.
    """
    settings = TenantConfigRepository.get_settings(db, tenant_id)
    record = TenantConfigRepository.get(db, tenant_id)

    systems: dict[str, dict[str, Any]] = {}
    for integration_key in TENANT_HEALTH_INTEGRATION_KEYS:
        selection = derive_integration_selection(db, record, integration_key)
        if not should_evaluate_tenant_health(selection):
            systems[integration_key] = _not_applicable_block(integration_key, selection)
            continue
        checker = _TENANT_CHECKERS[integration_key]
        raw = checker(settings, app_settings, db, tenant_id)
        systems[integration_key] = _apply_selection_to_health(integration_key, selection, raw)

    recent_errors = _recent_errors(db, tenant_id)

    return {
        "tenant_id":      tenant_id,
        "overall_status": _overall_status(systems),
        "systems":        systems,
        "platform_capabilities": get_platform_integration_capabilities(app_settings),
        "recent_errors":  recent_errors,
        "runbook_signals": _build_runbook_signals(systems, recent_errors),
    }


def normalize_health_system_key(raw: str) -> str | None:
    """Normalize external/system keys to canonical integration keys."""
    return normalize_integration_key(raw)
