"""
Admin operations triage service.

Aggregates actionable problems across ALL tenants for the super-admin
"needs-help" queue.  Read-only — no writes, no external API calls, no
secrets in the response.

Each row returned has the shape:
  {
    "tenant_id":          str,
    "tenant_name":        str,
    "severity":           "critical" | "high" | "medium" | "info",
    "area":               str,          # e.g. "integration", "approval", "pipeline"
    "title":              str,
    "detail":             str,
    "job_id":             str | None,
    "approval_id":        str | None,
    "created_at":         str | None,   # ISO-8601
    "recommended_action": str,
    "runbook_ref":        str,
  }

Top-level response:
  {
    "total":   int,
    "critical": int,
    "high":     int,
    "medium":   int,
    "items":   list[dict],
  }
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.job_models import JobRecord
from app.domain.integrations.models import IntegrationEvent
from app.health.integration_health import get_integration_health


_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "info": 3}
_FAILED_JOBS_WINDOW_H = 48
_STALE_APPROVAL_WINDOW_H = 24
_RECENT_ERRORS_WINDOW_D = 7


# ---------------------------------------------------------------------------
# Row builder helpers
# ---------------------------------------------------------------------------

def _row(
    *,
    tenant_id: str,
    tenant_name: str,
    severity: str,
    area: str,
    title: str,
    detail: str,
    job_id: str | None = None,
    approval_id: str | None = None,
    created_at: str | None = None,
    recommended_action: str = "",
    runbook_ref: str = "",
) -> dict[str, Any]:
    return {
        "tenant_id":          tenant_id,
        "tenant_name":        tenant_name or tenant_id,
        "severity":           severity,
        "area":               area,
        "title":              title,
        "detail":             detail,
        "job_id":             job_id,
        "approval_id":        approval_id,
        "created_at":         created_at,
        "recommended_action": recommended_action,
        "runbook_ref":        runbook_ref,
    }


# ---------------------------------------------------------------------------
# Per-tenant signal extractors
# ---------------------------------------------------------------------------

def _integration_signals(
    db: Session,
    tenant_id: str,
    tenant_name: str,
    app_settings: Any,
) -> list[dict]:
    rows: list[dict] = []
    try:
        health = get_integration_health(db, tenant_id, app_settings=app_settings)
        systems = health.get("systems", {})
        for system_name, sys_data in systems.items():
            status = sys_data.get("status", "not_configured")
            if status in ("error", "not_configured"):
                severity = "critical" if status == "error" else "high"
                rows.append(_row(
                    tenant_id=tenant_id,
                    tenant_name=tenant_name,
                    severity=severity,
                    area="integration",
                    title=f"{system_name.capitalize()} integration is {status.replace('_', ' ')}",
                    detail=sys_data.get("recommended_action", "Check integration configuration."),
                    recommended_action=sys_data.get("recommended_action", ""),
                    runbook_ref="docs/runbook-oauth.md" if system_name == "gmail" else "docs/12-production-guide.md",
                ))
            elif status == "warning":
                rows.append(_row(
                    tenant_id=tenant_id,
                    tenant_name=tenant_name,
                    severity="medium",
                    area="integration",
                    title=f"{system_name.capitalize()} integration needs validation",
                    detail=sys_data.get("recommended_action", "Run workflow scan to confirm connection."),
                    recommended_action=sys_data.get("recommended_action", ""),
                    runbook_ref="docs/runbook-oauth.md" if system_name == "gmail" else "docs/12-production-guide.md",
                ))
    except Exception:
        pass
    return rows


def _failed_pipeline_signals(
    db: Session,
    tenant_id: str,
    tenant_name: str,
) -> list[dict]:
    """Recent failed jobs in the last 48 hours."""
    rows: list[dict] = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=_FAILED_JOBS_WINDOW_H)
    try:
        failed_jobs = (
            db.query(JobRecord)
            .filter(
                JobRecord.tenant_id == tenant_id,
                JobRecord.status == "failed",
                JobRecord.updated_at >= cutoff,
            )
            .order_by(JobRecord.updated_at.desc())
            .limit(5)
            .all()
        )
        for job in failed_jobs:
            result = job.result or {}
            error_msg = result.get("error") or result.get("message") or "No error detail available."
            rows.append(_row(
                tenant_id=tenant_id,
                tenant_name=tenant_name,
                severity="high",
                area="pipeline",
                title=f"Failed {job.job_type} job",
                detail=str(error_msg)[:200],
                job_id=job.job_id,
                created_at=job.updated_at.isoformat() if job.updated_at else None,
                recommended_action="Review job detail and re-run or escalate.",
                runbook_ref="docs/runbook-pilot-support.md",
            ))
    except Exception:
        pass
    return rows


def _stale_approval_signals(
    db: Session,
    tenant_id: str,
    tenant_name: str,
) -> list[dict]:
    """Pending approvals older than 24 hours."""
    rows: list[dict] = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=_STALE_APPROVAL_WINDOW_H)
    try:
        stale = (
            db.query(ApprovalRequestRecord)
            .filter(
                ApprovalRequestRecord.tenant_id == tenant_id,
                ApprovalRequestRecord.state == "pending",
                ApprovalRequestRecord.created_at < cutoff,
            )
            .order_by(ApprovalRequestRecord.created_at.asc())
            .limit(5)
            .all()
        )
        for appr in stale:
            kind = appr.next_on_approve or "pipeline"
            area = "approval_email" if kind == "email_send" else "approval_dispatch" if kind == "controlled_dispatch" else "approval"
            title_map = {
                "email_send":          "Customer email waiting > 24 h for approval",
                "controlled_dispatch": "Dispatch approval pending > 24 h",
            }
            title = title_map.get(kind, f"Approval pending > 24 h ({kind})")
            hours = int((datetime.now(timezone.utc) - _ensure_aware(appr.created_at)).total_seconds() / 3600)
            rows.append(_row(
                tenant_id=tenant_id,
                tenant_name=tenant_name,
                severity="high",
                area=area,
                title=title,
                detail=f"Approval ID {appr.approval_id[:8]} has been pending for {hours} hours. Job: {appr.job_id[:8]}.",
                job_id=appr.job_id,
                approval_id=appr.approval_id,
                created_at=appr.created_at.isoformat() if appr.created_at else None,
                recommended_action="Review and approve or reject the pending approval.",
                runbook_ref="docs/runbook-pilot-support.md",
            ))
    except Exception:
        pass
    return rows


def _failed_integration_event_signals(
    db: Session,
    tenant_id: str,
    tenant_name: str,
) -> list[dict]:
    """Recent failed integration events (dispatch/export failures)."""
    rows: list[dict] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=_RECENT_ERRORS_WINDOW_D)
    try:
        failed_events = (
            db.query(IntegrationEvent)
            .filter(
                IntegrationEvent.tenant_id == tenant_id,
                IntegrationEvent.status == "failed",
                IntegrationEvent.created_at >= cutoff,
            )
            .order_by(IntegrationEvent.created_at.desc())
            .limit(5)
            .all()
        )
        for ev in failed_events:
            error_msg = ev.last_error or "No error detail."
            rows.append(_row(
                tenant_id=tenant_id,
                tenant_name=tenant_name,
                severity="high",
                area="integration_event",
                title=f"Failed {ev.integration_type} action",
                detail=str(error_msg)[:200],
                job_id=ev.job_id,
                created_at=ev.created_at.isoformat() if ev.created_at else None,
                recommended_action="Check integration credentials and retry from case detail.",
                runbook_ref="docs/runbook-oauth.md",
            ))
    except Exception:
        pass
    return rows


def _failed_scheduler_signals(
    db: Session,
    tenant_id: str,
    tenant_name: str,
) -> list[dict]:
    """Recent scheduler or inbox-sync failures from audit events."""
    rows: list[dict] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=_RECENT_ERRORS_WINDOW_D)
    try:
        failed = (
            db.query(AuditEventRecord)
            .filter(
                AuditEventRecord.tenant_id == tenant_id,
                AuditEventRecord.status == "failed",
                AuditEventRecord.category.in_(["scheduler", "inbox_sync", "oauth"]),
                AuditEventRecord.created_at >= cutoff,
            )
            .order_by(AuditEventRecord.created_at.desc())
            .limit(3)
            .all()
        )
        for ev in failed:
            rows.append(_row(
                tenant_id=tenant_id,
                tenant_name=tenant_name,
                severity="medium",
                area=ev.category,
                title=f"{ev.category.replace('_', ' ').capitalize()} failure: {ev.action}",
                detail=str(ev.details or {})[:200],
                created_at=ev.created_at.isoformat() if ev.created_at else None,
                recommended_action="Check scheduler status and logs.",
                runbook_ref="docs/runbook-scheduler.md",
            ))
    except Exception:
        pass
    return rows


# ---------------------------------------------------------------------------
# Tenant aggregator
# ---------------------------------------------------------------------------

def _build_tenant_triage(
    db: Session,
    tenant_id: str,
    tenant_name: str,
    app_settings: Any,
) -> list[dict]:
    """Collect all triage rows for a single tenant. Errors are silently skipped."""
    rows: list[dict] = []
    rows.extend(_integration_signals(db, tenant_id, tenant_name, app_settings))
    rows.extend(_failed_pipeline_signals(db, tenant_id, tenant_name))
    rows.extend(_stale_approval_signals(db, tenant_id, tenant_name))
    rows.extend(_failed_integration_event_signals(db, tenant_id, tenant_name))
    rows.extend(_failed_scheduler_signals(db, tenant_id, tenant_name))
    return rows


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_admin_needs_help(
    db: Session,
    *,
    app_settings: Any,
    limit: int = 50,
) -> dict[str, Any]:
    """
    Aggregate operational triage rows across all DB tenants.

    Read-only.  No external API calls.  No secrets in response.
    One failing tenant does not abort the rest.
    Returns rows sorted by severity (critical → high → medium → info),
    then by created_at descending within each severity bucket.
    """
    records = TenantConfigRepository.list_all(db)

    all_rows: list[dict] = []
    for record in records:
        try:
            tenant_rows = _build_tenant_triage(
                db,
                tenant_id=record.tenant_id,
                tenant_name=record.name or record.tenant_id,
                app_settings=app_settings,
            )
            all_rows.extend(tenant_rows)
        except Exception:
            pass

    # Sort: severity priority first, then newest first
    all_rows.sort(
        key=lambda r: (
            _SEVERITY_ORDER.get(r["severity"], 99),
            # Negate timestamp so newer rows come first within a severity bucket
            -(datetime.fromisoformat(r["created_at"]).timestamp()
              if r.get("created_at") else 0),
        )
    )
    all_rows = all_rows[:limit]

    counts = {"critical": 0, "high": 0, "medium": 0, "info": 0}
    for r in all_rows:
        counts[r["severity"]] = counts.get(r["severity"], 0) + 1

    return {
        "total":    len(all_rows),
        "critical": counts["critical"],
        "high":     counts["high"],
        "medium":   counts["medium"],
        "items":    all_rows,
    }


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _ensure_aware(dt: datetime | None) -> datetime:
    if dt is None:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
