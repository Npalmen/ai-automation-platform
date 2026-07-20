"""
Admin tenant directory — customer list and detail for the operator panel.

Read-only. No secrets in response. Settings are never serialized wholesale;
only allowlisted tenant config fields and two pause-signal keys
(automation.demo_mode, scheduler.run_mode) are read via support_console helpers.

List performance note: approvals, manual review, activity timestamps, and
jobs_last_30d use batched GROUP BY queries. open_issues_count inherits the
per-tenant query cost of collect_all_triage_rows (shared with Kapitel 2).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.admin.operations_overview import (
    _map_priority_item,
    _sort_priority_rows,
)
from app.admin.operations_triage import (
    _build_tenant_triage,
    _failed_integration_event_signals,
    _failed_pipeline_signals,
    _failed_scheduler_signals,
    _stale_approval_signals,
    collect_all_triage_rows,
)
from app.admin.operator_actions import (
    resolve_available_actions,
    tenant_detail_candidate_actions,
)
from app.admin.support_console import _get_automation, _get_scheduler
from app.analytics.usage import _tenant_usage_summary
from app.admin.integrations.selection_resolver import derive_integration_selection
from app.domain.integrations.models import IntegrationEvent
from app.health.integration_health import get_integration_health
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.approval_repository import ApprovalRequestRepository
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.audit_repository import AuditRepository
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.job_repository import JobRepository
from app.repositories.postgres.oauth_credential_models import OAuthCredentialRecord
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
from app.workflows.manual_review_handoff import list_unresolved_manual_review_jobs

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "info": 3}
_JOBS_WINDOW_D = 30
_EVENT_INTEGRATION_TYPES = ("visma", "google_sheets")
_OAUTH_PROVIDERS = {"visma": "visma", "google_sheets": "google_sheets"}
_HEALTH_LABELS = {
    "healthy": "Frisk",
    "warning": "Varning",
    "failed": "Fel",
    "paused": "Pausad",
    "unknown": "Okänd",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_tenant_status(status: str | None) -> str:
    value = (status or "").strip().lower()
    if value == "active":
        return "active"
    if value == "inactive":
        return "inactive"
    return "unknown"


def _enabled_modules(record: Any) -> list[str]:
    job_types = list(getattr(record, "enabled_job_types", None) or [])
    integrations = list(getattr(record, "allowed_integrations", None) or [])
    modules: list[str] = []
    for item in job_types:
        text = str(item)
        if text and text not in modules:
            modules.append(text)
    for item in integrations:
        text = str(item)
        if text and text not in modules:
            modules.append(text)
    return modules


def _pause_signals(settings: dict | None) -> tuple[bool, bool]:
    settings = settings or {}
    automation = _get_automation(settings)
    scheduler = _get_scheduler(settings)
    automation_paused = bool(automation.get("demo_mode", False))
    scheduler_paused = scheduler.get("run_mode") == "paused"
    return automation_paused, scheduler_paused


def _derive_tenant_health(
    worst_severity: str | None,
    automation_paused: bool,
    scheduler_paused: bool,
) -> dict[str, str]:
    if automation_paused or scheduler_paused:
        parts = []
        if automation_paused:
            parts.append("automation i demoläge")
        if scheduler_paused:
            parts.append("scheduler pausad")
        return {
            "level": "paused",
            "label": _HEALTH_LABELS["paused"],
            "summary": f"Verifierad paus: {', '.join(parts)}.",
        }
    if worst_severity in ("critical", "high"):
        return {
            "level": "failed",
            "label": _HEALTH_LABELS["failed"],
            "summary": "Öppna operativa avvikelser med hög allvarlighetsgrad.",
        }
    if worst_severity == "medium":
        return {
            "level": "warning",
            "label": _HEALTH_LABELS["warning"],
            "summary": "Operativa avvikelser kräver uppmärksamhet.",
        }
    return {
        "level": "healthy",
        "label": _HEALTH_LABELS["healthy"],
        "summary": "Inga öppna operativa avvikelser.",
    }


def _worst_severity(rows: list[dict[str, Any]]) -> str | None:
    if not rows:
        return None
    return min(
        rows,
        key=lambda r: _SEVERITY_ORDER.get(r.get("severity", ""), 99),
    ).get("severity")


def _gmail_summary_for_tenant(rows: list[dict[str, Any]]) -> str:
    gmail_rows = [
        r for r in rows
        if r.get("area") == "integration"
        and (
            "gmail" in (r.get("title") or "").lower()
            or "google mail" in (r.get("title") or "").lower()
        )
    ]
    if not gmail_rows:
        return "healthy"
    severities = {r.get("severity") for r in gmail_rows}
    if severities & {"critical", "high"}:
        return "failed"
    return "warning"


def _tenant_event_integration_status(
    has_oauth: bool,
    total_events: int,
    failed_events: int,
) -> str:
    if not has_oauth and total_events == 0:
        return "unknown"
    if total_events == 0:
        return "healthy"
    if failed_events == 0:
        return "healthy"
    return "warning"


def _map_health_system_status(raw_status: str) -> str:
    if raw_status == "error":
        return "failed"
    if raw_status == "not_configured":
        return "unknown"
    if raw_status in ("healthy", "warning", "failed", "unknown"):
        return raw_status
    return "unknown"


def _batch_count_by_tenant(
    db: Session,
    model: Any,
    *,
    extra_filter: Any | None = None,
) -> dict[str, int]:
    query = db.query(model.tenant_id, func.count()).group_by(model.tenant_id)
    if extra_filter is not None:
        query = query.filter(extra_filter)
    return {tenant_id: count for tenant_id, count in query.all()}


def _batch_max_created_at(db: Session, model: Any) -> dict[str, datetime]:
    query = (
        db.query(model.tenant_id, func.max(model.created_at))
        .group_by(model.tenant_id)
    )
    return {
        tenant_id: ts
        for tenant_id, ts in query.all()
        if ts is not None
    }


def _batch_max_job_activity(db: Session) -> dict[str, datetime]:
    created = _batch_max_created_at(db, JobRecord)
    updated_rows = (
        db.query(JobRecord.tenant_id, func.max(JobRecord.updated_at))
        .group_by(JobRecord.tenant_id)
        .all()
    )
    result: dict[str, datetime] = {}
    for tenant_id, updated_at in updated_rows:
        if updated_at is None:
            continue
        current = result.get(tenant_id)
        if current is None or updated_at > current:
            result[tenant_id] = updated_at
    for tenant_id, created_at in created.items():
        current = result.get(tenant_id)
        if current is None or created_at > current:
            result[tenant_id] = created_at
    return result


def _combine_last_activity(
    *maps: dict[str, datetime],
) -> dict[str, datetime]:
    combined: dict[str, datetime] = {}
    for mapping in maps:
        for tenant_id, ts in mapping.items():
            current = combined.get(tenant_id)
            if current is None or ts > current:
                combined[tenant_id] = ts
    return combined


def _batch_oauth_providers(db: Session) -> dict[str, set[str]]:
    rows = db.query(
        OAuthCredentialRecord.tenant_id,
        OAuthCredentialRecord.provider,
    ).all()
    result: dict[str, set[str]] = {}
    for tenant_id, provider in rows:
        result.setdefault(tenant_id, set()).add(str(provider))
    return result


def _batch_integration_event_stats(
    db: Session,
    *,
    integration_types: tuple[str, ...],
) -> dict[str, dict[str, dict[str, int]]]:
    rows = (
        db.query(
            IntegrationEvent.tenant_id,
            IntegrationEvent.integration_type,
            IntegrationEvent.status,
            func.count(),
        )
        .filter(IntegrationEvent.integration_type.in_(integration_types))
        .group_by(
            IntegrationEvent.tenant_id,
            IntegrationEvent.integration_type,
            IntegrationEvent.status,
        )
        .all()
    )
    result: dict[str, dict[str, dict[str, int]]] = {}
    for tenant_id, itype, status, count in rows:
        tenant_bucket = result.setdefault(tenant_id, {})
        type_bucket = tenant_bucket.setdefault(itype, {"total": 0, "failed": 0})
        type_bucket["total"] += count
        if status == "failed":
            type_bucket["failed"] += count
    return result


def _integrations_summary_for_tenant(
    tenant_id: str,
    triage_rows: list[dict[str, Any]],
    oauth_providers: set[str],
    event_stats: dict[str, dict[str, int]],
) -> dict[str, str]:
    gmail = _gmail_summary_for_tenant(triage_rows)
    visma_stats = event_stats.get("visma", {"total": 0, "failed": 0})
    sheets_stats = event_stats.get("google_sheets", {"total": 0, "failed": 0})
    return {
        "google_mail": gmail,
        "visma": _tenant_event_integration_status(
            "visma" in oauth_providers,
            visma_stats["total"],
            visma_stats["failed"],
        ),
        "google_sheets": _tenant_event_integration_status(
            "google_sheets" in oauth_providers,
            sheets_stats["total"],
            sheets_stats["failed"],
        ),
    }


def _tenant_visma_sheets_detail(
    db: Session,
    tenant_id: str,
    integration_type: str,
    provider: str,
) -> dict[str, Any]:
    has_oauth = (
        db.query(OAuthCredentialRecord)
        .filter(
            OAuthCredentialRecord.tenant_id == tenant_id,
            OAuthCredentialRecord.provider == provider,
        )
        .first()
        is not None
    )
    events = (
        db.query(IntegrationEvent)
        .filter(
            IntegrationEvent.tenant_id == tenant_id,
            IntegrationEvent.integration_type == integration_type,
        )
        .order_by(IntegrationEvent.created_at.desc())
        .limit(20)
        .all()
    )
    total = len(events)
    failed = sum(1 for e in events if e.status == "failed")
    status = _tenant_event_integration_status(has_oauth, total, failed)
    last_success = next((e for e in events if e.status == "success"), None)
    last_failed = next((e for e in events if e.status == "failed"), None)
    if not has_oauth and total == 0:
        description = "Ingen verifierbar OAuth- eller händelsedata för denna integration."
    elif has_oauth and total == 0:
        description = "OAuth-anslutning finns men inga integrationshändelser registrerade."
    elif failed > 0:
        description = f"{failed} misslyckade integrationshändelser i senaste urvalet."
    else:
        description = "Inga misslyckade integrationshändelser i senaste urvalet."
    return {
        "status": status,
        "description": description,
        "recommended_action": (
            "Kontrollera OAuth-anslutning och integrationslogg."
            if status in ("warning", "failed", "unknown")
            else None
        ),
        "data_source": "oauth_credentials_and_integration_event_log",
        "last_success_at": (
            last_success.created_at.isoformat()
            if last_success and last_success.created_at
            else None
        ),
        "last_error_at": (
            last_failed.created_at.isoformat()
            if last_failed and last_failed.created_at
            else None
        ),
    }


def _map_health_integration(system_name: str, sys_data: dict[str, Any]) -> dict[str, Any]:
    raw_status = sys_data.get("status", "not_configured")
    if raw_status in ("not_applicable", "not_connected"):
        return {
            "status": "unknown",
            "description": sys_data.get("description") or f"{system_name} är inte vald för denna kund.",
            "recommended_action": None,
            "data_source": "integration_health_check",
            "last_success_at": None,
            "last_error_at": None,
            "hidden": True,
        }
    return {
        "status": _map_health_system_status(raw_status),
        "description": (
            sys_data.get("recommended_action")
            or f"{system_name.capitalize()} — status från integrationshälsokontroll."
        ),
        "recommended_action": sys_data.get("recommended_action"),
        "data_source": "integration_health_check",
        "last_success_at": sys_data.get("last_success_at"),
        "last_error_at": sys_data.get("last_error_at"),
        "hidden": False,
    }


def _health_integrations_for_tenant(
    record: Any,
    db: Session,
    systems: dict[str, Any],
) -> dict[str, dict[str, Any] | None]:
    block: dict[str, dict[str, Any] | None] = {
        "google_mail": None,
        "monday": None,
        "fortnox": None,
    }
    for key in block:
        selection = derive_integration_selection(db, record, key)
        if selection.selection_status == "not_selected":
            continue
        mapped = _map_health_integration(key, systems.get(key, {}))
        if mapped.get("hidden"):
            continue
        block[key] = {k: v for k, v in mapped.items() if k != "hidden"}
    return block


def _count_jobs_last_30d(db: Session, tenant_id: str) -> int:
    cutoff = _utcnow() - timedelta(days=_JOBS_WINDOW_D)
    return (
        db.query(JobRecord)
        .filter(
            JobRecord.tenant_id == tenant_id,
            JobRecord.created_at >= cutoff,
        )
        .count()
    )


def _build_recent_errors(
    db: Session,
    tenant_id: str,
    tenant_name: str,
    app_settings: Any,
    *,
    limit: int = 15,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rows.extend(_failed_pipeline_signals(db, tenant_id, tenant_name))
    rows.extend(_stale_approval_signals(db, tenant_id, tenant_name))
    rows.extend(_failed_integration_event_signals(db, tenant_id, tenant_name))
    rows.extend(_failed_scheduler_signals(db, tenant_id, tenant_name))
    sorted_rows = _sort_priority_rows(rows)
    return [_map_priority_item(r) for r in sorted_rows[:limit]]


def list_admin_tenants(
    db: Session,
    *,
    app_settings: Any,
    search: str | None = None,
    status: str | None = None,
    health: str | None = None,
    sort: str = "name",
    order: str = "asc",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    records = TenantConfigRepository.list_all(db)
    all_triage = collect_all_triage_rows(db, app_settings=app_settings)

    triage_by_tenant: dict[str, list[dict[str, Any]]] = {}
    for row in all_triage:
        triage_by_tenant.setdefault(row["tenant_id"], []).append(row)

    pending_counts = _batch_count_by_tenant(
        db,
        ApprovalRequestRecord,
        extra_filter=ApprovalRequestRecord.state == "pending",
    )
    manual_review_counts = _batch_count_by_tenant(
        db,
        JobRecord,
        extra_filter=JobRecord.status == "manual_review",
    )
    jobs_30d_cutoff = _utcnow() - timedelta(days=_JOBS_WINDOW_D)
    jobs_30d_counts = _batch_count_by_tenant(
        db,
        JobRecord,
        extra_filter=JobRecord.created_at >= jobs_30d_cutoff,
    )

    last_activity = _combine_last_activity(
        _batch_max_job_activity(db),
        _batch_max_created_at(db, ApprovalRequestRecord),
        _batch_max_created_at(db, IntegrationEvent),
        _batch_max_created_at(db, AuditEventRecord),
    )

    oauth_by_tenant = _batch_oauth_providers(db)
    event_stats_by_tenant = _batch_integration_event_stats(
        db, integration_types=_EVENT_INTEGRATION_TYPES
    )

    items: list[dict[str, Any]] = []
    for record in records:
        tenant_id = record.tenant_id
        base = TenantConfigRepository.to_dict(record)
        tenant_rows = triage_by_tenant.get(tenant_id, [])
        automation_paused, scheduler_paused = _pause_signals(record.settings)
        worst = _worst_severity(tenant_rows)
        health_block = _derive_tenant_health(worst, automation_paused, scheduler_paused)
        activity = last_activity.get(tenant_id)
        items.append({
            "tenant_id": tenant_id,
            "name": base.get("name") or tenant_id,
            "slug": base.get("slug"),
            "tenant_status": _normalize_tenant_status(base.get("status")),
            "health": health_block,
            "package": None,
            "operator_owner": None,
            "enabled_modules": _enabled_modules(record),
            "open_issues_count": len(tenant_rows),
            "pending_approvals": pending_counts.get(tenant_id, 0),
            "open_manual_reviews": manual_review_counts.get(tenant_id, 0),
            "jobs_last_30d": jobs_30d_counts.get(tenant_id, 0),
            "last_activity_at": activity.isoformat() if activity else None,
            "integrations_summary": _integrations_summary_for_tenant(
                tenant_id,
                tenant_rows,
                oauth_by_tenant.get(tenant_id, set()),
                event_stats_by_tenant.get(tenant_id, {}),
            ),
            "created_at": base.get("created_at"),
            "updated_at": base.get("updated_at"),
        })

    if search:
        needle = search.strip().lower()
        if needle:
            items = [
                item for item in items
                if needle in (item.get("name") or "").lower()
                or needle in (item.get("tenant_id") or "").lower()
                or needle in (item.get("slug") or "").lower()
            ]

    if status:
        items = [item for item in items if item.get("tenant_status") == status]

    if health:
        items = [item for item in items if item.get("health", {}).get("level") == health]

    reverse = order.lower() == "desc"

    def _sort_key(item: dict[str, Any]) -> Any:
        if sort == "tenant_status":
            return item.get("tenant_status") or ""
        if sort == "health":
            return item.get("health", {}).get("level") or ""
        if sort == "last_activity":
            return item.get("last_activity_at") or ""
        if sort == "open_issues":
            return item.get("open_issues_count", 0)
        return (item.get("name") or "").lower()

    items.sort(key=_sort_key, reverse=reverse)

    total = len(items)
    page = items[offset : offset + limit]
    return {"items": page, "total": total}


def _onboarding_config_summary(settings: dict | None) -> dict[str, Any]:
    settings = settings or {}
    memory = settings.get("memory") or {}
    lead_config = memory.get("lead_config") or {}
    intake = settings.get("intake") or {}
    lead_requirements = dict(lead_config.get("lead_requirements") or {})
    internal_routing_hints = dict(memory.get("internal_routing_hints") or {})
    service_profiles = sorted(
        set(lead_requirements.keys()) | set(internal_routing_hints.keys())
    )
    return {
        "schema_version": settings.get("schema_version"),
        "service_profiles": service_profiles,
        "lead_requirements": lead_requirements,
        "internal_routing_hints": internal_routing_hints,
        "intake": {
            "mode": intake.get("mode"),
            "activation_cutoff_at": intake.get("activation_cutoff_at"),
            "enforcement": intake.get("enforcement"),
        },
    }


def get_tenant_detail(
    db: Session,
    tenant_id: str,
    *,
    app_settings: Any,
    operator_role: str = "read_only",
) -> dict[str, Any] | None:
    record = TenantConfigRepository.get(db, tenant_id)
    if record is None:
        return None

    base = TenantConfigRepository.to_dict(record)
    tenant_name = base.get("name") or tenant_id
    automation_paused, scheduler_paused = _pause_signals(record.settings)

    tenant_rows = _build_tenant_triage(
        db,
        tenant_id=tenant_id,
        tenant_name=tenant_name,
        app_settings=app_settings,
        record=record,
    )
    health_block = _derive_tenant_health(
        _worst_severity(tenant_rows),
        automation_paused,
        scheduler_paused,
    )

    integrations_health: dict[str, Any] = {}
    try:
        integrations_health = get_integration_health(
            db, tenant_id, app_settings=app_settings
        )
    except Exception:
        logger.exception("tenant_detail_integration_health_failed", extra={"tenant_id": tenant_id})

    systems = integrations_health.get("systems", {})
    health_integrations = _health_integrations_for_tenant(record, db, systems)
    integrations_block = {
        "google_mail": health_integrations["google_mail"],
        "monday": health_integrations["monday"],
        "fortnox": health_integrations["fortnox"],
        "visma": _tenant_visma_sheets_detail(db, tenant_id, "visma", "visma"),
        "google_sheets": _tenant_visma_sheets_detail(
            db, tenant_id, "google_sheets", "google_sheets"
        ),
    }

    recent_jobs = JobRepository.list_jobs_for_tenant(db, tenant_id, limit=10)
    jobs_block = {
        "total": JobRepository.count_jobs_for_tenant(db, tenant_id),
        "jobs_last_30d": _count_jobs_last_30d(db, tenant_id),
        "recent": [
            {
                "job_id": job.job_id,
                "job_type": job.job_type,
                "status": job.status,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "updated_at": job.updated_at.isoformat() if job.updated_at else None,
            }
            for job in recent_jobs
        ],
    }

    pending_records = ApprovalRequestRepository.list_pending_for_tenant(
        db, tenant_id, limit=10
    )
    approvals_block = {
        "pending_count": ApprovalRequestRepository.count_pending_for_tenant(db, tenant_id),
        "recent": [
            {
                "approval_id": appr.approval_id,
                "job_id": appr.job_id,
                "job_type": appr.job_type,
                "state": appr.state,
                "title": appr.title,
                "summary": appr.summary,
                "created_at": appr.created_at.isoformat() if appr.created_at else None,
            }
            for appr in pending_records
        ],
    }

    manual_items, manual_total = list_unresolved_manual_review_jobs(
        db, tenant_id, limit=10
    )
    manual_block = {
        "total": manual_total,
        "recent": [
            {
                "job_id": item.get("job_id", ""),
                "job_type": item.get("job_type", ""),
                "status": item.get("status", ""),
                "subject": item.get("subject"),
                "manual_review_reason": item.get("manual_review_reason"),
                "unresolved": bool(item.get("unresolved", True)),
            }
            for item in manual_items
        ],
    }

    cutoff_30d = _utcnow() - timedelta(days=_JOBS_WINDOW_D)
    usage_raw = _tenant_usage_summary(db, record, cutoff_30d, _utcnow())
    usage_block = {
        "jobs_created": usage_raw.get("jobs_created", 0),
        "jobs_completed": usage_raw.get("jobs_completed", 0),
        "pending_approvals": usage_raw.get("pending_approvals", 0),
        "blocked_flows": usage_raw.get("blocked_flows", 0),
        "dispatches_total": usage_raw.get("dispatches_total", 0),
        "dispatches_successful": usage_raw.get("dispatches_successful", 0),
        "dispatches_failed": usage_raw.get("dispatches_failed", 0),
        "automation_rate_percent": usage_raw.get("automation_rate_percent", 0),
        "time_saved_hours": usage_raw.get("time_saved_hours", 0.0),
    }

    audit_records = AuditRepository.list_events_for_tenant(db, tenant_id, limit=20)
    audit_block = {
        "total": AuditRepository.count_events_for_tenant(db, tenant_id),
        "recent": [
            {
                "event_id": ev.event_id,
                "tenant_id": ev.tenant_id,
                "category": ev.category,
                "action": ev.action,
                "status": ev.status,
                "details": ev.details or {},
                "created_at": ev.created_at.isoformat() if ev.created_at else None,
            }
            for ev in audit_records
        ],
    }

    resource_state = {
        "automation_paused": automation_paused,
        "scheduler_paused": scheduler_paused,
    }
    candidates = tenant_detail_candidate_actions(automation_paused, scheduler_paused)
    available_actions = [
        action.model_dump()
        for action in resolve_available_actions(
            candidates, operator_role, resource_state
        )
    ]

    from app.admin.tenant_lifecycle.constants import LIFECYCLE_LABELS_SV
    from app.admin.tenant_lifecycle.service import present_lifecycle

    lifecycle_block = present_lifecycle(record)

    return {
        "tenant": {
            "tenant_id": tenant_id,
            "name": tenant_name,
            "slug": base.get("slug"),
            "tenant_status": _normalize_tenant_status(base.get("status")),
            "package": None,
            "operator_owner": None,
            "enabled_modules": _enabled_modules(record),
            "enabled_job_types": base.get("enabled_job_types") or [],
            "allowed_integrations": base.get("allowed_integrations") or [],
            "auto_actions": base.get("auto_actions") or {},
            "created_at": base.get("created_at"),
            "updated_at": base.get("updated_at"),
        },
        "health": health_block,
        "integrations": integrations_block,
        "jobs": jobs_block,
        "approvals": approvals_block,
        "manual_review": manual_block,
        "recent_errors": _build_recent_errors(
            db, tenant_id, tenant_name, app_settings
        ),
        "usage": usage_block,
        "audit": audit_block,
        "onboarding_config": _onboarding_config_summary(record.settings),
        "lifecycle": lifecycle_block,
        "available_actions": available_actions,
    }
