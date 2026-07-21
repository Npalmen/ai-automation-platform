"""PostgreSQL atomicity tests for live-eval root job claim."""

from __future__ import annotations

import os
import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.registry import create_and_claim_live_eval_root_job
from app.repositories.postgres.job_repository import JobRepository
from app.repositories.postgres.live_eval_repository import (
    LiveEvalRunConflictError,
    LiveEvalRunRepository,
)
from app.repositories.postgres.schema_migrations import ensure_runtime_schema

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
    ensure_runtime_schema(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def pg_session(pg_engine):
    Session = sessionmaker(bind=pg_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


def _insert_registered_run(conn, run_id: str) -> None:
    now = datetime.now(timezone.utc)
    conn.execute(
        text(
            """
            INSERT INTO live_eval_runs (
                evaluation_run_id, tenant_id, scenario_id, attempt_id,
                transport_mode, ai_mode, fixture_bundle_id,
                expected_sender, expected_recipient, status,
                created_by, expires_at, config_hash
            ) VALUES (
                :run_id, 'TENANT_LIVE_EVAL', 'S01_lead_laddbox_quality', 1,
                'live_gmail', 'fixture_ai', 'k2f_bundle_s01',
                'sender@eval.test', 'recipient@eval.test', 'registered',
                'pg-test', :expires_at, 'hash'
            )
            ON CONFLICT (evaluation_run_id) DO NOTHING
            """
        ),
        {"run_id": run_id, "expires_at": now + timedelta(hours=2)},
    )


def _cleanup_run_and_jobs(engine, run_id: str) -> None:
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT root_job_id FROM live_eval_runs WHERE evaluation_run_id = :run_id"),
            {"run_id": run_id},
        ).fetchone()
        if row and row[0]:
            conn.execute(text("DELETE FROM jobs WHERE job_id = :job_id"), {"job_id": row[0]})
        conn.execute(
            text("DELETE FROM audit_events WHERE details::text LIKE :pattern"),
            {"pattern": f"%{run_id}%"},
        )
        conn.execute(
            text("DELETE FROM live_eval_runs WHERE evaluation_run_id = :run_id"),
            {"run_id": run_id},
        )
        conn.execute(
            text(
                "DELETE FROM jobs WHERE tenant_id = 'TENANT_LIVE_EVAL' "
                "AND input_data::text LIKE :pattern"
            ),
            {"pattern": f"%{run_id}%"},
        )


def _live_eval_job(message_id: str, run_id: str) -> Job:
    return Job(
        tenant_id="TENANT_LIVE_EVAL",
        job_type=JobType.LEAD,
        input_data={
            "subject": "eval",
            "live_eval": {
                "evaluation_run_id": run_id,
                "tenant_id": "TENANT_LIVE_EVAL",
                "scenario_id": "S01_lead_laddbox_quality",
                "attempt_id": 1,
                "transport_mode": "live_gmail",
                "ai_mode": "fixture_ai",
                "fixture_bundle_id": "k2f_bundle_s01",
                "expected_sender": "sender@eval.test",
                "expected_recipient": "recipient@eval.test",
                "trusted": True,
            },
            "source": {
                "system": "gmail",
                "message_id": message_id,
                "thread_id": f"thread-{message_id}",
            },
        },
    )


def test_concurrent_different_messages_one_root_job(pg_engine):
    run_id = f"run-pg-{uuid4()}"
    with pg_engine.begin() as conn:
        _insert_registered_run(conn, run_id)

    Session = sessionmaker(bind=pg_engine)
    barrier = threading.Barrier(2)
    winners: list[str] = []
    errors: list[Exception] = []

    def _attempt(message_id: str) -> None:
        session = Session()
        try:
            barrier.wait(timeout=5)
            job = _live_eval_job(message_id, run_id)
            create_and_claim_live_eval_root_job(
                session,
                job=job,
                evaluation_run_id=run_id,
                tenant_id="TENANT_LIVE_EVAL",
                root_gmail_message_id=message_id,
            )
            winners.append(job.job_id)
        except (LiveEvalSafetyError, LiveEvalRunConflictError) as exc:
            session.rollback()
            errors.append(exc)
        except Exception as exc:
            session.rollback()
            errors.append(exc)
        finally:
            session.close()

    t1 = threading.Thread(target=_attempt, args=("msg-a",))
    t2 = threading.Thread(target=_attempt, args=("msg-b",))
    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    with pg_engine.connect() as conn:
        run_row = conn.execute(
            text(
                "SELECT status, root_job_id FROM live_eval_runs WHERE evaluation_run_id = :run_id"
            ),
            {"run_id": run_id},
        ).mappings().one()
        job_count = conn.execute(
            text(
                "SELECT COUNT(*) FROM jobs WHERE tenant_id = 'TENANT_LIVE_EVAL' "
                "AND input_data::text LIKE :pattern"
            ),
            {"pattern": f"%{run_id}%"},
        ).scalar_one()

    assert run_row["status"] == "active"
    assert len(winners) == 1
    assert len(errors) >= 1
    assert job_count == 1
    assert run_row["root_job_id"] == winners[0]

    _cleanup_run_and_jobs(pg_engine, run_id)


def test_same_message_id_claim_is_idempotent(pg_engine):
    run_id = f"run-pg-{uuid4()}"
    message_id = f"msg-{uuid4()}"
    with pg_engine.begin() as conn:
        _insert_registered_run(conn, run_id)

    Session = sessionmaker(bind=pg_engine)
    session = Session()
    job = _live_eval_job(message_id, run_id)
    first = create_and_claim_live_eval_root_job(
        session,
        job=job,
        evaluation_run_id=run_id,
        tenant_id="TENANT_LIVE_EVAL",
        root_gmail_message_id=message_id,
    )
    second_job = _live_eval_job(message_id, run_id)
    with pytest.raises(LiveEvalSafetyError):
        create_and_claim_live_eval_root_job(
            session,
            job=second_job,
            evaluation_run_id=run_id,
            tenant_id="TENANT_LIVE_EVAL",
            root_gmail_message_id=message_id,
        )
    session.close()

    with pg_engine.connect() as conn:
        job_count = conn.execute(
            text("SELECT COUNT(*) FROM jobs WHERE job_id = :job_id"),
            {"job_id": first.job_id},
        ).scalar_one()
        run_row = conn.execute(
            text(
                "SELECT status, root_job_id, root_gmail_message_id "
                "FROM live_eval_runs WHERE evaluation_run_id = :run_id"
            ),
            {"run_id": run_id},
        ).mappings().one()

    assert job_count == 1
    assert run_row["status"] == "active"
    assert run_row["root_job_id"] == first.job_id
    assert run_row["root_gmail_message_id"] == message_id

    _cleanup_run_and_jobs(pg_engine, run_id)


def test_rollback_on_claim_failure_after_job_flush(pg_engine):
    run_id = f"run-pg-{uuid4()}"
    with pg_engine.begin() as conn:
        _insert_registered_run(conn, run_id)

    Session = sessionmaker(bind=pg_engine)
    session = Session()
    job = _live_eval_job(f"msg-{uuid4()}", run_id)
    with patch.object(
        LiveEvalRunRepository,
        "claim_root_job",
        side_effect=LiveEvalRunConflictError("claim lost"),
    ):
        with pytest.raises(LiveEvalSafetyError):
            create_and_claim_live_eval_root_job(
                session,
                job=job,
                evaluation_run_id=run_id,
                tenant_id="TENANT_LIVE_EVAL",
                root_gmail_message_id="msg-fail",
            )

    with pg_engine.connect() as conn:
        run_row = conn.execute(
            text("SELECT status, root_job_id FROM live_eval_runs WHERE evaluation_run_id = :run_id"),
            {"run_id": run_id},
        ).mappings().one()
        job_count = conn.execute(
            text("SELECT COUNT(*) FROM jobs WHERE job_id = :job_id"),
            {"job_id": job.job_id},
        ).scalar_one()

    assert run_row["status"] == "registered"
    assert run_row["root_job_id"] is None
    assert job_count == 0
    session.close()
    _cleanup_run_and_jobs(pg_engine, run_id)


def test_rollback_on_commit_failure_after_claim(pg_engine):
    run_id = f"run-pg-{uuid4()}"
    message_id = f"msg-{uuid4()}"
    with pg_engine.begin() as conn:
        _insert_registered_run(conn, run_id)

    Session = sessionmaker(bind=pg_engine)
    session = Session()
    job = _live_eval_job(message_id, run_id)
    with patch.object(session, "commit", side_effect=RuntimeError("commit failed")):
        with pytest.raises(RuntimeError, match="commit failed"):
            create_and_claim_live_eval_root_job(
                session,
                job=job,
                evaluation_run_id=run_id,
                tenant_id="TENANT_LIVE_EVAL",
                root_gmail_message_id=message_id,
            )

    with pg_engine.connect() as conn:
        run_row = conn.execute(
            text("SELECT status, root_job_id FROM live_eval_runs WHERE evaluation_run_id = :run_id"),
            {"run_id": run_id},
        ).mappings().one()
        job_count = conn.execute(
            text("SELECT COUNT(*) FROM jobs WHERE job_id = :job_id"),
            {"job_id": job.job_id},
        ).scalar_one()

    assert run_row["status"] == "registered"
    assert run_row["root_job_id"] is None
    assert job_count == 0
    session.close()
    _cleanup_run_and_jobs(pg_engine, run_id)


def test_repository_concurrent_claim_only_one_wins(pg_engine):
    run_id = f"run-pg-{uuid4()}"
    with pg_engine.begin() as conn:
        _insert_registered_run(conn, run_id)

    Session = sessionmaker(bind=pg_engine)
    barrier = threading.Barrier(2)
    results: list[str] = []
    errors: list[Exception] = []

    def _claim(msg_id: str, job_id: str) -> None:
        session = Session()
        try:
            barrier.wait(timeout=5)
            LiveEvalRunRepository.claim_root_job(
                session,
                evaluation_run_id=run_id,
                tenant_id="TENANT_LIVE_EVAL",
                root_gmail_message_id=msg_id,
                root_job_id=job_id,
            )
            session.commit()
            results.append(job_id)
        except LiveEvalRunConflictError as exc:
            session.rollback()
            errors.append(exc)
        finally:
            session.close()

    t1 = threading.Thread(target=_claim, args=("msg-a", "job-a"))
    t2 = threading.Thread(target=_claim, args=("msg-b", "job-b"))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    with pg_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT status, root_gmail_message_id, root_job_id, activated_at "
                "FROM live_eval_runs WHERE evaluation_run_id = :run_id"
            ),
            {"run_id": run_id},
        ).mappings().one()

    assert row["status"] == "active"
    assert len(results) == 1
    assert len(errors) >= 1
    assert row["activated_at"] is not None
    _cleanup_run_and_jobs(pg_engine, run_id)
