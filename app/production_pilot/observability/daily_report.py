"""Build P1 daily operational report from live DB records."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.core.canonical_commit import resolve_canonical_commit
from app.production_pilot.config_snapshot import compute_snapshot_hash
from app.production_pilot.constants import PILOT_TENANT_ID
from app.production_pilot.observability.constants import P1_DAILY_REPORT_SCHEMA_VERSION, P1_QUERY_SCHEMA_VERSION
from app.production_pilot.observability.metrics_queries import collect_day_metrics
from app.production_pilot.observability.repository import ProductionPilotReviewRepository
from app.production_pilot.p1_activation import build_p1_tenant_record
from app.production_pilot.stages import current_activation_stage
from app.repositories.postgres.tenant_config_models import TenantConfigRecord


def _operator_review_counts(reviews: list[Any]) -> dict[str, int]:
    classification = {"correct": 0, "incorrect": 0, "ambiguous": 0}
    extraction = {"acceptable": 0, "corrected": 0, "failed": 0}
    routing = {"correct": 0, "incorrect": 0}
    for row in reviews:
        classification[row.classification_verdict] = classification.get(row.classification_verdict, 0) + 1
        extraction[row.extraction_verdict] = extraction.get(row.extraction_verdict, 0) + 1
        routing[row.routing_verdict] = routing.get(row.routing_verdict, 0) + 1
    return {
        "operator_classification": classification,
        "operator_extraction": extraction,
        "operator_routing": routing,
    }


def build_p1_daily_report(
    db: Session,
    *,
    tenant_id: str,
    day: date,
    runtime_sha: str | None = None,
) -> dict[str, Any]:
    if tenant_id != PILOT_TENANT_ID:
        raise ValueError("daily report is pilot-tenant scoped only")
    metrics = collect_day_metrics(db, tenant_id=tenant_id, day=day)
    start, end = day.isoformat(), day.isoformat()
    reviews = ProductionPilotReviewRepository.list_for_tenant(
        db,
        tenant_id=tenant_id,
        start=None,
        end=None,
    )
    day_reviews = [row for row in reviews if row.reviewed_at.date() == day]
    tenant_row = db.query(TenantConfigRecord).filter(TenantConfigRecord.tenant_id == tenant_id).first()
    settings = (tenant_row.settings if tenant_row else None) or build_p1_tenant_record()["settings"]
    resolved_sha = runtime_sha or resolve_canonical_commit()
    return {
        "report_schema_version": P1_DAILY_REPORT_SCHEMA_VERSION,
        "query_schema_version": P1_QUERY_SCHEMA_VERSION,
        "tenant_id": tenant_id,
        "date": day.isoformat(),
        "date_range": {"start": start, "end": end},
        "activation_stage": current_activation_stage(settings),
        "runtime": {
            "runtime_sha": resolved_sha,
            "config_hash": compute_snapshot_hash(settings),
            "scheduler_state": (settings.get("scheduler") or {}).get("run_mode"),
            "feature_flags": {},
            "kill_switch_state": "armed",
        },
        "intake": metrics["intake"],
        "classification": {
            **metrics["classification"],
            **_operator_review_counts(day_reviews),
        },
        "queues": metrics["queues"],
        "shadow": metrics["shadow"],
        "safety": metrics["safety"],
        "redaction_status": "clean",
    }


def render_p1_daily_report_markdown(report: dict[str, Any]) -> str:
    intake = report["intake"]
    safety = report["safety"]
    lines = [
        f"# Production pilot P1 daily report — {report['date']}",
        "",
        f"- tenant: `{report['tenant_id']}`",
        f"- activation_stage: `{report['activation_stage']}`",
        f"- runtime_sha: `{report['runtime'].get('runtime_sha')}`",
        f"- config_hash: `{report['runtime'].get('config_hash', '')[:16]}…`",
        "",
        "## Intake",
        f"- provider_inbound_count: {intake.get('provider_inbound_count', 0)}",
        f"- correlated_intake_count: {intake.get('correlated_intake_count', 0)}",
        f"- processed_count: {intake.get('processed_count', 0)}",
        f"- failed_count: {intake.get('failed_count', 0)}",
        f"- pending_count: {intake.get('pending_count', 0)}",
        f"- duplicate_suppressions: {intake.get('duplicate_suppressions', 0)}",
        f"- correlation_gaps: {intake.get('correlation_gaps', 0)}",
        "",
        "## Safety",
        f"- gmail_replies: {safety.get('gmail_replies', 0)}",
        f"- gmail_adapter_invocations: {safety.get('gmail_adapter_invocations', 0)}",
        f"- external_writes: {sum((safety.get('external_writes_by_integration') or {}).values())}",
        f"- cross_tenant_findings: {safety.get('cross_tenant_findings', 0)}",
        "",
        "## Shadow",
        f"- observations_created: {report['shadow'].get('observations_created', 0)}",
        f"- match_proposals: {report['shadow'].get('match_proposals', 0)}",
        f"- promotions: {report['shadow'].get('promotions', 0)}",
    ]
    return "\n".join(lines) + "\n"
