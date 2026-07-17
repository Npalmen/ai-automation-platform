"""Service layer for usage/cost/capacity (Kapitel 7)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.admin.incident_repository import IncidentRepository
from app.admin.incident_schemas import OPEN_STATUSES
from app.admin.operations_triage import collect_all_triage_rows
from app.admin.tenant_directory import (
    _derive_tenant_health,
    _normalize_tenant_status,
    _pause_signals,
    _worst_severity,
)
from app.admin.usage_repository import (
    batch_audit_by_tenant,
    batch_critical_incidents_by_tenant,
    batch_incidents_created_by_tenant,
    batch_incidents_resolved_by_tenant,
    batch_integration_errors_by_tenant,
    batch_jobs_received_by_tenant,
    batch_jobs_terminal_by_tenant,
    batch_latest_activity_by_tenant,
    batch_open_manual_reviews_by_tenant,
    batch_pending_approvals_by_tenant,
    compute_peak_jobs_per_hour,
    compute_period_bounds,
    count_critical_incidents_created_global,
    count_incidents_created_global,
    count_incidents_resolved_global,
    sum_audit_global,
    sum_integration_errors_global,
    sum_jobs_received_global,
    sum_jobs_terminal_global,
    tenants_with_jobs_in_period,
)
from app.admin.usage_schemas import (
    AI_COST_UNKNOWN_REASON,
    AUTOMATION_RATE_NOT_MEASURED_REASON,
    MANUAL_REVIEWS_NOT_MEASURED_REASON,
    AiCostBlock,
    AiUsageBlock,
    CapacityBlock,
    ComparisonInt,
    ComparisonProxyMetric,
    NotMeasuredValue,
    ProxyTimestampMetric,
    UsageOverviewResponse,
    UsagePeriod,
    UsageSummary,
    UsageTenantItem,
    UsageTenantListResponse,
)
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

_SORT_FIELDS = frozenset({
    "jobs",
    "automation_rate",
    "operator_actions",
    "manual_reviews",
    "integration_errors",
    "ai_cost",
    "latest_activity",
    "customer",
})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _comparison_int(current: int, previous: int) -> ComparisonInt:
    absolute = current - previous
    if previous == 0:
        pct: float | None = None
    else:
        pct = round((absolute / previous) * 100.0, 1)
    return ComparisonInt(
        current=current,
        previous=previous,
        absolute_change=absolute,
        percentage_change=pct,
    )


def _comparison_proxy(current: int, previous: int) -> ComparisonProxyMetric:
    base = _comparison_int(current, previous)
    return ComparisonProxyMetric(
        current=ProxyTimestampMetric(value=base.current),
        previous=ProxyTimestampMetric(value=base.previous),
        absolute_change=base.absolute_change,
        percentage_change=base.percentage_change,
    )


def _not_measured_automation_rate() -> NotMeasuredValue:
    return NotMeasuredValue(reason=AUTOMATION_RATE_NOT_MEASURED_REASON)


def _not_measured_manual_reviews() -> NotMeasuredValue:
    return NotMeasuredValue(reason=MANUAL_REVIEWS_NOT_MEASURED_REASON)


def _ai_usage_block() -> AiUsageBlock:
    return AiUsageBlock(
        status="not_measured",
        reason="Token- och modellmätning är inte implementerad i LLM-klienten.",
    )


def _ai_cost_block() -> AiCostBlock:
    return AiCostBlock(
        status="unknown",
        amount=None,
        currency=None,
        reason=AI_COST_UNKNOWN_REASON,
    )


def _safe_ratio(numerator: int, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 1)


def _period_model(bounds: dict[str, Any]) -> UsagePeriod:
    return UsagePeriod(
        days=int(bounds["days"]),
        started_at=bounds["started_at"],
        ended_at=bounds["ended_at"],
        comparison_started_at=bounds["comparison_started_at"],
        comparison_ended_at=bounds["comparison_ended_at"],
    )


def _fetch_period_metrics(
    db: Session,
    *,
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    return {
        "jobs_received": sum_jobs_received_global(db, start=start, end=end),
        "jobs_completed": sum_jobs_terminal_global(
            db, status="completed", start=start, end=end
        ),
        "jobs_failed": sum_jobs_terminal_global(
            db, status="failed", start=start, end=end
        ),
        "operator_actions": sum_audit_global(
            db, category="operator_action", start=start, end=end
        ),
        "gmail_manual_review_handoffs": sum_audit_global(
            db,
            category="manual_review",
            start=start,
            end=end,
            action="gmail_handoff_applied",
        ),
        "incidents_created": count_incidents_created_global(db, start=start, end=end),
        "incidents_resolved": count_incidents_resolved_global(db, start=start, end=end),
        "critical_incidents_created": count_critical_incidents_created_global(
            db, start=start, end=end
        ),
        "integration_errors": sum_integration_errors_global(db, start=start, end=end),
    }


def _fetch_tenant_period_batches(
    db: Session,
    *,
    start: datetime,
    end: datetime,
) -> dict[str, dict[str, int]]:
    return {
        "jobs_received": batch_jobs_received_by_tenant(db, start=start, end=end),
        "jobs_completed": batch_jobs_terminal_by_tenant(
            db, status="completed", start=start, end=end
        ),
        "jobs_failed": batch_jobs_terminal_by_tenant(
            db, status="failed", start=start, end=end
        ),
        "operator_actions": batch_audit_by_tenant(
            db, category="operator_action", start=start, end=end
        ),
        "gmail_manual_review_handoffs": batch_audit_by_tenant(
            db,
            category="manual_review",
            start=start,
            end=end,
            action="gmail_handoff_applied",
        ),
        "incidents_created": batch_incidents_created_by_tenant(db, start=start, end=end),
        "integration_errors": batch_integration_errors_by_tenant(
            db, start=start, end=end
        ),
    }


def _build_triage_context(
    db: Session,
    *,
    app_settings: Any,
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    all_triage = collect_all_triage_rows(db, app_settings=app_settings)
    by_tenant: dict[str, list[dict[str, Any]]] = {}
    for row in all_triage:
        by_tenant.setdefault(row["tenant_id"], []).append(row)
    return all_triage, by_tenant


def _attention_status_for_tenant(
    tenant_rows: list[dict[str, Any]],
    *,
    automation_paused: bool,
    scheduler_paused: bool,
) -> str:
    worst = _worst_severity(tenant_rows)
    health = _derive_tenant_health(worst, automation_paused, scheduler_paused)
    return health["level"]


def get_usage_overview(
    db: Session,
    *,
    days: int,
    app_settings: Any,
) -> UsageOverviewResponse:
    bounds = compute_period_bounds(days)
    current_start = bounds["started_at"]
    current_end = bounds["ended_at"]
    comparison_start = bounds["comparison_started_at"]
    comparison_end = bounds["comparison_ended_at"]

    current = _fetch_period_metrics(db, start=current_start, end=current_end)
    previous = _fetch_period_metrics(db, start=comparison_start, end=comparison_end)

    all_triage, _ = _build_triage_context(db, app_settings=app_settings)
    tenants_with_signals = {row["tenant_id"] for row in all_triage}

    records = TenantConfigRepository.list_all(db)
    active_tenants = sum(
        1 for r in records if _normalize_tenant_status(r.status) == "active"
    )
    activity_tenants = tenants_with_jobs_in_period(
        db, start=current_start, end=current_end
    )

    pending_total = sum(batch_pending_approvals_by_tenant(db).values())
    open_manual_reviews = sum(batch_open_manual_reviews_by_tenant(db).values())
    open_incidents = IncidentRepository.count_by_status(db, OPEN_STATUSES)

    peak_hour = compute_peak_jobs_per_hour(
        db, start=current_start, end=current_end
    )
    operator_actions_per_day = _safe_ratio(
        current["operator_actions"], float(days)
    )

    summary = UsageSummary(
        active_tenants=active_tenants,
        tenants_with_activity=len(activity_tenants),
        jobs_received=_comparison_int(
            current["jobs_received"], previous["jobs_received"]
        ),
        jobs_completed=_comparison_proxy(
            current["jobs_completed"], previous["jobs_completed"]
        ),
        jobs_failed=_comparison_proxy(
            current["jobs_failed"], previous["jobs_failed"]
        ),
        automation_rate=_not_measured_automation_rate(),
        operator_actions=_comparison_int(
            current["operator_actions"], previous["operator_actions"]
        ),
        gmail_manual_review_handoffs=_comparison_int(
            current["gmail_manual_review_handoffs"],
            previous["gmail_manual_review_handoffs"],
        ),
        manual_reviews_created=_not_measured_manual_reviews(),
        open_manual_reviews_current=open_manual_reviews,
        pending_approvals_current=pending_total,
        incidents_created=_comparison_int(
            current["incidents_created"], previous["incidents_created"]
        ),
        incidents_resolved=_comparison_int(
            current["incidents_resolved"], previous["incidents_resolved"]
        ),
        open_incidents_current=open_incidents,
        critical_incidents_created=_comparison_int(
            current["critical_incidents_created"],
            previous["critical_incidents_created"],
        ),
        integration_errors=_comparison_int(
            current["integration_errors"], previous["integration_errors"]
        ),
        needs_help_open_current=len(all_triage),
        tenants_with_open_signals_current=len(tenants_with_signals),
    )

    capacity = CapacityBlock(
        status="baseline_missing",
        jobs_per_day_average=_safe_ratio(current["jobs_received"], float(days)),
        peak_jobs_per_hour=peak_hour,
        operator_actions_per_day=operator_actions_per_day,
        open_incidents_current=open_incidents,
        needs_help_open_current=len(all_triage),
    )

    data_quality_notes = [
        "jobs_completed och jobs_failed baseras på updated_at (proxy), inte dedikerad terminaltid.",
        "automation_rate är not_measured — audit_events saknar job_id för operator_action.",
        "manual_reviews_created är not_measured — endast gmail_manual_review_handoffs är auditerad.",
        "AI-användning och AI-kostnad mäts inte i detta kapitel.",
        "Kapacitetsstatus baseline_missing — inga konfigurerade trösklar.",
        "attention_status i tenantlistan ärver kostnad från collect_all_triage_rows (befintligt mönster).",
    ]

    return UsageOverviewResponse(
        generated_at=_utcnow(),
        period=_period_model(bounds),
        summary=summary,
        ai_usage=_ai_usage_block(),
        ai_cost=_ai_cost_block(),
        capacity=capacity,
        data_quality_notes=data_quality_notes,
    )


def _tenant_sort_key(item: UsageTenantItem, sort: str) -> tuple:
    if sort == "customer":
        return (item.customer_name.lower(), item.tenant_id)
    if sort == "automation_rate":
        return (item.automation_rate.status, item.tenant_id)
    if sort == "operator_actions":
        return (item.operator_actions, item.tenant_id)
    if sort == "manual_reviews":
        return (item.gmail_manual_review_handoffs, item.tenant_id)
    if sort == "integration_errors":
        return (item.integration_errors, item.tenant_id)
    if sort == "ai_cost":
        return (item.ai_cost.status, item.tenant_id)
    if sort == "latest_activity":
        ts = item.latest_activity_at
        return (ts is not None, ts or datetime.min.replace(tzinfo=timezone.utc), item.tenant_id)
    # default: jobs
    return (item.jobs_received, item.tenant_id)


def _default_sort_key(item: UsageTenantItem) -> tuple:
    """operator burden desc → integration_errors desc → jobs desc → tenant_id asc."""
    burden = item.operator_actions + item.open_manual_reviews_current + item.pending_approvals_current
    return (
        -burden,
        -item.integration_errors,
        -item.jobs_received,
        item.tenant_id,
    )


def get_usage_tenants(
    db: Session,
    *,
    days: int,
    app_settings: Any,
    search: str | None = None,
    tenant_status: str | None = None,
    attention_status: str | None = None,
    minimum_jobs: int | None = None,
    has_operator_burden: bool | None = None,
    ai_cost_status: str | None = None,
    sort: str = "jobs",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> UsageTenantListResponse:
    if sort not in _SORT_FIELDS:
        sort = "jobs"
    if order not in ("asc", "desc"):
        order = "desc"
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    bounds = compute_period_bounds(days)
    current_start = bounds["started_at"]
    current_end = bounds["ended_at"]

    batches = _fetch_tenant_period_batches(
        db, start=current_start, end=current_end
    )
    pending = batch_pending_approvals_by_tenant(db)
    open_manual = batch_open_manual_reviews_by_tenant(db)
    latest_activity = batch_latest_activity_by_tenant(db)

    _, triage_by_tenant = _build_triage_context(db, app_settings=app_settings)

    records = TenantConfigRepository.list_all(db)
    items: list[UsageTenantItem] = []

    for record in records:
        tenant_id = record.tenant_id
        base = TenantConfigRepository.to_dict(record)
        tenant_rows = triage_by_tenant.get(tenant_id, [])
        automation_paused, scheduler_paused = _pause_signals(record.settings)
        attention = _attention_status_for_tenant(
            tenant_rows,
            automation_paused=automation_paused,
            scheduler_paused=scheduler_paused,
        )

        jobs_received = batches["jobs_received"].get(tenant_id, 0)
        jobs_completed = batches["jobs_completed"].get(tenant_id, 0)
        jobs_failed = batches["jobs_failed"].get(tenant_id, 0)
        operator_actions = batches["operator_actions"].get(tenant_id, 0)
        gmail_handoffs = batches["gmail_manual_review_handoffs"].get(tenant_id, 0)
        incidents_created = batches["incidents_created"].get(tenant_id, 0)
        integration_errors = batches["integration_errors"].get(tenant_id, 0)
        pending_count = pending.get(tenant_id, 0)
        open_mr = open_manual.get(tenant_id, 0)

        items.append(
            UsageTenantItem(
                tenant_id=tenant_id,
                customer_name=base.get("name") or tenant_id,
                tenant_status=_normalize_tenant_status(base.get("status")),
                jobs_received=jobs_received,
                jobs_completed=ProxyTimestampMetric(value=jobs_completed),
                jobs_failed=ProxyTimestampMetric(value=jobs_failed),
                automation_rate=_not_measured_automation_rate(),
                gmail_manual_review_handoffs=gmail_handoffs,
                manual_reviews_created=_not_measured_manual_reviews(),
                open_manual_reviews_current=open_mr,
                pending_approvals_current=pending_count,
                operator_actions=operator_actions,
                incidents_created=incidents_created,
                integration_errors=integration_errors,
                ai_usage=_ai_usage_block(),
                ai_cost=_ai_cost_block(),
                latest_activity_at=latest_activity.get(tenant_id),
                attention_status=attention,
            )
        )

    if search:
        needle = search.strip().lower()
        if needle:
            items = [
                item
                for item in items
                if needle in item.customer_name.lower()
                or needle in item.tenant_id.lower()
            ]

    if tenant_status:
        status_filter = tenant_status.strip().lower()
        items = [item for item in items if item.tenant_status == status_filter]

    if attention_status:
        att_filter = attention_status.strip().lower()
        items = [item for item in items if item.attention_status == att_filter]

    if minimum_jobs is not None and minimum_jobs > 0:
        items = [item for item in items if item.jobs_received >= minimum_jobs]

    if has_operator_burden is True:
        items = [
            item
            for item in items
            if item.operator_actions > 0
            or item.open_manual_reviews_current > 0
            or item.pending_approvals_current > 0
        ]
    elif has_operator_burden is False:
        items = [
            item
            for item in items
            if item.operator_actions == 0
            and item.open_manual_reviews_current == 0
            and item.pending_approvals_current == 0
        ]

    if ai_cost_status:
        cost_filter = ai_cost_status.strip().lower()
        items = [item for item in items if item.ai_cost.status == cost_filter]

    if sort == "jobs" and order == "desc":
        items.sort(key=_default_sort_key)
    else:
        reverse = order == "desc"
        items.sort(key=lambda item: _tenant_sort_key(item, sort), reverse=reverse)

    total = len(items)
    page = items[offset : offset + limit]

    return UsageTenantListResponse(
        generated_at=_utcnow(),
        period=_period_model(bounds),
        total=total,
        limit=limit,
        offset=offset,
        items=page,
    )
