"""Admin route tests for 2F.2 observation and mutation gates."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_db
from app.evaluation.live.routes import router as live_eval_router


@pytest.fixture
def client(db, live_eval_env, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    app = FastAPI()
    app.include_router(live_eval_router)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _register(client, run_id: str = "run-obs-1"):
    with patch("app.evaluation.live.registry.emit_live_eval_audit"):
        return client.post(
            "/admin/live-eval/runs",
            headers={"X-Admin-API-Key": "test-admin-key"},
            json={
                "evaluation_run_id": run_id,
                "tenant_id": "TENANT_LIVE_EVAL",
                "scenario_id": "S01_lead_laddbox_quality",
                "attempt_id": 1,
                "ai_mode": "fixture_ai",
                "expected_sender": "sender@eval.test",
                "expected_recipient": "recipient@eval.test",
                "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            },
        )


def test_runtime_readiness(client):
    response = client.get(
        "/admin/live-eval/runtime-readiness",
        headers={"X-Admin-API-Key": "test-admin-key"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["env"] == "test"
    assert "database_ok" in body


def test_get_run_summary(client):
    assert _register(client).status_code == 200
    response = client.get(
        "/admin/live-eval/runs/run-obs-1",
        params={"tenant_id": "TENANT_LIVE_EVAL"},
        headers={"X-Admin-API-Key": "test-admin-key"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["evaluation_run_id"] == "run-obs-1"
    assert "input_data" not in body


def test_process_delivery_requires_side_effect_gate(client, monkeypatch):
    assert _register(client, "run-mut-1").status_code == 200
    monkeypatch.delenv("EXTERNAL_SIDE_EFFECT_TESTS", raising=False)
    from app.evaluation.live.config import get_live_eval_config

    get_live_eval_config.cache_clear()
    response = client.post(
        "/admin/live-eval/runs/run-mut-1/process-delivery",
        headers={"X-Admin-API-Key": "test-admin-key"},
        json={
            "tenant_id": "TENANT_LIVE_EVAL",
            "recipient_gmail_message_id": "msg-1",
        },
    )
    assert response.status_code == 400
