"""Server-side mutation gate tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_db
from app.evaluation.live.routes import router as live_eval_router
from app.repositories.postgres.live_eval_models import LiveEvalRunRow


@pytest.fixture
def live_eval_client(db, live_eval_env, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    monkeypatch.setenv("EXTERNAL_SIDE_EFFECT_TESTS", "yes")
    from app.evaluation.live.config import get_live_eval_config

    get_live_eval_config.cache_clear()
    app = FastAPI()
    app.include_router(live_eval_router)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()
    get_live_eval_config.cache_clear()


def _register(client, run_id: str, *, ai_mode: str = "fixture_ai", scenario: str = "S01_lead_laddbox_quality"):
    with patch("app.evaluation.live.registry.emit_live_eval_audit"):
        return client.post(
            "/admin/live-eval/runs",
            headers={"X-Admin-API-Key": "test-admin-key"},
            json={
                "evaluation_run_id": run_id,
                "tenant_id": "TENANT_LIVE_EVAL",
                "scenario_id": scenario,
                "attempt_id": 1,
                "ai_mode": ai_mode,
                "expected_sender": "sender@eval.test",
                "expected_recipient": "recipient@eval.test",
                "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            },
        )


def test_process_delivery_requires_external_side_effects(live_eval_client, monkeypatch):
    monkeypatch.delenv("EXTERNAL_SIDE_EFFECT_TESTS", raising=False)
    from app.evaluation.live.config import get_live_eval_config

    get_live_eval_config.cache_clear()
    reg = _register(live_eval_client, "run-gate-sidefx")
    assert reg.status_code == 200
    response = live_eval_client.post(
        "/admin/live-eval/runs/run-gate-sidefx/process-delivery",
        headers={"X-Admin-API-Key": "test-admin-key"},
        json={"tenant_id": "TENANT_LIVE_EVAL", "recipient_gmail_message_id": "msg-1"},
    )
    assert response.status_code == 400


def test_process_delivery_rejects_wrong_scenario_on_register(live_eval_client):
    response = _register(live_eval_client, "run-gate-scenario", scenario="S99_other")
    assert response.status_code == 400


def test_process_delivery_rejects_live_llm(live_eval_client):
    response = _register(live_eval_client, "run-gate-llm", ai_mode="live_llm")
    assert response.status_code == 400


def test_delivery_readonly_allowed_without_mutation_gate(live_eval_client, db, monkeypatch):
    monkeypatch.delenv("EXTERNAL_SIDE_EFFECT_TESTS", raising=False)
    from app.evaluation.live.config import get_live_eval_config

    get_live_eval_config.cache_clear()
    now = datetime.now(timezone.utc)
    row = LiveEvalRunRow(
        evaluation_run_id="run-readonly-delivery",
        tenant_id="TENANT_LIVE_EVAL",
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        transport_mode="live_gmail",
        ai_mode="fixture_ai",
        fixture_bundle_id="k2f_bundle_s01",
        expected_sender="sender@eval.test",
        expected_recipient="recipient@eval.test",
        status="registered",
        created_by="test",
        created_at=now,
        expires_at=now + timedelta(hours=2),
        config_hash="abc",
    )
    db.add(row)
    db.commit()
    with patch("app.evaluation.live.routes.observe_delivery_candidates") as observe:
        observe.return_value = type(
            "R",
            (),
            {
                "candidate_count": 0,
                "valid_count": 0,
                "duplicate_detected": False,
                "confirmed": None,
                "rejection_reasons": [],
            },
        )()
        response = live_eval_client.get(
            "/admin/live-eval/runs/run-readonly-delivery/delivery?tenant_id=TENANT_LIVE_EVAL",
            headers={"X-Admin-API-Key": "test-admin-key"},
        )
    assert response.status_code == 200


def test_status_update_rejects_non_allowlisted_tenant(live_eval_client):
    assert _register(live_eval_client, "run-status-tenant").status_code == 200
    response = live_eval_client.post(
        "/admin/live-eval/runs/run-status-tenant/status",
        headers={"X-Admin-API-Key": "test-admin-key"},
        json={"tenant_id": "OTHER_TENANT", "status": "aborted"},
    )
    assert response.status_code == 400


def test_status_update_allows_allowlisted_tenant(live_eval_client):
    assert _register(live_eval_client, "run-status-ok").status_code == 200
    response = live_eval_client.post(
        "/admin/live-eval/runs/run-status-ok/status",
        headers={"X-Admin-API-Key": "test-admin-key"},
        json={"tenant_id": "TENANT_LIVE_EVAL", "status": "aborted"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "aborted"
