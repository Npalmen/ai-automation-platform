"""Tests for redacted failure summaries and exit-code priority."""

from __future__ import annotations

from app.evaluation.live.exit_codes import (
    EXIT_CLEANUP,
    EXIT_INFRASTRUCTURE,
    EXIT_SUCCESS,
    EXIT_TRANSPORT,
    EXIT_UNRESOLVED_SEND,
)
from app.evaluation.live.reporting import build_failure_summary, compute_final_exit_code


def test_failure_summary_redacts_gmail_response_body():
    summary = build_failure_summary(
        evaluation_run_id="run-1",
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        failure_category="infrastructure",
        failed_stage="sending",
        primary_exit_code=EXIT_TRANSPORT,
        cleanup_exit_code=None,
        artifact_status="present",
        send_state="outcome_unknown",
        send_attempted=True,
        send_confirmed=False,
        reconciliation_result="transport_error",
        recipient_delivery_observed=False,
        root_job_bound=False,
        cleanup_state="not_run",
        error=RuntimeError(
            'Google Mail forbidden. Response: {"error": {"message": "secret"}}'
        ),
    )
    payload = summary.to_dict()
    assert "refresh_token" not in str(payload)
    assert "secret" not in payload.get("redacted_error", "")
    assert payload["send_state"] == "outcome_unknown"
    assert payload["primary_exit_code"] == EXIT_TRANSPORT
    assert payload["final_exit_code"] == EXIT_TRANSPORT


def test_transport_failure_preserved_over_cleanup_not_safe():
    final_code = compute_final_exit_code(
        primary_exit_code=EXIT_TRANSPORT,
        cleanup_exit_code=None,
        artifact_status="present",
    )
    assert final_code == EXIT_TRANSPORT


def test_transport_failure_preserved_over_artifact_failure():
    final_code = compute_final_exit_code(
        primary_exit_code=EXIT_TRANSPORT,
        cleanup_exit_code=None,
        artifact_status="missing",
    )
    assert final_code == EXIT_TRANSPORT


def test_success_with_artifact_failure_returns_infrastructure():
    final_code = compute_final_exit_code(
        primary_exit_code=EXIT_SUCCESS,
        cleanup_exit_code=None,
        artifact_status="missing",
    )
    assert final_code == EXIT_INFRASTRUCTURE


def test_unresolved_send_preserved_over_cleanup_failure():
    final_code = compute_final_exit_code(
        primary_exit_code=EXIT_UNRESOLVED_SEND,
        cleanup_exit_code=EXIT_CLEANUP,
        artifact_status="present",
    )
    assert final_code == EXIT_UNRESOLVED_SEND


def test_cleanup_failure_when_primary_success():
    final_code = compute_final_exit_code(
        primary_exit_code=EXIT_SUCCESS,
        cleanup_exit_code=EXIT_CLEANUP,
        artifact_status="present",
    )
    assert final_code == EXIT_CLEANUP
