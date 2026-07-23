"""Pre-claim vs post-claim cleanup phase resolver tests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.evaluation.live.cleanup_phase import resolve_cleanup_phase
from app.evaluation.live.exit_codes import EXIT_CLEANUP, EXIT_SUCCESS, EXIT_TRANSPORT
from app.evaluation.live.journal import RunCheckpoint
from app.evaluation.live.reporting import compute_final_exit_code
from app.evaluation.live.runner import cleanup_only


def _checkpoint(run_id: str, *, transitions: list[dict], sender_id: str | None = None) -> RunCheckpoint:
    return RunCheckpoint(
        evaluation_run_id=run_id,
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        tenant_id="TENANT_LIVE_EVAL",
        transport_mode="live_gmail",
        ai_mode="fixture_ai",
        config_hash="hash",
        send_window_start=datetime.now(timezone.utc),
        sender_account_fingerprint="",
        recipient_account_fingerprint="",
        last_state=transitions[-1]["state"] if transitions else "created",
        sender_gmail_message_id=sender_id,
        transitions=transitions,
    )


def test_pre_claim_when_root_not_bound_and_delivery_confirmed():
    checkpoint = _checkpoint(
        "run-pre",
        sender_id="sender-1",
        transitions=[
            {
                "state": "delivery_confirmed",
                "recipient_gmail_message_id": "recipient-1",
            }
        ],
    )
    with patch(
        "app.evaluation.live.cleanup_phase.resolve_recipient_from_journal",
        return_value=type("R", (), {"resolved": True, "recipient_gmail_message_id": "recipient-1", "blocked_reason": None})(),
    ):
        resolution = resolve_cleanup_phase(
            checkpoint,
            root_job_bound=False,
            root_gmail_message_id=None,
        )
    assert resolution.resolved
    assert resolution.phase == "pre_claim"


def test_post_claim_requires_root_binding():
    checkpoint = _checkpoint("run-post", transitions=[])
    resolution = resolve_cleanup_phase(
        checkpoint,
        root_job_bound=True,
        root_gmail_message_id="recipient-root",
    )
    assert resolution.resolved
    assert resolution.phase == "post_claim"


def test_post_claim_without_root_message_id_blocked():
    checkpoint = _checkpoint("run-post-missing", transitions=[])
    resolution = resolve_cleanup_phase(
        checkpoint,
        root_job_bound=True,
        root_gmail_message_id=None,
    )
    assert not resolution.resolved
    assert resolution.blocked_reason == "root_job_bound_without_message_id"


def test_cleanup_only_uses_pre_claim_when_root_not_bound(monkeypatch, tmp_path):
    run_id = "run-cleanup-auto"
    checkpoint = _checkpoint(
        run_id,
        sender_id="sender-1",
        transitions=[
            {
                "state": "delivery_confirmed",
                "recipient_gmail_message_id": "recipient-1",
            }
        ],
    )
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
    from app.evaluation.live.journal import append_transition, ensure_run_directory, write_run_config

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
    for transition in checkpoint.transitions:
        append_transition(run_id, transition)

    observer = MagicMock()
    observer.get_run.return_value = {"root_job_id": None, "root_gmail_message_id": None}
    observer.cleanup_recipient.return_value = {"result": "archived"}
    with patch("app.evaluation.live.runner.LiveEvalObserver", return_value=observer):
        exit_code = cleanup_only(
            base_url="http://127.0.0.1:8010",
            admin_api_key="key",
            tenant_id="TENANT_LIVE_EVAL",
            evaluation_run_id=run_id,
            phase="auto",
        )
    assert exit_code == EXIT_SUCCESS
    observer.cleanup_recipient.assert_called_once_with(run_id, "recipient-1", phase="pre_claim")


def test_pre_claim_blocked_when_root_message_id_present_without_binding():
    checkpoint = _checkpoint(
        "run-contradictory",
        transitions=[
            {
                "state": "delivery_confirmed",
                "recipient_gmail_message_id": "recipient-1",
            }
        ],
    )
    resolution = resolve_cleanup_phase(
        checkpoint,
        root_job_bound=False,
        root_gmail_message_id="recipient-root",
    )
    assert not resolution.resolved
    assert resolution.blocked_reason == "root_message_id_without_binding"


def test_primary_failure_preserved_over_cleanup_failure():
    assert (
        compute_final_exit_code(
            primary_exit_code=EXIT_TRANSPORT,
            cleanup_exit_code=EXIT_CLEANUP,
            artifact_status="present",
        )
        == EXIT_TRANSPORT
    )


def test_primary_success_cleanup_failure_is_exit_cleanup():
    assert (
        compute_final_exit_code(
            primary_exit_code=EXIT_SUCCESS,
            cleanup_exit_code=EXIT_CLEANUP,
            artifact_status="present",
        )
        == EXIT_CLEANUP
    )
