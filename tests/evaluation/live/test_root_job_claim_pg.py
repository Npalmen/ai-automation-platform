"""PostgreSQL concurrency tests for atomic root-job claim."""

from __future__ import annotations

import os
import threading
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.repositories.postgres.live_eval_models import LiveEvalRunRow
from app.repositories.postgres.live_eval_repository import (
    LiveEvalRunConflictError,
    LiveEvalRunRepository,
)
from app.repositories.postgres.schema_migrations import ensure_runtime_schema


def _postgres_url() -> str | None:
    url = (
        os.environ.get("EVAL_DATABASE_URL", "").strip()
        or os.environ.get("SLICE_B_TEST_DATABASE_URL", "").strip()
        or os.environ.get("DATABASE_URL", "").strip()
    )
    if not url or "sqlite" in url:
        return None
    return url


@pytest.mark.integration_db
def test_postgres_concurrent_root_claim_only_one_wins():
    database_url = _postgres_url()
    if database_url is None:
        pytest.skip("PostgreSQL DATABASE_URL not configured")

    pytest.importorskip("psycopg2")

    engine = create_engine(database_url)
    ensure_runtime_schema(engine)

    run_id = f"run-pg-{uuid4()}"
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
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
                """
            ),
            {"run_id": run_id, "expires_at": now + timedelta(hours=2)},
        )

    Session = sessionmaker(bind=engine)
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
        except Exception as exc:
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

    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT status, root_gmail_message_id, root_job_id "
                "FROM live_eval_runs WHERE evaluation_run_id = :run_id"
            ),
            {"run_id": run_id},
        ).mappings().one()

    assert row["status"] == "active"
    assert len(results) == 1
    assert len(errors) >= 1
    assert row["root_job_id"] in {"job-a", "job-b"}
    assert row["root_gmail_message_id"] in {"msg-a", "msg-b"}

    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM live_eval_runs WHERE evaluation_run_id = :run_id"),
            {"run_id": run_id},
        )

    engine.dispose()
