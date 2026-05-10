"""
Operational insights engine — deterministic, read-only, tenant-scoped.

Produces structured insight rows from existing DB state (jobs, approvals,
operations workspace, finance data). No external API calls, no writes.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.domain.integrations.models import IntegrationEvent


INSIGHT_TYPES = (
    "stale_lead",
    "hot_lead_pending",
    "missing_customer_info",
    "email_approval_waiting",
    "dispatch_approval_waiting",
    "support_escalation",
    "work_order_blocked",
    "delivery_incomplete",
    "underlag_ready",
    "fortnox_export_pending",
    "stale_active_case",
)

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "info": 3}
_ACTIVE_STATUSES = {"pending", "processing", "awaiting_approval", "manual_review"}
_STALE_HOURS_THRESHOLD = 48
_LEAD_STALE_HOURS = 24


def get_operational_insights(
    db: Session,
    tenant_id: str,
    *,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """Return prioritised operational insight rows for a tenant."""
    insights: list[dict[str, Any]] = []

    insights.extend(_lead_support_insights(db, tenant_id))
    insights.extend(_approval_insights(db, tenant_id))
    insights.extend(_ops_finance_insights(db, tenant_id))
    insights.extend(_stale_case_insights(db, tenant_id))

    insights.sort(key=lambda r: (SEVERITY_ORDER.get(r["severity"], 99), r.get("title", "")))
    return insights[:limit]


def _insight(
    insight_type: str,
    severity: str,
    title_sv: str,
    detail: str,
    job_id: str | None = None,
    pipeline_stage: str | None = None,
    evidence: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "type": insight_type,
        "severity": severity,
        "title": title_sv,
        "detail": detail,
        "job_id": job_id,
        "pipeline_stage": pipeline_stage,
        "evidence": evidence or [],
    }


def _lead_support_insights(db: Session, tenant_id: str) -> list[dict[str, Any]]:
    """Signals from lead and support jobs."""
    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(hours=_LEAD_STALE_HOURS)
    insights: list[dict[str, Any]] = []

    active_jobs = (
        db.query(JobRecord)
        .filter(
            JobRecord.tenant_id == tenant_id,
            JobRecord.status.in_(list(_ACTIVE_STATUSES) + ["completed"]),
            JobRecord.job_type.in_(["lead", "customer_inquiry"]),
        )
        .order_by(JobRecord.created_at.desc())
        .limit(200)
        .all()
    )

    for job in active_jobs:
        inp = job.input_data or {}
        result = job.result or {}
        history = result.get("processor_history") or getattr(job, "processor_history", None) or []

        lead_payload = _get_processor_payload(history, "lead_analyzer_processor")
        support_payload = _get_processor_payload(history, "support_analyzer_processor")

        lead_score_data = lead_payload.get("lead_score") or {}
        score = lead_score_data.get("score", 0)
        category = lead_score_data.get("category", "cold")
        lead_status = inp.get("lead_status") or lead_payload.get("lead_status") or "new"

        created_at = _ensure_aware(job.created_at)

        if job.job_type == "lead":
            if category == "hot" and lead_status in ("new", "contacted") and job.status in _ACTIVE_STATUSES:
                insights.append(_insight(
                    "hot_lead_pending", "high",
                    f"Hett lead väntar på åtgärd (score {score})",
                    f"Lead med score {score} har status '{lead_status}' — bör hanteras snabbt.",
                    job_id=job.job_id,
                    pipeline_stage="lead",
                    evidence=[f"score={score}", f"category={category}", f"lead_status={lead_status}"],
                ))

            if created_at and created_at < stale_cutoff and lead_status == "new" and job.status in _ACTIVE_STATUSES:
                hours = int((now - created_at).total_seconds() / 3600)
                insights.append(_insight(
                    "stale_lead", "high",
                    f"Lead utan svar i {hours} timmar",
                    f"Inget svar har registrerats. Riskerar att tappas.",
                    job_id=job.job_id,
                    pipeline_stage="lead",
                    evidence=[f"hours_since_created={hours}", f"lead_status={lead_status}"],
                ))

        missing_fields = _get_missing_fields(lead_payload, support_payload)
        if missing_fields and job.status in _ACTIVE_STATUSES:
            insights.append(_insight(
                "missing_customer_info", "medium",
                f"Saknar kundinformation ({len(missing_fields)} fält)",
                f"Fält som saknas: {', '.join(missing_fields[:5])}",
                job_id=job.job_id,
                pipeline_stage="lead" if job.job_type == "lead" else "project",
                evidence=[f"missing={f}" for f in missing_fields[:5]],
            ))

        if job.job_type == "customer_inquiry":
            support_priority = support_payload.get("support_priority") or {}
            p_category = support_priority.get("category", "normal")
            support_next = support_payload.get("support_next_action") or {}
            next_action = support_next.get("action") if isinstance(support_next, dict) else None
            if next_action == "escalate" or p_category == "critical":
                insights.append(_insight(
                    "support_escalation", "high",
                    "Supportärende kräver eskalering",
                    f"Prioritet: {p_category}, rekommenderad åtgärd: {next_action or 'eskalera'}",
                    job_id=job.job_id,
                    pipeline_stage="project",
                    evidence=[f"priority={p_category}", f"next_action={next_action}"],
                ))

    return insights


def _approval_insights(db: Session, tenant_id: str) -> list[dict[str, Any]]:
    """Signals from pending approval requests."""
    insights: list[dict[str, Any]] = []

    pending = (
        db.query(ApprovalRequestRecord)
        .filter(
            ApprovalRequestRecord.tenant_id == tenant_id,
            ApprovalRequestRecord.state == "pending",
        )
        .all()
    )

    email_count = 0
    dispatch_count = 0
    for approval in pending:
        noa = approval.next_on_approve or ""
        if noa == "email_send":
            email_count += 1
        elif noa == "controlled_dispatch":
            dispatch_count += 1

    if email_count:
        insights.append(_insight(
            "email_approval_waiting", "medium",
            f"{email_count} e-postmeddelande(n) väntar på godkännande",
            "Kundmail som genererats av AI väntar på operatörsgodkännande innan de skickas.",
            pipeline_stage="lead",
            evidence=[f"pending_email_approvals={email_count}"],
        ))

    if dispatch_count:
        insights.append(_insight(
            "dispatch_approval_waiting", "medium",
            f"{dispatch_count} dispatch-åtgärd(er) väntar på godkännande",
            "Kontrollerade dispatchar till externa system väntar på godkännande.",
            pipeline_stage="project",
            evidence=[f"pending_dispatch_approvals={dispatch_count}"],
        ))

    return insights


def _ops_finance_insights(db: Session, tenant_id: str) -> list[dict[str, Any]]:
    """Signals from operations workspace and finance data."""
    insights: list[dict[str, Any]] = []

    completed_jobs = (
        db.query(JobRecord)
        .filter(
            JobRecord.tenant_id == tenant_id,
            JobRecord.status == "completed",
        )
        .order_by(JobRecord.created_at.desc())
        .limit(200)
        .all()
    )

    underlag_ready_count = 0
    fortnox_exported_job_ids = set()

    exported_events = (
        db.query(IntegrationEvent.job_id)
        .filter(
            IntegrationEvent.tenant_id == tenant_id,
            IntegrationEvent.integration_type.ilike("%fortnox%"),
        )
        .all()
    )
    fortnox_exported_job_ids = {row[0] for row in exported_events if row[0]}

    for job in completed_jobs:
        inp = job.input_data or {}
        workspace = inp.get("operations_workspace") or {}
        work_order = workspace.get("work_order") or {}
        delivery = workspace.get("delivery_package") or {}
        finance = workspace.get("finance") or {}

        wo_status = work_order.get("status")

        if wo_status == "completed" and delivery.get("status") not in ("ready", "sent"):
            docs = workspace.get("documentation") or {}
            doc_count = sum(len(v or []) for v in docs.values() if isinstance(v, list))
            insights.append(_insight(
                "delivery_incomplete", "medium",
                "Slutfört arbete saknar leveransdokumentation",
                f"Arbetsorder avslutad men delivery package inte redo. {doc_count} dokument registrerade.",
                job_id=job.job_id,
                pipeline_stage="project",
                evidence=[f"wo_status={wo_status}", f"delivery_status={delivery.get('status')}", f"doc_count={doc_count}"],
            ))

        if wo_status == "blocked":
            insights.append(_insight(
                "work_order_blocked", "high",
                "Arbetsorder blockerad",
                "Arbetsorder har status 'blocked' — kräver åtgärd innan projektet kan fortsätta.",
                job_id=job.job_id,
                pipeline_stage="project",
                evidence=[f"wo_status={wo_status}"],
            ))

        is_underlag_ready = _is_underlag_ready(job, workspace, fortnox_exported_job_ids)
        if is_underlag_ready:
            underlag_ready_count += 1

        if is_underlag_ready and job.job_id not in fortnox_exported_job_ids:
            insights.append(_insight(
                "fortnox_export_pending", "info",
                "Fakturaunderlag redo — ej exporterat",
                "Underlag är komplett och kan förhandsgranskas/exporteras till Fortnox.",
                job_id=job.job_id,
                pipeline_stage="underlag",
                evidence=["underlag_ready=true", "fortnox_exported=false"],
            ))

    if underlag_ready_count:
        insights.append(_insight(
            "underlag_ready", "info",
            f"{underlag_ready_count} fakturaunderlag redo",
            f"{underlag_ready_count} ärende(n) har komplett underlag för faktura-/bokföringsförberedelse.",
            pipeline_stage="underlag",
            evidence=[f"count={underlag_ready_count}"],
        ))

    return insights


def _stale_case_insights(db: Session, tenant_id: str) -> list[dict[str, Any]]:
    """Stale active cases — no update for 48+ hours."""
    insights: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(hours=_STALE_HOURS_THRESHOLD)

    stale_jobs = (
        db.query(JobRecord)
        .filter(
            JobRecord.tenant_id == tenant_id,
            JobRecord.status.in_(list(_ACTIVE_STATUSES)),
            JobRecord.updated_at < stale_cutoff,
        )
        .limit(20)
        .all()
    )

    for job in stale_jobs:
        updated = _ensure_aware(job.updated_at or job.created_at)
        if updated:
            hours = int((now - updated).total_seconds() / 3600)
            insights.append(_insight(
                "stale_active_case", "medium",
                f"Aktivt ärende utan uppdatering i {hours} timmar",
                f"Ärende med status '{job.status}' har inte uppdaterats på {hours} timmar.",
                job_id=job.job_id,
                pipeline_stage="project",
                evidence=[f"hours_stale={hours}", f"status={job.status}"],
            ))

    return insights


def _is_underlag_ready(
    job: Any,
    workspace: dict[str, Any],
    exported_ids: set[str],
) -> bool:
    """Check if a job meets the 'underlag ready' criteria (see docs/16-underlag-ready-checklist.md)."""
    if job.status != "completed":
        return False

    if job.job_id in exported_ids:
        return False

    inp = job.input_data or {}
    work_order = workspace.get("work_order") or {}

    if job.job_type == "invoice":
        return True

    if job.job_type in ("lead", "customer_inquiry"):
        return work_order.get("status") == "completed"

    return False


def _get_processor_payload(history: list[dict], processor: str) -> dict:
    for entry in history:
        if entry.get("processor") == processor:
            payload = (entry.get("result") or {}).get("payload") or {}
            return payload if isinstance(payload, dict) else {}
    return {}


def _get_missing_fields(lead_payload: dict, support_payload: dict) -> list[str]:
    lead_missing = (lead_payload.get("missing_info") or {}).get("missing_fields") or []
    support_missing = (support_payload.get("support_missing_info") or {}).get("missing_fields") or []
    return list(dict.fromkeys([*lead_missing, *support_missing]))


def _ensure_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ── Dashboard KPI helpers (used by main.py endpoints) ─────────────────────

def compute_dashboard_kpis(db: Session, tenant_id: str) -> dict[str, Any]:
    """Extended dashboard KPIs beyond the basic summary."""
    return {
        "email_approval_queue": _count_email_approvals(db, tenant_id),
        "dispatch_approval_queue": _count_dispatch_approvals(db, tenant_id),
        "waiting_customer": _count_waiting_customer(db, tenant_id),
        "underlag_ready": _count_underlag_ready(db, tenant_id),
        "active_ops_cases": _count_active_ops_cases(db, tenant_id),
    }


def _count_email_approvals(db: Session, tenant_id: str) -> int:
    return (
        db.query(func.count(ApprovalRequestRecord.approval_id))
        .filter(
            ApprovalRequestRecord.tenant_id == tenant_id,
            ApprovalRequestRecord.state == "pending",
            ApprovalRequestRecord.next_on_approve == "email_send",
        )
        .scalar() or 0
    )


def _count_dispatch_approvals(db: Session, tenant_id: str) -> int:
    return (
        db.query(func.count(ApprovalRequestRecord.approval_id))
        .filter(
            ApprovalRequestRecord.tenant_id == tenant_id,
            ApprovalRequestRecord.state == "pending",
            ApprovalRequestRecord.next_on_approve == "controlled_dispatch",
        )
        .scalar() or 0
    )


def _count_waiting_customer(db: Session, tenant_id: str) -> int:
    """Jobs where recommended_status = needs_customer_info and job is not completed/failed."""
    return (
        db.query(func.count(JobRecord.job_id))
        .filter(
            JobRecord.tenant_id == tenant_id,
            JobRecord.status.notin_(["completed", "failed"]),
            JobRecord.result["payload"]["recommended_status"].as_string() == "needs_customer_info",
        )
        .scalar() or 0
    )


def _count_underlag_ready(db: Session, tenant_id: str) -> int:
    """Count jobs with completed underlag that haven't been exported to Fortnox."""
    exported_ids = {
        row[0] for row in
        db.query(IntegrationEvent.job_id)
        .filter(
            IntegrationEvent.tenant_id == tenant_id,
            IntegrationEvent.integration_type.ilike("%fortnox%"),
        )
        .all()
        if row[0]
    }

    count = 0
    completed_jobs = (
        db.query(JobRecord)
        .filter(
            JobRecord.tenant_id == tenant_id,
            JobRecord.status == "completed",
        )
        .all()
    )

    for job in completed_jobs:
        workspace = (job.input_data or {}).get("operations_workspace") or {}
        if _is_underlag_ready(job, workspace, exported_ids):
            count += 1

    return count


def _count_active_ops_cases(db: Session, tenant_id: str) -> int:
    """Count jobs that have a non-default operations_workspace with active work."""
    count = 0
    active_jobs = (
        db.query(JobRecord)
        .filter(
            JobRecord.tenant_id == tenant_id,
            JobRecord.status.in_(list(_ACTIVE_STATUSES) + ["completed"]),
        )
        .limit(500)
        .all()
    )

    for job in active_jobs:
        workspace = (job.input_data or {}).get("operations_workspace") or {}
        work_order = workspace.get("work_order") or {}
        project = workspace.get("project") or {}
        wo_status = work_order.get("status")
        p_status = project.get("status")
        if wo_status and wo_status != "new":
            count += 1
        elif p_status and p_status != "intake":
            count += 1

    return count
