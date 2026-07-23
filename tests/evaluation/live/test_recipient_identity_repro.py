"""Hermetic reproduction of RUN_S01 #8 recipient identity failure (2F.2C Phase A)."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_db
from app.evaluation.live.routes import router as live_eval_router
from app.evaluation.live.subject_parser import build_subject_with_token
from app.repositories.postgres.live_eval_models import LiveEvalRunRow
from app.repositories.postgres.tenant_config_models import TenantConfigRecord


@pytest.fixture
def api_client(db, live_eval_env, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    app = FastAPI()
    app.include_router(live_eval_router)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


def _seed_eval_tenant(db) -> None:
    db.add(
        TenantConfigRecord(
            tenant_id="TENANT_LIVE_EVAL",
            name="Live Eval",
            slug="live-eval",
            status="active",
            lifecycle_status="active",
            is_test_tenant=True,
            allowed_integrations=["google_mail"],
            enabled_job_types=["lead", "customer_inquiry", "invoice"],
            settings={"intake": {"enabled": True}, "live_eval": {"seeded": True}},
        )
    )
    db.commit()


def _register_run(db, run_id: str) -> LiveEvalRunRow:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    row = LiveEvalRunRow(
        evaluation_run_id=run_id,
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
        config_hash="hash-2f2c",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _message_for_run(run_row: LiveEvalRunRow) -> dict:
    subject = build_subject_with_token(
        evaluation_run_id=run_row.evaluation_run_id,
        scenario_id=run_row.scenario_id,
        attempt_id=run_row.attempt_id,
        base_subject="Laddbox installation inquiry",
    )
    created = run_row.created_at
    expires = run_row.expires_at
    midpoint = created + (expires - created) / 2
    internal_date_ms = int(midpoint.replace(tzinfo=timezone.utc).timestamp() * 1000)
    return {
        "message_id": "msg-recipient-repro",
        "subject": subject,
        "from": "sender@eval.test",
        "to": "recipient@eval.test",
        "body_text": (
            f"<!-- KROWOLF_EVAL:evaluation_run_id={run_row.evaluation_run_id} -->\n"
            "Jag vill ha en laddbox installerad."
        ),
        "internal_date_ms": internal_date_ms,
        "label_ids": ["label-krowolf"],
    }


@contextmanager
def _patches_for_me_identity(message: dict):
    adapter = MagicMock()
    adapter.execute_action.return_value = {"message": message}
    connection = {"user_id": "me", "metadata_json": {}}
    with (
        patch(
            "app.evaluation.live.routes.get_integration_connection_config",
            return_value=connection,
        ),
        patch(
            "app.evaluation.live.routes.get_integration_adapter",
            return_value=adapter,
        ),
        patch(
            "app.evaluation.live.routes.resolve_intake_label_id",
            return_value="label-krowolf",
        ),
        patch(
            "app.evaluation.live.gmail_intake.get_integration_connection_config",
            return_value=connection,
        ),
        patch(
            "app.evaluation.live.gmail_intake.get_integration_adapter",
            return_value=adapter,
        ),
        patch(
            "app.evaluation.live.routes.validate_delivery_candidate",
            return_value=(True, None),
        ),
    ):
        yield


def test_process_delivery_rejects_unverified_recipient_identity(api_client, db):
    run_id = "run-2f2c-repro-me"
    _seed_eval_tenant(db)
    run_row = _register_run(db, run_id)
    message = _message_for_run(run_row)

    with _patches_for_me_identity(message):
        response = api_client.post(
            f"/admin/live-eval/runs/{run_id}/process-delivery",
            headers={"X-Admin-API-Key": "test-admin-key"},
            json={
                "tenant_id": "TENANT_LIVE_EVAL",
                "recipient_gmail_message_id": "msg-recipient-repro",
            },
        )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["error_code"] == "live_eval_safety"
    assert detail["safety_reason"] == "recipient_identity_unverified"
    assert detail["evaluation_run_id"] == run_id
    assert detail["root_job_created"] is False
    assert db.query(LiveEvalRunRow).filter_by(evaluation_run_id=run_id).one().root_job_id is None
