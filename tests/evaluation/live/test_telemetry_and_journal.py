"""Telemetry idempotency and journal durability tests."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.evaluation.live.context import live_eval_context
from app.evaluation.live.journal import append_transition, load_transitions, write_report_atomic
from app.evaluation.live.redaction import redact_sensitive
from app.evaluation.live.schemas import LiveEvalReport, TrustedLiveEvalSnapshot
from app.evaluation.live.telemetry import record_live_eval_external_event
from app.repositories.postgres.live_eval_models import LiveEvalRunRow


def _snapshot():
    return TrustedLiveEvalSnapshot(
        evaluation_run_id="run-telemetry",
        tenant_id="TENANT_LIVE_EVAL",
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        transport_mode="live_gmail",
        ai_mode="fixture_ai",
        fixture_bundle_id="k2f_bundle_s01",
        expected_sender="sender@eval.test",
        expected_recipient="recipient@eval.test",
        config_hash="abc123",
        trusted=True,
    )


def test_telemetry_event_key_is_idempotent(db, live_eval_env, sample_run_row):
    sample_run_row.evaluation_run_id = "run-telemetry"
    sample_run_row.status = "active"
    db.add(sample_run_row)
    db.commit()

    snap = _snapshot()
    op_key = f"run-telemetry:app_external_write_blocked:send_email:op-1"
    with live_eval_context(snap):
        first = record_live_eval_external_event(
            db,
            operation_key=op_key,
            category="app_external_write_blocked",
            operation="send_email",
            integration_type="google_mail",
            outcome="blocked",
            job_id="job-1",
            snapshot=snap,
            attempt=1,
        )
        second = record_live_eval_external_event(
            db,
            operation_key=op_key,
            category="app_external_write_blocked",
            operation="send_email",
            integration_type="google_mail",
            outcome="blocked",
            job_id="job-1",
            snapshot=snap,
            attempt=1,
        )
    assert first is True
    assert second is False


def test_journal_append_and_atomic_report(tmp_path, live_eval_env, monkeypatch):
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
    from app.core.settings import get_settings
    from app.evaluation.live.config import get_live_eval_config

    get_settings.cache_clear()
    get_live_eval_config.cache_clear()

    run_id = "run-journal"
    append_transition(run_id, {"state": "registered"})
    append_transition(run_id, {"state": "dry_run_complete"})

    transitions = load_transitions(run_id)
    assert len(transitions) == 2

    report_path = write_report_atomic(
        run_id,
        LiveEvalReport(
            evaluation_run_id=run_id,
            scenario_id="S01_lead_laddbox_quality",
            result="dry_run",
            state_transitions=transitions,
        ),
    )
    assert report_path.exists()
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["evaluation_run_id"] == run_id

    run_dir = tmp_path / "live_eval" / "runs" / run_id
    assert run_dir.exists()
    if os.name != "nt":
        assert oct(run_dir.stat().st_mode & 0o777) == oct(0o750)
        assert oct(report_path.stat().st_mode & 0o777) == oct(0o640)

    get_settings.cache_clear()
    get_live_eval_config.cache_clear()


def test_redact_sensitive_nested_keys():
    payload = {
        "metadata": {
            "body": "secret email body",
            "nested": {"access_token": "tok", "safe": "ok"},
        },
        "items": [{"prompt": "hidden"}, {"label": "visible"}],
    }
    redacted = redact_sensitive(payload)
    assert "body" not in redacted["metadata"]
    assert "access_token" not in redacted["metadata"]["nested"]
    assert redacted["metadata"]["nested"]["safe"] == "ok"
    assert redacted["items"][0] == {}
    assert redacted["items"][1]["label"] == "visible"


def test_journal_redacts_nested_sensitive_fields(tmp_path, live_eval_env, monkeypatch):
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
    from app.core.settings import get_settings
    from app.evaluation.live.config import get_live_eval_config

    get_settings.cache_clear()
    get_live_eval_config.cache_clear()

    run_id = "run-redact"
    append_transition(
        run_id,
        {
            "state": "registered",
            "details": {"email_body": "full text", "count": 1},
        },
    )
    transitions = load_transitions(run_id)
    assert transitions[0]["details"]["count"] == 1
    assert "email_body" not in transitions[0]["details"]

    get_settings.cache_clear()
    get_live_eval_config.cache_clear()
