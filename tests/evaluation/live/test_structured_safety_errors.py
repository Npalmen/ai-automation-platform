"""Structured live-eval safety rejection observability tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from app.evaluation.live.errors import LiveEvalSafetyRejectedError
from app.evaluation.live.exit_codes import EXIT_CONFIG, EXIT_TRANSPORT
from app.evaluation.live.observer import LiveEvalObserver
from app.evaluation.live.reporting import build_failure_summary
from app.evaluation.live.safety_errors import (
    build_safety_rejected_payload,
    parse_safety_rejected_payload,
)


def test_parse_safety_rejected_payload_from_fastapi_detail():
    payload = build_safety_rejected_payload(
        evaluation_run_id="run-1",
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        tenant_id="TENANT_LIVE_EVAL",
        safety_reason="recipient_identity_unverified",
    )
    parsed = parse_safety_rejected_payload({"detail": payload.model_dump()})
    assert parsed is not None
    assert parsed.safety_reason == "recipient_identity_unverified"
    assert parsed.error_code == "live_eval_safety"


def test_observer_raises_structured_safety_error_not_transport():
    response = MagicMock()
    response.status_code = 400
    response.json.return_value = {
        "detail": build_safety_rejected_payload(
            evaluation_run_id="run-obs",
            scenario_id="S01_lead_laddbox_quality",
            attempt_id=1,
            tenant_id="TENANT_LIVE_EVAL",
            safety_reason="recipient_identity_unverified",
        ).model_dump()
    }

    observer = LiveEvalObserver(
        base_url="http://127.0.0.1:8010",
        admin_api_key="test-admin-key",
        tenant_id="TENANT_LIVE_EVAL",
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(httpx, "post", lambda *args, **kwargs: response)
        with pytest.raises(LiveEvalSafetyRejectedError) as excinfo:
            observer.process_delivery("run-obs", "msg-1")
    assert excinfo.value.payload["safety_reason"] == "recipient_identity_unverified"


def test_failure_summary_preserves_safety_reason_not_transport():
    summary = build_failure_summary(
        evaluation_run_id="run-1",
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        failure_category="safety_rejected",
        failed_stage="triggering_intake",
        primary_exit_code=EXIT_CONFIG,
        cleanup_exit_code=None,
        artifact_status="present",
        send_state="confirmed",
        send_attempted=True,
        send_confirmed=True,
        reconciliation_result="not_run",
        recipient_delivery_observed=True,
        root_job_bound=False,
        cleanup_state="not_run",
        safety_reason="recipient_identity_unverified",
        workflow_sha="aa002d7b8183804f579da699cdde494b21137f96",
    )
    payload = summary.to_dict()
    assert payload["primary_exit_code"] == EXIT_CONFIG
    assert payload["final_exit_code"] == EXIT_CONFIG
    assert payload["primary_exit_code"] != EXIT_TRANSPORT
    assert payload["safety_reason"] == "recipient_identity_unverified"
    assert "refresh_token" not in str(payload)
