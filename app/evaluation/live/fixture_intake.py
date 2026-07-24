"""Fixture-input intake for live LLM eval (no Gmail)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.evaluation.live.constants import (
    RUN_STATUS_ACTIVE,
    TELEMETRY_APP_INTAKE_FAILED,
    TELEMETRY_APP_INTAKE_STARTED,
    TELEMETRY_APP_INTAKE_SUCCEEDED,
)
from app.evaluation.live.context import live_eval_context
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.registry import (
    create_and_claim_fixture_root_job,
    trusted_snapshot_from_row,
)
from app.evaluation.live.safety import validate_fixture_input_run_for_intake
from app.evaluation.live.scenario_input import (
    build_fixture_job_input_data,
    load_locked_scenario_input,
)
from app.evaluation.live.telemetry import build_operation_key, record_live_eval_external_event
from app.repositories.postgres.job_repository import JobRepository
from app.repositories.postgres.live_eval_repository import LiveEvalRunRepository
from app.workflows.pipeline_runner import run_pipeline


def process_fixture_input_for_run(
    db: Session,
    *,
    evaluation_run_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    """Load locked scenario server-side, create root job, and run production pipeline."""
    row = LiveEvalRunRepository.get_run(db, evaluation_run_id, tenant_id=tenant_id)
    if row is None:
        raise LiveEvalSafetyError("run not found")

    validate_fixture_input_run_for_intake(row, tenant_id=tenant_id)

    if row.status == RUN_STATUS_ACTIVE and row.root_job_id:
        existing = JobRepository.get_job_by_id(db, tenant_id, row.root_job_id)
        return {
            "status": "skipped",
            "reason": "duplicate",
            "job_id": row.root_job_id,
            "job_status": (
                existing.status.value
                if existing is not None and hasattr(existing.status, "value")
                else None
            ),
            "pipeline_run_id": _extract_pipeline_run_id(existing) if existing else None,
        }

    snapshot = trusted_snapshot_from_row(row)
    _record_fixture_intake_telemetry(
        db,
        snapshot=snapshot,
        outcome="started",
        job_id=None,
    )

    try:
        scenario = load_locked_scenario_input(
            row.scenario_id,
            evaluation_run_id=evaluation_run_id,
        )
    except LiveEvalSafetyError as exc:
        _record_fixture_intake_telemetry(
            db,
            snapshot=snapshot,
            outcome="failed",
            job_id=None,
        )
        raise

    input_data = build_fixture_job_input_data(scenario)
    input_data["live_eval"] = snapshot.model_dump(mode="json")

    job = Job(
        tenant_id=tenant_id,
        job_type=JobType.LEAD,
        input_data=input_data,
    )

    try:
        with live_eval_context(snapshot, db=db):
            saved_job = create_and_claim_fixture_root_job(
                db,
                job=job,
                evaluation_run_id=evaluation_run_id,
                tenant_id=tenant_id,
            )
            processed_job = run_pipeline(saved_job, db)
    except Exception:
        _record_fixture_intake_telemetry(
            db,
            snapshot=snapshot,
            outcome="failed",
            job_id=None,
        )
        raise

    pipeline_run_id = _extract_pipeline_run_id(processed_job)
    _record_fixture_intake_telemetry(
        db,
        snapshot=snapshot,
        outcome="succeeded",
        job_id=processed_job.job_id,
        pipeline_run_id=pipeline_run_id,
    )

    return {
        "status": "created",
        "job_id": processed_job.job_id,
        "job_status": (
            processed_job.status.value
            if hasattr(processed_job.status, "value")
            else str(processed_job.status)
        ),
        "pipeline_run_id": pipeline_run_id,
        "inferred_type": "lead",
    }


def _extract_pipeline_run_id(job) -> str | None:
    if job is None:
        return None
    from app.workflows.processors.ai_processor_utils import get_latest_processor_payload

    for processor in ("policy_processor", "classification_processor"):
        payload = get_latest_processor_payload(job, processor) or {}
        if payload.get("pipeline_run_id"):
            return str(payload["pipeline_run_id"])
    records = (job.result or {}).get("processor_history") or []
    if hasattr(job, "processor_history"):
        records = job.processor_history or records
    for entry in records:
        payload = (entry or {}).get("result", {}).get("payload") or (entry or {}).get("payload") or {}
        if payload.get("pipeline_run_id"):
            return str(payload["pipeline_run_id"])
    return None


def _record_fixture_intake_telemetry(
    db: Session,
    *,
    snapshot,
    outcome: str,
    job_id: str | None,
    pipeline_run_id: str | None = None,
) -> None:
    category = {
        "started": TELEMETRY_APP_INTAKE_STARTED,
        "succeeded": TELEMETRY_APP_INTAKE_SUCCEEDED,
        "failed": TELEMETRY_APP_INTAKE_FAILED,
    }.get(outcome)
    if category is None:
        return
    event_outcome = "succeeded" if outcome == "succeeded" else (
        "failed" if outcome == "failed" else "blocked"
    )
    operation = "fixture_input"
    operation_key = build_operation_key(
        evaluation_run_id=snapshot.evaluation_run_id,
        category=category,
        operation=operation,
    )
    record_live_eval_external_event(
        db,
        operation_key=operation_key,
        outcome=event_outcome,
        category=category,
        operation=operation,
        integration_type="fixture_input",
        job_id=job_id,
        pipeline_run_id=pipeline_run_id,
        snapshot=snapshot,
        metadata={"transport_mode": "fixture_input"},
    )
    if outcome in ("started", "succeeded", "failed"):
        db.commit()
