"""Gmail readiness route and offline mode tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_db
from app.evaluation.live.routes import router as live_eval_router
from app.evaluation.live.readiness import run_gmail_readiness_checks, run_offline_readiness_checks


def test_offline_readiness_makes_no_network_calls(live_eval_env, monkeypatch):
    def fail_network(*args, **kwargs):
        raise AssertionError("offline readiness must not perform network calls")

    monkeypatch.setattr("httpx.get", fail_network)
    report = run_offline_readiness_checks()
    assert report.checks["mode"] == "offline"


@pytest.fixture
def live_eval_client(db, live_eval_env, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    app = FastAPI()
    app.include_router(live_eval_router)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


def test_gmail_readiness_route_uses_read_only_adapter(db, live_eval_env, live_eval_client):
    mock_adapter = MagicMock()
    mock_adapter.execute_action.return_value = {
        "labels": [{"id": "lbl1", "name": "krowolf-live-eval"}],
    }
    with patch(
        "app.evaluation.live.readiness.get_integration_connection_config",
        return_value={"user_id": "recipient@eval.test", "access_token": "x"},
    ), patch(
        "app.evaluation.live.readiness.get_integration_adapter",
        return_value=mock_adapter,
    ):
        response = live_eval_client.post(
            "/admin/live-eval/gmail-readiness",
            headers={"X-Admin-API-Key": "test-admin-key"},
            json={"tenant_id": "TENANT_LIVE_EVAL"},
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ready"] is True
    mock_adapter.execute_action.assert_called_once_with(action="list_labels", payload={})


def test_gmail_readiness_service_read_only(db, live_eval_env):
    mock_adapter = MagicMock()
    mock_adapter.execute_action.return_value = {
        "labels": [{"id": "lbl1", "name": "krowolf-live-eval"}],
    }
    with patch(
        "app.evaluation.live.readiness.get_integration_connection_config",
        return_value={"user_id": "recipient@eval.test"},
    ), patch(
        "app.evaluation.live.readiness.get_integration_adapter",
        return_value=mock_adapter,
    ):
        report = run_gmail_readiness_checks(db, "TENANT_LIVE_EVAL")
    assert report.ready is True
    assert report.checks["label_present"] is True
