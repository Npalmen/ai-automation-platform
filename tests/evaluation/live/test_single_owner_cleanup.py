"""Single-owner cleanup contract and run #13 hermetic reproduction.

Run #13 note: legacy artifacts recorded cleanup_ok=true after the cleanup endpoint
returned HTTP success, but did not persist adapter result or mutation counters.
The first adapter outcome therefore cannot be proven retroactively.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.evaluation.live.cleanup import cleanup_recipient_message
from app.evaluation.live.constants import (
    CLEANUP_STATE_ALREADY_ARCHIVED,
    CLEANUP_STATE_DEFERRED,
    CLEANUP_STATE_FAILED,
    CLEANUP_STATE_SUCCESS,
    LIVE_EVAL_MUTATION_CLEANUP_ARCHIVE,
)
from app.evaluation.live.errors import LiveEvalSafetyError
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
    LiveEvalRunner,
    cleanup_only,
    resolve_post_cleanup_run_status,
)
from app.evaluation.live.safety import validate_live_gmail_run_for_mutation
from app.evaluation.live.schemas import LiveEvalReport

RUN13_ID = "run13-single-owner"
RUN13_RECIPIENT = "msg-recipient-run13"
RUN13_SENDER = "msg-sender-run13"
RUN13_JOB = "job-root-run13"


def _seed_run13_journal(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
    ensure_run_directory(RUN13_ID)
    write_run_config(
        RUN13_ID,
        {
            "evaluation_run_id": RUN13_ID,
            "tenant_id": "TENANT_LIVE_EVAL",
            "scenario_id": "S01_lead_laddbox_quality",
            "attempt_id": 1,
        },
    )
    for transition in [
        {"state": "delivery_confirmed", "recipient_gmail_message_id": RUN13_RECIPIENT},
        {"state": "intake_completed", "job_id": RUN13_JOB, "pipeline_run_id": None},
        {"state": "pipeline_completed"},
        {"state": "passed"},
    ]:
        append_transition(RUN13_ID, transition)


def _write_passed_report(run_id: str, *, cleanup_state: str = CLEANUP_STATE_DEFERRED) -> None:
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


def _write_failed_report(run_id: str) -> None:
    summary = build_failure_summary(
        evaluation_run_id=run_id,
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        failure_category="assertion_failure",
        failed_stage="asserting",
        primary_exit_code=4,
        cleanup_exit_code=None,
        artifact_status="present",
        send_state="confirmed",
        send_attempted=True,
        send_confirmed=True,
        reconciliation_result="not_run",
        recipient_delivery_observed=True,
        root_job_bound=True,
        cleanup_state="not_run",
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
            result="failed",
            failure_summary=summary.to_dict(),
        ),
    )


def _cleanup_patches(observer_cls):
    return (
        patch("app.evaluation.live.runner.acquire_run_writer_lock", return_value=MagicMock()),
        patch("app.evaluation.live.runner.release_run_writer_lock"),
        patch("app.evaluation.live.runner.LiveEvalObserver", observer_cls),
    )


def test_run13_workflow_cleanup_single_archive_and_complete(
    live_eval_env, monkeypatch, tmp_path, capsys
):
    """Run #13 logical state: deferred scenario cleanup + one workflow archive."""
    _seed_run13_journal(tmp_path, monkeypatch)
    _write_passed_report(RUN13_ID)

    with patch("app.evaluation.live.runner.LiveEvalObserver") as observer_cls:
        observer = observer_cls.return_value
        observer.get_run.return_value = {
            "root_job_id": RUN13_JOB,
            "root_gmail_message_id": RUN13_RECIPIENT,
            "status": "active",
        }
        observer.cleanup_recipient.return_value = {"result": "archived", "phase": "post_claim"}
        lock, release, _ = _cleanup_patches(observer_cls)
        with lock, release:
            code = cleanup_only(
                base_url="http://localhost:8010",
                admin_api_key="key",
                tenant_id="TENANT_LIVE_EVAL",
                evaluation_run_id=RUN13_ID,
                phase="post_claim",
            )

    assert code == EXIT_SUCCESS
    observer.cleanup_recipient.assert_called_once_with(
        RUN13_ID, RUN13_RECIPIENT, phase="post_claim"
    )
    observer.complete_run.assert_called_once_with(RUN13_ID, "completed")
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["workflow_cleanup_mutations"] == 1
    assert payload["total_gmail_mutations"] == 1
    report = load_report(RUN13_ID)
    assert report["failure_summary"]["cleanup_state"] == CLEANUP_STATE_SUCCESS
    assert report["failure_summary"]["recipient_delivery_observed"] is True


