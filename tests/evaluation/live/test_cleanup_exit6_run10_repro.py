"""Run #10 cleanup exit 6 reproduction and post-abort post_claim contract."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.evaluation.live.cleanup import cleanup_recipient_message
from app.evaluation.live.cleanup_phase import resolve_cleanup_phase
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.exit_codes import EXIT_CLEANUP, EXIT_SUCCESS, EXIT_TIMEOUT
from app.evaluation.live.journal import append_transition, ensure_run_directory, write_run_config
from app.evaluation.live.runner import cleanup_only
from app.repositories.postgres.live_eval_models import LiveEvalRunRow


# Structural reproduction of run #10 cleanup exit 6 (fictional IDs — no live Gmail data).
RUN10_ID = "run-exit6-repro"
RUN10_RECIPIENT = "msg-recipient-exit6"
RUN10_SENDER = "msg-sender-exit6"
RUN10_JOB = "job-root-exit6"


def _seed_run10_journal(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
    ensure_run_directory(RUN10_ID)
    write_run_config(
        RUN10_ID,
        {
            "evaluation_run_id": RUN10_ID,
            "tenant_id": "TENANT_LIVE_EVAL",
            "scenario_id": "S01_lead_laddbox_quality",
            "attempt_id": 1,
        },
    )
    for transition in [
        {"state": "delivery_confirmed", "recipient_gmail_message_id": RUN10_RECIPIENT},
        {
            "state": "intake_completed",
            "job_id": RUN10_JOB,
            "pipeline_run_id": None,
        },
        {"state": "job_detected"},
    ]:
        append_transition(RUN10_ID, transition)


def test_run10_phase_resolver_selects_post_claim():
    from app.evaluation.live.journal import RunCheckpoint

    cp = RunCheckpoint(
        evaluation_run_id=RUN10_ID,
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        tenant_id="TENANT_LIVE_EVAL",
        transport_mode="live_gmail",
        ai_mode="fixture_ai",
        config_hash="652075231f2a8851",
        send_window_start=datetime.now(timezone.utc),
        sender_account_fingerprint="",
        recipient_account_fingerprint="",
        last_state="job_detected",
        sender_gmail_message_id=RUN10_SENDER,
        transitions=[
            {"state": "delivery_confirmed", "recipient_gmail_message_id": RUN10_RECIPIENT},
            {"state": "intake_completed", "job_id": RUN10_JOB},
        ],
    )
    resolution = resolve_cleanup_phase(
        cp,
        root_job_bound=True,
        root_gmail_message_id=RUN10_RECIPIENT,
    )
    assert resolution.resolved
    assert resolution.phase == "post_claim"


def test_run10_post_claim_cleanup_allowed_after_abort_with_root_binding(
    db, live_eval_env, monkeypatch
):
    """After abort, post_claim cleanup is allowed when root binding matches."""
    now = datetime.now(timezone.utc)
    row = LiveEvalRunRow(
        evaluation_run_id=RUN10_ID,
        tenant_id="TENANT_LIVE_EVAL",
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        transport_mode="live_gmail",
        ai_mode="fixture_ai",
        fixture_bundle_id="k2f_bundle_s01",
        expected_sender="sender@eval.test",
        expected_recipient="recipient@eval.test",
        status="completed",
        created_by="test",
        created_at=now,
        expires_at=now + timedelta(hours=2),
        config_hash="652075231f2a8851",
        root_gmail_message_id=RUN10_RECIPIENT,
        root_job_id=RUN10_JOB,
    )
    row.status = "aborted"
    db.add(row)
    db.commit()

    monkeypatch.setenv("EXTERNAL_SIDE_EFFECT_TESTS", "yes")
    from app.evaluation.live.config import get_live_eval_config

    get_live_eval_config.cache_clear()

    adapter = MagicMock()
    adapter.execute_action.return_value = {
        "message": {
            "message_id": RUN10_RECIPIENT,
            "subject": "KROWOLF-EVAL",
            "from": "sender@eval.test",
            "to": "recipient@eval.test",
            "internal_date_ms": int(now.timestamp() * 1000),
            "label_ids": ["label-krowolf"],
            "body_text": "",
        }
    }
    with patch(
        "app.evaluation.live.cleanup.get_integration_connection_config",
        return_value={},
    ), patch(
        "app.evaluation.live.cleanup.get_integration_adapter",
        return_value=adapter,
    ), patch(
        "app.evaluation.live.cleanup.validate_delivery_candidate",
        return_value=(True, None),
    ):
        result = cleanup_recipient_message(
            db,
            evaluation_run_id=RUN10_ID,
            tenant_id="TENANT_LIVE_EVAL",
            recipient_gmail_message_id=RUN10_RECIPIENT,
            phase="post_claim",
        )
    assert result["result"] == "archived"
    adapter.client.archive_from_inbox.assert_called_once_with(RUN10_RECIPIENT)


def test_cleanup_only_run10_state_reports_typed_failure_when_http_fails(
    live_eval_env, monkeypatch, tmp_path, capsys
):
    _seed_run10_journal(tmp_path, monkeypatch)
    with patch(
        "app.evaluation.live.runner.acquire_run_writer_lock",
        return_value=MagicMock(),
    ), patch("app.evaluation.live.runner.release_run_writer_lock"), patch(
        "app.evaluation.live.runner.LiveEvalObserver"
    ) as observer_cls, patch(
        "app.evaluation.live.runner.cleanup_not_safe_exit_code",
        return_value=EXIT_TIMEOUT,
    ):
        observer = observer_cls.return_value
        observer.get_run.return_value = {
            "root_job_id": RUN10_JOB,
            "root_gmail_message_id": RUN10_RECIPIENT,
        }
        observer.cleanup_recipient.side_effect = LiveEvalSafetyError(
            "run status is terminal: aborted"
        )
        code = cleanup_only(
            base_url="http://localhost:8010",
            admin_api_key="key",
            tenant_id="TENANT_LIVE_EVAL",
            evaluation_run_id=RUN10_ID,
            phase="post_claim",
        )

    assert code == EXIT_CLEANUP
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["cleanup_state"] == "failed"
    assert payload["reason_type"] == "safety_error"
    assert "terminal: aborted" in payload["reason"]


def test_primary_timeout_preserved_when_cleanup_fails(live_eval_env, monkeypatch, tmp_path):
    _seed_run10_journal(tmp_path, monkeypatch)
    from app.evaluation.live.reporting import build_failure_summary

    summary = build_failure_summary(
        evaluation_run_id=RUN10_ID,
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        failure_category="unexpected_terminal_status",
        failed_stage="job_detected",
        primary_exit_code=EXIT_TIMEOUT,
        cleanup_exit_code=EXIT_CLEANUP,
        artifact_status="present",
        send_state="confirmed",
        send_attempted=True,
        send_confirmed=True,
        reconciliation_result="not_run",
        recipient_delivery_observed=True,
        root_job_bound=True,
        cleanup_state="failed",
        gmail_mutations=0,
    )
    assert summary.primary_exit_code == EXIT_TIMEOUT
    assert summary.final_exit_code == EXIT_TIMEOUT


def test_cleanup_only_success_preserves_primary_timeout_exit(
    live_eval_env, monkeypatch, tmp_path, capsys
):
    _seed_run10_journal(tmp_path, monkeypatch)
    with patch(
        "app.evaluation.live.runner.acquire_run_writer_lock",
        return_value=MagicMock(),
    ), patch("app.evaluation.live.runner.release_run_writer_lock"), patch(
        "app.evaluation.live.runner.LiveEvalObserver"
    ) as observer_cls, patch(
        "app.evaluation.live.runner.cleanup_not_safe_exit_code",
        return_value=EXIT_TIMEOUT,
    ):
        observer = observer_cls.return_value
        observer.get_run.return_value = {
            "root_job_id": RUN10_JOB,
            "root_gmail_message_id": RUN10_RECIPIENT,
        }
        code = cleanup_only(
            base_url="http://localhost:8010",
            admin_api_key="key",
            tenant_id="TENANT_LIVE_EVAL",
            evaluation_run_id=RUN10_ID,
            phase="post_claim",
        )

    assert code == EXIT_SUCCESS
    observer.cleanup_recipient.assert_called_once_with(
        RUN10_ID, RUN10_RECIPIENT, phase="post_claim"
    )
