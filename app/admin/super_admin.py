"""
Super Admin overview service.

Aggregates tenant-level state for ALL tenants in the DB.
Read-only — no writes, no external API calls, no secrets in output.

This endpoint is sensitive (multi-tenant data). Caller must ensure
appropriate auth before exposing in a multi-customer production context.
Real owner/admin auth (e.g. a separate ADMIN_API_KEY env var) is required
before broad production exposure — currently protected by the same
per-tenant API key auth as other operator endpoints.

For each tenant, computes:
  - onboarding status / percent (from get_onboarding_status)
  - pilot readiness status / percent (from get_pilot_readiness)
  - integration health (from get_integration_health)
  - dispatch 30d stats (from get_dispatch_report)
  - recent error count (from _recent_errors)
  - latest_activity_at (from AuditEventRecord)

Top-level response:
  total_tenants, healthy, warning, error, not_ready,
  total_hours_saved_30d, items: [...]
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

# Module-level imports for test patchability
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
from app.repositories.postgres.audit_models import AuditEventRecord
from app.health.integration_health import get_integration_health
from app.health.production_readiness import get_pilot_readiness
from app.onboarding.readiness import get_onboarding_status
from app.workflows.dispatchers.observability import get_dispatch_report

_MINUTES_PER_DISPATCH = 5  # same constant as observability.py


# ---------------------------------------------------------------------------
# Per-tenant helpers
# ---------------------------------------------------------------------------

def _latest_activity_at(db: Session, tenant_id: str) -> str | None:
    """Return the most recent AuditEventRecord created_at for the tenant, or None."""
    record = (
        db.query(AuditEventRecord)
        .filter(AuditEventRecord.tenant_id == tenant_id)
        .order_by(AuditEventRecord.created_at.desc())
        .first()
    )
    if record and record.created_at:
        return record.created_at.isoformat()
    return None


def _recent_error_count(db: Session, tenant_id: str) -> int:
    """Return number of failed AuditEventRecords in last 30 days for the tenant."""
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    return (
        db.query(AuditEventRecord)
        .filter(
            AuditEventRecord.tenant_id == tenant_id,
            AuditEventRecord.status == "failed",
            AuditEventRecord.created_at >= cutoff,
        )
        .count()
    )


def _tenant_overall_status(
    onboarding_status: str,
    pilot_status: str,
    integration_status: str,
) -> str:
    """
    Derive a single tenant-level health status.

    Priority: error → warning → not_ready → healthy
    """
    if integration_status == "error":
        return "error"
    if pilot_status == "not_ready":
        return "not_ready"
    if integration_status == "warning" or onboarding_status in ("not_started", "in_progress"):
        return "warning"
    if pilot_status == "almost_ready":
        return "warning"
    return "healthy"


def _build_tenant_summary(
    db: Session,
    tenant_id: str,
    name: str | None,
    app_settings: Any,
) -> dict[str, Any]:
    """Build the per-tenant summary dict. Errors are caught per-tenant to avoid poisoning the full overview."""
    try:
        onboarding = get_onboarding_status(db, tenant_id, app_settings=app_settings)
        onb_status  = onboarding.get("status", "not_started")
        onb_percent = onboarding.get("score", {}).get("percent", 0)
    except Exception:
        onb_status, onb_percent = "not_started", 0

    try:
        pilot = get_pilot_readiness(db, tenant_id, app_settings=app_settings)
        pilot_status  = pilot.get("overall_status", "not_ready")
        pilot_score   = pilot.get("score", {})
        pilot_passed  = pilot_score.get("passed", 0)
        pilot_total   = pilot_score.get("total", 1) or 1
        pilot_percent = round(pilot_passed / pilot_total * 100)
    except Exception:
        pilot_status, pilot_percent = "not_ready", 0

    try:
        health = get_integration_health(db, tenant_id, app_settings=app_settings)
        integration_overall = health.get("overall_status", "warning")
        systems = health.get("systems", {})
        gmail_status   = (systems.get("gmail")   or {}).get("status", "not_configured")
        monday_status  = (systems.get("monday")  or {}).get("status", "not_configured")
        fortnox_status = (systems.get("fortnox") or {}).get("status", "not_configured")
    except Exception:
        integration_overall = "warning"
        gmail_status = monday_status = fortnox_status = "not_configured"

    try:
        report = get_dispatch_report(db, tenant_id, range_="30d")
        headline = report.get("headline", {})
        total_30d   = headline.get("dispatches_completed", 0)
        hours_30d   = headline.get("time_saved_hours", 0.0)
        success_rate = headline.get("success_rate_percent", 0)
        auto_share   = headline.get("automation_share_percent", 0)
        # Derive failed from total and success_rate
        success_30d = round(total_30d * success_rate / 100) if total_30d else 0
        failed_30d  = total_30d - success_30d
    except Exception:
        total_30d = success_30d = failed_30d = 0
        hours_30d = 0.0
        auto_share = 0

    try:
        error_count = _recent_error_count(db, tenant_id)
    except Exception:
        error_count = 0

    try:
        activity_at = _latest_activity_at(db, tenant_id)
    except Exception:
        activity_at = None

    overall = _tenant_overall_status(onb_status, pilot_status, integration_overall)

    return {
        "tenant_id": tenant_id,
        "name":      name or tenant_id,
        "status":    overall,
        "onboarding": {
            "status":  onb_status,
            "percent": onb_percent,
        },
        "pilot_readiness": {
            "status":  pilot_status,
            "percent": pilot_percent,
        },
        "integrations": {
            "overall_status": integration_overall,
            "gmail":          gmail_status,
            "monday":         monday_status,
            "fortnox":        fortnox_status,
        },
        "dispatch": {
            "total_30d":                  total_30d,
            "success_30d":                success_30d,
            "failed_30d":                 failed_30d,
            "hours_saved_30d":            round(hours_30d, 2),
            "automation_share_percent_30d": auto_share,
        },
        "latest_activity_at": activity_at,
        "recent_error_count": error_count,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_super_admin_overview(
    db: Session,
    *,
    app_settings: Any,
) -> dict[str, Any]:
    """
    Aggregate tenant-level health state for all DB tenants.

    Read-only. No external API calls. No secrets in response.
    One failing tenant does not abort the rest.
    """
    records = TenantConfigRepository.list_all(db)

    items: list[dict] = []
    for record in records:
        summary = _build_tenant_summary(
            db,
            tenant_id=record.tenant_id,
            name=record.name,
            app_settings=app_settings,
        )
        items.append(summary)

    # Top-level status counts
    counts: dict[str, int] = {"healthy": 0, "warning": 0, "error": 0, "not_ready": 0}
    total_hours = 0.0
    for item in items:
        s = item["status"]
        counts[s] = counts.get(s, 0) + 1
        total_hours += item["dispatch"]["hours_saved_30d"]

    return {
        "total_tenants":       len(items),
        "healthy":             counts["healthy"],
        "warning":             counts["warning"],
        "error":               counts["error"],
        "not_ready":           counts["not_ready"],
        "total_hours_saved_30d": round(total_hours, 2),
        "items":               items,
    }