def test_run13_second_cleanup_is_idempotent_skip(live_eval_env, monkeypatch, tmp_path, capsys):
    _seed_run13_journal(tmp_path, monkeypatch)
    _write_passed_report(RUN13_ID, cleanup_state=CLEANUP_STATE_SUCCESS)
    report = load_report(RUN13_ID)
    report["failure_summary"]["workflow_cleanup_mutations"] = 1
    report["failure_summary"]["total_gmail_mutations"] = 1
    write_report_atomic(RUN13_ID, LiveEvalReport.model_validate(report))

    with patch("app.evaluation.live.runner.LiveEvalObserver") as observer_cls:
        lock, release, _ = _cleanup_patches(observer_cls)
        with lock, release:
            code = cleanup_only(
                base_url="http://localhost:8010",
                admin_api_key="key",
                tenant_id="TENANT_LIVE_EVAL",
                evaluation_run_id=RUN13_ID,
                phase="post_claim",
            )

    assert code == EXIT_SUCCESS
    observer_cls.return_value.cleanup_recipient.assert_not_called()
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["idempotent"] is True
    assert payload["gmail_mutations"] == 0


def test_run13_already_archived_adapter_result(live_eval_env, monkeypatch, tmp_path, capsys):
    _seed_run13_journal(tmp_path, monkeypatch)
    _write_passed_report(RUN13_ID)

    with patch("app.evaluation.live.runner.LiveEvalObserver") as observer_cls:
        observer = observer_cls.return_value
        observer.get_run.return_value = {
            "root_job_id": RUN13_JOB,
            "root_gmail_message_id": RUN13_RECIPIENT,
            "status": "active",
        }
        observer.cleanup_recipient.return_value = {"result": "already_archived"}
        lock, release, _ = _cleanup_patches(observer_cls)
        with lock, release:
            code = cleanup_only(
                base_url="http://localhost:8010",
                admin_api_key="key",
                tenant_id="TENANT_LIVE_EVAL",
                evaluation_run_id=RUN13_ID,
                phase="post_claim",
            )

    assert code == EXIT_SUCCESS
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["cleanup_adapter_result"] == "already_archived"
    assert payload["workflow_cleanup_mutations"] == 0
    report = load_report(RUN13_ID)
    assert report["failure_summary"]["cleanup_state"] == CLEANUP_STATE_ALREADY_ARCHIVED


def test_run13_completed_before_workflow_cleanup_fails(live_eval_env, monkeypatch, tmp_path, capsys):
    """Legacy double-cleanup bug: premature complete_run blocks workflow cleanup."""
    _seed_run13_journal(tmp_path, monkeypatch)
    _write_passed_report(RUN13_ID, cleanup_state=CLEANUP_STATE_DEFERRED)

    with patch("app.evaluation.live.runner.LiveEvalObserver") as observer_cls:
        observer = observer_cls.return_value
        observer.get_run.return_value = {
            "root_job_id": RUN13_JOB,
            "root_gmail_message_id": RUN13_RECIPIENT,
            "status": "completed",
        }
        response = httpx.Response(400, request=httpx.Request("POST", "http://test/cleanup"))
        observer.cleanup_recipient.side_effect = httpx.HTTPStatusError(
            "blocked", request=response.request, response=response
        )
        lock, release, _ = _cleanup_patches(observer_cls)
        with lock, release:
            code = cleanup_only(
                base_url="http://localhost:8010",
                admin_api_key="key",
                tenant_id="TENANT_LIVE_EVAL",
                evaluation_run_id=RUN13_ID,
                phase="post_claim",
            )

    assert code == EXIT_CLEANUP
    observer.cleanup_recipient.assert_called_once()
    observer.complete_run.assert_not_called()


