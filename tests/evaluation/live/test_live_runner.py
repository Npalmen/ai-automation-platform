"""Hermetic live runner state machine tests."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.evaluation.live.exit_codes import (
    EXIT_CONFIG,
    EXIT_INFRASTRUCTURE,
    EXIT_SUCCESS,
    EXIT_TRANSPORT,
    EXIT_UNRESOLVED_SEND,
)
from app.evaluation.live.journal import load_report
from app.evaluation.live.runner import LiveEvalRunner, cleanup_only
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


def test_exit_infrastructure_is_seven():
    assert EXIT_INFRASTRUCTURE == 7
