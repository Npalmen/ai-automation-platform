"""Gmail readiness route and offline mode tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_db
from app.evaluation.live.routes import router as live_eval_router
from app.evaluation.live.readiness import run_gmail_readiness_checks, run_offline_readiness_checks

_FORBIDDEN_ACTIONS = (
    "send_message",
    "create_label",
    "modify_labels",
    "mark_as_read",
    "mark_read",
    "archive",
    "delete",
)


def _mock_adapter():
    mock_adapter = MagicMock()

    def _execute_action(*, action, payload=None):
        if action == "get_profile":
            return {"email_address": "recipient@eval.test"}
        if action == "list_labels":
            return {"labels": [{"id": "lbl1", "name": "krowolf-live-eval"}]}
        raise AssertionError(f"unexpected gmail action: {action}")

    mock_adapter.execute_action.side_effect = _execute_action
    return mock_adapter


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
    mock_adapter = _mock_adapter()
    with patch(
        "app.evaluation.live.readiness.get_integration_connection_config",
        return_value={"user_id": "recipient@eval.test", "access_token": "x"},
    ), patch(
        "app.evaluation.live.readiness.is_integration_enabled_for_tenant",
        return_value=True,
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
    called_actions = [
        call.kwargs.get("action") or call.args[0]
        for call in mock_adapter.execute_action.call_args_list
    ]
    assert called_actions == ["get_profile", "list_labels"]
    for forbidden in _FORBIDDEN_ACTIONS:
        assert forbidden not in called_actions


def test_gmail_readiness_service_read_only(db, live_eval_env):
    mock_adapter = _mock_adapter()
    with patch(
        "app.evaluation.live.readiness.get_integration_connection_config",
        return_value={"user_id": "recipient@eval.test", "access_token": "token"},
    ), patch(
        "app.evaluation.live.readiness.is_integration_enabled_for_tenant",
        return_value=True,
    ), patch(
        "app.evaluation.live.readiness.get_integration_adapter",
        return_value=mock_adapter,
    ):
        report = run_gmail_readiness_checks(db, "TENANT_LIVE_EVAL")
    assert report.ready is True
    assert report.checks["label_present"] is True
    assert report.checks["gmail_profile_email"] == "recipient@eval.test"
    called_actions = [call.kwargs["action"] for call in mock_adapter.execute_action.call_args_list]
    assert set(called_actions) == {"get_profile", "list_labels"}
