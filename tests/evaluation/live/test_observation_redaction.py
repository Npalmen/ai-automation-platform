"""DecisionRecord metadata redaction in observation API."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.evaluation.live.observation import build_job_observation


def test_decision_metadata_redacts_nested_tokens(db, live_eval_env):
    job = MagicMock()
    job.job_id = "job-obs-1"
    job.job_type = MagicMock(value="lead")
    job.status = MagicMock(value="awaiting_approval")
    job.input_data = {}
    job.result = {}

    record = MagicMock()
    record.record_type = "classification"
    record.event_sequence = 1
    record.policy_authorization = None
    record.action_authorization = None
    record.pipeline_run_id = "pipe-1"
    record.metadata_json = {
        "access_token": "secret-access",
        "nested": {"refresh_token": "secret-refresh", "prompt": "system prompt"},
        "items": [{"body_text": "full email body"}],
        "safe_field": "visible",
    }

    with patch(
        "app.evaluation.live.observation.JobRepository.get_job_by_id",
        return_value=job,
    ), patch(
        "app.evaluation.live.observation.get_latest_processor_payload",
        return_value={},
    ), patch(
        "app.evaluation.live.observation.DecisionRecordRepository.list_for_job",
        return_value=[record],
    ), patch(
        "app.evaluation.live.observation.has_pending_approval",
        return_value=True,
    ):
        observation = build_job_observation(db, "TENANT_LIVE_EVAL", "job-obs-1")

    metadata = observation["decision_records"][0]["metadata"]
    assert "access_token" not in metadata
    assert "refresh_token" not in metadata
    assert "prompt" not in metadata
    assert "body_text" not in metadata
    assert metadata.get("safe_field") == "visible"
    assert "nested" in metadata
