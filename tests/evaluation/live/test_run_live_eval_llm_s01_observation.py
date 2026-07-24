"""Regression tests for cmd_run_llm_s01 observation unwrap and failure reporting."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.evaluation.live.errors import LiveEvalObservationContractError
from app.evaluation.live.llm_assertions import assert_s01_live_llm_semantics
from app.evaluation.live.llm_report import LLM_FAILURE_REPORT_SCHEMA_VERSION, LLM_REPORT_SCHEMA_VERSION
from app.evaluation.live.pipeline_poll import PipelinePollResult
from scripts.run_live_eval import _extract_observation, cmd_run_llm_s01


def _valid_observation() -> dict:
    return {
        "run": {
            "tenant_id": "TENANT_LIVE_EVAL",
            "scenario_id": "S01_lead_laddbox_quality",
            "transport_mode": "fixture_input",
            "ai_mode": "live_llm",
            "status": "active",
        },
        "job": {
            "job_id": "job-1",
            "job_type": "lead",
            "job_status": "awaiting_approval",
            "pending_approval_count": 1,
            "classification": {"detected_job_type": "lead"},
            "entities": {
                "entities": {
                    "customer_name": "Anna Lindqvist",
                    "email": "anna@example.com",
                }
            },
            "service_profile": {"profile": "laddbox"},
            "policy": {
                "policy_authorization": "approval_required",
                "decision": "send_for_approval",
            },
            "decision_records": [
                {"record_type": "pipeline_run_started", "event_sequence": 1},
                {"record_type": "classification", "event_sequence": 2},
                {"record_type": "decisioning_recommendation", "event_sequence": 3},
                {"record_type": "policy_authorization", "event_sequence": 4},
            ],
            "processor_history": [
                {"processor": "classification_processor", "result": {"payload": {"used_fallback": False}}},
                {"processor": "entity_extraction_processor", "result": {"payload": {"used_fallback": False}}},
                {"processor": "lead_processor", "result": {"payload": {"used_fallback": False}}},
                {"processor": "decisioning_processor", "result": {"payload": {"used_fallback": False}}},
            ],
        },
        "events": [],
    }


def _poll_result(observation: dict | object) -> PipelinePollResult:
    return PipelinePollResult(
        observation=observation,
        poll_attempts=1,
        poll_duration_seconds=0.1,
    )


@pytest.fixture
def llm_s01_env(monkeypatch):
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("LIVE_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_LLM_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_EVAL_TENANT_IDS", "TENANT_LIVE_EVAL")
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    monkeypatch.setenv("LIVE_EVAL_APP_BASE_URL", "http://127.0.0.1:8010")
    monkeypatch.setenv("LIVE_EVAL_LLM_PROVIDER", "openai")
    monkeypatch.setenv("LIVE_EVAL_LLM_MODEL", "gpt-4o-mini")


def _http_ok(payload: dict | None = None) -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = payload or {}
    response.text = ""
    return response


def _cli_args(tmp_path: Path) -> Namespace:
    return Namespace(
        confirm_external=True,
        app_base_url="http://127.0.0.1:8010",
        tenant_id="TENANT_LIVE_EVAL",
        evaluation_run_id="run-cli-observation",
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        run_id_file=str(tmp_path / "run_id.txt"),
        failure_artifact_file=str(tmp_path / "llm_failure_report.json"),
    )


def test_extract_observation_unwraps_pipeline_poll_result():
    payload = _valid_observation()
    extracted = _extract_observation(_poll_result(payload))
    assert extracted is payload
    assert isinstance(extracted, dict)


def test_extract_observation_rejects_invalid_type():
    with pytest.raises(LiveEvalObservationContractError):
        _extract_observation("not-a-mapping")


def test_cmd_run_llm_s01_success_unwraps_poll_result_and_writes_report(llm_s01_env, tmp_path):
    observation = _valid_observation()
    args = _cli_args(tmp_path)
    report_path = tmp_path / "llm_report.json"

    def _fake_write_report(run_id: str, report):
        report_path.write_text(
            json.dumps(report.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )
        return report_path

    with (
        patch("httpx.post", return_value=_http_ok()),
        patch(
            "httpx.get",
            return_value=_http_ok(observation),
        ),
        patch(
            "app.evaluation.live.pipeline_poll.poll_pipeline_observation",
            return_value=_poll_result(observation),
        ) as poll_mock,
        patch(
            "app.evaluation.live.llm_assertions.assert_s01_live_llm_semantics",
            wraps=assert_s01_live_llm_semantics,
        ) as semantics_mock,
        patch(
            "app.evaluation.live.llm_report.build_live_eval_llm_report",
            wraps=__import__(
                "app.evaluation.live.llm_report",
                fromlist=["build_live_eval_llm_report"],
            ).build_live_eval_llm_report,
        ) as report_mock,
        patch(
            "app.evaluation.live.llm_report.write_llm_report_atomic",
            side_effect=_fake_write_report,
        ),
    ):
        exit_code = cmd_run_llm_s01(args)

    assert exit_code == 0
    poll_mock.assert_called_once()
    semantics_arg = semantics_mock.call_args.args[0]
    report_observation = report_mock.call_args.kwargs["observation"]
    assert isinstance(semantics_arg, dict)
    assert not isinstance(semantics_arg, PipelinePollResult)
    assert semantics_arg is observation
    assert report_observation is observation
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved["report_schema_version"] == LLM_REPORT_SCHEMA_VERSION
    assert saved["evaluation_run_id"] == args.evaluation_run_id
    assert saved["transport_mode"] == "fixture_input"
    assert saved["ai_mode"] == "live_llm"
    assert not (tmp_path / "llm_failure_report.json").exists()


def test_cmd_run_llm_s01_assertion_failure_writes_failure_report(llm_s01_env, tmp_path):
    observation = _valid_observation()
    observation["job"]["job_status"] = "processing"
    args = _cli_args(tmp_path)

    with (
        patch("httpx.post", return_value=_http_ok()),
        patch("httpx.get", return_value=_http_ok(observation)),
        patch(
            "app.evaluation.live.pipeline_poll.poll_pipeline_observation",
            return_value=_poll_result(observation),
        ),
        patch(
            "app.evaluation.live.llm_report.write_llm_report_atomic",
            return_value=tmp_path / "llm_report.json",
        ),
    ):
        exit_code = cmd_run_llm_s01(args)

    assert exit_code == 1
    failure = json.loads((tmp_path / "llm_failure_report.json").read_text(encoding="utf-8"))
    assert failure["report_schema_version"] == LLM_FAILURE_REPORT_SCHEMA_VERSION
    assert failure["failure_category"] == "assertion_failed"
    assert failure["failure_stage"] == "report"


def test_cmd_run_llm_s01_observation_contract_error_writes_failure_report(llm_s01_env, tmp_path):
    args = _cli_args(tmp_path)

    with (
        patch("httpx.post", return_value=_http_ok()),
        patch(
            "app.evaluation.live.pipeline_poll.poll_pipeline_observation",
            return_value=_poll_result("not-a-mapping"),
        ),
    ):
        exit_code = cmd_run_llm_s01(args)

    assert exit_code == 1
    failure = json.loads((tmp_path / "llm_failure_report.json").read_text(encoding="utf-8"))
    assert failure["report_schema_version"] == LLM_FAILURE_REPORT_SCHEMA_VERSION
    assert failure["failure_category"] == "observation_contract_error"
    assert failure["failure_stage"] == "pipeline_poll"
    assert not (tmp_path / "llm_report.json").exists()


def test_cmd_run_llm_s01_write_failure_handles_missing_observation(llm_s01_env, tmp_path):
    args = _cli_args(tmp_path)

    with (
        patch("httpx.post", return_value=_http_ok()),
        patch(
            "app.evaluation.live.pipeline_poll.poll_pipeline_observation",
            return_value=_poll_result(_valid_observation()),
        ),
        patch(
            "app.evaluation.live.llm_assertions.assert_s01_live_llm_semantics",
            side_effect=RuntimeError("assertion exploded"),
        ),
    ):
        exit_code = cmd_run_llm_s01(args)

    assert exit_code == 1
    failure = json.loads((tmp_path / "llm_failure_report.json").read_text(encoding="utf-8"))
    assert failure["failure_category"] == "report_failure"
    assert failure["failure_stage"] == "assertions"


def test_cmd_run_llm_s01_failure_writer_uses_fallback_without_replacing_primary_category(
    llm_s01_env,
    tmp_path,
):
    observation = _valid_observation()
    observation["job"]["job_status"] = "processing"
    args = _cli_args(tmp_path)

    with (
        patch("httpx.post", return_value=_http_ok()),
        patch("httpx.get", return_value=_http_ok(observation)),
        patch(
            "app.evaluation.live.pipeline_poll.poll_pipeline_observation",
            return_value=_poll_result(observation),
        ),
        patch(
            "app.evaluation.live.llm_report.write_llm_report_atomic",
            return_value=tmp_path / "llm_report.json",
        ),
        patch(
            "app.evaluation.live.llm_report.build_live_eval_llm_failure_report",
            side_effect=RuntimeError("builder exploded"),
        ),
    ):
        exit_code = cmd_run_llm_s01(args)

    assert exit_code == 1
    failure = json.loads((tmp_path / "llm_failure_report.json").read_text(encoding="utf-8"))
    assert failure["report_schema_version"] == LLM_FAILURE_REPORT_SCHEMA_VERSION
    assert failure["failure_category"] == "assertion_failed"
    assert failure["failure_stage"] == "report"
    assert failure["report_builder_error"] == "builder exploded"
    assert failure["operations"] == []


def test_cmd_run_llm_s01_failure_artifact_redacts_sensitive_error_text(llm_s01_env, tmp_path):
    args = _cli_args(tmp_path)
    sensitive = (
        'Bearer sk-testsecret1234567890 prompt body {"message_text":"secret"} '
        "anna@example.com"
    )

    with patch(
        "httpx.post",
        return_value=MagicMock(status_code=500, text=sensitive, json=lambda: {}),
    ):
        exit_code = cmd_run_llm_s01(args)

    assert exit_code == 1
    raw = (tmp_path / "llm_failure_report.json").read_text(encoding="utf-8")
    failure = json.loads(raw)
    assert failure["failure_category"] == "registration_failed"
    redacted = failure.get("redacted_error") or ""
    assert "Bearer" not in raw
    assert "sk-testsecret" not in raw
    assert "anna@example.com" not in raw
    assert "Bearer" not in redacted
    assert "sk-testsecret" not in redacted
