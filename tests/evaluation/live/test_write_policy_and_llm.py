"""Write policy and LLM provider fail-closed tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.evaluation.live.context import live_eval_context
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.llm_provider import FixtureEvalLLMClient, resolve_llm_client
from app.evaluation.live.schemas import TrustedLiveEvalSnapshot
from app.evaluation.live.write_policy import enforce_live_eval_write_policy
from app.repositories.postgres.live_eval_models import LiveEvalRunRow


def _snapshot(**overrides):
    base = dict(
        evaluation_run_id="run-001",
        tenant_id="TENANT_LIVE_EVAL",
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        transport_mode="live_gmail",
        ai_mode="fixture_ai",
        fixture_bundle_id="k2f_bundle_s01",
        expected_sender="sender@eval.test",
        expected_recipient="recipient@eval.test",
        trusted=True,
    )
    base.update(overrides)
    return TrustedLiveEvalSnapshot(**base)


def test_write_policy_blocks_internal_handoff(db, live_eval_env, sample_run_row):
    sample_run_row.status = "active"
    db.add(sample_run_row)
    db.commit()

    with live_eval_context(_snapshot()):
        with patch(
            "app.evaluation.live.write_policy.is_external_write_enabled_for_integration",
            return_value=True,
        ), patch("app.evaluation.live.write_policy.emit_live_eval_audit"):
            with pytest.raises(LiveEvalSafetyError):
                enforce_live_eval_write_policy(
                    {"type": "send_internal_handoff", "to": "sender@eval.test"},
                    db=db,
                    job_id="job-1",
                )


def test_write_policy_allows_registered_reply(db, live_eval_env, sample_run_row):
    sample_run_row.evaluation_run_id = "run-001"
    sample_run_row.status = "active"
    db.add(sample_run_row)
    db.commit()

    with live_eval_context(_snapshot()):
        with patch(
            "app.evaluation.live.write_policy.is_external_write_enabled_for_integration",
            return_value=True,
        ), patch("app.evaluation.live.write_policy.emit_live_eval_audit"):
            enforce_live_eval_write_policy(
                {
                    "type": "send_customer_auto_reply",
                    "to": "sender@eval.test",
                },
                db=db,
            )


def test_resolve_llm_client_uses_fixture_bundle(live_eval_env):
    job = SimpleNamespace(
        input_data={
            "live_eval": _snapshot().model_dump(mode="json"),
        }
    )
    with live_eval_context(_snapshot()):
        client = resolve_llm_client(job=job)
        assert isinstance(client, FixtureEvalLLMClient)


def test_resolve_llm_client_fail_closed_without_snapshot(live_eval_env):
    job = SimpleNamespace(
        input_data={"live_eval": _snapshot().model_dump(mode="json")},
    )
    with pytest.raises(LiveEvalSafetyError):
        resolve_llm_client(job=job)