def test_scenario_pass_cleanup_http_failure(live_eval_env, monkeypatch, tmp_path, capsys):
    _seed_run13_journal(tmp_path, monkeypatch)
    _write_passed_report(RUN13_ID)

    with patch("app.evaluation.live.runner.LiveEvalObserver") as observer_cls:
        observer = observer_cls.return_value
        observer.get_run.return_value = {
            "root_job_id": RUN13_JOB,
            "root_gmail_message_id": RUN13_RECIPIENT,
            "status": "active",
        }
        response = httpx.Response(500, request=httpx.Request("POST", "http://test/cleanup"))
        observer.cleanup_recipient.side_effect = httpx.HTTPStatusError(
            "server error", request=response.request, response=response
        )
        lock, release, _ = _cleanup_patches(observer_cls)
        with lock, release:
            code = cleanup_only(
                base_url="http://localhost:8010",
                admin_api_key="key",
                tenant_id="TENANT_LIVE_EVAL",
                evaluation_run_id=RUN13_ID,
                phase="post_claim",
            )

    assert code == EXIT_CLEANUP
    observer.complete_run.assert_called_once_with(RUN13_ID, "aborted")
    report = load_report(RUN13_ID)
    assert report["failure_summary"]["cleanup_state"] == CLEANUP_STATE_FAILED
    assert report["result"] == "passed"
    assert report["failure_summary"]["primary_exit_code"] == EXIT_SUCCESS


def test_scenario_failure_cleanup_failure_keeps_aborted(
    live_eval_env, monkeypatch, tmp_path, capsys
):
    _seed_run13_journal(tmp_path, monkeypatch)
    _write_failed_report(RUN13_ID)

    with patch("app.evaluation.live.runner.LiveEvalObserver") as observer_cls:
        observer = observer_cls.return_value
        observer.get_run.return_value = {
            "root_job_id": RUN13_JOB,
            "root_gmail_message_id": RUN13_RECIPIENT,
            "status": "aborted",
        }
        response = httpx.Response(500, request=httpx.Request("POST", "http://test/cleanup"))
        observer.cleanup_recipient.side_effect = httpx.HTTPStatusError(
            "server error", request=response.request, response=response
        )
        lock, release, _ = _cleanup_patches(observer_cls)
        with lock, release:
            code = cleanup_only(
                base_url="http://localhost:8010",
                admin_api_key="key",
                tenant_id="TENANT_LIVE_EVAL",
                evaluation_run_id=RUN13_ID,
                phase="post_claim",
            )

    assert code == EXIT_CLEANUP
    observer.complete_run.assert_not_called()
    report = load_report(RUN13_ID)
    assert report["result"] == "failed"
    assert report["failure_summary"]["cleanup_state"] == CLEANUP_STATE_FAILED


def test_cleanup_failure_never_leaves_active_status():
    assert resolve_post_cleanup_run_status(
        scenario_passed=True,
        cleanup_succeeded=False,
        current_status="active",
    ) == "aborted"


def test_double_cleanup_only_one_archive_call(live_eval_env, monkeypatch, tmp_path):
    _seed_run13_journal(tmp_path, monkeypatch)
    _write_passed_report(RUN13_ID)

    with patch("app.evaluation.live.runner.LiveEvalObserver") as observer_cls:
        observer = observer_cls.return_value
        observer.get_run.return_value = {
            "root_job_id": RUN13_JOB,
            "root_gmail_message_id": RUN13_RECIPIENT,
            "status": "active",
        }
        observer.cleanup_recipient.return_value = {"result": "archived"}
        lock, release, _ = _cleanup_patches(observer_cls)
        with lock, release:
            first = cleanup_only(
                base_url="http://localhost:8010",
                admin_api_key="key",
                tenant_id="TENANT_LIVE_EVAL",
                evaluation_run_id=RUN13_ID,
                phase="post_claim",
            )
            second = cleanup_only(
                base_url="http://localhost:8010",
                admin_api_key="key",
                tenant_id="TENANT_LIVE_EVAL",
                evaluation_run_id=RUN13_ID,
                phase="post_claim",
            )

    assert first == EXIT_SUCCESS
    assert second == EXIT_SUCCESS
    observer.cleanup_recipient.assert_called_once()


