"""Tests for automatic Gmail canary fixture bundle registration and completeness."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_db
from app.evaluation.live.campaign.automatic_action_contract import (
    AUTOMATIC_GMAIL_CANARY_SCENARIO_IDS,
)
from app.evaluation.live.campaign.automatic_fixture_completeness import (
    AUTOMATIC_CANARY_FIXTURE_BUNDLE_MISSING,
    validate_automatic_fixture_bundle_completeness,
)
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.fixture_bundle import (
    BUNDLE_FIXTURES,
    SCENARIO_BUNDLE_MAP,
    load_bundle_fixtures,
    resolve_fixture_bundle_id,
)
from app.evaluation.live.routes import router as live_eval_router


@pytest.mark.parametrize(
    "scenario_id,expected_bundle",
    [
        ("TBA01_safe_lead_auto_reply", "k2f_bundle_tba01"),
        ("TBA02_unknown_auto_hold", "k2f_bundle_tba02"),
    ],
)
def test_tba_scenarios_map_to_dedicated_fixture_bundles(scenario_id, expected_bundle):
    assert SCENARIO_BUNDLE_MAP[scenario_id] == expected_bundle
    bundle_id = resolve_fixture_bundle_id(scenario_id=scenario_id, ai_mode="fixture_ai")
    assert bundle_id == expected_bundle
    assert bundle_id in BUNDLE_FIXTURES


def test_tba01_bundle_yields_lead_classification():
    fixtures = load_bundle_fixtures("k2f_bundle_tba01")
    classification = fixtures["classification_v1"]
    assert classification["detected_job_type"] == "lead"
    entities = fixtures["entity_extraction_v1"]["entities"]
    assert entities.get("phone")
    assert entities.get("address")
    decision = fixtures["decisioning_v1"]
    assert decision["decision"] == "auto_route"
    flags = decision.get("action_flags") or {}
    assert "auto_execute" not in flags
    assert "send_customer_auto_reply" not in flags


def test_tba02_bundle_yields_unknown_hold_classification():
    fixtures = load_bundle_fixtures("k2f_bundle_tba02")
    classification = fixtures["classification_v1"]
    assert classification["detected_job_type"] == "unknown"
    assert classification["confidence"] < 0.6
    decision = fixtures["decisioning_v1"]
    assert decision["target_queue"] == "manual_review"
    assert decision["decision"] == "send_for_approval"
    flags = decision.get("action_flags") or {}
    assert "auto_execute" not in flags
    assert "send_customer_auto_reply" not in flags


def test_unknown_tba_scenario_remains_fail_closed():
    with pytest.raises(LiveEvalSafetyError, match="No allowlisted fixture bundle"):
        resolve_fixture_bundle_id(scenario_id="TBA99_missing", ai_mode="fixture_ai")


def test_automatic_fixture_completeness_passes_for_canary_scenarios():
    issues, matrix = validate_automatic_fixture_bundle_completeness()
    assert issues == []
    assert matrix["complete"] is True
    for scenario_id in AUTOMATIC_GMAIL_CANARY_SCENARIO_IDS:
        assert scenario_id in matrix["mappings"]
        assert matrix["mappings"][scenario_id]["bundle_id"].startswith("k2f_bundle_tba")


def test_automatic_fixture_completeness_fails_when_mapping_missing(monkeypatch):
    original = SCENARIO_BUNDLE_MAP["TBA01_safe_lead_auto_reply"]
    monkeypatch.setitem(SCENARIO_BUNDLE_MAP, "TBA01_safe_lead_auto_reply", "")
    try:
        issues, _ = validate_automatic_fixture_bundle_completeness()
        assert any(AUTOMATIC_CANARY_FIXTURE_BUNDLE_MISSING in issue for issue in issues)
    finally:
        SCENARIO_BUNDLE_MAP["TBA01_safe_lead_auto_reply"] = original


def test_register_tba01_via_api(db, live_eval_env, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    monkeypatch.setenv("FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED", "yes")
    app = FastAPI()
    app.include_router(live_eval_router)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app, raise_server_exceptions=False) as client, patch(
        "app.evaluation.live.registry.emit_live_eval_audit"
    ):
        response = client.post(
            "/admin/live-eval/runs",
            headers={"X-Admin-API-Key": "test-admin-key"},
            json={
                "evaluation_run_id": "508a55b5-f191-42ca-b3a0-a5face946795",
                "tenant_id": "TENANT_LIVE_EVAL",
                "scenario_id": "TBA01_safe_lead_auto_reply",
                "attempt_id": 1,
                "transport_mode": "live_gmail",
                "ai_mode": "fixture_ai",
                "expected_sender": "sender@eval.test",
                "expected_recipient": "recipient@eval.test",
                "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            },
        )
    app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    assert response.json()["fixture_bundle_id"] == "k2f_bundle_tba01"


def test_register_tba02_via_api(db, live_eval_env, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    monkeypatch.setenv("FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED", "yes")
    app = FastAPI()
    app.include_router(live_eval_router)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app, raise_server_exceptions=False) as client, patch(
        "app.evaluation.live.registry.emit_live_eval_audit"
    ):
        response = client.post(
            "/admin/live-eval/runs",
            headers={"X-Admin-API-Key": "test-admin-key"},
            json={
                "evaluation_run_id": "87347114-242d-4c9d-a4ac-668e09d70f60",
                "tenant_id": "TENANT_LIVE_EVAL",
                "scenario_id": "TBA02_unknown_auto_hold",
                "attempt_id": 1,
                "transport_mode": "live_gmail",
                "ai_mode": "fixture_ai",
                "expected_sender": "sender@eval.test",
                "expected_recipient": "recipient@eval.test",
                "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            },
        )
    app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    assert response.json()["fixture_bundle_id"] == "k2f_bundle_tba02"


def test_register_unknown_scenario_returns_400(db, live_eval_env, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    monkeypatch.setenv("FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED", "yes")
    app = FastAPI()
    app.include_router(live_eval_router)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/admin/live-eval/runs",
            headers={"X-Admin-API-Key": "test-admin-key"},
            json={
                "evaluation_run_id": "run-tba-unknown-1",
                "tenant_id": "TENANT_LIVE_EVAL",
                "scenario_id": "TBA99_missing",
                "attempt_id": 1,
                "transport_mode": "live_gmail",
                "ai_mode": "fixture_ai",
                "expected_sender": "sender@eval.test",
                "expected_recipient": "recipient@eval.test",
            },
        )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "not allowlisted" in detail or "No allowlisted fixture bundle" in detail


def test_register_run_sets_campaign_run_creation_failed_stage():
    from app.evaluation.live.runner import LiveEvalRunner

    request = httpx.Request("POST", "http://127.0.0.1:8010/admin/live-eval/runs")
    response = httpx.Response(400, request=request, json={"detail": "rejected"})

    runner = LiveEvalRunner(
        base_url="http://127.0.0.1:8010",
        admin_api_key="test-admin-key",
        tenant_id="TENANT_LIVE_EVAL",
        scenario_id="TBA01_safe_lead_auto_reply",
        expected_sender="sender@eval.test",
        expected_recipient="recipient@eval.test",
        evaluation_run_id="run-register-fail-1",
    )

    with patch.object(
        runner.observer,
        "register_run",
        side_effect=httpx.HTTPStatusError("bad request", request=request, response=response),
    ), pytest.raises(httpx.HTTPStatusError):
        runner._register_run()

    assert runner._failed_stage == "campaign_run_creation_failed"
