"""Checkpoint, run_config, and resume planner tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.journal import (
    append_transition,
    derive_resume_state,
    load_checkpoint,
    load_run_config,
    write_run_config,
)


@pytest.fixture
def storage_root(tmp_path, live_eval_env, monkeypatch):
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
    from app.evaluation.live.config import get_live_eval_config

    get_live_eval_config.cache_clear()
    yield
    get_live_eval_config.cache_clear()


def _seed_run_config(run_id: str) -> None:
    write_run_config(
        run_id,
        {
            "evaluation_run_id": run_id,
            "scenario_id": "S01_lead_laddbox_quality",
            "attempt_id": 1,
            "tenant_id": "TENANT_LIVE_EVAL",
            "transport_mode": "live_gmail",
            "ai_mode": "fixture_ai",
            "config_hash": "abc123",
            "send_window_start": datetime.now(timezone.utc).isoformat(),
            "sender_account_fingerprint": "senderfp",
            "recipient_account_fingerprint": "recipfp",
        },
    )


def test_run_config_roundtrip(storage_root):
    run_id = "run-cfg-1"
    _seed_run_config(run_id)
    loaded = load_run_config(run_id)
    assert loaded["evaluation_run_id"] == run_id
    assert "@" not in json_dump(loaded)


def json_dump(obj):
    import json

    return json.dumps(obj)


def test_derive_resume_pre_send(storage_root):
    run_id = "run-resume-pre"
    _seed_run_config(run_id)
    append_transition(run_id, {"state": "sender_ready"})
    cp = load_checkpoint(run_id)
    assert derive_resume_state(cp).phase == "pre_send"


def test_derive_resume_reconcile_only(storage_root):
    run_id = "run-resume-sending"
    _seed_run_config(run_id)
    append_transition(run_id, {"state": "sending"})
    cp = load_checkpoint(run_id)
    assert derive_resume_state(cp).phase == "reconcile_only"


def test_derive_resume_post_send(storage_root):
    run_id = "run-resume-sent"
    _seed_run_config(run_id)
    append_transition(run_id, {"state": "sent", "sender_gmail_message_id": "s1"})
    cp = load_checkpoint(run_id)
    assert derive_resume_state(cp).phase == "post_send"


def test_derive_resume_post_delivery(storage_root):
    run_id = "run-resume-delivery"
    _seed_run_config(run_id)
    append_transition(run_id, {"state": "sent", "sender_gmail_message_id": "s1"})
    append_transition(
        run_id,
        {"state": "delivery_confirmed", "recipient_gmail_message_id": "r1"},
    )
    cp = load_checkpoint(run_id)
    assert derive_resume_state(cp).phase == "post_delivery"


def test_derive_resume_post_intake(storage_root):
    run_id = "run-resume-intake"
    _seed_run_config(run_id)
    append_transition(run_id, {"state": "intake_completed", "job_id": "job-1"})
    cp = load_checkpoint(run_id)
    assert derive_resume_state(cp).phase == "post_intake"


def test_terminal_passed_not_resumable(storage_root):
    run_id = "run-terminal"
    _seed_run_config(run_id)
    append_transition(run_id, {"state": "passed"})
    from app.evaluation.live.journal import write_report_atomic
    from app.evaluation.live.schemas import LiveEvalReport

    write_report_atomic(
        run_id,
        LiveEvalReport(evaluation_run_id=run_id, result="passed"),
    )
    cp = load_checkpoint(run_id)
    with pytest.raises(LiveEvalSafetyError, match="terminal_run_not_resumable"):
        derive_resume_state(cp)
