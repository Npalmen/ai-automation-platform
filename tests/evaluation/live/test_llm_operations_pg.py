"""PostgreSQL contract tests for permanent live LLM operation idempotency."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.evaluation.live.constants import (
    EVENT_OUTCOME_FAILED,
    EVENT_OUTCOME_SUCCEEDED,
    LLM_OPERATION_IN_PROGRESS,
    LLM_OPERATION_OUTCOME_UNKNOWN,
    S01_LLM_MAX_CALLS,
)
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.llm_operations import (
    build_llm_operation_key,
    count_llm_operations_for_run,
    count_provider_attempts,
    count_succeeded_llm_operations,
    prompt_ordinal,
    record_live_llm_operation_result,
    reserve_live_llm_operation,
)
from app.evaluation.live.schemas import TrustedLiveEvalSnapshot
from app.repositories.postgres.migration_runner import verify_ci_postgres_schema_provisioned

pytestmark = pytest.mark.integration_db


def _postgres_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url or "sqlite" in url:
        pytest.skip("DATABASE_URL postgres required for integration_db live-eval tests")
    return url


@pytest.fixture(scope="module")
def pg_engine():
    pytest.importorskip("psycopg2")
    engine = create_engine(_postgres_url())
    verify_ci_postgres_schema_provisioned(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def pg_session(pg_engine):
    Session = sessionmaker(bind=pg_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


def _insert_registered_run(
    pg_session,
    run_id: str,
    *,
    llm_max_calls: int = S01_LLM_MAX_CALLS,
) -> None:
    now = datetime.now(timezone.utc)
    pg_session.execute(
        text(
            """
            INSERT INTO live_eval_runs (
                evaluation_run_id, tenant_id, scenario_id, attempt_id,
                transport_mode, ai_mode, fixture_bundle_id,
                expected_sender, expected_recipient,
                llm_provider, llm_requested_model, llm_max_calls,
                status, created_by, expires_at, config_hash
            ) VALUES (
                :run_id, 'TENANT_LIVE_EVAL', 'S01_lead_laddbox_quality', 1,
                'fixture_input', 'live_llm', NULL,
                NULL, NULL,
                'openai', 'fake-model', :llm_max_calls,
                'registered', 'pg-test', :expires_at, 'cfg-llm'
            )
            ON CONFLICT (evaluation_run_id) DO NOTHING
            """
        ),
        {
            "run_id": run_id,
            "expires_at": now.replace(year=now.year + 1),
            "llm_max_calls": llm_max_calls,
        },
    )
    pg_session.flush()


def _snapshot(
    run_id: str,
    *,
    llm_max_calls: int = S01_LLM_MAX_CALLS,
    llm_requested_model: str = "fake-model",
    llm_provider: str = "openai",
) -> TrustedLiveEvalSnapshot:
    return TrustedLiveEvalSnapshot(
        evaluation_run_id=run_id,
        tenant_id="TENANT_LIVE_EVAL",
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        transport_mode="fixture_input",
        ai_mode="live_llm",
        fixture_bundle_id=None,
        expected_sender=None,
        expected_recipient=None,
        llm_provider=llm_provider,
        llm_requested_model=llm_requested_model,
        llm_max_calls=llm_max_calls,
        config_hash="cfg-llm",
        trusted=True,
    )


def _complete_prompt(pg_session, *, snap: TrustedLiveEvalSnapshot, prompt_name: str) -> str:
    op_key = reserve_live_llm_operation(
        pg_session,
        snapshot=snap,
        prompt_name=prompt_name,
        requested_model=snap.llm_requested_model,
    )
    record_live_llm_operation_result(
        pg_session,
        operation_key=op_key,
        snapshot=snap,
        prompt_name=prompt_name,
        outcome=EVENT_OUTCOME_SUCCEEDED,
        requested_model=snap.llm_requested_model or "fake-model",
        returned_model=snap.llm_requested_model or "fake-model",
        usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        validated_output={"ok": True},
    )
    return op_key


def _operation_count(pg_session, run_id: str) -> int:
    return pg_session.execute(
        text("SELECT COUNT(*) FROM live_eval_llm_operations WHERE evaluation_run_id = :run_id"),
        {"run_id": run_id},
    ).scalar_one()


def test_concurrent_reservation_creates_single_permanent_row(pg_engine):
    run_id = str(uuid4())
    Session = sessionmaker(bind=pg_engine)
    session_a = Session()
    session_b = Session()
    try:
        _insert_registered_run(session_a, run_id)
        session_a.commit()
        snap = _snapshot(run_id)

        key_a = reserve_live_llm_operation(
            session_a,
            snapshot=snap,
            prompt_name="classification_v1",
            requested_model="fake-model",
        )
        assert key_a

        with pytest.raises(LiveEvalSafetyError, match="in progress|concurrent|retry"):
            reserve_live_llm_operation(
                session_b,
                snapshot=snap,
                prompt_name="classification_v1",
                requested_model="fake-model",
            )

        assert _operation_count(session_a, run_id) == 1
    finally:
        session_a.rollback()
        session_b.rollback()
        session_a.close()
        session_b.close()


def test_succeeded_operation_cannot_be_reserved_again(pg_session):
    run_id = str(uuid4())
    _insert_registered_run(pg_session, run_id)
    snap = _snapshot(run_id)
    _complete_prompt(pg_session, snap=snap, prompt_name="classification_v1")

    with pytest.raises(LiveEvalSafetyError, match="retry blocked"):
        reserve_live_llm_operation(
            pg_session,
            snapshot=snap,
            prompt_name="classification_v1",
            requested_model="fake-model",
        )
    assert _operation_count(pg_session, run_id) == 1


def test_failed_operation_cannot_be_reserved_again(pg_session):
    run_id = str(uuid4())
    _insert_registered_run(pg_session, run_id)
    snap = _snapshot(run_id)
    op_key = reserve_live_llm_operation(
        pg_session,
        snapshot=snap,
        prompt_name="classification_v1",
        requested_model="fake-model",
    )
    record_live_llm_operation_result(
        pg_session,
        operation_key=op_key,
        snapshot=snap,
        prompt_name="classification_v1",
        outcome=EVENT_OUTCOME_FAILED,
        requested_model="fake-model",
        failure_reason="authentication",
    )

    with pytest.raises(LiveEvalSafetyError, match="retry blocked"):
        reserve_live_llm_operation(
            pg_session,
            snapshot=snap,
            prompt_name="classification_v1",
            requested_model="fake-model",
        )


def test_outcome_unknown_operation_cannot_be_reserved_again(pg_session):
    run_id = str(uuid4())
    _insert_registered_run(pg_session, run_id)
    snap = _snapshot(run_id)
    op_key = reserve_live_llm_operation(
        pg_session,
        snapshot=snap,
        prompt_name="classification_v1",
        requested_model="fake-model",
    )
    record_live_llm_operation_result(
        pg_session,
        operation_key=op_key,
        snapshot=snap,
        prompt_name="classification_v1",
        outcome=LLM_OPERATION_OUTCOME_UNKNOWN,
        requested_model="fake-model",
        failure_reason="timeout",
    )

    with pytest.raises(LiveEvalSafetyError, match="retry blocked|outcome_unknown"):
        reserve_live_llm_operation(
            pg_session,
            snapshot=snap,
            prompt_name="classification_v1",
            requested_model="fake-model",
        )


def test_unknown_prompt_blocked(pg_session):
    run_id = str(uuid4())
    _insert_registered_run(pg_session, run_id)
    snap = _snapshot(run_id)

    with pytest.raises(LiveEvalSafetyError, match="not in S01 LLM order"):
        reserve_live_llm_operation(
            pg_session,
            snapshot=snap,
            prompt_name="unknown_prompt_v9",
            requested_model="fake-model",
        )


def test_prompt_order_violation_blocked(pg_session):
    run_id = str(uuid4())
    _insert_registered_run(pg_session, run_id)
    snap = _snapshot(run_id)

    with pytest.raises(LiveEvalSafetyError, match="prompt order violation"):
        reserve_live_llm_operation(
            pg_session,
            snapshot=snap,
            prompt_name="entity_extraction_v1",
            requested_model="fake-model",
        )


def test_in_progress_blocks_next_ordinal(pg_session):
    run_id = str(uuid4())
    _insert_registered_run(pg_session, run_id)
    snap = _snapshot(run_id)
    reserve_live_llm_operation(
        pg_session,
        snapshot=snap,
        prompt_name="classification_v1",
        requested_model="fake-model",
    )

    with pytest.raises(LiveEvalSafetyError, match="ordinal 2 blocked"):
        reserve_live_llm_operation(
            pg_session,
            snapshot=snap,
            prompt_name="entity_extraction_v1",
            requested_model="fake-model",
        )


def test_model_mismatch_blocked_before_reservation(pg_session):
    run_id = str(uuid4())
    _insert_registered_run(pg_session, run_id)
    snap = _snapshot(run_id)

    with pytest.raises(LiveEvalSafetyError, match="model mismatch"):
        reserve_live_llm_operation(
            pg_session,
            snapshot=snap,
            prompt_name="classification_v1",
            requested_model="other-model",
        )


def test_provider_mismatch_blocked_before_reservation(pg_session):
    run_id = str(uuid4())
    _insert_registered_run(pg_session, run_id)
    snap = _snapshot(run_id)

    with pytest.raises(LiveEvalSafetyError, match="provider mismatch"):
        reserve_live_llm_operation(
            pg_session,
            snapshot=snap,
            prompt_name="classification_v1",
            requested_provider="anthropic",
            requested_model="fake-model",
        )


def test_completed_step_with_different_model_cannot_create_new_operation(pg_session):
    run_id = str(uuid4())
    _insert_registered_run(pg_session, run_id)
    snap = _snapshot(run_id)
    _complete_prompt(pg_session, snap=snap, prompt_name="classification_v1")

    with pytest.raises(LiveEvalSafetyError, match="retry blocked|model mismatch"):
        reserve_live_llm_operation(
            pg_session,
            snapshot=snap,
            prompt_name="classification_v1",
            requested_model="other-model",
        )
    assert _operation_count(pg_session, run_id) == 1


def test_budget_exactly_four_operations(pg_session):
    run_id = str(uuid4())
    _insert_registered_run(pg_session, run_id, llm_max_calls=4)
    snap = _snapshot(run_id, llm_max_calls=4)
    for prompt_name in (
        "classification_v1",
        "entity_extraction_v1",
        "lead_scoring_v1",
        "decisioning_v1",
    ):
        _complete_prompt(pg_session, snap=snap, prompt_name=prompt_name)

    assert count_succeeded_llm_operations(pg_session, run_id) == 4
    assert count_provider_attempts(pg_session, run_id) == 4
    assert _operation_count(pg_session, run_id) == 4

    with pytest.raises(LiveEvalSafetyError, match="budget exhausted"):
        reserve_live_llm_operation(
            pg_session,
            snapshot=snap,
            prompt_name="classification_v1",
            requested_model="fake-model",
        )


def test_snapshot_budget_not_env(pg_session, monkeypatch):
    run_id = str(uuid4())
    _insert_registered_run(pg_session, run_id, llm_max_calls=4)
    snap = _snapshot(run_id, llm_max_calls=4)
    monkeypatch.setenv("LIVE_EVAL_MAX_LLM_CALLS", "99")
    for prompt_name in (
        "classification_v1",
        "entity_extraction_v1",
        "lead_scoring_v1",
        "decisioning_v1",
    ):
        _complete_prompt(pg_session, snap=snap, prompt_name=prompt_name)
    assert _operation_count(pg_session, run_id) == 4


def test_invalid_snapshot_budget_blocked(pg_session):
    run_id = str(uuid4())
    _insert_registered_run(pg_session, run_id, llm_max_calls=3)
    snap = _snapshot(run_id, llm_max_calls=3)

    with pytest.raises(LiveEvalSafetyError, match="call budget must be 4"):
        reserve_live_llm_operation(
            pg_session,
            snapshot=snap,
            prompt_name="classification_v1",
            requested_model="fake-model",
        )


def test_db_unique_constraints_block_conflicting_prompt_ordinal(pg_session):
    run_id = str(uuid4())
    _insert_registered_run(pg_session, run_id)
    now = datetime.now(timezone.utc)
    operation_key = build_llm_operation_key(
        evaluation_run_id=run_id,
        prompt_name="classification_v1",
        ordinal=1,
    )
    pg_session.execute(
        text(
            """
            INSERT INTO live_eval_llm_operations (
                tenant_id, evaluation_run_id, scenario_id, prompt_name, request_ordinal,
                operation_key, llm_provider, requested_model, status, created_at, updated_at
            ) VALUES (
                'TENANT_LIVE_EVAL', :run_id, 'S01_lead_laddbox_quality',
                'classification_v1', 1, :operation_key,
                'openai', 'fake-model', 'in_progress', :now, :now
            )
            """
        ),
        {"run_id": run_id, "operation_key": operation_key, "now": now},
    )
    pg_session.flush()

    with pytest.raises(IntegrityError):
        pg_session.execute(
            text(
                """
                INSERT INTO live_eval_llm_operations (
                    tenant_id, evaluation_run_id, scenario_id, prompt_name, request_ordinal,
                    operation_key, llm_provider, requested_model, status, created_at, updated_at
                ) VALUES (
                    'TENANT_LIVE_EVAL', :run_id, 'S01_lead_laddbox_quality',
                    'entity_extraction_v1', 1, :operation_key2,
                    'openai', 'fake-model', 'in_progress', :now, :now
                )
                """
            ),
            {
                "run_id": run_id,
                "operation_key2": f"{run_id}:app_live_llm:entity_extraction_v1:1",
                "now": now,
            },
        )
        pg_session.flush()


def test_db_check_constraint_blocks_invalid_ordinal(pg_session):
    run_id = str(uuid4())
    _insert_registered_run(pg_session, run_id)
    now = datetime.now(timezone.utc)

    with pytest.raises(IntegrityError):
        pg_session.execute(
            text(
                """
                INSERT INTO live_eval_llm_operations (
                    tenant_id, evaluation_run_id, scenario_id, prompt_name, request_ordinal,
                    operation_key, llm_provider, requested_model, status, created_at, updated_at
                ) VALUES (
                    'TENANT_LIVE_EVAL', :run_id, 'S01_lead_laddbox_quality',
                    'classification_v1', 5, :operation_key,
                    'openai', 'fake-model', 'in_progress', :now, :now
                )
                """
            ),
            {
                "run_id": run_id,
                "operation_key": f"{run_id}:app_live_llm:classification_v1:5",
                "now": now,
            },
        )
        pg_session.flush()


def test_provenance_readable_from_new_session(pg_engine):
    run_id = str(uuid4())
    Session = sessionmaker(bind=pg_engine)
    writer = Session()
    reader = Session()
    try:
        _insert_registered_run(writer, run_id)
        writer.commit()
        snap = _snapshot(run_id)
        op_key = _complete_prompt(writer, snap=snap, prompt_name="classification_v1")
        assert op_key == build_llm_operation_key(
            evaluation_run_id=run_id,
            prompt_name="classification_v1",
            ordinal=prompt_ordinal("classification_v1"),
        )

        row = reader.execute(
            text(
                """
                SELECT status, requested_model, llm_provider, request_ordinal
                FROM live_eval_llm_operations
                WHERE operation_key = :operation_key
                """
            ),
            {"operation_key": op_key},
        ).first()
        assert row is not None
        assert row.status == EVENT_OUTCOME_SUCCEEDED
        assert row.requested_model == "fake-model"
        assert row.llm_provider == "openai"
        assert row.request_ordinal == 1
    finally:
        writer.rollback()
        reader.rollback()
        writer.close()
        reader.close()


def test_full_success_creates_four_permanent_rows(pg_session):
    run_id = str(uuid4())
    _insert_registered_run(pg_session, run_id)
    snap = _snapshot(run_id)
    for prompt_name in (
        "classification_v1",
        "entity_extraction_v1",
        "lead_scoring_v1",
        "decisioning_v1",
    ):
        _complete_prompt(pg_session, snap=snap, prompt_name=prompt_name)

    rows = pg_session.execute(
        text(
            """
            SELECT prompt_name, request_ordinal, status
            FROM live_eval_llm_operations
            WHERE evaluation_run_id = :run_id
            ORDER BY request_ordinal
            """
        ),
        {"run_id": run_id},
    ).all()
    assert len(rows) == 4
    assert [row.prompt_name for row in rows] == [
        "classification_v1",
        "entity_extraction_v1",
        "lead_scoring_v1",
        "decisioning_v1",
    ]
    assert all(row.status == EVENT_OUTCOME_SUCCEEDED for row in rows)
    assert count_llm_operations_for_run(pg_session, run_id) == 4
