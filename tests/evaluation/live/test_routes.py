"""Admin route auth contract for live-eval registry."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_db
from app.evaluation.live.routes import router as live_eval_router


@pytest.fixture
def live_eval_client(db, live_eval_env, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    app = FastAPI()
    app.include_router(live_eval_router)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


def test_register_run_requires_admin_key(live_eval_env, db, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    app = FastAPI()
    app.include_router(live_eval_router)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/admin/live-eval/runs",
            json={
                "evaluation_run_id": "run-route-1",
                "tenant_id": "TENANT_LIVE_EVAL",
                "scenario_id": "S01_lead_laddbox_quality",
                "attempt_id": 1,
                "ai_mode": "fixture_ai",
                "expected_sender": "sender@eval.test",
                "expected_recipient": "recipient@eval.test",
            },
        )
        assert response.status_code == 401
    app.dependency_overrides.clear()


def test_register_run_with_admin_key(live_eval_client):
    with patch("app.evaluation.live.registry.emit_live_eval_audit"):
        response = live_eval_client.post(
            "/admin/live-eval/runs",
            headers={"X-Admin-API-Key": "test-admin-key"},
            json={
                "evaluation_run_id": "run-route-2",
                "tenant_id": "TENANT_LIVE_EVAL",
                "scenario_id": "S01_lead_laddbox_quality",
                "attempt_id": 1,
                "ai_mode": "fixture_ai",
                "expected_sender": "sender@eval.test",
                "expected_recipient": "recipient@eval.test",
                "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            },
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["fixture_bundle_id"] == "k2f_bundle_s01"
    assert body["status"] == "registered"
