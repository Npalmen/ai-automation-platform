"""Hermetic live runner state machine tests."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.evaluation.live.exit_codes import (
    EXIT_CLEANUP,
    EXIT_CONFIG,
    EXIT_INFRASTRUCTURE,
    EXIT_SUCCESS,
    EXIT_TRANSPORT,
    EXIT_UNRESOLVED_SEND,
)
from app.evaluation.live.gmail_transport import SendOutcome
from app.evaluation.live.journal import load_report
from app.evaluation.live.reporting import build_failure_summary, compute_final_exit_code
from app.evaluation.live.runner import (
    LiveEvalRunner,
    cleanup_not_safe_exit_code,
    cleanup_only,
)
from app.evaluation.live.sender_scope import SenderSendScopeReport


def _runner(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTERNAL_SIDE_EFFECT_TESTS", "yes")
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
    from app.evaluation.live.config import get_live_eval_config

    get_live_eval_config.cache_clear()
    return LiveEvalRunner(
        base_url="http://localhost:8010",
        admin_api_key="key",
        tenant_id="TENANT_LIVE_EVAL",
        scenario_id="S01_lead_laddbox_quality",
        expected_sender="sender@eval.test",
        expected_recipient="recipient@eval.test",
    )


def _preflight_patches(runner):
    return (
        patch.object(
            runner.observer,
            "runtime_readiness",
            return_value={"env": "test", "build_git_sha": ""},
        ),
        patch(
            "app.evaluation.live.runner.run_sender_readiness_read_only",
            return_value=MagicMock(ready=True, issues=[]),
        ),
        patch(
            "app.evaluation.live.sender_scope.verify_sender_send_scope",
            return_value=SenderSendScopeReport(
                verified=True,
                unverifiable=False,
                issues=[],
                granted_send_scopes=["https://www.googleapis.com/auth/gmail.send"],
            ),
        ),
    )


def test_runner_unresolved_send_on_transport_failure(live_eval_env, monkeypatch, tmp_path):
    runner = _runner(tmp_path, monkeypatch)
    readiness, sender_ready, scope = _preflight_patches(runner)
    with readiness, sender_ready, scope, patch.object(
        runner.observer, "register_run"
    ), patch.object(
        runner.observer, "get_run", return_value={"config_hash": "abc", "expires_at": None}
    ), patch(
        "app.evaluation.live.runner.send_scenario_email",
        side_effect=RuntimeError("network"),
    ), patch(
        "app.evaluation.live.runner.reconcile_sent_message",
        return_value=None,
    ), patch.object(runner.observer, "complete_run"):
        code = runner.run()
    assert code == EXIT_UNRESOLVED_SEND
    assert runner._send_state == "outcome_unknown"


def test_runner_transport_before_send_sets_failed_before_send(live_eval_env, monkeypatch, tmp_path):
    runner = _runner(tmp_path, monkeypatch)
    readiness, sender_ready, scope = _preflight_patches(runner)
    with readiness, sender_ready, scope, patch.object(
        runner.observer, "register_run", side_effect=RuntimeError("http down")
    ), patch.object(runner.observer, "complete_run"):
        code = runner.run()
    assert code == EXIT_TRANSPORT
    assert runner._send_state == "failed_before_send"


def test_runner_reconcile_transport_sets_outcome_unknown(live_eval_env, monkeypatch, tmp_path):
    runner = _runner(tmp_path, monkeypatch)
    readiness, sender_ready, scope = _preflight_patches(runner)
    with readiness, sender_ready, scope, patch.object(
        runner.observer, "register_run"
    ), patch.object(
        runner.observer, "get_run", return_value={"config_hash": "abc", "expires_at": None}
    ), patch(
        "app.evaluation.live.runner.send_scenario_email",
        side_effect=RuntimeError("network"),
    ), patch(
        "app.evaluation.live.runner.reconcile_sent_message",
        side_effect=RuntimeError("gmail down"),
    ), patch.object(runner.observer, "complete_run"):
        code = runner.run()
    assert code == EXIT_TRANSPORT
    assert runner._send_state == "outcome_unknown"
    assert runner._reconciliation_result == "transport_error"


def test_scope_failure_before_register_run(live_eval_env, monkeypatch, tmp_path):
    runner = _runner(tmp_path, monkeypatch)
    readiness, sender_ready, _ = _preflight_patches(runner)
    with readiness, sender_ready, patch(
        "app.evaluation.live.sender_scope.verify_sender_send_scope",
        return_value=SenderSendScopeReport(
            verified=False,
            unverifiable=True,
            issues=["missing scope metadata"],
            granted_send_scopes=[],
            failure_category="sender_scope_unverifiable",
        ),
    ), patch.object(runner.observer, "register_run") as register_mock, patch(
        "app.evaluation.live.runner.send_scenario_email"
    ) as send_mock:
        code = runner.run()
    register_mock.assert_not_called()
    send_mock.assert_not_called()
    assert code == EXIT_CONFIG
    assert runner.failure_category == "sender_scope_unverifiable"
    assert runner._send_state == "not_attempted"
    report = load_report(runner.evaluation_run_id)
    assert report is not None


def test_unverifiable_scope_writes_preliminary_report_before_network(
    live_eval_env, monkeypatch, tmp_path
):
    runner = _runner(tmp_path, monkeypatch)
    readiness, sender_ready, _ = _preflight_patches(runner)
    with readiness, sender_ready, patch(
        "app.evaluation.live.sender_scope.verify_sender_send_scope",
        return_value=SenderSendScopeReport(
            verified=False,
            unverifiable=True,
            issues=["missing scope metadata"],
            granted_send_scopes=[],
            failure_category="sender_scope_unverifiable",
        ),
    ), patch.object(runner.observer, "runtime_readiness") as runtime_mock:
        runner.run()
    runtime_mock.assert_not_called()
    report = load_report(runner.evaluation_run_id)
    assert report is not None
    assert runner._send_state == "not_attempted"


def test_config_failure_creates_artifact(live_eval_env, monkeypatch, tmp_path):
    runner = _runner(tmp_path, monkeypatch)
    with patch(
        "app.evaluation.live.runner.validate_config_readiness",
        return_value=["config invalid"],
    ), patch.object(runner.observer, "register_run") as register_mock:
        code = runner.run()
    register_mock.assert_not_called()
    assert code == EXIT_CONFIG
    assert load_report(runner.evaluation_run_id) is not None


def test_cleanup_only_without_message_id_is_not_primary_failure(live_eval_env, monkeypatch, tmp_path):
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
    from app.evaluation.live.journal import append_transition, ensure_run_directory

    run_id = "run-no-id"
    ensure_run_directory(run_id)
    append_transition(run_id, {"state": "created"})
    with patch(
        "app.evaluation.live.runner.acquire_run_writer_lock",
        return_value=MagicMock(),
    ), patch("app.evaluation.live.runner.release_run_writer_lock"):
        code = cleanup_only(
            base_url="http://localhost:8010",
            admin_api_key="key",
            tenant_id="TENANT_LIVE_EVAL",
            evaluation_run_id=run_id,
        )
    assert code == EXIT_SUCCESS


def test_cleanup_only_rejects_sender_id_as_recipient(live_eval_env, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
    from app.evaluation.live.journal import append_transition, ensure_run_directory

    run_id = "run-sender-only"
    ensure_run_directory(run_id)
    append_transition(
        run_id,
        {
            "state": "sent",
            "sender_gmail_message_id": "sender-msg-1",
        },
    )
    with patch(
        "app.evaluation.live.runner.acquire_run_writer_lock",
        return_value=MagicMock(),
    ), patch("app.evaluation.live.runner.release_run_writer_lock"), patch(
        "app.evaluation.live.runner.LiveEvalObserver.cleanup_recipient"
    ) as cleanup_mock:
        code = cleanup_only(
            base_url="http://localhost:8010",
            admin_api_key="key",
            tenant_id="TENANT_LIVE_EVAL",
            evaluation_run_id=run_id,
            recipient_gmail_message_id="sender-msg-1",
        )
    cleanup_mock.assert_not_called()
    assert code == EXIT_SUCCESS
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["cleanup_state"] == "not_safe_to_execute"
    assert payload["gmail_mutations"] == 0
    assert payload["cleanup_exit_code"] is None


def test_runner_intake_skip_uses_config_not_transport(live_eval_env, monkeypatch, tmp_path):
    runner = _runner(tmp_path, monkeypatch)
    readiness, sender_ready, scope = _preflight_patches(runner)
    intake_payload = {
        "error_code": "intake_skipped",
        "intake_result": "skipped",
        "intake_skip_reason": "missing_intake_cutoff",
        "evaluation_run_id": runner.evaluation_run_id,
        "failed_stage": "triggering_intake",
        "http_status": 409,
        "run_status": "registered",
        "root_claimed": False,
        "job_created": False,
        "retry_allowed": False,
        "diagnostic_code": "INTAKE_GATE_MISSING_CUTOFF",
    }
    from app.evaluation.live.errors import LiveEvalIntakeSkippedError

    with readiness, sender_ready, scope, patch.object(
        runner.observer, "register_run"
    ), patch.object(
        runner.observer, "get_run", return_value={"config_hash": "abc", "expires_at": None}
    ), patch(
        "app.evaluation.live.runner.send_scenario_email",
        return_value=(
            SendOutcome(
                sender_gmail_message_id="sender-1",
                sender_gmail_thread_id="thread-1",
                rfc_message_id=None,
                reconciled=False,
            ),
            [],
        ),
    ), patch.object(
        runner.observer,
        "poll_delivery",
        return_value={
            "valid_count": 1,
            "confirmed": {"message_id": "recipient-1", "thread_id": "t2"},
            "duplicate_detected": False,
        },
    ), patch.object(
        runner.observer,
        "process_delivery",
        side_effect=LiveEvalIntakeSkippedError(intake_payload),
    ), patch.object(runner.observer, "complete_run"):
        code = runner.run()

    assert code == EXIT_CONFIG
    assert runner.failure_category == "intake_skipped"
    assert runner._intake_skip_reason == "missing_intake_cutoff"
    assert runner._last_failure_summary is not None
    assert runner._last_failure_summary.get("intake_skip_reason") == "missing_intake_cutoff"
    assert runner._last_failure_summary.get("primary_exit_code") == EXIT_CONFIG
    assert runner._last_failure_summary.get("final_exit_code") == EXIT_CONFIG


def test_cleanup_only_resolves_recipient_from_journal(live_eval_env, monkeypatch, tmp_path):
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
    from app.evaluation.live.journal import append_transition, ensure_run_directory

    run_id = "run-runner-journal-cleanup"
    ensure_run_directory(run_id)
    append_transition(run_id, {"state": "sent", "sender_gmail_message_id": "sender-msg-1"})
    append_transition(
        run_id,
        {
            "state": "delivery_confirmed",
            "recipient_gmail_message_id": "recipient-msg-journal",
        },
    )
    with patch(
        "app.evaluation.live.runner.acquire_run_writer_lock",
        return_value=MagicMock(),
    ), patch("app.evaluation.live.runner.release_run_writer_lock"), patch(
        "app.evaluation.live.runner.LiveEvalObserver.cleanup_recipient"
    ) as cleanup_mock:
        code = cleanup_only(
            base_url="http://localhost:8010",
            admin_api_key="key",
            tenant_id="TENANT_LIVE_EVAL",
            evaluation_run_id=run_id,
        )
    cleanup_mock.assert_called_once_with(run_id, "recipient-msg-journal", phase="post_claim")
    assert code == EXIT_SUCCESS


def test_cleanup_not_safe_exit_after_primary_failure_returns_success(live_eval_env, monkeypatch, tmp_path):
    """Workflow cleanup step must not mask an existing primary scenario failure."""
    from datetime import datetime, timezone

    from app.evaluation.live.journal import append_transition, ensure_run_directory, write_report_atomic
    from app.evaluation.live.schemas import LiveEvalReport

    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
    run_id = "run-cleanup-after-fail"
    ensure_run_directory(run_id)
    append_transition(run_id, {"state": "triggering_intake"})
    summary = build_failure_summary(
        evaluation_run_id=run_id,
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        failure_category="intake_skipped",
        failed_stage="triggering_intake",
        primary_exit_code=EXIT_CONFIG,
        cleanup_exit_code=None,
        artifact_status="present",
        send_state="confirmed",
        send_attempted=True,
        send_confirmed=True,
        reconciliation_result="one",
        recipient_delivery_observed=True,
        root_job_bound=False,
        cleanup_state="not_run",
        intake_skip_reason="missing_intake_cutoff",
    )
    write_report_atomic(
        run_id,
        LiveEvalReport(
            evaluation_run_id=run_id,
            scenario_id="S01_lead_laddbox_quality",
            attempt_id=1,
            result="failed",
            failure_summary=summary.to_dict(),
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        ),
    )
    assert cleanup_not_safe_exit_code(run_id) == EXIT_SUCCESS
    final_code = compute_final_exit_code(
        primary_exit_code=EXIT_CONFIG,
        cleanup_exit_code=None,
        artifact_status="present",
    )
    assert final_code == EXIT_CONFIG

    with patch(
        "app.evaluation.live.runner.acquire_run_writer_lock",
        return_value=MagicMock(),
    ), patch("app.evaluation.live.runner.release_run_writer_lock"), patch(
        "app.evaluation.live.runner.LiveEvalObserver.cleanup_recipient"
    ) as cleanup_mock:
        code = cleanup_only(
            base_url="http://localhost:8010",
            admin_api_key="key",
            tenant_id="TENANT_LIVE_EVAL",
            evaluation_run_id=run_id,
        )
    cleanup_mock.assert_not_called()
    assert code == EXIT_SUCCESS


def test_cleanup_not_safe_exit_after_primary_pass_returns_cleanup(live_eval_env, monkeypatch, tmp_path, capsys):
    """Passed scenario with blocked cleanup must fail cleanup, not report PASS."""
    from datetime import datetime, timezone

    from app.evaluation.live.journal import append_transition, ensure_run_directory, write_report_atomic
    from app.evaluation.live.schemas import LiveEvalReport

    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
    run_id = "run-cleanup-after-pass"
    ensure_run_directory(run_id)
    append_transition(run_id, {"state": "passed"})
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
        reconciliation_result="one",
        recipient_delivery_observed=True,
        root_job_bound=True,
        cleanup_state="not_run",
    )
    write_report_atomic(
        run_id,
        LiveEvalReport(
            evaluation_run_id=run_id,
            scenario_id="S01_lead_laddbox_quality",
            attempt_id=1,
            result="passed",
            failure_summary=summary.to_dict(),
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        ),
    )
    assert cleanup_not_safe_exit_code(run_id) == EXIT_CLEANUP

    with patch(
        "app.evaluation.live.runner.acquire_run_writer_lock",
        return_value=MagicMock(),
    ), patch("app.evaluation.live.runner.release_run_writer_lock"), patch(
        "app.evaluation.live.runner.LiveEvalObserver.cleanup_recipient"
    ) as cleanup_mock:
        code = cleanup_only(
            base_url="http://localhost:8010",
            admin_api_key="key",
            tenant_id="TENANT_LIVE_EVAL",
            evaluation_run_id=run_id,
        )

    cleanup_mock.assert_not_called()
    assert code == EXIT_CLEANUP
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["cleanup_state"] == "not_safe_to_execute"
    assert payload["cleanup_exit_code"] == EXIT_CLEANUP
    assert payload["gmail_mutations"] == 0
    final_code = compute_final_exit_code(
        primary_exit_code=EXIT_SUCCESS,
        cleanup_exit_code=EXIT_CLEANUP,
        artifact_status="present",
    )
    assert final_code == EXIT_CLEANUP
    report = load_report(run_id)
    assert report["result"] == "passed"


def test_exit_infrastructure_is_seven():
    assert EXIT_INFRASTRUCTURE == 7
