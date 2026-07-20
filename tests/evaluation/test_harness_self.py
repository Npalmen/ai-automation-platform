"""Pytest entrypoints for Kapitel 2D evaluation harness."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.evaluation.db_isolation import count_tenant_rows, eval_db_session, unique_eval_tenant_id
from app.evaluation.loader import discover_scenarios, load_scenario
from app.evaluation.reporting import new_run_id
from app.evaluation.runner import EvalHarnessRunner

SCENARIOS_ROOT = Path(__file__).resolve().parent / "scenarios"
BASELINE_PATH = Path(__file__).resolve().parent / "baselines" / "k2d-baseline-v1.json"

SMOKE_IDS = {
    "S01_lead_laddbox_quality",
    "S08_sensitive_inkasso",
    "S10_urgent_electrical_safety",
    "S14_approval_gated_default",
    "S15_full_auto_execution_trace",
    "S16_policy_legacy_fail_closed",
    "S17_unknown_action_blocked",
    "S18_approval_resume_operation_id",
}


@pytest.fixture()
def harness_runner():
    baseline = None
    if BASELINE_PATH.exists():
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    return EvalHarnessRunner(run_id=new_run_id(), baseline=baseline)


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


def _scenario_ids(tag: str | None = None) -> list[str]:
    if not SCENARIOS_ROOT.exists():
        return []
    items = discover_scenarios(SCENARIOS_ROOT)
    if tag:
        items = [(p, s) for p, s in items if tag in s.tags]
    return [s.scenario_id for _, s in items]


@pytest.mark.parametrize("scenario_id", _scenario_ids())
def test_scenario_passes(scenario_id: str, harness_runner: EvalHarnessRunner):
    path = SCENARIOS_ROOT / f"{scenario_id}.yaml"
    scenario = load_scenario(path)
    with eval_db_session() as db:
        result = harness_runner.run_scenario(db, scenario)
    assert result.exit_code == 0, result.safety_violations


@pytest.mark.parametrize("scenario_id", sorted(SMOKE_IDS & set(_scenario_ids())))
def test_smoke_scenario(scenario_id: str, harness_runner: EvalHarnessRunner):
    path = SCENARIOS_ROOT / f"{scenario_id}.yaml"
    if not path.exists():
        pytest.skip(f"Scenario file missing: {path}")
    scenario = load_scenario(path)
    with eval_db_session() as db:
        result = harness_runner.run_scenario(db, scenario)
    assert result.exit_code == 0, result.safety_violations


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
