"""Map Job domain objects to Google Sheets row values.

Required tabs and their columns:

  Leads   — Datum, Kund, Telefon, E-post, Ärendetyp, Prioritet,
             Sammanfattning, Saknas, Föreslaget nästa steg, Status, Källa, Job ID

  Support — Datum, Kund, Telefon, E-post, Ärende, Prioritet,
             Risk, Sammanfattning, Föreslagen åtgärd, Status, Källa, Job ID

  Logg    — Tid, Typ, Job ID, Action, Resultat, Kommentar

Export mode: append-only. Repeated exports for the same job append duplicate rows.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.domain.workflows.models import Job

# ── Tab name constants ────────────────────────────────────────────────────────
TAB_LEADS = "Leads"
TAB_SUPPORT = "Support"
TAB_LOGG = "Logg"

_PREFERRED_DICT_KEYS = (
    "label",
    "level",
    "priority",
    "action",
    "reason",
    "summary",
    "text",
    "category",
    "score",
)


def normalize_sheet_cell(value: Any) -> str | int | float | bool:
    """Coerce a value into a Google Sheets scalar (string, number, boolean, or blank)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return value
    if hasattr(value, "value"):
        return str(value.value)
    if isinstance(value, list):
        parts = [normalize_sheet_cell(item) for item in value]
        rendered = "; ".join(str(part) for part in parts if part != "")
        return rendered
    if isinstance(value, dict):
        return _normalize_dict_cell(value)
    return str(value)


def _normalize_dict_cell(value: dict[str, Any]) -> str:
    if "score" in value and "category" in value and "reasons" in value:
        return _format_support_priority(value)
    if "action" in value and "reason" in value:
        return _format_support_next_action(value)

    for key in _PREFERRED_DICT_KEYS:
        if key in value and value[key] not in (None, "", [], {}):
            return str(normalize_sheet_cell(value[key]))

    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _format_support_priority(value: dict[str, Any]) -> str:
    category = normalize_sheet_cell(value.get("category")) or "normal"
    score = value.get("score")
    parts: list[str] = []
    if score is not None and score != "":
        parts.append(f"{category} (score {score})")
    else:
        parts.append(str(category))

    reasons = value.get("reasons") or []
    if isinstance(reasons, list) and reasons:
        reason_text = "; ".join(str(normalize_sheet_cell(r)) for r in reasons if r)
        if reason_text:
            parts.append(reason_text)

    risk = value.get("business_risk_reason")
    if risk:
        parts.append(f"risk: {normalize_sheet_cell(risk)}")

    return " — ".join(parts)


def _format_support_next_action(value: dict[str, Any]) -> str:
    action = normalize_sheet_cell(value.get("action")) or "unknown"
    reason = normalize_sheet_cell(value.get("reason"))
    requires_approval = value.get("requires_approval")

    if reason:
        text = f"{action} — {reason}"
    else:
        text = str(action)

    if requires_approval is True:
        text = f"{text} (approval required)"
    return text


# ── Tab selection ─────────────────────────────────────────────────────────────

def choose_tab(job: Job, target: str) -> str:
    """Return the target tab name for the given job and explicit target hint.

    target values: "auto" | "leads" | "support" | "logg"
    For "auto" the tab is inferred from job_type.
    """
    if target == "logg":
        return TAB_LOGG
    if target == "leads":
        return TAB_LEADS
    if target == "support":
        return TAB_SUPPORT

    # auto: derive from job_type
    job_type = _str_val(job.job_type)
    if job_type == "lead":
        return TAB_LEADS
    if job_type in ("customer_inquiry", "support"):
        return TAB_SUPPORT
    # unknown, invoice, etc. → Logg
    return TAB_LOGG


# ── Row builders ──────────────────────────────────────────────────────────────

