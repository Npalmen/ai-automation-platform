"""Customer-facing status normalization for workspace API."""

from __future__ import annotations

from typing import Literal

CustomerStatus = Literal[
    "new",
    "prioritized",
    "in_progress",
    "waiting_for_decision",
    "waiting_for_customer",
    "prepared",
    "scheduled",
    "completed",
    "needs_help",
    "failed",
    "cancelled",
    "unknown",
]

_STATUS_LABELS: dict[str, str] = {
    "new": "Nytt",
    "prioritized": "Prioriterad",
    "in_progress": "Pågår",
    "waiting_for_decision": "Väntar på beslut",
    "waiting_for_customer": "Väntar på kund",
    "prepared": "Förberedd",
    "scheduled": "Schemalagd",
    "completed": "Klar",
    "needs_help": "Behöver hjälp",
    "failed": "Misslyckad",
    "cancelled": "Avbruten",
    "unknown": "Okänd status",
}

_INTERNAL_STATUS_MAP: dict[str, CustomerStatus] = {
    "pending": "new",
    "received": "new",
    "new": "new",
    "prioritized": "prioritized",
    "hot": "prioritized",
    "processing": "in_progress",
    "running": "in_progress",
    "awaiting_approval": "waiting_for_decision",
    "waiting_customer": "waiting_for_customer",
    "awaiting_info": "waiting_for_customer",
    "needs_customer_info": "waiting_for_customer",
    "draft_ready": "prepared",
    "prepared": "prepared",
    "scheduled": "scheduled",
    "completed": "completed",
    "done": "completed",
    "needs_help": "needs_help",
    "manual_review": "needs_help",
    "failed": "failed",
    "error": "failed",
    "cancelled": "cancelled",
    "rejected": "cancelled",
}

_PRIORITY_RANK: dict[str, int] = {
    "hot": 1,
    "high": 1,
    "warm": 2,
    "medium": 3,
    "normal": 3,
    "low": 4,
    "cold": 5,
}

_PRIORITY_LABELS: dict[str, str] = {
    "hot": "Hög prioritet",
    "high": "Hög prioritet",
    "warm": "Medel prioritet",
    "medium": "Medel prioritet",
    "normal": "Normal prioritet",
    "low": "Låg prioritet",
    "cold": "Låg prioritet",
}


def map_internal_status(
    raw_status: str | None,
    *,
    has_pending_approval: bool = False,
    recommended_status: str | None = None,
) -> CustomerStatus:
    if has_pending_approval:
        return "waiting_for_decision"
    if recommended_status:
        mapped = _INTERNAL_STATUS_MAP.get(recommended_status.strip().lower())
        if mapped:
            return mapped
    key = (raw_status or "").strip().lower()
    return _INTERNAL_STATUS_MAP.get(key, "unknown")


def customer_status_label(status: CustomerStatus) -> str:
    return _STATUS_LABELS.get(status, _STATUS_LABELS["unknown"])


def priority_rank(priority: str | None) -> int:
    if not priority:
        return 50
    return _PRIORITY_RANK.get(priority.strip().lower(), 50)


def priority_label(priority: str | None) -> str | None:
    if not priority:
        return None
    return _PRIORITY_LABELS.get(priority.strip().lower())


def map_job_type_to_work_item_type(job_type: str | None) -> str:
    key = (job_type or "").strip().lower()
    if key == "lead":
        return "lead"
    if key in {"customer_inquiry", "support", "invoice"}:
        return "support"
    return "support"


def map_work_item_type_to_job_types(work_item_type: str) -> list[str] | None:
    key = work_item_type.strip().lower()
    if key == "lead":
        return ["lead"]
    if key == "support":
        return ["customer_inquiry", "support", "invoice"]
    if key == "needs_help":
        return None
    return None
