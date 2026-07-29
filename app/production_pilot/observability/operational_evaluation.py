"""Evaluate P1 operational evidence for P2 readiness."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.production_pilot.constants import (
    P1_GMAIL_REPLY_BUDGET,
    P1_MIN_INBOUND_MESSAGES,
    P1_MIN_OPERATION_DAYS,
    P1_NON_GMAIL_WRITE_BUDGET,
    PILOT_TENANT_ID,
)
from app.production_pilot.observability.constants import (
    GO_FOR_P2_APPROVAL_GMAIL,
    NO_GO_FOR_P2_APPROVAL_GMAIL,
    P1_OPERATIONAL_EVAL_SCHEMA_VERSION,
)
from app.production_pilot.observability.metrics_queries import (
    collect_day_metrics,
    list_real_message_refs,
)
from app.production_pilot.observability.repository import ProductionPilotReviewRepository


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    end = datetime.combine(day, time.max, tzinfo=timezone.utc)
    return start, end


def _iter_days(start: date, end: date) -> list[date]:
    days: list[date] = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


def evaluate_p1_operational_evidence(
    db: Session,
    *,
    tenant_id: str,
    start_date: date,
    end_date: date,
    runtime_sha: str | None,
    expected_runtime_sha: str | None = None,
    release_manifest_version: str | None = None,
    config_hash: str | None = None,
    open_critical_incidents: int = 0,
    kill_switches_verified: bool = True,
    config_drift_explained: bool = True,
) -> dict[str, Any]:
    failures: list[str] = []
    days = _iter_days(start_date, end_date)
    operation_days_with_traffic = 0
    total_real_messages = 0
    total_correlation_gaps = 0
    total_gmail_replies = 0
    total_external_writes = 0
    total_cross_tenant = 0
    total_auto_facts = 0
    total_auto_links = 0
    total_auto_merges = 0

    for day in days:
        metrics = collect_day_metrics(db, tenant_id=tenant_id, day=day)
        intake = metrics["intake"]
        safety = metrics["safety"]
        shadow = metrics["shadow"]
        inbound = int(intake.get("provider_inbound_count") or 0)
        if inbound > 0:
            operation_days_with_traffic += 1
        total_real_messages += inbound
        total_correlation_gaps += int(intake.get("correlation_gaps") or 0)
        total_gmail_replies += int(safety.get("gmail_replies") or 0)
        total_external_writes += sum((safety.get("external_writes_by_integration") or {}).values())
        total_cross_tenant += int(safety.get("cross_tenant_findings") or 0)
        total_auto_facts += int(shadow.get("automatic_verified_facts") or 0)
        total_auto_links += int(shadow.get("automatic_customer_links") or 0)
        total_auto_merges += int(shadow.get("automatic_merges") or 0)

    refs = list_real_message_refs(db, tenant_id=tenant_id, start=start_date, end=end_date)
    ref_hashes = {ref["provider_message_ref_hash"] for ref in refs}
    all_reviews = ProductionPilotReviewRepository.list_for_tenant(db, tenant_id=tenant_id)
    reviewed_hashes = {
        row.provider_message_ref_hash
        for row in all_reviews
        if row.provider_message_ref_hash in ref_hashes
    }
    missing_reviews = [ref for ref in refs if ref["provider_message_ref_hash"] not in reviewed_hashes]

    if operation_days_with_traffic < P1_MIN_OPERATION_DAYS:
        failures.append(f"operation_days={operation_days_with_traffic} below minimum {P1_MIN_OPERATION_DAYS}")
    if total_real_messages < P1_MIN_INBOUND_MESSAGES:
        failures.append(f"real_messages={total_real_messages} below minimum {P1_MIN_INBOUND_MESSAGES}")
    if total_correlation_gaps > 0:
        failures.append(f"correlation_gaps={total_correlation_gaps}")
    if missing_reviews:
        failures.append(f"unreviewed_messages={len(missing_reviews)}")
    if total_gmail_replies > P1_GMAIL_REPLY_BUDGET:
        failures.append(f"gmail_replies={total_gmail_replies}")
    if total_external_writes > P1_NON_GMAIL_WRITE_BUDGET:
        failures.append(f"external_writes={total_external_writes}")
    if total_cross_tenant > 0:
        failures.append(f"cross_tenant_findings={total_cross_tenant}")
    if total_auto_facts > 0:
        failures.append(f"automatic_verified_facts={total_auto_facts}")
    if total_auto_links > 0:
        failures.append(f"automatic_customer_links={total_auto_links}")
    if total_auto_merges > 0:
        failures.append(f"automatic_merges={total_auto_merges}")
    if expected_runtime_sha and runtime_sha and not runtime_sha.startswith(expected_runtime_sha[:7]):
        if expected_runtime_sha not in {runtime_sha, runtime_sha[:7]}:
            failures.append(f"runtime_sha_mismatch expected={expected_runtime_sha} actual={runtime_sha}")
    if open_critical_incidents > 0:
        failures.append(f"open_critical_incidents={open_critical_incidents}")
    if not kill_switches_verified:
        failures.append("kill_switches_not_verified")
    if not config_drift_explained:
        failures.append("config_drift_unexplained")

    operational_pass = not failures
    p2_result = GO_FOR_P2_APPROVAL_GMAIL if operational_pass else NO_GO_FOR_P2_APPROVAL_GMAIL
    return {
        "report_schema_version": P1_OPERATIONAL_EVAL_SCHEMA_VERSION,
        "tenant_id": tenant_id,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "operation_days_with_traffic": operation_days_with_traffic,
        "real_message_count": total_real_messages,
        "reviewed_message_count": len(reviewed_hashes),
        "correlation_gaps": total_correlation_gaps,
        "gmail_replies": total_gmail_replies,
        "external_writes": total_external_writes,
        "cross_tenant_findings": total_cross_tenant,
        "runtime_sha": runtime_sha,
        "expected_runtime_sha": expected_runtime_sha,
        "release_manifest_version": release_manifest_version,
        "config_hash": config_hash,
        "operational_pass": operational_pass,
        "p2_readiness": p2_result,
        "failures": failures,
    }


def render_operational_result_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Production pilot P1 operational result",
        "",
        f"- period: {report['start_date']} → {report['end_date']}",
        f"- operation_days_with_traffic: {report['operation_days_with_traffic']}",
        f"- real_message_count: {report['real_message_count']}",
        f"- reviewed_message_count: {report['reviewed_message_count']}",
        f"- operational_pass: **{report['operational_pass']}**",
        f"- p2_readiness: **{report['p2_readiness']}**",
    ]
    if report.get("failures"):
        lines.append("")
        lines.append("## Failures")
        for failure in report["failures"]:
            lines.append(f"- {failure}")
    return "\n".join(lines) + "\n"