def test_aborted_pre_claim_allowed_with_exact_journal_recipient(db, live_eval_env, monkeypatch, tmp_path):
    from datetime import timedelta

    from app.repositories.postgres.live_eval_models import LiveEvalRunRow

    run_id = "run-preclaim-hermetic"
    recipient_id = "msg-preclaim-recipient"
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
    now = datetime.now(timezone.utc)
    row = LiveEvalRunRow(
        evaluation_run_id=run_id,
        tenant_id="TENANT_LIVE_EVAL",
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        transport_mode="live_gmail",
        ai_mode="fixture_ai",
        fixture_bundle_id="k2f_bundle_s01",
        expected_sender="sender@eval.test",
        expected_recipient="recipient@eval.test",
        status="aborted",
        created_by="test",
        created_at=now,
        expires_at=now + timedelta(hours=2),
        config_hash="hash",
    )
    db.add(row)
    db.commit()

    validate_live_gmail_run_for_mutation(
        row,
        tenant_id=row.tenant_id,
        recipient_message_id=recipient_id,
        mutation_operation=LIVE_EVAL_MUTATION_CLEANUP_ARCHIVE,
        cleanup_phase="pre_claim",
    )

    monkeypatch.setenv("EXTERNAL_SIDE_EFFECT_TESTS", "yes")
    adapter = MagicMock()
    adapter.execute_action.return_value = {"message": {"message_id": recipient_id}}
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
            evaluation_run_id=run_id,
            tenant_id=row.tenant_id,
            recipient_gmail_message_id=recipient_id,
            phase="pre_claim",
        )
    assert result["result"] == "archived"
    adapter.client.archive_from_inbox.assert_called_once_with(recipient_id)


def test_aborted_pre_claim_blocks_wrong_recipient(db, live_eval_env, monkeypatch, tmp_path):
    from datetime import timedelta

    from app.repositories.postgres.live_eval_models import LiveEvalRunRow

    run_id = "run-preclaim-wrong-id"
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
        {"state": "delivery_confirmed", "recipient_gmail_message_id": "msg-expected"},
    )
    now = datetime.now(timezone.utc)
    row = LiveEvalRunRow(
        evaluation_run_id=run_id,
        tenant_id="TENANT_LIVE_EVAL",
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        transport_mode="live_gmail",
        ai_mode="fixture_ai",
        fixture_bundle_id="k2f_bundle_s01",
        expected_sender="sender@eval.test",
        expected_recipient="recipient@eval.test",
        status="aborted",
        created_by="test",
        created_at=now,
        expires_at=now + timedelta(hours=2),
        config_hash="hash",
    )
    db.add(row)
    db.commit()
    with pytest.raises(LiveEvalSafetyError, match="does not match journal"):
        validate_live_gmail_run_for_mutation(
            row,
            tenant_id=row.tenant_id,
            recipient_message_id="msg-other",
            mutation_operation=LIVE_EVAL_MUTATION_CLEANUP_ARCHIVE,
            cleanup_phase="pre_claim",
        )


def test_aborted_pre_claim_blocks_root_binding(db, live_eval_env):
    from datetime import timedelta

    from app.repositories.postgres.live_eval_models import LiveEvalRunRow

    now = datetime.now(timezone.utc)
    row = LiveEvalRunRow(
        evaluation_run_id="run-preclaim-root-bound",
        tenant_id="TENANT_LIVE_EVAL",
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        transport_mode="live_gmail",
        ai_mode="fixture_ai",
        fixture_bundle_id="k2f_bundle_s01",
        expected_sender="sender@eval.test",
        expected_recipient="recipient@eval.test",
        status="aborted",
        created_by="test",
        created_at=now,
        expires_at=now + timedelta(hours=2),
        config_hash="hash",
        root_job_id="job-1",
        root_gmail_message_id="msg-1",
    )
    with pytest.raises(LiveEvalSafetyError, match="root_job_id is set"):
        validate_live_gmail_run_for_mutation(
            row,
            tenant_id=row.tenant_id,
            recipient_message_id="msg-1",
            mutation_operation=LIVE_EVAL_MUTATION_CLEANUP_ARCHIVE,
            cleanup_phase="pre_claim",
        )


