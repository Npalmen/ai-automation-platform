"""
Admin operations triage service.

Aggregates actionable problems across ALL tenants for the super-admin
"needs-help" queue.  Read-only — no writes, no external API calls, no
secrets in the response.

Each row returned has the shape documented in _row().  After collection,
rows pass through dedupe_and_normalize_signals for a shared current-state
view consumed by Kapitel 2, 3, 4 and get_admin_needs_help.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.admin.support_console import _get_automation
from app.admin.alerts.signal_sources import collect_stale_approval_signals
from app.domain.integrations.models import IntegrationEvent
from app.health.integration_health import get_integration_health
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

SignalState = Literal["yes", "no", "unknown", "not_applicable"]

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "info": 3}
_FAILED_JOBS_WINDOW_H = 48
_RECENT_ERRORS_WINDOW_D = 7
_INTEGRATION_EVENT_LOOKBACK_D = 14
_IMPACT_MAX_LEN = 200

_SEVERITY_BADGE_MAP = {
    "critical": "P1",
    "high": "P2",
    "medium": "P3",
    "info": "P4",
}

_RUNBOOK_REGISTRY: dict[str, dict[str, str]] = {
    "oauth_integration": {"id": "oauth_integration", "label": "OAuth och integration"},
    "pilot_support": {"id": "pilot_support", "label": "Pilotstöd"},
    "scheduler": {"id": "scheduler", "label": "Scheduler"},
    "visma_write_safety": {"id": "visma_write_safety", "label": "Visma write safety"},
    "tenant_configuration": {"id": "tenant_configuration", "label": "Tenantkonfiguration"},
    "integration_general": {"id": "integration_general", "label": "Integration (allmänt)"},
}


def _resolve_runbook(runbook_id: str) -> dict[str, str] | None:
    if not runbook_id:
        return None
    entry = _RUNBOOK_REGISTRY.get(runbook_id)
    if entry is None:
        return None
    return {"id": entry["id"], "label": entry["label"]}


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
    source_id: str | None = None,
    source_type: str = "",
    detected_at: str | None = None,
    last_observed_at: str | None = None,
    retryable: SignalState = "unknown",
    external_impact: SignalState = "unknown",
) -> dict[str, Any]:
    ts = created_at
    detected = detected_at if detected_at is not None else ts
    observed = last_observed_at if last_observed_at is not None else ts
    return {
        "tenant_id": tenant_id,
        "tenant_name": tenant_name or tenant_id,
        "severity": severity,
        "area": area,
        "title": title,
        "detail": detail,
        "job_id": job_id,
        "approval_id": approval_id,
        "created_at": ts,
        "recommended_action": recommended_action,
        "runbook_ref": runbook_ref,
        "source_id": source_id,
        "source_type": source_type,
        "detected_at": detected,
        "last_observed_at": observed,
        "retryable": retryable,
        "external_impact": external_impact,
    }


def _normalize_tenant_status(status: str | None) -> str:
    value = (status or "").strip().lower()
    if value == "active":
        return "active"
    if value == "inactive":
        return "inactive"
    return "unknown"


def _signal_key(row: dict[str, Any]) -> tuple:
    source_id = row.get("source_id")
    if source_id:
        return ("source", row.get("tenant_id", ""), source_id)
    job_id = row.get("job_id")
    if job_id:
        return ("job", row.get("tenant_id", ""), row.get("area", ""), job_id)
    approval_id = row.get("approval_id")
    if approval_id:
        return ("approval", row.get("tenant_id", ""), approval_id)
    return ("generic", row.get("tenant_id", ""), row.get("area", ""), row.get("title", ""))


def _iso_timestamp(value: str | None, *, missing: float = float("inf")) -> float:
    if not value:
        return missing
    try:
        return datetime.fromisoformat(value).timestamp()
    except (TypeError, ValueError):
        return missing


def dedupe_and_normalize_signals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Collapse duplicate signals by stable key.

    Per group: keep highest severity, earliest detected_at, latest last_observed_at.
    """
    groups: dict[tuple, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(_signal_key(row), []).append(row)

    normalized: list[dict[str, Any]] = []
    for group_rows in groups.values():
        representative = min(
            group_rows,
            key=lambda r: _SEVERITY_ORDER.get(r.get("severity", ""), 99),
        )
        detected_values = [
            r.get("detected_at") or r.get("created_at")
            for r in group_rows
            if r.get("detected_at") or r.get("created_at")
        ]
        observed_values = [
            r.get("last_observed_at") or r.get("created_at")
            for r in group_rows
            if r.get("last_observed_at") or r.get("created_at")
        ]
        earliest_detected = (
            min(detected_values, key=lambda v: _iso_timestamp(v))
            if detected_values else None
        )
        latest_observed = (
            max(
                observed_values,
                key=lambda v: _iso_timestamp(v, missing=float("-inf")),
            )
            if observed_values else None
        )
        normalized.append({
            **representative,
            "detected_at": earliest_detected or representative.get("detected_at"),
            "last_observed_at": latest_observed or representative.get("last_observed_at"),
        })
    return normalized


# ---------------------------------------------------------------------------
# Priority mapping (shared by Kapitel 2, 3, 4)
# ---------------------------------------------------------------------------

def _priority_id(row: dict[str, Any]) -> str:
    source_id = row.get("source_id")
    if source_id:
        return str(source_id)
    job_id = row.get("job_id")
    if job_id:
        return f"job:{job_id}"
    approval_id = row.get("approval_id")
    if approval_id:
        return f"approval:{approval_id}"
    created_at = row.get("created_at") or ""
    payload = (
        f"{row.get('tenant_id', '')}|{row.get('area', '')}|"
        f"{row.get('title', '')}|{created_at}"
    )
    digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
    return f"hash:{digest}"


def _is_external_or_uncertain(area: str | None) -> bool:
    return bool(area and area.startswith("integration"))


def _created_at_sort_key(created_at: str | None) -> float:
    return _iso_timestamp(created_at)


def _sort_priority_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    with_ids = [{**r, "_sort_id": _priority_id(r)} for r in rows]
    with_ids.sort(
        key=lambda r: (
            _SEVERITY_ORDER.get(r.get("severity", ""), 99),
            not _is_external_or_uncertain(r.get("area")),
            _created_at_sort_key(r.get("detected_at") or r.get("created_at")),
            r["_sort_id"],
        )
    )
    return [{k: v for k, v in r.items() if k != "_sort_id"} for r in with_ids]


def _truncate_impact(detail: str | None) -> str:
    text = str(detail or "")
    if len(text) <= _IMPACT_MAX_LEN:
        return text
    return text[: _IMPACT_MAX_LEN - 3] + "..."


def _age_hours(detected_at: str | None) -> int | None:
    if not detected_at:
        return None
    try:
        dt = datetime.fromisoformat(detected_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        return max(0, int(delta.total_seconds() / 3600))
    except (TypeError, ValueError):
        return None


def _collapse_tri_state(value: SignalState | str | None) -> str:
    if value == "not_applicable":
        return "unknown"
    if value in ("yes", "no", "unknown"):
        return value
    return "unknown"


def _map_priority_item(row: dict[str, Any]) -> dict[str, Any]:
    area = row.get("area") or ""
    severity = row.get("severity") or "info"
    detected_at = row.get("detected_at") or row.get("created_at")
    tenant_id = row.get("tenant_id", "")
    return {
        "id": _priority_id(row),
        "tenant_id": tenant_id,
        "customer_name": row.get("tenant_name") or tenant_id,
        "category": area,
        "title": row.get("title") or "",
        "impact": _truncate_impact(row.get("detail")),
        "severity": severity,
        "severity_badge": _SEVERITY_BADGE_MAP.get(severity, "P4"),
        "detected_at": detected_at,
        "age_hours": _age_hours(detected_at),
        "recommended_action": row.get("recommended_action") or "",
        "safe_retry_available": _collapse_tri_state(row.get("retryable")),
        "external_action_may_have_occurred": _collapse_tri_state(row.get("external_impact")),
        "link": f"/customers/{tenant_id}",
        "source_type": row.get("source_type") or "",
    }


# ---------------------------------------------------------------------------
# Integration event current-state helper
# ---------------------------------------------------------------------------

def _latest_integration_events_by_source(
    db: Session,
    tenant_id: str,
    *,
    integration_types: tuple[str, ...] | None = None,
    lookback_days: int = _INTEGRATION_EVENT_LOOKBACK_D,
) -> dict[tuple[str, str], IntegrationEvent]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    try:
        query = (
            db.query(IntegrationEvent)
            .filter(
                IntegrationEvent.tenant_id == tenant_id,
                IntegrationEvent.created_at >= cutoff,
            )
        )
        if integration_types:
            query = query.filter(IntegrationEvent.integration_type.in_(integration_types))
        events = query.order_by(IntegrationEvent.created_at.desc()).all()
    except Exception:
        return {}

    latest: dict[tuple[str, str], IntegrationEvent] = {}
    for ev in events:
        key = (ev.job_id or "", ev.integration_type or "")
        if key not in latest:
            latest[key] = ev
    return latest


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
            runbook = (
                "oauth_integration" if system_name == "gmail" else "integration_general"
            )
            source_id = f"integration_health:{tenant_id}:{system_name}"
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
                    runbook_ref=runbook,
                    source_id=source_id,
                    source_type="integration_health",
                    retryable="not_applicable",
                    external_impact="unknown",
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
                    runbook_ref=runbook,
                    source_id=source_id,
                    source_type="integration_health",
                    retryable="not_applicable",
                    external_impact="unknown",
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
            ts = job.updated_at.isoformat() if job.updated_at else None
            rows.append(_row(
                tenant_id=tenant_id,
                tenant_name=tenant_name,
                severity="high",
                area="pipeline",
                title=f"Failed {job.job_type} job",
                detail=str(error_msg)[:200],
                job_id=job.job_id,
                created_at=ts,
                recommended_action="Review job detail and re-run or escalate.",
                runbook_ref="pilot_support",
                source_id=f"job:{job.job_id}",
                source_type="job",
                retryable="unknown",
                external_impact="unknown",
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
    try:
        for sig in collect_stale_approval_signals(
            db, tenant_id=tenant_id, tenant_name=tenant_name, limit=5
        ):
            kind = sig.kind
            area = (
                "approval_email" if kind == "email_send"
                else "approval_dispatch" if kind == "controlled_dispatch"
                else "approval"
            )
            title_map = {
                "email_send": "Customer email waiting > 24 h for approval",
                "controlled_dispatch": "Dispatch approval pending > 24 h",
            }
            title = title_map.get(kind, f"Approval pending > 24 h ({kind})")
            ts = sig.created_at.isoformat() if sig.created_at else None
            rows.append(_row(
                tenant_id=tenant_id,
                tenant_name=tenant_name,
                severity="high",
                area=area,
                title=title,
                detail=(
                    f"Approval ID {sig.approval_id[:8]} has been pending for {sig.age_hours} hours. "
                    f"Job: {sig.job_id[:8]}."
                ),
                job_id=sig.job_id,
                approval_id=sig.approval_id,
                created_at=ts,
                recommended_action="Review and approve or reject the pending approval.",
                runbook_ref="pilot_support",
                source_id=sig.source_id,
                source_type="approval",
                retryable="not_applicable",
                external_impact="no",
            ))
    except Exception:
        pass
    return rows


def _failed_integration_event_signals(
    db: Session,
    tenant_id: str,
    tenant_name: str,
) -> list[dict]:
    """Latest-per-source integration events where current state is failed."""
    rows: list[dict] = []
    try:
        latest = _latest_integration_events_by_source(db, tenant_id)
        for ev in latest.values():
            if ev.status != "failed":
                continue
            error_msg = ev.last_error or "No error detail."
            ts = ev.created_at.isoformat() if ev.created_at else None
            rows.append(_row(
                tenant_id=tenant_id,
                tenant_name=tenant_name,
                severity="high",
                area="integration_event",
                title=f"Failed {ev.integration_type} action",
                detail=str(error_msg)[:200],
                job_id=ev.job_id,
                created_at=ts,
                recommended_action="Check integration credentials and retry from case detail.",
                runbook_ref="oauth_integration",
                source_id=f"integration_event:{ev.id}",
                source_type="integration_event",
                retryable="unknown",
                external_impact="yes",
            ))
    except Exception:
        pass
    return rows


def _reconciliation_required_signals(
    db: Session,
    tenant_id: str,
    tenant_name: str,
) -> list[dict]:
    """Latest-per-source integration events where current state is reconciliation_required."""
    rows: list[dict] = []
    try:
        latest = _latest_integration_events_by_source(db, tenant_id)
        for ev in latest.values():
            if ev.status != "reconciliation_required":
                continue
            error_msg = ev.last_error or "Reconciliation required before retry."
            ts = ev.created_at.isoformat() if ev.created_at else None
            rows.append(_row(
                tenant_id=tenant_id,
                tenant_name=tenant_name,
                severity="critical",
                area="integration_reconciliation",
                title=f"Reconciliation required for {ev.integration_type} action",
                detail=str(error_msg)[:200],
                job_id=ev.job_id,
                created_at=ts,
                recommended_action="Reconcile external state before any retry.",
                runbook_ref="visma_write_safety",
                source_id=f"integration_event:{ev.id}",
                source_type="integration_event",
                retryable="no",
                external_impact="yes",
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
            category = ev.category
            external_impact: SignalState = (
                "no" if category == "oauth" else "unknown"
            )
            ts = ev.created_at.isoformat() if ev.created_at else None
            rows.append(_row(
                tenant_id=tenant_id,
                tenant_name=tenant_name,
                severity="medium",
                area=category,
                title=f"{category.replace('_', ' ').capitalize()} failure: {ev.action}",
                detail=str(ev.details or {})[:200],
                created_at=ts,
                recommended_action="Check scheduler status and logs.",
                runbook_ref="scheduler",
                source_id=f"audit_event:{ev.event_id}",
                source_type="audit_event",
                retryable="not_applicable",
                external_impact=external_impact,
            ))
    except Exception:
        pass
    return rows


def _missing_tenant_config_signals(
    record: Any,
    tenant_id: str,
    tenant_name: str,
) -> list[dict]:
    """Active, non-demo tenants with no enabled job types or integrations."""
    status = _normalize_tenant_status(getattr(record, "status", None))
    settings = getattr(record, "settings", None) or {}
    automation = _get_automation(settings)
    demo_mode = bool(automation.get("demo_mode", False))
    if status != "active" or demo_mode:
        return []

    job_types = list(getattr(record, "enabled_job_types", None) or [])
    integrations = list(getattr(record, "allowed_integrations", None) or [])
    if job_types or integrations:
        return []

    return [_row(
        tenant_id=tenant_id,
        tenant_name=tenant_name,
        severity="medium",
        area="tenant_config",
        title="Tenant configuration incomplete",
        detail="No enabled job types or allowed integrations configured.",
        recommended_action="Konfigurera tenant (jobbtyper och integrationer).",
        runbook_ref="tenant_configuration",
        source_id=f"tenant_config:{tenant_id}",
        source_type="tenant_config",
        retryable="not_applicable",
        external_impact="no",
    )]


# ---------------------------------------------------------------------------
# Tenant aggregator
# ---------------------------------------------------------------------------

def _build_tenant_triage(
    db: Session,
    tenant_id: str,
    tenant_name: str,
    app_settings: Any,
    *,
    record: Any | None = None,
) -> list[dict]:
    """Collect all triage rows for a single tenant. Errors are silently skipped."""
    rows: list[dict] = []
    rows.extend(_integration_signals(db, tenant_id, tenant_name, app_settings))
    rows.extend(_failed_pipeline_signals(db, tenant_id, tenant_name))
    rows.extend(_stale_approval_signals(db, tenant_id, tenant_name))
    rows.extend(_failed_integration_event_signals(db, tenant_id, tenant_name))
    rows.extend(_reconciliation_required_signals(db, tenant_id, tenant_name))
    rows.extend(_failed_scheduler_signals(db, tenant_id, tenant_name))
    if record is not None:
        rows.extend(_missing_tenant_config_signals(record, tenant_id, tenant_name))
    return rows


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def enrich_triage_rows_with_alerts(db: Session, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Enrich existing triage rows with open alert data — no duplicate rows."""
    from app.admin.alerts.repository import AlertRepository

    active_alerts = AlertRepository.list_active_alerts(db)
    by_source: dict[tuple[str | None, str, str], Any] = {}
    unmatched_alerts: list[Any] = []
    for alert in active_alerts:
        details = alert.safe_details or {}
        source_type = str(details.get("source_type") or "")
        source_id = str(details.get("source_id") or "")
        if source_type and source_id:
            by_source[(alert.tenant_id, source_type, source_id)] = alert
        else:
            unmatched_alerts.append(alert)

    enriched: list[dict[str, Any]] = []
    matched_alert_ids: set[str] = set()
    for row in rows:
        key = (
            row.get("tenant_id"),
            str(row.get("source_type") or ""),
            str(row.get("source_id") or ""),
        )
        alert = by_source.get(key)
        if alert is not None:
            row = {
                **row,
                "related_alert_id": alert.id,
                "alert_severity": alert.severity,
                "alert_status": alert.status,
                "alert_occurrence_count": alert.occurrence_count,
            }
            matched_alert_ids.add(alert.id)
        enriched.append(row)

    for alert in unmatched_alerts:
        if alert.id in matched_alert_ids:
            continue
        details = alert.safe_details or {}
        base = _row(
            tenant_id=alert.tenant_id or "PLATFORM",
            tenant_name=alert.tenant_id or "System",
            severity="high" if alert.severity in ("critical", "high") else "medium",
            area="alert",
            title=alert.title,
            detail=alert.summary[:200],
            recommended_action=str(details.get("recommended_action") or ""),
            runbook_ref=str(details.get("runbook_ref") or ""),
            source_id=str(details.get("source_id") or f"alert:{alert.id}"),
            source_type="alert",
            retryable="unknown",
            external_impact="unknown",
        )
        base.update(
            {
                "related_alert_id": alert.id,
                "alert_severity": alert.severity,
                "alert_status": alert.status,
                "alert_occurrence_count": alert.occurrence_count,
            }
        )
        enriched.append(base)
    return enriched


def collect_all_triage_rows(
    db: Session,
    *,
    app_settings: Any,
    enrich_alerts: bool = True,
) -> list[dict[str, Any]]:
    """
    Collect all triage rows across all DB tenants, normalized and deduped.

    Read-only. One failing tenant does not abort the rest.
    Shared by get_admin_needs_help, operations overview, tenant directory,
    and the needs-help queue service.
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
                record=record,
            )
            all_rows.extend(tenant_rows)
        except Exception:
            pass
    rows = dedupe_and_normalize_signals(all_rows)
    if enrich_alerts:
        try:
            rows = enrich_triage_rows_with_alerts(db, rows)
        except Exception:
            pass
    return rows


def get_admin_needs_help(
    db: Session,
    *,
    app_settings: Any,
    limit: int = 50,
) -> dict[str, Any]:
    """
    Aggregate operational triage rows across all DB tenants.

    Legacy compatibility surface — kept for existing tests and consumers.
    The HTTP route uses list_needs_help_queue instead.

    Read-only.  No external API calls.  No secrets in response.
    One failing tenant does not abort the rest.
    Returns rows sorted by severity (critical → high → medium → info),
    then by created_at descending within each severity bucket.
    """
    all_rows = collect_all_triage_rows(db, app_settings=app_settings)

    all_rows.sort(
        key=lambda r: (
            _SEVERITY_ORDER.get(r["severity"], 99),
            -(datetime.fromisoformat(r["created_at"]).timestamp()
              if r.get("created_at") else 0),
        )
    )
    all_rows = all_rows[:limit]

    counts = {"critical": 0, "high": 0, "medium": 0, "info": 0}
    for r in all_rows:
        counts[r["severity"]] = counts.get(r["severity"], 0) + 1

    return {
        "total": len(all_rows),
        "critical": counts["critical"],
        "high": counts["high"],
        "medium": counts["medium"],
        "items": all_rows,
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