def build_leads_row(job: Job) -> list[Any]:
    """Build a Leads tab row (12 columns)."""
    data = job.input_data or {}
    sender = _get_sender(data)
    lead_payload = _get_processor_payload(job, "lead_analyzer_processor")
    lead_analysis = lead_payload.get("lead_analysis") or {}
    missing_info = lead_payload.get("missing_info") or {}

    datum = _format_dt(job.created_at)
    kund = sender.get("name") or data.get("customer_name") or ""
    telefon = sender.get("phone") or data.get("phone") or ""
    epost = sender.get("email") or data.get("email") or ""
    arendetyp = lead_analysis.get("lead_type") or _str_val(job.job_type)
    prioritet = lead_payload.get("next_action") or ""
    sammanfattning = _truncate(data.get("message_text") or data.get("subject") or "")
    saknas = ", ".join(missing_info.get("missing_fields") or [])
    foreslaget_steg = lead_payload.get("next_action") or ""
    status = _str_val(job.status)
    kalla = _source(data)
    job_id = job.job_id

    return [datum, kund, telefon, epost, arendetyp, prioritet,
            sammanfattning, saknas, foreslaget_steg, status, kalla, job_id]


def build_support_row(job: Job) -> list[Any]:
    """Build a Support tab row (12 columns)."""
    data = job.input_data or {}
    sender = _get_sender(data)
    support_payload = _get_processor_payload(job, "support_analyzer_processor")
    support_analysis = support_payload.get("support_analysis") or {}

    datum = _format_dt(job.created_at)
    kund = sender.get("name") or data.get("customer_name") or ""
    telefon = sender.get("phone") or data.get("phone") or ""
    epost = sender.get("email") or data.get("email") or ""
    arende = data.get("subject") or support_analysis.get("category") or ""
    prioritet = normalize_sheet_cell(support_payload.get("support_priority"))
    risk = normalize_sheet_cell(support_analysis.get("ticket_type"))
    sammanfattning = _truncate(data.get("message_text") or data.get("subject") or "")
    foresl_atgard = normalize_sheet_cell(support_payload.get("support_next_action"))
    status = _str_val(job.status)
    kalla = _source(data)
    job_id = job.job_id

    row = [
        datum,
        normalize_sheet_cell(kund),
        normalize_sheet_cell(telefon),
        normalize_sheet_cell(epost),
        normalize_sheet_cell(arende),
        prioritet,
        risk,
        sammanfattning,
        foresl_atgard,
        status,
        kalla,
        job_id,
    ]
    return row


def build_logg_row(
    job: Job,
    action: str = "export",
    kommentar: str = "",
) -> list[Any]:
    """Build a Logg tab row (6 columns)."""
    tid = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    typ = _str_val(job.job_type)
    job_id = job.job_id
    resultat = _str_val(job.status)
    return [tid, typ, job_id, action, resultat, kommentar]


# ── Private helpers ───────────────────────────────────────────────────────────

def _str_val(value: Any) -> str:
    """Return the string value of an enum member or plain value."""
    if hasattr(value, "value"):
        return str(value.value)
    return str(value) if value is not None else ""


def _format_dt(dt: datetime | None) -> str:
    if dt is None:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    return dt.strftime("%Y-%m-%d %H:%M")


def _truncate(value: Any, max_len: int = 300) -> str:
    s = str(value or "")
    return s[:max_len] + "…" if len(s) > max_len else s


def _get_sender(data: dict) -> dict:
    raw = data.get("sender") or {}
    return raw if isinstance(raw, dict) else {}


def _source(data: dict) -> str:
    src = data.get("source") or ""
    if isinstance(src, dict):
        return src.get("system") or "unknown"
    return str(src) or "unknown"


def _get_processor_payload(job: Job, processor_name: str) -> dict:
    """Return the payload dict from the latest matching processor history entry."""
    for item in reversed(job.processor_history):
        if item.get("processor") == processor_name:
            result = item.get("result") or {}
            return result.get("payload") or {}
    return {}
