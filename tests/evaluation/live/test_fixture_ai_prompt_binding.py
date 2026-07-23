"""Prompt-binding contract tests for trusted live-eval fixture AI."""

from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.ai.schemas import ClassificationResponse
from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.evaluation.fixture_ai import _active_prompt_name, reset_active_prompt_name, set_active_prompt_name
from app.evaluation.live.context import live_eval_context
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.llm_provider import FixtureEvalLLMClient, resolve_llm_client
from app.evaluation.live.schemas import TrustedLiveEvalSnapshot
from app.workflows.processors.ai_processor_utils import run_ai_step


def _snapshot(**overrides):
    base = dict(
        evaluation_run_id="run-prompt-1",
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
    base.update(overrides)
    return TrustedLiveEvalSnapshot(**base)


def _classification_step(job: Job) -> Job:
    return run_ai_step(
        job=job,
        processor_name="classification_processor",
        prompt_name="classification_v1",
        context={"job_id": job.job_id},
        response_model=ClassificationResponse,
        success_summary="classified",
        success_payload_builder=lambda parsed: {
            "detected_job_type": parsed.detected_job_type,
            "confidence": parsed.confidence,
            "reasons": parsed.reasons,
        },
        fallback_payload_builder=lambda _msg: {
            "detected_job_type": "unknown",
            "confidence": 0.0,
            "reasons": ["fallback"],
            "used_fallback": True,
        },
    )


def test_classification_fixture_selected_by_prompt_name(db, live_eval_env, sample_run_row):
    sample_run_row.evaluation_run_id = "run-prompt-1"
    sample_run_row.status = "active"
    db.add(sample_run_row)
    db.commit()

    job = Job(
        tenant_id="TENANT_LIVE_EVAL",
        job_type=JobType.LEAD,
        input_data={
            "subject": "Offert laddbox",
            "message_text": "Hej",
            "live_eval": _snapshot().model_dump(mode="json"),
        },
    )
    with live_eval_context(_snapshot(), db=db):
        result = _classification_step(job)

    payload = result.result["payload"]
    assert payload["detected_job_type"] == "lead"
    assert payload.get("used_fallback") is not True


def test_prompt_context_reset_after_exception(db, live_eval_env, sample_run_row):
    sample_run_row.evaluation_run_id = "run-prompt-1"
    sample_run_row.status = "active"
    db.add(sample_run_row)
    db.commit()

    outer = set_active_prompt_name("classification_v1")
    job = Job(
        tenant_id="TENANT_LIVE_EVAL",
        job_type=JobType.LEAD,
        input_data={"live_eval": _snapshot().model_dump(mode="json")},
    )

    class BoomClient:
        def generate_json(self, _prompt: str):
            raise RuntimeError("boom")

    with live_eval_context(_snapshot(), db=db):
        with patch(
            "app.evaluation.live.llm_provider.resolve_llm_client",
            return_value=BoomClient(),
        ):
            with pytest.raises(RuntimeError, match="boom"):
                run_ai_step(
                    job=job,
                    processor_name="classification_processor",
                    prompt_name="decisioning_v1",
                    context={},
                    response_model=ClassificationResponse,
                    success_summary="classified",
                    success_payload_builder=lambda parsed: parsed.model_dump(),
                    fallback_payload_builder=lambda msg: {"error": msg, "used_fallback": True},
                )

    assert _active_prompt_name.get() == "classification_v1"
    reset_active_prompt_name(outer)


def test_concurrent_prompt_names_isolated(db, live_eval_env, sample_run_row):
    sample_run_row.evaluation_run_id = "run-prompt-1"
    sample_run_row.status = "active"
    db.add(sample_run_row)
    db.commit()

    fixtures = {
        "classification_v1": {
            "detected_job_type": "lead",
            "confidence": 0.9,
            "reasons": [],
        },
        "decisioning_v1": {
            "decision": "auto_route",
            "target_queue": "sales_queue",
            "action_flags": {
                "create_crm_lead": False,
                "notify_human": False,
                "request_missing_data": True,
            },
            "reasons": [],
            "confidence": 0.85,
        },
    }
    client = FixtureEvalLLMClient(fixtures)
    errors: list[str] = []
    seen: list[str] = []

    def worker(prompt_name: str) -> None:
        token = set_active_prompt_name(prompt_name)
        try:
            payload = client.generate_json("rendered prompt without embedded name")
            seen.append(f"{prompt_name}:{payload.get('decision', payload.get('detected_job_type'))}")
        except Exception as exc:
            errors.append(str(exc))
        finally:
            reset_active_prompt_name(token)

    t1 = threading.Thread(target=worker, args=("classification_v1",))
    t2 = threading.Thread(target=worker, args=("decisioning_v1",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors
    assert "classification_v1:lead" in seen
    assert "decisioning_v1:auto_route" in seen


def test_non_eval_llm_path_unchanged(live_eval_env):
    job = Job(
        tenant_id="TENANT_A",
        job_type=JobType.LEAD,
        input_data={"subject": "hello"},
    )
    with patch("app.workflows.processors.ai_processor_utils.get_llm_client") as get_client:
        get_client.return_value.generate_json.return_value = {
            "detected_job_type": "lead",
            "confidence": 0.9,
            "reasons": [],
        }
        result = run_ai_step(
            job=job,
            processor_name="classification_processor",
            prompt_name="classification_v1",
            context={},
            response_model=ClassificationResponse,
            success_summary="classified",
            success_payload_builder=lambda parsed: parsed.model_dump(),
            fallback_payload_builder=lambda msg: {"error": msg},
        )
    get_client.assert_called_once()
    assert result.result["payload"]["detected_job_type"] == "lead"


def test_live_llm_mode_does_not_use_fixture_binding(db, live_eval_env, monkeypatch, sample_run_row):
    monkeypatch.setenv("LIVE_LLM_EVAL_ALLOWED", "yes")
    from app.evaluation.live.config import get_live_eval_config

    get_live_eval_config.cache_clear()
    sample_run_row.evaluation_run_id = "run-llm"
    sample_run_row.status = "active"
    sample_run_row.ai_mode = "live_llm"
    db.add(sample_run_row)
    db.commit()

    snap = _snapshot(evaluation_run_id="run-llm", ai_mode="live_llm")
    job = SimpleNamespace(
        tenant_id="TENANT_LIVE_EVAL",
        input_data={"live_eval": snap.model_dump(mode="json")},
    )
    with live_eval_context(snap, db=db), patch(
        "app.evaluation.live.llm_provider.get_llm_client"
    ) as get_llm:
        get_llm.return_value = MagicMock()
        client = resolve_llm_client(job=job, db=db)
        assert not isinstance(client, FixtureEvalLLMClient)
    get_live_eval_config.cache_clear()


def test_unknown_prompt_name_fails_closed(db, live_eval_env, sample_run_row):
    sample_run_row.evaluation_run_id = "run-prompt-1"
    sample_run_row.status = "active"
    db.add(sample_run_row)
    db.commit()

    job = Job(
        tenant_id="TENANT_LIVE_EVAL",
        job_type=JobType.LEAD,
        input_data={"live_eval": _snapshot().model_dump(mode="json")},
    )
    with live_eval_context(_snapshot(), db=db):
        result = run_ai_step(
            job=job,
            processor_name="classification_processor",
            prompt_name="unknown_prompt_v9",
            context={},
            response_model=ClassificationResponse,
            success_summary="classified",
            success_payload_builder=lambda parsed: parsed.model_dump(),
            fallback_payload_builder=lambda msg: {
                "detected_job_type": "unknown",
                "confidence": 0.0,
                "reasons": [msg],
                "used_fallback": True,
            },
        )

    payload = result.result["payload"]
    assert payload.get("used_fallback") is True
    assert result.result["requires_human_review"] is True
