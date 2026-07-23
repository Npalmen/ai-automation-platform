"""Journal-based recipient cleanup resolver tests."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.evaluation.live.cleanup_resolver import resolve_recipient_from_journal
from app.evaluation.live.exit_codes import EXIT_SUCCESS
from app.evaluation.live.journal import (
    RunCheckpoint,
    append_transition,
    ensure_run_directory,
    load_checkpoint,
    write_run_config,
)
from app.evaluation.live.runner import cleanup_only


def _checkpoint(
    run_id: str,
    *,
    transitions: list[dict],
    tenant_id: str = "TENANT_LIVE_EVAL",
    scenario_id: str = "S01_lead_laddbox_quality",
    attempt_id: int = 1,
    sender_id: str | None = None,
) -> RunCheckpoint:
    return RunCheckpoint(
        evaluation_run_id=run_id,
        scenario_id=scenario_id,
        attempt_id=attempt_id,
        tenant_id=tenant_id,
        transport_mode="live_gmail",
        ai_mode="fixture_ai",
        config_hash="abc",
        send_window_start=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        sender_account_fingerprint="",
        recipient_account_fingerprint="",
        last_state=transitions[-1]["state"] if transitions else "created",
        sender_gmail_message_id=sender_id,
        transitions=transitions,
    )


def test_resolver_finds_unique_recipient_from_delivery_confirmed():
    run_id = "run-journal-1"
    checkpoint = _checkpoint(
        run_id,
        sender_id="sender-msg-1",
        transitions=[
            {"state": "sent", "sender_gmail_message_id": "sender-msg-1"},
            {
                "state": "delivery_confirmed",
                "recipient_gmail_message_id": "recipient-msg-1",
            },
        ],
    )
    with patch(
        "app.evaluation.live.cleanup_resolver.load_run_config",
        return_value={
            "evaluation_run_id": run_id,
            "tenant_id": "TENANT_LIVE_EVAL",
            "scenario_id": "S01_lead_laddbox_quality",
            "attempt_id": 1,
        },
    ):
        resolution = resolve_recipient_from_journal(checkpoint)
    assert resolution.resolved
    assert resolution.recipient_gmail_message_id == "recipient-msg-1"


def test_duplicate_transitions_same_recipient_id_allowed():
    checkpoint = _checkpoint(
        "run-journal-dup",
        transitions=[
            {
                "state": "delivery_confirmed",
                "recipient_gmail_message_id": "recipient-msg-1",
            },
            {
                "state": "delivery_confirmed",
                "recipient_gmail_message_id": "recipient-msg-1",
            },
        ],
    )
    with patch(
        "app.evaluation.live.cleanup_resolver.load_run_config",
        return_value={"evaluation_run_id": "run-journal-dup"},
    ):
        resolution = resolve_recipient_from_journal(checkpoint)
    assert resolution.resolved
    assert resolution.recipient_gmail_message_id == "recipient-msg-1"


def test_multiple_distinct_recipient_ids_blocked():
    checkpoint = _checkpoint(
        "run-journal-multi",
        transitions=[
            {
                "state": "delivery_confirmed",
                "recipient_gmail_message_id": "recipient-a",
            },
            {
                "state": "delivery_confirmed",
                "recipient_gmail_message_id": "recipient-b",
            },
        ],
    )
    with patch(
        "app.evaluation.live.cleanup_resolver.load_run_config",
        return_value={"evaluation_run_id": "run-journal-multi"},
    ):
        resolution = resolve_recipient_from_journal(checkpoint)
    assert not resolution.resolved
    assert resolution.blocked_reason == "multiple_distinct_recipient_ids"


def test_sender_id_only_blocked():
    checkpoint = _checkpoint(
        "run-journal-sender",
        sender_id="sender-msg-1",
        transitions=[
            {
                "state": "delivery_confirmed",
                "recipient_gmail_message_id": "sender-msg-1",
            },
        ],
    )
    with patch(
        "app.evaluation.live.cleanup_resolver.load_run_config",
        return_value={"evaluation_run_id": "run-journal-sender"},
    ):
        resolution = resolve_recipient_from_journal(checkpoint)
    assert not resolution.resolved
    assert "sender" in (resolution.blocked_reason or "")


def test_cleanup_only_resolves_from_journal(live_eval_env, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
    run_id = "run-cleanup-journal"
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
    append_transition(run_id, {"state": "sent", "sender_gmail_message_id": "sender-msg-1"})
    append_transition(
        run_id,
        {
            "state": "delivery_confirmed",
            "recipient_gmail_message_id": "recipient-msg-1",
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

    cleanup_mock.assert_called_once_with(run_id, "recipient-msg-1", phase="post_claim")
    assert code == EXIT_SUCCESS


def test_cleanup_only_blocks_when_journal_ambiguous(live_eval_env, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
    run_id = "run-cleanup-ambiguous"
    ensure_run_directory(run_id)
    append_transition(
        run_id,
        {
            "state": "delivery_confirmed",
            "recipient_gmail_message_id": "recipient-a",
        },
    )
    append_transition(
        run_id,
        {
            "state": "delivery_confirmed",
            "recipient_gmail_message_id": "recipient-b",
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

    cleanup_mock.assert_not_called()
    assert code == EXIT_SUCCESS
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["cleanup_state"] == "not_safe_to_execute"
    assert payload["gmail_mutations"] == 0


def test_tenant_metadata_mismatch_blocked():
    checkpoint = _checkpoint(
        "run-journal-tenant",
        tenant_id="TENANT_LIVE_EVAL",
        transitions=[
            {
                "state": "delivery_confirmed",
                "recipient_gmail_message_id": "recipient-msg-1",
            },
        ],
    )
    with patch(
        "app.evaluation.live.cleanup_resolver.load_run_config",
        return_value={
            "evaluation_run_id": "run-journal-tenant",
            "tenant_id": "OTHER_TENANT",
            "scenario_id": "S01_lead_laddbox_quality",
            "attempt_id": 1,
        },
    ):
        resolution = resolve_recipient_from_journal(checkpoint)
    assert not resolution.resolved
    assert resolution.blocked_reason == "tenant_id_mismatch"


def test_scenario_metadata_mismatch_blocked():
    checkpoint = _checkpoint(
        "run-journal-scenario",
        transitions=[
            {
                "state": "delivery_confirmed",
                "recipient_gmail_message_id": "recipient-msg-1",
            },
        ],
    )
    with patch(
        "app.evaluation.live.cleanup_resolver.load_run_config",
        return_value={
            "evaluation_run_id": "run-journal-scenario",
            "tenant_id": "TENANT_LIVE_EVAL",
            "scenario_id": "S99_other",
            "attempt_id": 1,
        },
    ):
        resolution = resolve_recipient_from_journal(checkpoint)
    assert not resolution.resolved
    assert resolution.blocked_reason == "scenario_id_mismatch"


def test_old_run_id_in_config_blocked():
    checkpoint = _checkpoint(
        "run-journal-new",
        transitions=[
            {
                "state": "delivery_confirmed",
                "recipient_gmail_message_id": "recipient-msg-1",
            },
        ],
    )
    with patch(
        "app.evaluation.live.cleanup_resolver.load_run_config",
        return_value={
            "evaluation_run_id": "run-journal-old",
            "tenant_id": "TENANT_LIVE_EVAL",
            "scenario_id": "S01_lead_laddbox_quality",
            "attempt_id": 1,
        },
    ):
        resolution = resolve_recipient_from_journal(checkpoint)
    assert not resolution.resolved
    assert resolution.blocked_reason == "evaluation_run_id_mismatch"


def test_exact_cleanup_makes_at_most_one_mutation(db, live_eval_env, monkeypatch):
    """Resolved journal cleanup must archive exactly one recipient message."""
    from datetime import datetime, timedelta, timezone
    from unittest.mock import MagicMock

    from app.evaluation.live.cleanup import cleanup_recipient_message
    from app.repositories.postgres.live_eval_models import LiveEvalRunRow

    monkeypatch.setenv("EXTERNAL_SIDE_EFFECT_TESTS", "yes")
    from app.evaluation.live.config import get_live_eval_config

    get_live_eval_config.cache_clear()
    now = datetime.now(timezone.utc)
    row = LiveEvalRunRow(
        evaluation_run_id="run-exact-one",
        tenant_id="TENANT_LIVE_EVAL",
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        transport_mode="live_gmail",
        ai_mode="fixture_ai",
        fixture_bundle_id="k2f_bundle_s01",
        expected_sender="sender@eval.test",
        expected_recipient="recipient@eval.test",
        status="active",
        created_by="test",
        created_at=now,
        expires_at=now + timedelta(hours=2),
        config_hash="abc",
        root_gmail_message_id="msg-recipient-exact",
        root_job_id="job-1",
    )
    db.add(row)
    db.commit()
    adapter = MagicMock()
    adapter.execute_action.return_value = {
        "message": {
            "message_id": "msg-recipient-exact",
            "subject": "KROWOLF-EVAL/run-exact-one/S01_lead_laddbox_quality/1 | Test",
            "from": "sender@eval.test",
            "to": "recipient@eval.test",
            "internal_date_ms": int(now.timestamp() * 1000),
            "label_ids": ["x"],
            "body_text": "",
        }
    }
    with patch(
        "app.evaluation.live.cleanup.get_integration_connection_config",
        return_value={},
    ), patch(
        "app.evaluation.live.cleanup.get_integration_adapter",
        return_value=adapter,
    ):
        result = cleanup_recipient_message(
            db,
            evaluation_run_id=row.evaluation_run_id,
            tenant_id=row.tenant_id,
            recipient_gmail_message_id="msg-recipient-exact",
            phase="post_claim",
        )
    assert result["result"] == "archived"
    adapter.client.archive_from_inbox.assert_called_once_with("msg-recipient-exact")


def test_load_checkpoint_uses_delivery_confirmed_recipient(live_eval_env, monkeypatch, tmp_path):
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
    run_id = "run-checkpoint-recipient"
    ensure_run_directory(run_id)
    append_transition(
        run_id,
        {
            "state": "delivery_confirmed",
            "recipient_gmail_message_id": "recipient-from-journal",
        },
    )
    checkpoint = load_checkpoint(run_id)
    assert checkpoint.recipient_gmail_message_id == "recipient-from-journal"
