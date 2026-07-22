"""Happy-path telemetry tests for delivery route and intake."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_db
from app.domain.workflows.enums import JobType
from app.domain.workflows.statuses import JobStatus
from app.domain.workflows.models import Job
from app.evaluation.live.constants import (
    TELEMETRY_APP_DELIVERY_OBSERVED,
    TELEMETRY_APP_INTAKE_FAILED,
    TELEMETRY_APP_INTAKE_STARTED,
    TELEMETRY_APP_INTAKE_SUCCEEDED,
)
from app.evaluation.live.delivery import DeliveryCandidate, DeliveryObservationResult
from app.evaluation.live.routes import router as live_eval_router
from app.evaluation.live.schemas import TrustedLiveEvalSnapshot
from app.integrations.enums import IntegrationType
from app.repositories.postgres.live_eval_models import LiveEvalExternalEventRow, LiveEvalRunRow
from app.repositories.postgres.tenant_config_models import TenantConfigRecord


@pytest.fixture
def api_client(db, live_eval_env, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    app = FastAPI()
    app.include_router(live_eval_router)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client
    app.dependency_overrides.clear()


def _seed_run(db, run_id: str = "run-telemetry-1") -> LiveEvalRunRow:
    now = datetime.now(timezone.utc)
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
        config_hash="abc123",
    )
    db.add(row)
    db.commit()
    return row


def _snapshot_for(run_id: str) -> TrustedLiveEvalSnapshot:
    return TrustedLiveEvalSnapshot(
        evaluation_run_id=run_id,
        tenant_id="TENANT_LIVE_EVAL",
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        transport_mode="live_gmail",
        ai_mode="fixture_ai",
        fixture_bundle_id="k2f_bundle_s01",
        expected_sender="sender@eval.test",
        expected_recipient="recipient@eval.test",
        config_hash="abc123",
    )


def test_delivery_route_records_google_mail_telemetry(api_client, db):
    _seed_run(db)
    confirmed = DeliveryCandidate(
        message_id="msg-delivery-1",
        thread_id="thread-1",
        rfc_message_id="<abc@mail>",
        sender_email="sender@eval.test",
        recipient_email="recipient@eval.test",
    )
    with patch(
        "app.evaluation.live.routes.observe_delivery_candidates",
        return_value=DeliveryObservationResult(
            candidate_count=1,
            valid_count=1,
            duplicate_detected=False,
            confirmed=confirmed,
            rejection_reasons=[],
        ),
    ):
        response = api_client.get(
            "/admin/live-eval/runs/run-telemetry-1/delivery",
            params={"tenant_id": "TENANT_LIVE_EVAL"},
            headers={"X-Admin-API-Key": "test-admin-key"},
        )
    assert response.status_code == 200, response.text
    events = db.query(LiveEvalExternalEventRow).filter_by(
        evaluation_run_id="run-telemetry-1",
        category=TELEMETRY_APP_DELIVERY_OBSERVED,
    ).all()
    assert len(events) == 1
    assert events[0].integration_type == IntegrationType.GOOGLE_MAIL.value
    assert events[0].outcome == "succeeded"


def _seed_tenant_config(db) -> None:
    db.add(
        TenantConfigRecord(
            tenant_id="TENANT_LIVE_EVAL",
            name="Live Eval",
            slug="live-eval",
            status="active",
            lifecycle_status="active",
            is_test_tenant=True,
            enabled_job_types=["lead"],
            settings={"intake": {}},
        )
    )
    db.commit()


def test_intake_success_records_started_and_succeeded_telemetry(db, live_eval_env):
    run_id = "run-intake-ok"
    _seed_run(db, run_id)
    _seed_tenant_config(db)
    job = Job(
        tenant_id="TENANT_LIVE_EVAL",
        job_type=JobType.LEAD,
        status=JobStatus.AWAITING_APPROVAL,
        input_data={"live_eval": _snapshot_for(run_id).model_dump(mode="json")},
    )
    adapter = MagicMock()
    adapter.execute_action.return_value = {
        "message": {
            "message_id": "msg-intake-1",
            "subject": f"KROWOLF-EVAL/{run_id}/S01_lead_laddbox_quality/1 Test",
            "from": "sender@eval.test",
            "to": "recipient@eval.test",
            "body_text": f"<!-- KROWOLF_EVAL:evaluation_run_id={run_id} -->",
        }
    }

    with patch(
        "app.evaluation.live.gmail_intake.get_integration_connection_config",
        return_value={"user_id": "recipient@eval.test"},
    ), patch(
        "app.evaluation.live.gmail_intake.get_integration_adapter",
        return_value=adapter,
    ), patch(
        "app.evaluation.live.gmail_intake.JobRepository.get_by_gmail_message_id",
        return_value=None,
    ), patch(
        "app.evaluation.live.gmail_intake.evaluate_intake_gate",
        return_value={"allowed": True},
    ), patch(
        "app.evaluation.live.gmail_intake.get_tenant_config",
        return_value={"enabled_job_types": ["lead"]},
    ), patch(
        "app.evaluation.live.gmail_intake.classify_email_type",
        return_value="lead",
    ), patch(
        "app.evaluation.live.gmail_intake.resolve_trusted_live_eval_from_message",
        return_value=_snapshot_for(run_id),
    ), patch(
        "app.evaluation.live.registry.create_and_claim_live_eval_root_job",
        return_value=job,
    ), patch(
        "app.evaluation.live.gmail_intake.run_pipeline",
        return_value=job,
    ), patch(
        "app.evaluation.live.gmail_intake.post_pipeline_gmail_message_outcome",
        return_value={"marked_handled": True},
    ):
        from app.evaluation.live.gmail_intake import process_gmail_message_by_id

        result = process_gmail_message_by_id(
            db,
            "TENANT_LIVE_EVAL",
            "msg-intake-1",
            intake_query=f'label:krowolf-live-eval subject:"KROWOLF-EVAL/{run_id}"',
            live_eval_run_id=run_id,
            skip_slack_notify=True,
        )

    assert result["status"] == "created"
    categories = {
        row.category: row
        for row in db.query(LiveEvalExternalEventRow).filter_by(evaluation_run_id=run_id).all()
    }
    assert TELEMETRY_APP_INTAKE_STARTED in categories
    assert TELEMETRY_APP_INTAKE_SUCCEEDED in categories
    assert categories[TELEMETRY_APP_INTAKE_SUCCEEDED].integration_type == IntegrationType.GOOGLE_MAIL.value


def test_intake_failure_records_failed_telemetry_without_masking_error(db, live_eval_env):
    run_id = "run-intake-fail"
    _seed_run(db, run_id)
    _seed_tenant_config(db)
    adapter = MagicMock()
    adapter.execute_action.return_value = {
        "message": {
            "message_id": "msg-intake-fail",
            "subject": f"KROWOLF-EVAL/{run_id}/S01_lead_laddbox_quality/1 Test",
            "from": "sender@eval.test",
            "to": "recipient@eval.test",
            "body_text": "",
        }
    }

    with patch(
        "app.evaluation.live.gmail_intake.get_integration_connection_config",
        return_value={"user_id": "recipient@eval.test"},
    ), patch(
        "app.evaluation.live.gmail_intake.get_integration_adapter",
        return_value=adapter,
    ), patch(
        "app.evaluation.live.gmail_intake.JobRepository.get_by_gmail_message_id",
        return_value=None,
    ), patch(
        "app.evaluation.live.gmail_intake.evaluate_intake_gate",
        return_value={"allowed": True},
    ), patch(
        "app.evaluation.live.gmail_intake.get_tenant_config",
        return_value={"enabled_job_types": ["lead"]},
    ), patch(
        "app.evaluation.live.gmail_intake.classify_email_type",
        return_value="lead",
    ), patch(
        "app.evaluation.live.gmail_intake.resolve_trusted_live_eval_from_message",
        return_value=_snapshot_for(run_id),
    ), patch(
        "app.evaluation.live.registry.create_and_claim_live_eval_root_job",
        side_effect=RuntimeError("claim exploded"),
    ):
        from app.evaluation.live.gmail_intake import process_gmail_message_by_id

        result = process_gmail_message_by_id(
            db,
            "TENANT_LIVE_EVAL",
            "msg-intake-fail",
            intake_query=f'label:krowolf-live-eval subject:"KROWOLF-EVAL/{run_id}"',
            live_eval_run_id=run_id,
            skip_slack_notify=True,
        )

    assert result["status"] == "failed"
    assert "claim exploded" in result["reason"]
    failed = (
        db.query(LiveEvalExternalEventRow)
        .filter_by(
            evaluation_run_id=run_id,
            category=TELEMETRY_APP_INTAKE_FAILED,
        )
        .one()
    )
    assert failed.integration_type == IntegrationType.GOOGLE_MAIL.value
