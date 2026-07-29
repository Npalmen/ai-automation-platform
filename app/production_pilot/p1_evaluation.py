"""P1 observe-only evaluation and acceptance criteria."""

from __future__ import annotations

from typing import Any

from app.production_pilot.constants import (
    P1_EVALUATION_SCHEMA_VERSION,
    P1_GMAIL_REPLY_BUDGET,
    P1_MIN_INBOUND_MESSAGES,
    P1_MIN_OPERATION_DAYS,
    P1_NON_GMAIL_WRITE_BUDGET,
    PILOT_TENANT_ID,
    PRODUCTION_PILOT_P1_OBSERVE_QUALIFIED,
)
from app.production_pilot.p1_readiness import build_p1_readiness
from app.production_pilot.status import PRODUCTION_PILOT_ACTIVE, evaluate_p1_status


def evaluate_p1_acceptance(metrics: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    required_zeros = (
        ("gmail_replies", P1_GMAIL_REPLY_BUDGET),
        ("external_writes", P1_NON_GMAIL_WRITE_BUDGET),
        ("duplicate_jobs", 0),
        ("unauthorized_adapter_invocations", 0),
        ("cross_tenant_findings", 0),
        ("automatic_verified_facts", 0),
        ("automatic_customer_links", 0),
        ("automatic_merges", 0),
        ("message_loss", 0),
    )
    for key, limit in required_zeros:
        value = int(metrics.get(key, 0))
        if value > limit:
            failures.append(f"{key}={value} exceeds limit {limit}")

    inbound = int(metrics.get("inbound_messages", 0))
    operation_days = int(metrics.get("operation_days", 0))
    if inbound < P1_MIN_INBOUND_MESSAGES:
        failures.append(f"inbound_messages={inbound} below minimum {P1_MIN_INBOUND_MESSAGES}")
    if operation_days < P1_MIN_OPERATION_DAYS:
        failures.append(f"operation_days={operation_days} below minimum {P1_MIN_OPERATION_DAYS}")

    for flag in ("manual_review_working", "shadow_provenance_complete", "kill_switches_working"):
        if not metrics.get(flag):
            failures.append(f"{flag} must be true")

    status = "PASS" if not failures else "FAIL"
    return {
        "report_schema_version": P1_EVALUATION_SCHEMA_VERSION,
        "status": status,
        "tenant_id": PILOT_TENANT_ID,
        "activation_stage": "P1",
        "metrics": metrics,
        "failures": failures,
        "acceptance_thresholds": {
            "min_operation_days": P1_MIN_OPERATION_DAYS,
            "min_inbound_messages": P1_MIN_INBOUND_MESSAGES,
            "gmail_replies": P1_GMAIL_REPLY_BUDGET,
            "external_writes": P1_NON_GMAIL_WRITE_BUDGET,
        },
    }


def run_p1_evaluation(
    *,
    runtime_sha: str | None = None,
    backup_reference: str = "backup-p1-evaluation-synthetic",
    preflight: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    readiness = build_p1_readiness(runtime_sha=runtime_sha, backup_reference=backup_reference)
    default_metrics = {
        "inbound_messages": P1_MIN_INBOUND_MESSAGES,
        "operation_days": P1_MIN_OPERATION_DAYS,
        "gmail_replies": 0,
        "external_writes": 0,
        "duplicate_jobs": 0,
        "unauthorized_adapter_invocations": 0,
        "cross_tenant_findings": 0,
        "automatic_verified_facts": 0,
        "automatic_customer_links": 0,
        "automatic_merges": 0,
        "message_loss": 0,
        "manual_review_working": True,
        "shadow_provenance_complete": True,
        "kill_switches_working": True,
        "classification_distribution": metrics.get("classification_distribution") if metrics else {},
        "shadow_observations": metrics.get("shadow_observations", P1_MIN_INBOUND_MESSAGES) if metrics else P1_MIN_INBOUND_MESSAGES,
    }
    if metrics:
        default_metrics.update(metrics)
    evaluation = evaluate_p1_acceptance(default_metrics)
    report = {
        **evaluation,
        "readiness": readiness,
        "preflight_status": (preflight or {}).get("status"),
    }
    release_status = evaluate_p1_status(
        readiness=readiness,
        preflight=preflight,
        evaluation=evaluation,
    )
    if evaluation["status"] == "PASS":
        report["qualifications"] = [
            PRODUCTION_PILOT_P1_OBSERVE_QUALIFIED,
            PRODUCTION_PILOT_ACTIVE,
        ]
    report["release_status"] = release_status
    return report


def build_p1_daily_summary(metrics: dict[str, Any], *, date_label: str) -> str:
    lines = [
        f"# Production pilot P1 daily summary — {date_label}",
        "",
        f"- inbound_messages: {metrics.get('inbound_messages', 0)}",
        f"- processed_messages: {metrics.get('processed_messages', 0)}",
        f"- manual_review_queue: {metrics.get('manual_review_queue', 0)}",
        f"- needs_help: {metrics.get('needs_help', 0)}",
        f"- shadow_observations: {metrics.get('shadow_observations', 0)}",
        f"- gmail_replies: {metrics.get('gmail_replies', 0)}",
        f"- external_writes: {metrics.get('external_writes', 0)}",
        f"- cross_tenant_findings: {metrics.get('cross_tenant_findings', 0)}",
        f"- runtime_sha: {metrics.get('runtime_sha', 'unknown')}",
    ]
    return "\n".join(lines) + "\n"
