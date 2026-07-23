"""PostgreSQL persistence for workflow cleanup outcomes and terminal run status."""

from __future__ import annotations

import os
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.evaluation.live.cleanup import cleanup_recipient_message
from app.evaluation.live.constants import CLEANUP_STATE_FAILED, CLEANUP_STATE_SUCCESS
from app.evaluation.live.exit_codes import EXIT_CLEANUP, EXIT_SUCCESS
from app.evaluation.live.journal import (
    append_transition,
    ensure_run_directory,
    load_report,
    write_report_atomic,
    write_run_config,
)
from app.evaluation.live.reporting import build_failure_summary
from app.evaluation.live.runner import (
    resolve_post_cleanup_run_status,
)
from app.evaluation.live.schemas import LiveEvalReport
from app.repositories.postgres.live_eval_repository import LiveEvalRunRepository
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


def _cleanup_pg(engine, run_id: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM live_eval_external_events WHERE operation_key LIKE :prefix"),
            {"prefix": f"{run_id}%"},
        )
        conn.execute(
            text("DELETE FROM live_eval_runs WHERE evaluation_run_id = :run_id"),
            {"run_id": run_id},
        )


def _insert_run(engine, run_id: str, *, status: str, root_job_id: str | None = None, root_msg: str | None = None):
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO live_eval_runs (
                    evaluation_run_id, tenant_id, scenario_id, attempt_id,
                    transport_mode, ai_mode, fixture_bundle_id,
                    expected_sender, expected_recipient, status,
                    created_by, expires_at, config_hash,
                    root_job_id, root_gmail_message_id
                ) VALUES (
                    :run_id, 'TENANT_LIVE_EVAL', 'S01_lead_laddbox_quality', 1,
                    'live_gmail', 'fixture_ai', 'k2f_bundle_s01',
                    'sender@eval.test', 'recipient@eval.test', :status,
                    'pg-cleanup', :expires_at, 'hash',
                    :root_job_id, :root_msg
                )
                """
            ),
            {
                "run_id": run_id,
                "status": status,
                "expires_at": now + timedelta(hours=2),
                "root_job_id": root_job_id,
                "root_msg": root_msg,
            },
        )


def _seed_journal(tmp_path, monkeypatch, run_id: str, recipient_id: str) -> None:
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
    ensure_run_directory(run_id)
    write_run_config(
        run_id,
        {
            "evaluation_run_id": run_id,
            "tenant_id": "TENANT_LIVE_EVAL",
            "scenario_id": "S01_lead_laddbox_quality",
            "attempt_id": 1,
        },
    )
    append_transition(
        run_id,
        {"state": "delivery_confirmed", "recipient_gmail_message_id": recipient_id},
    )


def _write_passed_report(run_id: str, *, cleanup_state: str) -> None:
    summary = build_failure_summary(
        evaluation_run_id=run_id,
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        failure_category=None,
        failed_stage="passed",
        primary_exit_code=EXIT_SUCCESS,
        cleanup_exit_code=None,
        artifact_status="present",
        send_state="confirmed",
        send_attempted=True,
        send_confirmed=True,
        reconciliation_result="not_run",
        recipient_delivery_observed=True,
        root_job_bound=True,
        cleanup_state=cleanup_state,
        gmail_mutations=0,
    )
    write_report_atomic(
        run_id,
        LiveEvalReport(
            evaluation_run_id=run_id,
            scenario_id="S01_lead_laddbox_quality",
            attempt_id=1,
            transport_mode="live_gmail",
            ai_mode="fixture_ai",
            result="passed",
            failure_summary=summary.to_dict(),
        ),
    )


def _cleanup_adapter_patches(adapter: MagicMock):
    return (
        patch("app.evaluation.live.cleanup.get_integration_connection_config", return_value={}),
        patch("app.evaluation.live.cleanup.get_integration_adapter", return_value=adapter),
        patch("app.evaluation.live.cleanup.validate_delivery_candidate", return_value=(True, None)),
    )


def test_pg_cleanup_success_finalizes_completed_from_new_session(pg_engine, tmp_path, monkeypatch, live_eval_env):
    run_id = f"run-pg-cleanup-success-{datetime.now(timezone.utc).timestamp()}"
    recipient_id = "msg-pg-success-recipient"
    _cleanup_pg(pg_engine, run_id)
    _insert_run(
        pg_engine,
        run_id,
        status="active",
        root_job_id="job-pg-success",
        root_msg=recipient_id,
    )
    _seed_journal(tmp_path, monkeypatch, run_id, recipient_id)
    _write_passed_report(run_id, cleanup_state="deferred")

    Session = sessionmaker(bind=pg_engine)
    session = Session()
    try:
        monkeypatch.setenv("EXTERNAL_SIDE_EFFECT_TESTS", "yes")
        adapter = MagicMock()
        adapter.execute_action.return_value = {"message": {"message_id": recipient_id}}
        with ExitStack() as stack:
            for patcher in _cleanup_adapter_patches(adapter):
                stack.enter_context(patcher)
            result = cleanup_recipient_message(
                session,
                evaluation_run_id=run_id,
                tenant_id="TENANT_LIVE_EVAL",
                recipient_gmail_message_id=recipient_id,
                phase="post_claim",
            )
        session.commit()
        assert result["result"] == "archived"
        LiveEvalRunRepository.transition_status(
            session,
            run_id,
            tenant_id="TENANT_LIVE_EVAL",
            to_status="completed",
        )
        session.commit()
    finally:
        session.close()

    session_b = Session()
    try:
        row = session_b.execute(
            text("SELECT status FROM live_eval_runs WHERE evaluation_run_id = :run_id"),
            {"run_id": run_id},
        ).one()
        assert row[0] == "completed"
    finally:
        session_b.close()

    report = load_report(run_id)
    assert report["result"] == "passed"
    _cleanup_pg(pg_engine, run_id)


def test_pg_cleanup_failure_finalizes_aborted_from_new_session(pg_engine, tmp_path, monkeypatch):
    run_id = f"run-pg-cleanup-fail-{datetime.now(timezone.utc).timestamp()}"
    recipient_id = "msg-pg-fail-recipient"
    _cleanup_pg(pg_engine, run_id)
    _insert_run(
        pg_engine,
        run_id,
        status="active",
        root_job_id="job-pg-fail",
        root_msg=recipient_id,
    )
    _seed_journal(tmp_path, monkeypatch, run_id, recipient_id)
    _write_passed_report(run_id, cleanup_state="deferred")

    Session = sessionmaker(bind=pg_engine)
    session = Session()
    try:
        next_status = resolve_post_cleanup_run_status(
            scenario_passed=True,
            cleanup_succeeded=False,
            current_status="active",
        )
        assert next_status == "aborted"
        LiveEvalRunRepository.transition_status(
            session,
            run_id,
            tenant_id="TENANT_LIVE_EVAL",
            to_status=next_status,
        )
        session.commit()
    finally:
        session.close()

    summary = build_failure_summary(
        evaluation_run_id=run_id,
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        failure_category=None,
        failed_stage="passed",
        primary_exit_code=EXIT_SUCCESS,
        cleanup_exit_code=EXIT_CLEANUP,
        artifact_status="present",
        send_state="confirmed",
        send_attempted=True,
        send_confirmed=True,
        reconciliation_result="not_run",
        recipient_delivery_observed=True,
        root_job_bound=True,
        cleanup_state=CLEANUP_STATE_FAILED,
        gmail_mutations=0,
    )
    payload = summary.to_dict()
    payload["cleanup_failure_reason"] = "HTTPStatusError"
    write_report_atomic(
        run_id,
        LiveEvalReport(
            evaluation_run_id=run_id,
            scenario_id="S01_lead_laddbox_quality",
            attempt_id=1,
            transport_mode="live_gmail",
            ai_mode="fixture_ai",
            result="passed",
            failure_summary=payload,
        ),
    )

    session_b = Session()
    try:
        row = session_b.execute(
            text("SELECT status FROM live_eval_runs WHERE evaluation_run_id = :run_id"),
            {"run_id": run_id},
        ).one()
        assert row[0] == "aborted"
    finally:
        session_b.close()

    report = load_report(run_id)
    assert report["result"] == "passed"
    assert report["failure_summary"]["cleanup_state"] == CLEANUP_STATE_FAILED
    assert report["failure_summary"]["cleanup_exit_code"] == EXIT_CLEANUP
    assert report["failure_summary"]["cleanup_failure_reason"] == "HTTPStatusError"
    _cleanup_pg(pg_engine, run_id)


def test_pg_aborted_pre_claim_archives_once_then_idempotent(pg_engine, tmp_path, monkeypatch, live_eval_env):
    run_id = f"run-pg-preclaim-{datetime.now(timezone.utc).timestamp()}"
    recipient_id = "msg-pg-preclaim-recipient"
    _cleanup_pg(pg_engine, run_id)
    _insert_run(pg_engine, run_id, status="aborted")
    _seed_journal(tmp_path, monkeypatch, run_id, recipient_id)

    Session = sessionmaker(bind=pg_engine)
    session = Session()
    try:
        monkeypatch.setenv("EXTERNAL_SIDE_EFFECT_TESTS", "yes")
        adapter = MagicMock()
        adapter.execute_action.return_value = {"message": {"message_id": recipient_id}}
        with ExitStack() as stack:
            for patcher in _cleanup_adapter_patches(adapter):
                stack.enter_context(patcher)
            first = cleanup_recipient_message(
                session,
                evaluation_run_id=run_id,
                tenant_id="TENANT_LIVE_EVAL",
                recipient_gmail_message_id=recipient_id,
                phase="pre_claim",
            )
            second = cleanup_recipient_message(
                session,
                evaluation_run_id=run_id,
                tenant_id="TENANT_LIVE_EVAL",
                recipient_gmail_message_id=recipient_id,
                phase="pre_claim",
            )
        session.commit()
        assert first["result"] == "archived"
        assert second["result"] == "already_archived"
        adapter.client.archive_from_inbox.assert_called_once_with(recipient_id)
    finally:
        session.close()

    session_b = Session()
    try:
        row = session_b.execute(
            text(
                "SELECT root_job_id, root_gmail_message_id, status "
                "FROM live_eval_runs WHERE evaluation_run_id = :run_id"
            ),
            {"run_id": run_id},
        ).one()
        assert row[0] is None
        assert row[1] is None
        assert row[2] == "aborted"
    finally:
        session_b.close()
        _cleanup_pg(pg_engine, run_id)
