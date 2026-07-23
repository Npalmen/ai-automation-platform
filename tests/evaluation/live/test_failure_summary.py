"""Tests for redacted failure summaries and exit-code priority."""

from __future__ import annotations

from app.evaluation.live.exit_codes import (
    EXIT_CLEANUP,
    EXIT_CONFIG,
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


def test_intake_skip_reason_in_failure_summary():
    from app.evaluation.live.exit_codes import EXIT_CONFIG

    summary = build_failure_summary(
        evaluation_run_id="run-intake-skip",
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
    payload = summary.to_dict()
    assert payload["intake_skip_reason"] == "missing_intake_cutoff"
    assert payload["primary_exit_code"] == EXIT_CONFIG
    assert payload["final_exit_code"] == EXIT_CONFIG


def test_cleanup_failure_when_primary_success():
    final_code = compute_final_exit_code(
        primary_exit_code=EXIT_SUCCESS,
        cleanup_exit_code=EXIT_CLEANUP,
        artifact_status="present",
    )
    assert final_code == EXIT_CLEANUP


def test_cleanup_not_safe_preserves_primary_failure_exit():
    """Primary already failed: not_safe cleanup must not mask with EXIT_CLEANUP."""
    final_code = compute_final_exit_code(
        primary_exit_code=EXIT_CONFIG,
        cleanup_exit_code=None,
        artifact_status="present",
    )
    assert final_code == EXIT_CONFIG


def test_cleanup_not_safe_after_primary_success_becomes_cleanup_failure():
    """Primary passed but cleanup blocked: final exit must be EXIT_CLEANUP."""
    final_code = compute_final_exit_code(
        primary_exit_code=EXIT_SUCCESS,
        cleanup_exit_code=EXIT_CLEANUP,
        artifact_status="present",
    )
    assert final_code == EXIT_CLEANUP


def test_failure_summary_mutation_fields_from_adapter():
    summary = build_failure_summary(
        evaluation_run_id="run-obs",
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        failure_category=None,
        failed_stage="passed",
        primary_exit_code=EXIT_SUCCESS,
        cleanup_exit_code=EXIT_SUCCESS,
        artifact_status="present",
        send_state="confirmed",
        send_attempted=True,
        send_confirmed=True,
        reconciliation_result="not_run",
        recipient_delivery_observed=True,
        root_job_bound=True,
        cleanup_state="success",
        workflow_cleanup_mutations=1,
        cleanup_adapter_called=True,
        cleanup_adapter_result="archived",
    )
    payload = summary.to_dict()
    assert payload["workflow_cleanup_mutations"] == 1
    assert payload["scenario_cleanup_mutations"] == 0
    assert payload["total_gmail_mutations"] == 1
    assert payload["cleanup_adapter_called"] is True
    assert payload["cleanup_adapter_result"] == "archived"
