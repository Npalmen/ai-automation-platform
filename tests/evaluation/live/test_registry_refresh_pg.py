"""PostgreSQL registry refresh visibility after root-job claim."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.evaluation.live.registry import create_and_claim_live_eval_root_job
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


def _cleanup(engine, run_id: str) -> None:
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT root_job_id FROM live_eval_runs WHERE evaluation_run_id = :run_id"),
            {"run_id": run_id},
        ).fetchone()
        if row and row[0]:
            conn.execute(text("DELETE FROM jobs WHERE job_id = :job_id"), {"job_id": row[0]})
        conn.execute(
            text("DELETE FROM live_eval_runs WHERE evaluation_run_id = :run_id"),
            {"run_id": run_id},
        )


def test_registry_refresh_sees_committed_root_job_from_new_session(pg_engine):
    run_id = f"run-refresh-{datetime.now(timezone.utc).timestamp()}"
    _cleanup(pg_engine, run_id)
    Session = sessionmaker(bind=pg_engine)
    now = datetime.now(timezone.utc)

    with pg_engine.begin() as conn:
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
                    'pg-refresh', :expires_at, 'hash'
                )
                """
            ),
            {"run_id": run_id, "expires_at": now + timedelta(hours=2)},
        )

    session_a = Session()
    try:
        job = Job(tenant_id="TENANT_LIVE_EVAL", job_type=JobType.LEAD, input_data={})
        with patch("app.evaluation.live.registry.emit_live_eval_audit"):
            saved = create_and_claim_live_eval_root_job(
                session_a,
                job=job,
                evaluation_run_id=run_id,
                tenant_id="TENANT_LIVE_EVAL",
                root_gmail_message_id="msg-refresh-1",
            )
        session_a.commit()
        assert saved.job_id
    finally:
        session_a.close()

    session_b = Session()
    try:
        row = session_b.execute(
            text(
                "SELECT root_job_id, root_gmail_message_id, tenant_id, status "
                "FROM live_eval_runs WHERE evaluation_run_id = :run_id"
            ),
            {"run_id": run_id},
        ).mappings().one()
        assert row["root_job_id"]
        assert row["root_gmail_message_id"] == "msg-refresh-1"
        assert row["tenant_id"] == "TENANT_LIVE_EVAL"
        assert row["status"] == "active"
        assert bool(row["root_job_id"]) is True
    finally:
        session_b.close()
        _cleanup(pg_engine, run_id)
