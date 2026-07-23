"""Strict aborted-run cleanup permission contract tests."""

from __future__ import annotations

from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.evaluation.live.cleanup import cleanup_recipient_message
from app.evaluation.live.constants import LIVE_EVAL_MUTATION_CLEANUP_ARCHIVE
from app.evaluation.live.context import live_eval_context
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.safety import validate_live_gmail_run_for_mutation
from app.evaluation.live.schemas import TrustedLiveEvalSnapshot
from app.repositories.postgres.live_eval_models import LiveEvalRunRow


def _aborted_row(**overrides) -> LiveEvalRunRow:
    now = datetime.now(timezone.utc)
    base = dict(
        evaluation_run_id="run-aborted-cleanup",
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
        root_gmail_message_id="msg-recipient-1",
        root_job_id="job-root-1",
    )
    base.update(overrides)
    return LiveEvalRunRow(**base)


def _snapshot(**overrides):
    base = dict(
        evaluation_run_id="run-aborted-cleanup",
        tenant_id="TENANT_LIVE_EVAL",
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        transport_mode="live_gmail",
        ai_mode="fixture_ai",
        fixture_bundle_id="k2f_bundle_s01",
        expected_sender="sender@eval.test",
        expected_recipient="recipient@eval.test",
        config_hash="hash",
        trusted=True,
    )
    base.update(overrides)
    return TrustedLiveEvalSnapshot(**base)


def _cleanup_patches(adapter: MagicMock):
    return (
        patch("app.evaluation.live.cleanup.get_integration_connection_config", return_value={}),
        patch("app.evaluation.live.cleanup.get_integration_adapter", return_value=adapter),
        patch("app.evaluation.live.cleanup.validate_delivery_candidate", return_value=(True, None)),
    )


def test_aborted_post_claim_cleanup_archives_once(db, live_eval_env, monkeypatch):
    monkeypatch.setenv("EXTERNAL_SIDE_EFFECT_TESTS", "yes")
    from app.evaluation.live.config import get_live_eval_config

    get_live_eval_config.cache_clear()
    row = _aborted_row()
    db.add(row)
    db.commit()

    adapter = MagicMock()
    adapter.execute_action.return_value = {"message": {"message_id": "msg-recipient-1"}}
    with ExitStack() as stack:
        for patcher in _cleanup_patches(adapter):
            stack.enter_context(patcher)
        first = cleanup_recipient_message(
            db,
            evaluation_run_id=row.evaluation_run_id,
            tenant_id=row.tenant_id,
            recipient_gmail_message_id="msg-recipient-1",
            phase="post_claim",
        )
        second = cleanup_recipient_message(
            db,
            evaluation_run_id=row.evaluation_run_id,
            tenant_id=row.tenant_id,
            recipient_gmail_message_id="msg-recipient-1",
            phase="post_claim",
        )

    assert first["result"] == "archived"
    assert second["result"] == "already_archived"
    adapter.client.archive_from_inbox.assert_called_once_with("msg-recipient-1")


def test_aborted_gmail_reply_blocked(db, live_eval_env, monkeypatch):
    monkeypatch.setenv("EXTERNAL_SIDE_EFFECT_TESTS", "yes")
    row = _aborted_row()
    db.add(row)
    db.commit()
    snap = _snapshot()
    with live_eval_context(snap, db=db), patch(
        "app.evaluation.live.write_policy.is_external_write_enabled_for_integration",
        return_value=True,
    ), patch("app.evaluation.live.write_policy.emit_live_eval_audit"):
        from app.evaluation.live.write_policy import enforce_live_eval_write_policy

        with pytest.raises(LiveEvalSafetyError):
            enforce_live_eval_write_policy(
                {"type": "send_customer_auto_reply", "to": "sender@eval.test"},
                db=db,
                job=SimpleNamespace(tenant_id="TENANT_LIVE_EVAL"),
            )


def test_aborted_new_send_blocked(db, live_eval_env):
    row = _aborted_row()
    with pytest.raises(LiveEvalSafetyError, match="terminal: aborted"):
        validate_live_gmail_run_for_mutation(row, tenant_id=row.tenant_id)


def test_aborted_other_mutation_blocked(db, live_eval_env):
    row = _aborted_row()
    with pytest.raises(LiveEvalSafetyError, match="terminal: aborted"):
        validate_live_gmail_run_for_mutation(
            row,
            tenant_id=row.tenant_id,
            recipient_message_id="msg-recipient-1",
        )


def test_aborted_wrong_root_message_id_blocked(db, live_eval_env):
    row = _aborted_row()
    with pytest.raises(LiveEvalSafetyError, match="does not match registry root"):
        validate_live_gmail_run_for_mutation(
            row,
            tenant_id=row.tenant_id,
            recipient_message_id="msg-other",
            mutation_operation=LIVE_EVAL_MUTATION_CLEANUP_ARCHIVE,
            cleanup_phase="post_claim",
        )


def test_aborted_cross_tenant_blocked(db, live_eval_env):
    row = _aborted_row()
    with pytest.raises(LiveEvalSafetyError, match="not in LIVE_EVAL_TENANT_IDS"):
        validate_live_gmail_run_for_mutation(
            row,
            tenant_id="TENANT_OTHER",
            recipient_message_id="msg-recipient-1",
            mutation_operation=LIVE_EVAL_MUTATION_CLEANUP_ARCHIVE,
            cleanup_phase="post_claim",
        )


def test_completed_run_cannot_use_aborted_cleanup_exception(db, live_eval_env):
    row = _aborted_row(status="completed")
    with pytest.raises(LiveEvalSafetyError, match="terminal: completed"):
        validate_live_gmail_run_for_mutation(
            row,
            tenant_id=row.tenant_id,
            recipient_message_id="msg-recipient-1",
            mutation_operation=LIVE_EVAL_MUTATION_CLEANUP_ARCHIVE,
            cleanup_phase="post_claim",
        )


def test_expired_run_cannot_use_cleanup_exception(db, live_eval_env):
    row = _aborted_row(
        status="expired",
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    with pytest.raises(LiveEvalSafetyError, match="expired"):
        validate_live_gmail_run_for_mutation(
            row,
            tenant_id=row.tenant_id,
            recipient_message_id="msg-recipient-1",
            mutation_operation=LIVE_EVAL_MUTATION_CLEANUP_ARCHIVE,
            cleanup_phase="post_claim",
        )
