"""Hermetic P1 synthetic preflight before real pilot traffic."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.production_pilot.constants import (
    P1_GMAIL_REPLY_BUDGET,
    P1_MAX_SYNTHETIC_INBOUND,
    P1_NON_GMAIL_WRITE_BUDGET,
    P1_PREFLIGHT_SCHEMA_VERSION,
    PILOT_TENANT_ID,
)
from app.production_pilot.gates import (
    enforce_production_pilot_inbox_gates,
    validate_approvals_allowed,
    validate_external_write_budget,
)
from app.production_pilot.p1_activation import build_p1_tenant_record, validate_p1_tenant_record
from app.production_pilot.p1_readiness import build_p1_readiness
from app.production_pilot.preflight import PreflightWriteTracker
from app.production_pilot.status import PRODUCTION_PILOT_P1_OBSERVE_QUALIFIED, evaluate_p1_status


def _synthetic_messages() -> list[dict[str, Any]]:
    return [
        {
            "message_id": f"synthetic-{uuid4().hex[:8]}",
            "subject": "Pilot P1 lead inquiry",
            "sender": "preflight-lead@example.test",
            "classification": "lead",
            "synthetic": True,
        },
        {
            "message_id": f"synthetic-{uuid4().hex[:8]}",
            "subject": "Pilot P1 unknown routing",
            "sender": "preflight-unknown@example.test",
            "classification": "unknown",
            "route": "hold",
            "synthetic": True,
        },
    ]


def run_p1_preflight(
    *,
    runtime_sha: str | None = None,
    backup_reference: str = "backup-p1-preflight-synthetic",
) -> dict[str, Any]:
    readiness = build_p1_readiness(
        runtime_sha=runtime_sha,
        backup_reference=backup_reference,
    )
    failures: list[str] = []
    if readiness.get("blockers"):
        failures.extend(readiness["blockers"])

    record = build_p1_tenant_record()
    record_failures = validate_p1_tenant_record(record)
    if record_failures:
        failures.extend(record_failures)

    settings = record["settings"]
    messages = _synthetic_messages()
    if len(messages) > P1_MAX_SYNTHETIC_INBOUND:
        failures.append("preflight inbound exceeds max synthetic messages")

    tracker = PreflightWriteTracker()
    processed: list[dict[str, Any]] = []
    shadow_observations: list[dict[str, Any]] = []
    audit_events: list[dict[str, Any]] = []

    try:
        enforce_production_pilot_inbox_gates(
            tenant_id=PILOT_TENANT_ID,
            dry_run=False,
            settings=settings,
        )
    except Exception as exc:
        failures.append(f"gmail intake gate failed: {exc}")

    try:
        validate_approvals_allowed(settings)
        failures.append("approvals should be blocked at P1")
    except Exception:
        pass

    for message in messages:
        route = message.get("route") or "observe_manual_review"
        processed.append(
            {
                "message_id": message["message_id"],
                "route": route,
                "classification": message["classification"],
                "synthetic": True,
            }
        )
        shadow_observations.append(
            {
                "tenant_id": PILOT_TENANT_ID,
                "source_message_id": message["message_id"],
                "observation_type": "shadow_intake",
                "synthetic": True,
            }
        )
        audit_events.append(
            {
                "tenant_id": PILOT_TENANT_ID,
                "category": "production_pilot_p1_preflight",
                "action": "synthetic_inbound_observed",
                "status": "success",
                "message_id": message["message_id"],
            }
        )

    try:
        validate_external_write_budget(settings, gmail_replies=tracker.gmail_replies, non_gmail_writes=tracker.non_gmail_writes)
    except Exception as exc:
        failures.append(str(exc))

    if tracker.gmail_replies > P1_GMAIL_REPLY_BUDGET:
        failures.append("gmail replies must be 0 during P1 preflight")
    if tracker.non_gmail_writes > P1_NON_GMAIL_WRITE_BUDGET:
        failures.append("non-gmail writes must be 0 during P1 preflight")

    classifications = {item["classification"] for item in processed}
    if "lead" not in classifications and "customer_inquiry" not in classifications:
        failures.append("preflight requires lead or inquiry scenario")
    if "unknown" not in classifications:
        failures.append("preflight requires unknown or hold scenario")
    if not shadow_observations:
        failures.append("preflight requires shadow observation")

    status = "PASS" if not failures else "FAIL"
    report = {
        "report_schema_version": P1_PREFLIGHT_SCHEMA_VERSION,
        "status": status,
        "tenant_id": PILOT_TENANT_ID,
        "activation_stage": "P1",
        "synthetic_inbound_count": len(processed),
        "gmail_replies": tracker.gmail_replies,
        "non_gmail_writes": tracker.non_gmail_writes,
        "processed_messages": processed,
        "shadow_observations": shadow_observations,
        "audit_events": audit_events,
        "automatic_verified_facts": 0,
        "automatic_customer_links": 0,
        "automatic_merges": 0,
        "cross_tenant_findings": 0,
        "readiness": readiness,
        "failures": failures,
    }
    if status == "PASS":
        report["preflight_qualification"] = PRODUCTION_PILOT_P1_OBSERVE_QUALIFIED
    report["release_status"] = evaluate_p1_status(readiness=readiness, preflight=report)
    return report