def test_aborted_pre_claim_cross_tenant_blocked(db, live_eval_env):
    from datetime import timedelta

    from app.repositories.postgres.live_eval_models import LiveEvalRunRow

    now = datetime.now(timezone.utc)
    row = LiveEvalRunRow(
        evaluation_run_id="run-preclaim-cross-tenant",
        tenant_id="TENANT_LIVE_EVAL",
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        transport_mode="live_gmail",
        ai_mode="fixture_ai",
        fixture_bundle_id="k2f_bundle_s01",
        expected_sender="sender@eval.test",
        expected_recipient="recipient@eval.test",
        status="aborted",
        created_by="test",
        created_at=now,
        expires_at=now + timedelta(hours=2),
        config_hash="hash",
    )
    with pytest.raises(LiveEvalSafetyError, match="not in LIVE_EVAL_TENANT_IDS"):
        validate_live_gmail_run_for_mutation(
            row,
            tenant_id="TENANT_OTHER",
            recipient_message_id="msg-1",
            mutation_operation=LIVE_EVAL_MUTATION_CLEANUP_ARCHIVE,
            cleanup_phase="pre_claim",
        )


def test_scenario_failure_cleanup_success_does_not_complete_run(
    live_eval_env, monkeypatch, tmp_path, capsys
):
    _seed_run13_journal(tmp_path, monkeypatch)
    _write_failed_report(RUN13_ID)

    with patch("app.evaluation.live.runner.LiveEvalObserver") as observer_cls:
        observer = observer_cls.return_value
        observer.get_run.return_value = {
            "root_job_id": RUN13_JOB,
            "root_gmail_message_id": RUN13_RECIPIENT,
            "status": "aborted",
        }
        observer.cleanup_recipient.return_value = {"result": "archived"}
        lock, release, _ = _cleanup_patches(observer_cls)
        with lock, release:
            code = cleanup_only(
                base_url="http://localhost:8010",
                admin_api_key="key",
                tenant_id="TENANT_LIVE_EVAL",
                evaluation_run_id=RUN13_ID,
                phase="post_claim",
            )

    assert code == EXIT_SUCCESS
    observer.complete_run.assert_not_called()


def test_delivery_summary_follows_transition_journal(live_eval_env, monkeypatch, tmp_path):
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
    runner = LiveEvalRunner(
        base_url="http://localhost:8010",
        admin_api_key="key",
        tenant_id="TENANT_LIVE_EVAL",
        scenario_id="S01_lead_laddbox_quality",
        expected_sender="sender@eval.test",
        expected_recipient="recipient@eval.test",
        evaluation_run_id=RUN13_ID,
    )
    ensure_run_directory(RUN13_ID)
    append_transition(
        RUN13_ID,
        {"state": "delivery_confirmed", "recipient_gmail_message_id": RUN13_RECIPIENT},
    )
    assert runner._delivery_observed() is True


def test_mutation_summary_follows_adapter_outcome():
    summary = build_failure_summary(
        evaluation_run_id=RUN13_ID,
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
        cleanup_state=CLEANUP_STATE_SUCCESS,
        workflow_cleanup_mutations=1,
        cleanup_adapter_called=True,
        cleanup_adapter_result="archived",
    )
    payload = summary.to_dict()
    assert payload["workflow_cleanup_mutations"] == 1
    assert payload["total_gmail_mutations"] == 1
    assert payload["cleanup_adapter_result"] == "archived"


def test_runner_success_path_defers_cleanup_without_complete_run():
    """Success tail in _run_main_scenario must defer cleanup and not finalize run."""
    import inspect
    from app.evaluation.live import runner as runner_module

    source = inspect.getsource(runner_module.LiveEvalRunner._run_main_scenario)
    success_tail = source.split("if violations:")[-1]
    assert "_cleanup_all" not in success_tail
    assert "CLEANUP_STATE_DEFERRED" in success_tail
    assert "complete_run" not in success_tail
