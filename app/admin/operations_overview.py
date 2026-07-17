"""
Global operations overview aggregation service.

Read-only. No writes, no external API calls, no secrets in response.

Counter definitions (locked, tested):
  active_tenants       — TenantConfigRecord where status == "active"; point-in-time, no window
  jobs_last_24h        — JobRecord created_at >= now - 24h
  pending_approvals    — ApprovalRequestRecord state == "pending"; point-in-time, no window
  open_manual_reviews  — JobRecord status == "manual_review"; point-in-time, no window
  failed_jobs          — JobRecord status == "failed", updated_at >= now - 48h
  stuck_jobs           — JobRecord status IN ("pending","processing"), updated_at < now - 48h
  integration_errors   — IntegrationEvent status == "failed", created_at >= now - 24h

Platform status priority (highest wins):
  1. critical — database unavailable (not used in practice; DB errors yield 503)
  2. failed   — integration failed with affected tenants, or stuck_jobs > 0
  3. warning  — failed_jobs, integration_errors, open_manual_reviews, or integration warning/unknown
  4. healthy  — no above signals and no unknown integrations
  5. unknown  — mandatory signal could not be determined

Priority list sorting (overview-specific, independent of needs-help order):
  1. severity (critical < high < medium < info)
  2. external/uncertain impact before internal (area starts with "integration")
  3. oldest unresolved first (created_at ascending)
  4. stable id lexicographic tie-breaker

Inherited N+1 cost: collect_all_triage_rows loops per tenant for triage signals.
No new triage engine or cache in this chapter.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.admin.operations_triage import (
    _FAILED_JOBS_WINDOW_H,
    _map_priority_item,
    _priority_id,
    _sort_priority_rows,
    collect_all_triage_rows,
)
from app.domain.integrations.models import IntegrationEvent
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

logger = logging.getLogger(__name__)

_STUCK_JOB_WINDOW_H = 48
_OVERVIEW_INTEGRATION_TYPES = ("google_mail", "visma", "google_sheets")
_NO_BACKUP_DEPLOY_SOURCE = "Ingen backup-/deploykälla finns i plattformen ännu."
_API_DESCRIPTION = (
    "API-processen svarade och kunde generera översikten. "
    "Detta intygar inte att bakgrundsflöden (scheduler, köbearbetning) är friska "
    "— se separata signaler."
)


class OperationsOverviewUnavailable(Exception):
    """Raised when a mandatory global aggregation query fails."""


def _counter(value: int, window_hours: int | None) -> dict[str, Any]:
    return {"value": value, "window_hours": window_hours}


def _count_active_and_total_tenants(records: list[Any]) -> int:
    return sum(1 for r in records if getattr(r, "status", None) == "active")


def _count_jobs_last_24h(db: Session, since: datetime) -> int:
    return (
        db.query(JobRecord)
        .filter(JobRecord.created_at >= since)
        .count()
    )


def _count_pending_approvals(db: Session) -> int:
    return (
        db.query(ApprovalRequestRecord)
        .filter(ApprovalRequestRecord.state == "pending")
        .count()
    )


def _count_open_manual_reviews(db: Session) -> int:
    return (
        db.query(JobRecord)
        .filter(JobRecord.status == "manual_review")
        .count()
    )


def _count_failed_jobs(db: Session, since: datetime) -> int:
    return (
        db.query(JobRecord)
        .filter(
            JobRecord.status == "failed",
            JobRecord.updated_at >= since,
        )
        .count()
    )


def _count_stuck_jobs(db: Session, cutoff: datetime) -> int:
    return (
        db.query(JobRecord)
        .filter(
            JobRecord.status.in_(("pending", "processing")),
            JobRecord.updated_at < cutoff,
        )
        .count()
    )


def _integration_event_breakdown(
    db: Session,
    since: datetime,
) -> dict[str, dict[str, int]]:
    """Per integration_type: failed count, total events, distinct tenants with failures."""
    all_events = (
        db.query(IntegrationEvent)
        .filter(
            IntegrationEvent.created_at >= since,
            IntegrationEvent.integration_type.in_(_OVERVIEW_INTEGRATION_TYPES),
        )
        .all()
    )
    breakdown: dict[str, dict[str, int]] = {
        t: {"issues": 0, "total_events": 0, "affected_tenants": 0}
        for t in _OVERVIEW_INTEGRATION_TYPES
    }
    failed_tenants: dict[str, set[str]] = {t: set() for t in _OVERVIEW_INTEGRATION_TYPES}
    for ev in all_events:
        itype = ev.integration_type
        if itype not in breakdown:
            continue
        breakdown[itype]["total_events"] += 1
        if ev.status == "failed":
            breakdown[itype]["issues"] += 1
            if ev.tenant_id:
                failed_tenants[itype].add(ev.tenant_id)
    for itype in _OVERVIEW_INTEGRATION_TYPES:
        breakdown[itype]["affected_tenants"] = len(failed_tenants[itype])
    return breakdown


def _gmail_status_from_triage_rows(
    all_rows: list[dict[str, Any]],
    tenant_count: int,
) -> dict[str, Any]:
    """Aggregate gmail health from integration triage rows (area == integration, gmail title)."""
    gmail_rows = [
        r for r in all_rows
        if r.get("area") == "integration"
        and "gmail" in (r.get("title") or "").lower()
    ]
    if tenant_count == 0:
        return {
            "status": "unknown",
            "issues": 0,
            "affected_tenants": 0,
            "data_source": "integration_health_check",
        }
    if not gmail_rows:
        return {
            "status": "healthy",
            "issues": 0,
            "affected_tenants": 0,
            "data_source": "integration_health_check",
        }
    affected = len({r["tenant_id"] for r in gmail_rows})
    severities = {r.get("severity") for r in gmail_rows}
    if severities & {"critical", "high"}:
        status = "failed"
    elif "medium" in severities:
        status = "warning"
    else:
        status = "warning"
    return {
        "status": status,
        "issues": len(gmail_rows),
        "affected_tenants": affected,
        "data_source": "integration_health_check",
    }


def _event_log_integration_status(
    breakdown: dict[str, dict[str, int]],
    integration_key: str,
    event_type: str,
) -> dict[str, Any]:
    data = breakdown.get(event_type, {"issues": 0, "total_events": 0, "affected_tenants": 0})
    total = data["total_events"]
    issues = data["issues"]
    affected = data["affected_tenants"]
    if total == 0:
        status = "unknown"
    elif issues == 0:
        status = "healthy"
    elif affected <= 1:
        status = "warning"
    else:
        status = "failed"
    return {
        "status": status,
        "issues": issues,
        "affected_tenants": affected,
        "data_source": "integration_event_log",
    }


def _compute_integration_status(
    breakdown: dict[str, dict[str, int]],
    gmail_from_triage: dict[str, Any],
) -> dict[str, Any]:
    return {
        "gmail": gmail_from_triage,
        "visma": _event_log_integration_status(breakdown, "visma", "visma"),
        "google_sheets": _event_log_integration_status(
            breakdown, "google_sheets", "google_sheets"
        ),
    }


def _derive_scheduler_signal(records: list[Any]) -> dict[str, Any]:
    has_failure = False
    has_warning = False
    for record in records:
        settings = getattr(record, "settings", None) or {}
        scheduler_state = settings.get("scheduler_state") or {}
        last_status = scheduler_state.get("last_status")
        if last_status == "failed":
            has_failure = True
        elif last_status == "warning":
            has_warning = True
        run_mode = (settings.get("scheduler") or {}).get("run_mode") or settings.get("run_mode")
        if run_mode == "paused":
            return {"status": "paused", "description": "Minst en tenant har scheduler pausad."}
    if has_failure:
        return {"status": "failed", "description": "Scheduler-fel rapporterat för minst en tenant."}
    if has_warning:
        return {"status": "warning", "description": "Scheduler-varning för minst en tenant."}
    if not records:
        return {"status": "unknown", "description": "Inga tenants konfigurerade."}
    return {"status": "healthy", "description": "Inga scheduler-fel i tenant-konfiguration."}


def _compute_platform_status(
    counters: dict[str, Any],
    integrations: dict[str, Any],
    system: dict[str, Any],
) -> dict[str, Any]:
    if system.get("database", {}).get("status") == "failed":
        return {
            "level": "critical",
            "label": "Kritiskt",
            "summary": "Databasen är otillgänglig.",
        }
    stuck = counters.get("stuck_jobs", {}).get("value", 0)
    for key in ("gmail", "visma", "google_sheets"):
        integ = integrations.get(key, {})
        if integ.get("status") == "failed" and integ.get("affected_tenants", 0) > 0:
            return {
                "level": "failed",
                "label": "Fel",
                "summary": f"Integrationsfel påverkar kunder ({key}).",
            }
    if stuck > 0:
        return {
            "level": "failed",
            "label": "Fel",
            "summary": f"{stuck} jobb har fastnat i kön.",
        }
    failed_jobs = counters.get("failed_jobs", {}).get("value", 0)
    integration_errors = counters.get("integration_errors", {}).get("value", 0)
    open_reviews = counters.get("open_manual_reviews", {}).get("value", 0)
    has_warning_integ = any(
        integrations.get(k, {}).get("status") in ("warning", "unknown")
        for k in ("gmail", "visma", "google_sheets")
    )
    if failed_jobs > 0 or integration_errors > 0 or open_reviews > 0 or has_warning_integ:
        parts = []
        if failed_jobs:
            parts.append(f"{failed_jobs} misslyckade jobb")
        if integration_errors:
            parts.append(f"{integration_errors} integrationsfel")
        if open_reviews:
            parts.append(f"{open_reviews} manuella granskningar")
        if has_warning_integ:
            parts.append("integrationsstatus oklar")
        return {
            "level": "warning",
            "label": "Varning",
            "summary": "; ".join(parts) + "." if parts else "Avvikelser kräver uppmärksamhet.",
        }
    has_unknown = any(
        integrations.get(k, {}).get("status") == "unknown"
        for k in ("gmail", "visma", "google_sheets")
    )
    if has_unknown:
        return {
            "level": "warning",
            "label": "Varning",
            "summary": "Minst en integration har okänd status.",
        }
    if system.get("database", {}).get("status") == "unknown":
        return {
            "level": "unknown",
            "label": "Okänd",
            "summary": "Plattformsstatus kunde inte fastställas.",
        }
    return {
        "level": "healthy",
        "label": "Frisk",
        "summary": "Inga kritiska avvikelser.",
    }


def _build_priority_items(
    all_rows: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    sorted_rows = _sort_priority_rows(all_rows)
    return [_map_priority_item(r) for r in sorted_rows[:limit]]


def get_operations_overview(
    db: Session,
    *,
    app_settings: Any,
    period_hours: int = 24,
    priority_limit: int = 15,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    period_start = now - timedelta(hours=period_hours)
    since_48h = now - timedelta(hours=_FAILED_JOBS_WINDOW_H)
    stuck_cutoff = now - timedelta(hours=_STUCK_JOB_WINDOW_H)

    try:
        tenant_records = TenantConfigRepository.list_all(db)
        active_tenants = _count_active_and_total_tenants(tenant_records)
        jobs_last_24h = _count_jobs_last_24h(db, period_start)
        pending_approvals = _count_pending_approvals(db)
        open_manual_reviews = _count_open_manual_reviews(db)
        failed_jobs = _count_failed_jobs(db, since_48h)
        stuck_jobs = _count_stuck_jobs(db, stuck_cutoff)
        event_breakdown = _integration_event_breakdown(db, period_start)
        integration_errors = sum(
            event_breakdown.get(t, {}).get("issues", 0) for t in _OVERVIEW_INTEGRATION_TYPES
        )
    except Exception as exc:
        logger.error(
            "operations_overview_query_failed",
            exc_info=False,
            extra={"error_type": type(exc).__name__},
        )
        raise OperationsOverviewUnavailable from exc

    all_triage_rows = collect_all_triage_rows(db, app_settings=app_settings)
    gmail_status = _gmail_status_from_triage_rows(all_triage_rows, len(tenant_records))
    integrations = _compute_integration_status(event_breakdown, gmail_status)

    counters = {
        "active_tenants": _counter(active_tenants, None),
        "jobs_last_24h": _counter(jobs_last_24h, period_hours),
        "pending_approvals": _counter(pending_approvals, None),
        "open_manual_reviews": _counter(open_manual_reviews, None),
        "failed_jobs": _counter(failed_jobs, _FAILED_JOBS_WINDOW_H),
        "stuck_jobs": _counter(stuck_jobs, _STUCK_JOB_WINDOW_H),
        "integration_errors": _counter(integration_errors, period_hours),
    }

    system = {
        "api": {"status": "healthy", "description": _API_DESCRIPTION},
        "database": {"status": "healthy", "description": "Aggregeringsfrågor lyckades."},
        "scheduler": _derive_scheduler_signal(tenant_records),
        "backup": {"status": "unknown", "data_source": _NO_BACKUP_DEPLOY_SOURCE},
        "deploy": {"status": "unknown", "data_source": _NO_BACKUP_DEPLOY_SOURCE},
    }

    platform_status = _compute_platform_status(counters, integrations, system)
    priorities = _build_priority_items(all_triage_rows, priority_limit)

    return {
        "generated_at": now,
        "period": {"hours": period_hours, "started_at": period_start},
        "platform_status": platform_status,
        "counters": counters,
        "integrations": integrations,
        "system": system,
        "priorities": priorities,
    }
