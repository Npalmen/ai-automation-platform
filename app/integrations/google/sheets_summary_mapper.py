"""Build the Sammanfattning tab matrix for Google Sheets."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.domain.workflows.models import Job
from app.domain.workflows.statuses import JobStatus
from app.reporting.daily_report import generate_daily_report
from app.repositories.postgres.job_repository import JobRepository
from app.workflows.derived_status import derive_job_status
from app.workflows.manual_review_handoff import is_unresolved_manual_review
from app.workflows.processors.ai_processor_utils import get_latest_processor_payload
from app.integrations.google.sheets_row_mapper import normalize_sheet_cell

TAB_SUMMARY = "Sammanfattning"
SUMMARY_CLEAR_RANGE = "Sammanfattning!A1:G60"
SUMMARY_COLUMN_COUNT = 7
SUMMARY_MAX_TEXT_LEN = 120
SUMMARY_MAX_PRIORITY_ROWS = 10


def build_summary_sheet_data(
    db: Session,
    tenant_id: str,
    *,
    since_hours: int = 24,
) -> dict[str, Any]:
    """Build summary report data and the Sammanfattning sheet matrix."""
    report = generate_daily_report(db, tenant_id=tenant_id, since_hours=since_hours)
    all_jobs = JobRepository.list_jobs(db, tenant_id=tenant_id, limit=500, offset=0)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    recent_jobs = [job for job in all_jobs if job.created_at >= cutoff]
    priority_jobs = _collect_priority_jobs(report, recent_jobs)
    matrix = build_summary_matrix(report, priority_jobs)
    return {
        "report": report,
        "matrix": matrix,
        "priority_job_ids": [job.job_id for job in priority_jobs],
        "tab": TAB_SUMMARY,
        "clear_range": SUMMARY_CLEAR_RANGE,
        "write_range": f"{TAB_SUMMARY}!A1",
    }


def build_summary_matrix(report: dict[str, Any], priority_jobs: list[Job]) -> list[list[Any]]:
    counts = report.get("counts") or {}
    since_hours = int(report.get("period_hours") or 24)
    period_label = "sedan igår" if since_hours == 24 else f"senaste {since_hours} timmarna"
    generated_at = _format_generated_at(report.get("generated_at"))

    total_current = (
        int(counts.get("new_leads") or 0)
        + int(counts.get("inquiries_needing_response") or 0)
        + int(counts.get("unresolved_manual_review") or 0)
        + int(counts.get("pending_approvals") or 0)
        + int(counts.get("risk_review_required") or 0)
    )

    rows: list[list[Any]] = [
        ["Senast uppdaterad", generated_at, "Tenant", normalize_sheet_cell(report.get("tenant_id"))],
        ["Tidsperiod", period_label, "", ""],
        [],
        ["Räknare", "Antal"],
        ["Totalt antal aktuella ärenden", total_current],
        ["Nya leads", int(counts.get("new_leads") or 0)],
        ["Kundärenden som behöver svar", int(counts.get("inquiries_needing_response") or 0)],
        ["Manuell granskning", int(counts.get("unresolved_manual_review") or 0)],
        ["Väntande godkännanden", int(counts.get("pending_approvals") or 0)],
        ["Interna handoffs skickade", int(counts.get("internal_handoffs_sent") or 0)],
        [],
        [
            "Typ",
            "Prioritet",
            "Kort sammanfattning",
            "Saknas / risk",
            "Föreslaget nästa steg",
            "Status",
            "Job ID",
        ],
    ]

    for job in priority_jobs[:SUMMARY_MAX_PRIORITY_ROWS]:
        rows.append(build_priority_row(job))

    return _pad_matrix(rows)


def build_priority_row(job: Job) -> list[Any]:
    ds = derive_job_status(job)
    support_payload = get_latest_processor_payload(job, "support_analyzer_processor")
    lead_payload = get_latest_processor_payload(job, "lead_analyzer_processor")
    policy_payload = get_latest_processor_payload(job, "policy_processor")
    handoff = (job.result or {}).get("manual_review_handoff") or {}

    job_type = _job_type_value(job)
    if is_unresolved_manual_review(job) or job.status == JobStatus.MANUAL_REVIEW:
        typ = "manual_review"
    elif job.status == JobStatus.AWAITING_APPROVAL:
        typ = "väntar_godkännande"
    else:
        typ = job_type

    priority = _priority_label(job, support_payload, lead_payload)
    summary = concise_operational_summary(job)
    missing_risk = _missing_or_risk(job, support_payload, lead_payload, policy_payload, handoff)
    next_step = _next_step_label(job, support_payload, lead_payload, ds)
    status = _job_status_value(job)

    return [
        normalize_sheet_cell(typ),
        normalize_sheet_cell(priority),
        normalize_sheet_cell(summary),
        normalize_sheet_cell(missing_risk),
        normalize_sheet_cell(next_step),
        normalize_sheet_cell(status),
        normalize_sheet_cell(job.job_id),
    ]


def concise_operational_summary(job: Job, *, max_len: int = SUMMARY_MAX_TEXT_LEN) -> str:
    """Return a short operational summary without full email body."""
    data = job.input_data or {}
    subject = str(data.get("subject") or "").strip()
    if subject:
        return _truncate_text(subject, max_len)

    handoff = (job.result or {}).get("manual_review_handoff") or {}
    reason = handoff.get("manual_review_reason")
    if reason:
        return _truncate_text(str(reason), max_len)

    human_payload = get_latest_processor_payload(job, "human_handoff_processor")
    human_summary = (human_payload or {}).get("human_summary")
    if human_summary:
        return _truncate_text(str(human_summary), max_len)

    lead_payload = get_latest_processor_payload(job, "lead_analyzer_processor")
    service = lead_payload.get("service_profile_type")
    if service:
        return _truncate_text(f"Ärende: {service}", max_len)

    body = str(data.get("message_text") or "").strip()
    if body:
        first_line = next((line.strip() for line in body.splitlines() if line.strip()), "")
        return _truncate_text(first_line, max_len)

    return ""


def _collect_priority_jobs(report: dict[str, Any], recent_jobs: list[Job]) -> list[Job]:
    by_id = {job.job_id: job for job in recent_jobs}
    seen: set[str] = set()
    ordered: list[Job] = []

    def add_job(job: Job | None) -> None:
        if job is None or job.job_id in seen:
            return
        seen.add(job.job_id)
        ordered.append(job)

    for item in report.get("top_priorities") or []:
        add_job(by_id.get(item.get("job_id", "")))

    for job in recent_jobs:
        if is_unresolved_manual_review(job):
            add_job(job)

    for job in recent_jobs:
        if job.status == JobStatus.AWAITING_APPROVAL:
            add_job(job)

    for job in recent_jobs:
        ds = derive_job_status(job)
        if ds.get("derived_status") == "risk_review_required":
            add_job(job)

    return ordered[:SUMMARY_MAX_PRIORITY_ROWS]


def _priority_label(job: Job, support_payload: dict, lead_payload: dict) -> str:
    if job.status == JobStatus.AWAITING_APPROVAL:
        return "väntar godkännande"
    if support_payload.get("support_priority"):
        return str(normalize_sheet_cell(support_payload["support_priority"]))
    if lead_payload.get("next_action"):
        return str(normalize_sheet_cell(lead_payload["next_action"]))
    return str(normalize_sheet_cell(derive_job_status(job).get("derived_status")))


def _missing_or_risk(
    job: Job,
    support_payload: dict,
    lead_payload: dict,
    policy_payload: dict,
    handoff: dict,
) -> str:
    parts: list[str] = []
    missing = (lead_payload.get("missing_info") or {}).get("missing_fields") or []
    if missing:
        parts.append("saknas: " + ", ".join(str(normalize_sheet_cell(v)) for v in missing))

    risk = policy_payload.get("risk") or {}
    risk_reasons = risk.get("reasons") or []
    if risk_reasons:
        parts.append("risk: " + "; ".join(str(normalize_sheet_cell(v)) for v in risk_reasons))

    reason_codes = handoff.get("manual_review_reason_codes") or []
    if reason_codes:
        parts.append("; ".join(str(normalize_sheet_cell(v)) for v in reason_codes))

    ticket_type = (support_payload.get("support_analysis") or {}).get("ticket_type")
    if ticket_type and not parts:
        parts.append(str(normalize_sheet_cell(ticket_type)))

    return " — ".join(parts)


def _next_step_label(job: Job, support_payload: dict, lead_payload: dict, ds: dict) -> str:
    if support_payload.get("support_next_action"):
        return str(normalize_sheet_cell(support_payload["support_next_action"]))
    if lead_payload.get("next_action"):
        return str(normalize_sheet_cell(lead_payload["next_action"]))
    return str(normalize_sheet_cell(ds.get("next_action") or ds.get("derived_status") or ""))


def _truncate_text(value: str, max_len: int) -> str:
    text = " ".join(value.split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def _format_generated_at(value: Any) -> str:
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        except ValueError:
            return value
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _pad_matrix(rows: list[list[Any]]) -> list[list[Any]]:
    padded: list[list[Any]] = []
    for row in rows:
        cells = list(row)
        if len(cells) < SUMMARY_COLUMN_COUNT:
            cells.extend([""] * (SUMMARY_COLUMN_COUNT - len(cells)))
        else:
            cells = cells[:SUMMARY_COLUMN_COUNT]
        padded.append([normalize_sheet_cell(cell) for cell in cells])
    return padded


def _job_type_value(job: Job) -> str:
    if hasattr(job.job_type, "value"):
        return str(job.job_type.value)
    return str(job.job_type)


def _job_status_value(job: Job) -> str:
    if hasattr(job.status, "value"):
        return str(job.status.value)
    return str(job.status)
