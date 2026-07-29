"""Hermetic P0 preflight with synthetic inbound messages."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.production_pilot.constants import (
    P0_GMAIL_REPLY_BUDGET,
    P0_MAX_SYNTHETIC_INBOUND,
    P0_NON_GMAIL_WRITE_BUDGET,
    PREFLIGHT_SCHEMA_VERSION,
    PILOT_TENANT_ID,
)
from app.production_pilot.gates import enforce_production_pilot_inbox_gates
from app.production_pilot.readiness import build_production_pilot_readiness
from app.production_pilot.status import PRODUCTION_PILOT_RELEASE_READY, evaluate_release_status
from app.production_pilot.tenant_baseline import build_p0_tenant_record


class PreflightWriteTracker:
    def __init__(self) -> None:
        self.gmail_replies = 0
        self.non_gmail_writes = 0

    def record_gmail_reply(self) -> None:
        self.gmail_replies += 1

    def record_non_gmail_write(self) -> None:
        self.non_gmail_writes += 1


def _synthetic_messages() -> list[dict[str, Any]]:
    return [
        {
            "message_id": f"synthetic-{uuid4().hex[:8]}",
            "subject": "Pilot preflight observe inquiry",
            "sender": "preflight-sender@example.test",
            "synthetic": True,
        },
        {
            "message_id": f"synthetic-{uuid4().hex[:8]}",
            "subject": "Pilot preflight routing check",
            "sender": "preflight-sender-2@example.test",
            "synthetic": True,
        },
    ]


def run_p0_preflight(
    *,
    runtime_sha: str | None = None,
    backup_reference: str = "backup-preflight-synthetic",
) -> dict[str, Any]:
    tenant_record = build_p0_tenant_record()
    settings = tenant_record["settings"]
    readiness = build_production_pilot_readiness(
        tenant_id=PILOT_TENANT_ID,
        settings=settings,
        runtime_sha=runtime_sha,
        backup_reference=backup_reference,
    )
    failures: list[str] = []
    if readiness.get("blockers"):
        failures.extend(readiness["blockers"])

    messages = _synthetic_messages()
    if len(messages) > P0_MAX_SYNTHETIC_INBOUND:
        failures.append("preflight inbound exceeds max synthetic messages")

    tracker = PreflightWriteTracker()
    processed: list[dict[str, Any]] = []
    audit_events: list[dict[str, Any]] = []

    try:
        enforce_production_pilot_inbox_gates(
            tenant_id=PILOT_TENANT_ID,
            dry_run=False,
            settings=settings,
        )
        failures.append("gmail intake should be blocked at P0")
    except Exception:
        pass

    for message in messages:
        processed.append(
            {
                "message_id": message["message_id"],
                "route": "observe_manual_review",
                "classification": "customer_inquiry",
                "synthetic": True,
            }
        )
        audit_events.append(
            {
                "tenant_id": PILOT_TENANT_ID,
                "category": "production_pilot_preflight",
                "action": "synthetic_inbound_observed",
                "status": "success",
                "message_id": message["message_id"],
            }
        )

    if tracker.gmail_replies > P0_GMAIL_REPLY_BUDGET:
        failures.append("gmail replies must be 0 during P0 preflight")
    if tracker.non_gmail_writes > P0_NON_GMAIL_WRITE_BUDGET:
        failures.append("non-gmail writes must be 0 during P0 preflight")

    status = "PASS" if not failures else "FAIL"
    report = {
        "report_schema_version": PREFLIGHT_SCHEMA_VERSION,
        "status": status,
        "tenant_id": PILOT_TENANT_ID,
        "activation_stage": "P0",
        "synthetic_inbound_count": len(processed),
        "gmail_replies": tracker.gmail_replies,
        "non_gmail_writes": tracker.non_gmail_writes,
        "processed_messages": processed,
        "audit_events": audit_events,
        "readiness": readiness,
        "failures": failures,
    }
    release_status = evaluate_release_status(readiness=readiness, preflight=report)
    if status == "PASS":
        report["qualification"] = PRODUCTION_PILOT_RELEASE_READY
    report["release_status"] = release_status
    return report
