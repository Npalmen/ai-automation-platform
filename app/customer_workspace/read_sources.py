"""Shared read helpers for customer workspace adapters."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import String, cast, func, or_
from sqlalchemy.orm import Session

from app.core.config import get_tenant_config
from app.core.settings import get_settings
from app.repositories.postgres.action_execution_models import ActionExecutionRecord
from app.repositories.postgres.approval_repository import ApprovalRequestRepository
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

_ROI_LEAD_MIN = 12
_ROI_SUPPORT_MIN = 8
_ROI_INVOICE_MIN = 6
_ROI_FOLLOWUP_MIN = 5
_ROI_HOURLY_SEK = 500


def build_account_context(db: Session, tenant_id: str) -> dict[str, Any]:
    settings_dict = TenantConfigRepository.get_settings(db, tenant_id)
    config = get_tenant_config(tenant_id, db=db)
    account = settings_dict.get("account") or {}
    branding = settings_dict.get("branding") or {}
    return {
        "tenant_id": tenant_id,
        "company_name": (
            account.get("company_name")
            or branding.get("company_display_name")
            or config.get("name")
            or tenant_id
        ),
        "contact_name": account.get("contact_name") or "",
        "contact_email": account.get("contact_email") or "",
        "support_email": account.get("support_email") or settings_dict.get("support_email") or "",
        "language": account.get("language") or "sv",
        "region": account.get("region") or "SE",
    }


def derive_case_fields(record: JobRecord) -> dict[str, Any]:
    inp = record.input_data or {}
    result = record.result or {}
    history = result.get("processor_history") or []

    subject: str | None = inp.get("subject") or inp.get("latest_message_subject") or None
    sender = inp.get("sender") or {}
    customer_email: str | None = sender.get("email") or inp.get("sender_email") or None
    customer_name: str | None = None
    for entry in reversed(history):
        payload = (entry.get("result") or {}).get("payload") or {}
        entities = payload.get("entities") or {}
        name = entities.get("customer_name")
        if name:
            customer_name = name
            break
    if not customer_name:
        for entry in history:
            payload = (entry.get("result") or {}).get("payload") or {}
            origin = payload.get("origin") or {}
            name = origin.get("sender_name")
            if name:
                customer_name = name
                break
    if not customer_name:
        customer_name = sender.get("name") or inp.get("sender_name") or None

    priority: str | None = None
    for entry in reversed(history):
        if entry.get("processor") == "action_dispatch_processor":
            for action in ((entry.get("result") or {}).get("payload") or {}).get("actions_requested") or []:
                p = action.get("column_values", {}).get("priority")
                if p:
                    priority = str(p).lower()
                    break
        if priority:
            break

    recommended_status: str | None = None
    payload = result.get("payload") or {}
    if isinstance(payload, dict):
        recommended_status = payload.get("recommended_status")

    received_at: str | None = inp.get("received_at") or None
    processed_at: str | None = record.updated_at.isoformat() if record.updated_at else None
    created_at: str | None = record.created_at.isoformat() if record.created_at else None

    return {
        "subject": subject,
        "customer_name": customer_name,
        "customer_email": customer_email,
        "priority": priority,
        "received_at": received_at,
        "processed_at": processed_at,
        "created_at": created_at,
        "recommended_status": recommended_status,
    }


def _today_start() -> datetime:
    return datetime.combine(date.today(), datetime.min.time()).replace(tzinfo=timezone.utc)


def compute_summary_metrics(db: Session, tenant_id: str) -> dict[str, int]:
    today_start = _today_start()

    def _count(job_type: str | None, status: str | None, since: datetime | None = None) -> int:
        query = db.query(func.count(JobRecord.job_id)).filter(JobRecord.tenant_id == tenant_id)
        if job_type:
            query = query.filter(JobRecord.job_type == job_type)
        if status:
            query = query.filter(JobRecord.status == status)
        if since:
            query = query.filter(JobRecord.created_at >= since)
        return query.scalar() or 0

    waiting_customer = 0
    try:
        waiting_customer = (
            db.query(func.count(JobRecord.job_id))
            .filter(
                JobRecord.tenant_id == tenant_id,
                JobRecord.status.notin_(["completed", "failed"]),
                JobRecord.result["payload"]["recommended_status"].as_string() == "needs_customer_info",
            )
            .scalar()
            or 0
        )
    except Exception:
        waiting_customer = 0

    return {
        "leads_today": _count("lead", None, today_start),
        "inquiries_today": _count("customer_inquiry", None, today_start),
        "invoices_today": _count("invoice", None, today_start),
        "waiting_customer": waiting_customer,
        "ready_cases": ApprovalRequestRepository.count_pending_for_tenant(db, tenant_id),
        "completed_today": _count(None, "completed", today_start),
        "failed_today": _count(None, "failed", today_start),
    }


def compute_roi_metrics(db: Session, tenant_id: str) -> dict[str, float | int]:
    today_start = _today_start()

    def _count_jobs(job_type: str) -> int:
        return (
            db.query(func.count(JobRecord.job_id))
            .filter(
                JobRecord.tenant_id == tenant_id,
                JobRecord.job_type == job_type,
                JobRecord.created_at >= today_start,
            )
            .scalar()
            or 0
        )

    leads_created = _count_jobs("lead")
    support_cases = _count_jobs("customer_inquiry")
    invoices_processed = _count_jobs("invoice")
    followups_sent = (
        db.query(func.count(ActionExecutionRecord.execution_id))
        .join(JobRecord, ActionExecutionRecord.job_id == JobRecord.job_id)
        .filter(
            ActionExecutionRecord.tenant_id == tenant_id,
            ActionExecutionRecord.action_type == "send_email",
            ActionExecutionRecord.executed_at >= today_start,
            JobRecord.job_type.in_(["lead", "customer_inquiry"]),
        )
        .scalar()
        or 0
    )
    total_minutes = (
        leads_created * _ROI_LEAD_MIN
        + support_cases * _ROI_SUPPORT_MIN
        + invoices_processed * _ROI_INVOICE_MIN
        + followups_sent * _ROI_FOLLOWUP_MIN
    )
    total_hours = round(total_minutes / 60, 2)
    return {
        "estimated_hours_saved": total_hours,
        "estimated_value_sek": round(total_hours * _ROI_HOURLY_SEK),
    }


def list_job_records(
    db: Session,
    tenant_id: str,
    *,
    job_types: list[str] | None = None,
    raw_status: str | None = None,
    q: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    sort_by: str = "updated_at",
    sort_dir: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[JobRecord], int]:
    query = db.query(JobRecord).filter(JobRecord.tenant_id == tenant_id)
    if job_types:
        query = query.filter(JobRecord.job_type.in_(job_types))
    if raw_status:
        query = query.filter(JobRecord.status == raw_status)
    if created_from:
        query = query.filter(JobRecord.created_at >= created_from)
    if created_to:
        query = query.filter(JobRecord.created_at <= created_to)
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(
            or_(
                JobRecord.job_id.ilike(term),
                cast(JobRecord.input_data, String).ilike(term),
            )
        )

    records = query.all()
    if q and q.strip():
        needle = q.strip().lower()
        filtered: list[JobRecord] = []
        for record in records:
            derived = derive_case_fields(record)
            haystack = " ".join(
                filter(
                    None,
                    [
                        derived.get("subject"),
                        derived.get("customer_name"),
                        derived.get("customer_email"),
                    ],
                )
            ).lower()
            if needle in haystack or needle in (record.job_id or "").lower():
                filtered.append(record)
        records = filtered

    reverse = sort_dir.lower() == "desc"
    if sort_by == "created_at":
        records.sort(key=lambda r: r.created_at or datetime.min.replace(tzinfo=timezone.utc), reverse=reverse)
    elif sort_by == "priority_rank":
        from app.customer_workspace.status import priority_rank

        records.sort(
            key=lambda r: (
                priority_rank(derive_case_fields(r).get("priority")),
                r.updated_at or r.created_at or datetime.min.replace(tzinfo=timezone.utc),
            ),
            reverse=not reverse,
        )
    else:
        records.sort(key=lambda r: r.updated_at or r.created_at or datetime.min.replace(tzinfo=timezone.utc), reverse=reverse)

    total = len(records)
    page = records[offset : offset + limit]
    return page, total


def get_job_record(db: Session, tenant_id: str, work_item_id: str) -> JobRecord | None:
    return (
        db.query(JobRecord)
        .filter(JobRecord.job_id == work_item_id, JobRecord.tenant_id == tenant_id)
        .first()
    )


def has_pending_approval(db: Session, tenant_id: str, job_id: str) -> bool:
    return ApprovalRequestRepository.count_pending_for_job(db, tenant_id, job_id) > 0


def list_activity_records(
    db: Session,
    tenant_id: str,
    *,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    records = (
        db.query(JobRecord)
        .filter(JobRecord.tenant_id == tenant_id)
        .order_by(JobRecord.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    total = (
        db.query(func.count(JobRecord.job_id))
        .filter(JobRecord.tenant_id == tenant_id)
        .scalar()
        or 0
    )

    job_ids = [r.job_id for r in records]
    latest_actions: dict[str, str] = {}
    if job_ids:
        subq = (
            db.query(
                ActionExecutionRecord.job_id,
                func.max(ActionExecutionRecord.executed_at).label("max_at"),
            )
            .filter(
                ActionExecutionRecord.tenant_id == tenant_id,
                ActionExecutionRecord.job_id.in_(job_ids),
            )
            .group_by(ActionExecutionRecord.job_id)
            .subquery()
        )
        rows = (
            db.query(ActionExecutionRecord.job_id, ActionExecutionRecord.action_type)
            .join(
                subq,
                (ActionExecutionRecord.job_id == subq.c.job_id)
                & (ActionExecutionRecord.executed_at == subq.c.max_at),
            )
            .filter(ActionExecutionRecord.tenant_id == tenant_id)
            .all()
        )
        latest_actions = {job_id: action_type for job_id, action_type in rows}

    items: list[dict[str, Any]] = []
    for record in records:
        derived = derive_case_fields(record)
        items.append(
            {
                "created_at": record.created_at.isoformat() if record.created_at else None,
                "type": record.job_type or "unknown",
                "status": record.status or "unknown",
                "latest_action": latest_actions.get(record.job_id),
                "priority": derived.get("priority"),
                "recommended_status": derived.get("recommended_status"),
                "has_pending_approval": has_pending_approval(db, tenant_id, record.job_id),
            }
        )
    return items, total


def build_customer_timeline(
    db: Session,
    tenant_id: str,
    record: JobRecord,
) -> list[dict[str, Any | None]]:
    inp = record.input_data or {}
    events: list[dict[str, Any | None]] = []

    received_at = inp.get("received_at")
    if received_at:
        events.append(
            {
                "at": received_at,
                "kind": "received",
                "label": "Ärende mottaget",
                "detail": None,
            }
        )

    for msg in inp.get("conversation_messages") or []:
        if (msg.get("source") or "gmail") in {"system", "outgoing"}:
            continue
        ts = msg.get("received_at") or msg.get("created_at")
        if ts:
            events.append(
                {
                    "at": ts,
                    "kind": "message",
                    "label": "Kundsvar mottaget",
                    "detail": None,
                }
            )

    approvals = ApprovalRequestRepository.list_for_job(db, tenant_id, record.job_id)
    for approval in approvals:
        ts = (
            approval.resolved_at.isoformat()
            if approval.resolved_at
            else approval.requested_at.isoformat()
            if approval.requested_at
            else approval.created_at.isoformat()
        )
        label = approval.title or "Godkännande"
        events.append(
            {
                "at": ts,
                "kind": "approval",
                "label": label,
                "detail": None,
            }
        )

    actions = (
        db.query(ActionExecutionRecord)
        .filter(
            ActionExecutionRecord.job_id == record.job_id,
            ActionExecutionRecord.tenant_id == tenant_id,
        )
        .order_by(ActionExecutionRecord.executed_at.asc())
        .all()
    )
    for action in actions:
        if not action.executed_at:
            continue
        events.append(
            {
                "at": action.executed_at.isoformat(),
                "kind": "system_action",
                "label": "Systemåtgärd utförd",
                "detail": None,
            }
        )

    events.sort(key=lambda item: item.get("at") or "")
    return events


def customer_health_payload(db: Session, tenant_id: str) -> dict[str, Any]:
    from app.health.integration_health import get_integration_health

    health = get_integration_health(db, tenant_id, app_settings=get_settings())
    overall = health.get("overall_status") or "warning"
    labels = {
        "healthy": "Alla kopplingar fungerar",
        "warning": "Kontroll rekommenderas",
        "error": "Åtgärd krävs",
        "not_configured": "Integration saknas",
    }
    systems: dict[str, dict[str, str]] = {}
    for key, value in (health.get("systems") or {}).items():
        status = value.get("status") if isinstance(value, dict) else "warning"
        systems[key] = {
            "status": status,
            "label": labels.get(status, "Kontroll rekommenderas"),
        }
    return {
        "overall_status": overall,
        "message": labels.get(overall, "Kontroll rekommenderas"),
        "systems": systems,
    }


def needs_help_job_ids(db: Session, tenant_id: str) -> set[str]:
    from app.admin.operations_triage import _build_tenant_triage, dedupe_and_normalize_signals

    record = TenantConfigRepository.get(db, tenant_id)
    tenant_name = record.name if record and record.name else tenant_id
    rows = _build_tenant_triage(db, tenant_id, tenant_name, get_settings(), record=record)
    rows = dedupe_and_normalize_signals(rows)
    job_ids: set[str] = set()
    for row in rows:
        job_id = row.get("job_id")
        if job_id:
            job_ids.add(str(job_id))
    return job_ids
