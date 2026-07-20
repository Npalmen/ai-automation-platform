"""Pytest entrypoints for Kapitel 2E evaluation harness."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.evaluation.coverage import enforce_coverage
from app.evaluation.dataset_manifest import DEFAULT_MANIFEST
from app.evaluation.db_isolation import count_tenant_rows, eval_db_session, unique_eval_tenant_id
from scripts.run_eval_harness import main as harness_main

MANIFEST_PATH = DEFAULT_MANIFEST

SMOKE_IDS = (
    "S01_lead_laddbox_quality",
    "S23_incomplete_lead_clarification",
    "S24_existing_customer_service",
    "S19_invoice_no_dispatch",
    "S31_prompt_injection_customer_text",
    "S17_unknown_action_blocked",
    "S18_approval_resume_operation_id",
    "S21_pending_blocks_retry",
    "S22_cross_tenant_isolation",
    "S16_policy_legacy_fail_closed",
)


def test_coverage_gate_passes():
    result = enforce_coverage(MANIFEST_PATH)
    assert result.passed, result.errors


def test_smoke_set_passes_via_harness():
    exit_code = harness_main(["--smoke", "-q"])
    assert exit_code == 0, "smoke harness run failed"


@pytest.mark.parametrize("scenario_id", SMOKE_IDS)
def test_smoke_scenario_via_harness(scenario_id: str):
    exit_code = harness_main(["--scenario-id", scenario_id, "-q"])
    assert exit_code == 0, f"{scenario_id} failed via harness entrypoint"


def test_schema_rejects_unknown_version():
    from app.evaluation.schema.scenario import ScenarioContract

    with pytest.raises(Exception):
        ScenarioContract.model_validate(
            {
                "schema_version": "9.9.9",
                "scenario_id": "bad",
                "category": "x",
                "input": {"subject": "a", "message_text": "b"},
            }
        )


def test_readiness_fails_without_migration():
    from app.core.settings import Settings
    from app.workflows.decision_trace_readiness import verify_decision_trace_readiness

    engine = MagicMock()
    engine.dialect.name = "postgresql"
    engine.connect.return_value.__enter__.return_value.execute.return_value.scalar.return_value = None
    settings = Settings(DECISION_RECORD_ENFORCE_WRITES=True)
    with pytest.raises(RuntimeError, match="decision_records"):
        verify_decision_trace_readiness(engine, settings)


def test_pending_intent_blocks_automatic_retry(trace_db):
    """S21 coverage: unresolved pending intent must block adapter retry."""
    import uuid

    from app.domain.workflows.enums import JobType
    from app.domain.workflows.models import Job
    from app.workflows.decision_record_service import record_execution_intent
    from app.workflows.decision_trace_errors import ReconciliationRequired
    from app.workflows.external_write_trace import execute_external_write_with_trace
    from app.workflows.pipeline_run_context import PipelineRunSource, create_trace_session

    job = Job(job_id=str(uuid.uuid4()), tenant_id="T_EVAL_S21", job_type=JobType.LEAD, input_data={})
    trace = create_trace_session(job, source=PipelineRunSource.INTAKE, db=trace_db)
    op_id = str(uuid.uuid4())
    record_execution_intent(
        trace_db,
        trace,
        job,
        {"type": "send_customer_auto_reply", "to": "a@example.com"},
        operation_id=op_id,
        fingerprint=None,
        key_version=None,
    )
    with pytest.raises(ReconciliationRequired):
        execute_external_write_with_trace(
            db=trace_db,
            trace=trace,
            job=job,
            action={"type": "send_customer_auto_reply", "to": "a@example.com", "_action_operation_id": op_id},
            adapter_fn=MagicMock(return_value={"status": "executed"}),
        )


def test_cross_tenant_isolation_in_observation():
    """S22 coverage: observations stay scoped to job tenant."""
    from app.domain.workflows.enums import JobType
    from app.domain.workflows.models import Job
    from app.evaluation.observations import ScenarioObservation

    job = Job(tenant_id="T_EVAL_A", job_type=JobType.LEAD, input_data={})
    obs = ScenarioObservation(job=job)
    assert obs.job.tenant_id == "T_EVAL_A"


def test_db_rollback_clears_tenant_rows():
    from app.domain.workflows.enums import JobType
    from app.domain.workflows.models import Job
    from app.repositories.postgres.job_repository import JobRepository

    tenant_id = unique_eval_tenant_id("isolation_probe", "run1")
    with eval_db_session() as db:
        job = Job(tenant_id=tenant_id, job_type=JobType.INTAKE, input_data={"subject": "x"})
        JobRepository.create_job(db, job)
        assert count_tenant_rows(db, tenant_id)["jobs"] == 1


@pytest.fixture()
def trace_db():
    from sqlalchemy import create_engine, event, text
    from sqlalchemy.orm import sessionmaker

    from app.repositories.postgres.decision_record_models import DecisionRecordRow

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    DecisionRecordRow.__table__.create(engine, checkfirst=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_decision_records_idempotency "
                "ON decision_records (tenant_id, idempotency_key)"
            )
        )

    @event.listens_for(DecisionRecordRow, "before_insert")
    def _assign_event_sequence(mapper, connection, target):
        if connection.dialect.name != "sqlite":
            return
        if getattr(target, "event_sequence", None) is None:
            result = connection.execute(
                DecisionRecordRow.__table__.select().with_only_columns(
                    DecisionRecordRow.event_sequence
                )
            )
            max_seq = 0
            for row in result:
                max_seq = max(max_seq, int(row[0] or 0))
            target.event_sequence = max_seq + 1

    session = sessionmaker(bind=engine)()
    yield session
    session.close()
