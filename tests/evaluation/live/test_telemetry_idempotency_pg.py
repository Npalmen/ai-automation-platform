"""PostgreSQL idempotency contract tests for live-eval telemetry."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.evaluation.live.telemetry import (
    build_event_key,
    build_operation_key,
    record_live_eval_external_event,
)
from app.evaluation.live.schemas import TrustedLiveEvalSnapshot
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.live_eval_models import LiveEvalExternalEventRow
from app.repositories.postgres.live_eval_repository import LiveEvalExternalEventRepository
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


def _insert_active_run(pg_session, run_id: str) -> None:
    now = datetime.now(timezone.utc)
    pg_session.execute(
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
                'sender@eval.test', 'recipient@eval.test', 'active',
                'pg-test', :expires_at, 'abc123'
            )
            ON CONFLICT (evaluation_run_id) DO NOTHING
            """
        ),
        {"run_id": run_id, "expires_at": now.replace(year=now.year + 1)},
    )
    pg_session.flush()


def _snapshot(run_id: str) -> TrustedLiveEvalSnapshot:
    return TrustedLiveEvalSnapshot(
        evaluation_run_id=run_id,
        tenant_id="TENANT_LIVE_EVAL",
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        transport_mode="live_gmail",
        ai_mode="fixture_ai",
        fixture_bundle_id="k2f_bundle_s01",
        expected_sender="sender@eval.test",
        expected_recipient="recipient@eval.test",
        config_hash="abc123",
        trusted=True,
    )


def test_second_succeeded_same_operation_key_blocked_on_pg(pg_session):
    run_id = str(uuid4())
    _insert_active_run(pg_session, run_id)
    snap = _snapshot(run_id)
    op_key = build_operation_key(
        evaluation_run_id=run_id,
        category="app_gmail_reply",
        operation="send_customer_auto_reply",
        action_operation_id="pg-op-1",
    )
    assert (
        record_live_eval_external_event(
            pg_session,
            operation_key=op_key,
            outcome="succeeded",
            category="app_gmail_reply",
            operation="send_customer_auto_reply",
            integration_type="google_mail",
            snapshot=snap,
        )
        is True
    )

    alt_event_key = build_event_key(operation_key=op_key, outcome="succeeded") + ":alt"
    alt = LiveEvalExternalEventRow(
        event_key=alt_event_key,
        operation_key=op_key,
        evaluation_run_id=run_id,
        tenant_id="TENANT_LIVE_EVAL",
        integration_type="google_mail",
        category="app_gmail_reply",
        operation="send_customer_auto_reply",
        outcome="succeeded",
        started_at=datetime.now(timezone.utc),
        redacted_metadata={},
    )
    assert LiveEvalExternalEventRepository.record_event(pg_session, alt) is False


def test_duplicate_event_preserves_sibling_on_pg(pg_session):
    run_id = str(uuid4())
    _insert_active_run(pg_session, run_id)
    now = datetime.now(timezone.utc)
    pg_session.add(
        JobRecord(
            job_id=f"pg-sibling-{run_id[:8]}",
            tenant_id="TENANT_LIVE_EVAL",
            job_type="lead",
            status="created",
            input_data={},
            result=None,
            created_at=now,
            updated_at=now,
            created_by=None,
        )
    )
    pg_session.flush()

    snap = _snapshot(run_id)
    op_key = build_operation_key(
        evaluation_run_id=run_id,
        category="app_external_write_blocked",
        operation="send_email",
        action_operation_id="pg-op-2",
    )
    assert (
        record_live_eval_external_event(
            pg_session,
            operation_key=op_key,
            outcome="blocked",
            category="app_external_write_blocked",
            operation="send_email",
            integration_type="google_mail",
            snapshot=snap,
            attempt=1,
        )
        is True
    )
    assert (
        record_live_eval_external_event(
            pg_session,
            operation_key=op_key,
            outcome="blocked",
            category="app_external_write_blocked",
            operation="send_email",
            integration_type="google_mail",
            snapshot=snap,
            attempt=1,
        )
        is False
    )

    pg_session.commit()
    assert (
        pg_session.get(JobRecord, f"pg-sibling-{run_id[:8]}") is not None
    )
