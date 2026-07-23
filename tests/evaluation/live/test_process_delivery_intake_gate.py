"""Hermetic process-delivery intake gate tests (2F.2B Phase A + observability)."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_db
from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.domain.workflows.statuses import JobStatus
from app.evaluation.live.errors import LiveEvalIntakeSkippedError
from app.evaluation.live.intake_errors import ALLOWED_INTAKE_SKIP_REASONS
from app.evaluation.live.observer import LiveEvalObserver
from app.evaluation.live.routes import router as live_eval_router
from app.evaluation.live.schemas import TrustedLiveEvalSnapshot
from app.evaluation.live.subject_parser import build_subject_with_token
from app.repositories.postgres.job_models import JobRecord
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


def _seed_eval_tenant_no_cutoff(db) -> None:
    """Mirror eval seed: intake enabled, no cutoff field."""
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


def _seed_eval_tenant_with_cutoff(db, *, cutoff_at: datetime) -> None:
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
            settings={
                "intake": {
                    "enabled": True,
                    "intake_cutoff_at": cutoff_at.replace(microsecond=0).isoformat(),
                },
                "live_eval": {"seeded": True},
            },
        )
    )
    db.commit()


def _register(api_client, db, run_id: str) -> LiveEvalRunRow:
    with patch("app.evaluation.live.registry.emit_live_eval_audit"):
        response = api_client.post(
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
    assert response.status_code == 200, response.text
    row = db.query(LiveEvalRunRow).filter_by(evaluation_run_id=run_id).one()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    row.created_at = now
    row.expires_at = now + timedelta(hours=2)
    db.commit()
    db.refresh(row)
    return row


def _s01_message(run_row: LiveEvalRunRow, *, internal_date_ms: int | None = None) -> dict:
    subject = build_subject_with_token(
        evaluation_run_id=run_row.evaluation_run_id,
        scenario_id=run_row.scenario_id,
        attempt_id=run_row.attempt_id,
        base_subject="Laddbox installation inquiry",
    )
    if internal_date_ms is None:
        created = run_row.created_at
        expires = run_row.expires_at
        if created.tzinfo is not None:
            created = created.astimezone(timezone.utc).replace(tzinfo=None)
        if expires.tzinfo is not None:
            expires = expires.astimezone(timezone.utc).replace(tzinfo=None)
        midpoint = created + (expires - created) / 2
        internal_date_ms = int(midpoint.replace(tzinfo=timezone.utc).timestamp() * 1000)
    return {
        "message_id": "msg-recipient-s01",
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


def _gmail_patches(message: dict):
    adapter = MagicMock()
    adapter.execute_action.return_value = {"message": message}
    return (
        patch(
            "app.evaluation.live.routes.get_integration_connection_config",
            return_value={"user_id": "recipient@eval.test"},
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
            return_value={"user_id": "recipient@eval.test"},
        ),
        patch(
            "app.evaluation.live.gmail_intake.get_integration_adapter",
            return_value=adapter,
        ),
    )


@contextmanager
def _delivery_valid_for_intake():
    """Bypass delivery date-window quirks in sqlite tests; covered in test_delivery_hardening."""
    with patch(
        "app.evaluation.live.routes.validate_delivery_candidate",
        return_value=(True, None),
    ):
        yield


@contextmanager
def _mock_delivery_chain(message: dict):
    adapter = MagicMock()
    adapter.execute_action.return_value = {"message": message}
    with (
        patch(
            "app.evaluation.live.routes.get_integration_connection_config",
            return_value={"user_id": "recipient@eval.test"},
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
            return_value={"user_id": "recipient@eval.test"},
        ),
        patch(
            "app.evaluation.live.gmail_intake.get_integration_adapter",
            return_value=adapter,
        ),
    ):
        yield adapter


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



def test_repro_seed_without_cutoff_returns_missing_intake_cutoff(api_client, db):
    """Phase A: eval seed shape without intake_cutoff_at must 409 with missing_intake_cutoff."""
    run_id = "run-2f2b-repro"
    _seed_eval_tenant_no_cutoff(db)
    run_row = _register(api_client, db, run_id)
    message = _s01_message(run_row)

    with _delivery_valid_for_intake(), _mock_delivery_chain(message), patch(
        "app.evaluation.live.gmail_intake.run_pipeline"
    ) as pipeline_mock:
        response = api_client.post(
            f"/admin/live-eval/runs/{run_id}/process-delivery",
            headers={"X-Admin-API-Key": "test-admin-key"},
            json={
                "tenant_id": "TENANT_LIVE_EVAL",
                "recipient_gmail_message_id": "msg-recipient-s01",
            },
        )

    assert response.status_code == 409, response.json()
    detail = response.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["intake_skip_reason"] == "missing_intake_cutoff"
    assert detail["error_code"] == "intake_skipped"
    assert detail["intake_result"] == "skipped"
    assert detail["evaluation_run_id"] == run_id
    assert detail["failed_stage"] == "triggering_intake"
    assert detail["http_status"] == 409
    assert detail["job_created"] is False
    assert detail["retry_allowed"] is False
    assert detail["root_claimed"] is False
    assert detail["intake_skip_reason"] in ALLOWED_INTAKE_SKIP_REASONS
    pipeline_mock.assert_not_called()
    assert db.query(JobRecord).count() == 0


def test_cutoff_allows_exactly_one_root_job(api_client, db):
    run_id = "run-2f2b-cutoff-ok"
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    _seed_eval_tenant_with_cutoff(db, cutoff_at=cutoff)
    run_row = _register(api_client, db, run_id)
    message = _s01_message(run_row)
    job = Job(
        tenant_id="TENANT_LIVE_EVAL",
        job_type=JobType.LEAD,
        status=JobStatus.AWAITING_APPROVAL,
        input_data={"live_eval": _snapshot_for(run_id).model_dump(mode="json")},
    )
    job.job_id = "job-root-1"

    with _delivery_valid_for_intake(), _mock_delivery_chain(message), patch(
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
        response = api_client.post(
            f"/admin/live-eval/runs/{run_id}/process-delivery",
            headers={"X-Admin-API-Key": "test-admin-key"},
            json={
                "tenant_id": "TENANT_LIVE_EVAL",
                "recipient_gmail_message_id": "msg-recipient-s01",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["root_job_id"] == "job-root-1"
    assert body["intake_status"] == "created"


def test_message_before_cutoff_returns_before_intake_cutoff(api_client, db):
    run_id = "run-2f2b-before-cutoff"
    cutoff = datetime.now(timezone.utc)
    _seed_eval_tenant_with_cutoff(db, cutoff_at=cutoff)
    run_row = _register(api_client, db, run_id)
    created = run_row.created_at
    if created.tzinfo is not None:
        created = created.astimezone(timezone.utc).replace(tzinfo=None)
    old_ms = int(created.replace(tzinfo=timezone.utc).timestamp() * 1000) - 3_600_000
    message = _s01_message(run_row, internal_date_ms=old_ms)

    with _delivery_valid_for_intake(), _mock_delivery_chain(message):
        response = api_client.post(
            f"/admin/live-eval/runs/{run_id}/process-delivery",
            headers={"X-Admin-API-Key": "test-admin-key"},
            json={
                "tenant_id": "TENANT_LIVE_EVAL",
                "recipient_gmail_message_id": "msg-recipient-s01",
            },
        )

    assert response.status_code == 409
    assert response.json()["detail"]["intake_skip_reason"] == "before_intake_cutoff"


def test_disabled_job_type_is_fail_closed(api_client, db):
    run_id = "run-2f2b-disabled-type"
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    db.add(
        TenantConfigRecord(
            tenant_id="TENANT_LIVE_EVAL",
            name="Live Eval",
            slug="live-eval",
            status="active",
            lifecycle_status="active",
            is_test_tenant=True,
            enabled_job_types=["invoice"],
            settings={
                "intake": {
                    "enabled": True,
                    "intake_cutoff_at": cutoff.isoformat(),
                }
            },
        )
    )
    db.commit()
    run_row = _register(api_client, db, run_id)
    message = _s01_message(run_row)

    with _delivery_valid_for_intake(), _mock_delivery_chain(message):
        response = api_client.post(
            f"/admin/live-eval/runs/{run_id}/process-delivery",
            headers={"X-Admin-API-Key": "test-admin-key"},
            json={
                "tenant_id": "TENANT_LIVE_EVAL",
                "recipient_gmail_message_id": "msg-recipient-s01",
            },
        )

    assert response.status_code == 409
    assert response.json()["detail"]["intake_skip_reason"] == "lead_disabled"


def test_duplicate_intake_is_idempotent(api_client, db):
    run_id = "run-2f2b-dup"
    now = datetime.now(timezone.utc)
    run_row = LiveEvalRunRow(
        evaluation_run_id=run_id,
        tenant_id="TENANT_LIVE_EVAL",
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        transport_mode="live_gmail",
        ai_mode="fixture_ai",
        fixture_bundle_id="k2f_bundle_s01",
        expected_sender="sender@eval.test",
        expected_recipient="recipient@eval.test",
        status="active",
        created_by="test",
        created_at=now,
        expires_at=now + timedelta(hours=2),
        config_hash="abc123",
        root_job_id="job-existing",
        root_gmail_message_id="msg-recipient-s01",
    )
    db.add(run_row)
    db.commit()
    _seed_eval_tenant_no_cutoff(db)

    patches = _gmail_patches(_s01_message(run_row))
    with patches[0], patches[1], patches[2]:
        response = api_client.post(
            f"/admin/live-eval/runs/{run_id}/process-delivery",
            headers={"X-Admin-API-Key": "test-admin-key"},
            json={
                "tenant_id": "TENANT_LIVE_EVAL",
                "recipient_gmail_message_id": "msg-recipient-s01",
            },
        )

    assert response.status_code == 200
    assert response.json()["intake_detail"]["reason"] == "duplicate"


def test_wrong_sender_blocked_before_intake(api_client, db):
    run_id = "run-2f2b-bad-sender"
    _seed_eval_tenant_no_cutoff(db)
    run_row = _register(api_client, db, run_id)
    message = _s01_message(run_row)
    message["from"] = "evil@eval.test"

    patches = _gmail_patches(message)
    with patches[0], patches[1], patches[2]:
        response = api_client.post(
            f"/admin/live-eval/runs/{run_id}/process-delivery",
            headers={"X-Admin-API-Key": "test-admin-key"},
            json={
                "tenant_id": "TENANT_LIVE_EVAL",
                "recipient_gmail_message_id": "msg-recipient-s01",
            },
        )

    assert response.status_code == 400
    assert "sender_mismatch" in response.json()["detail"]


def test_wrong_recipient_blocked(api_client, db):
    run_id = "run-2f2b-bad-recipient"
    _seed_eval_tenant_no_cutoff(db)
    run_row = _register(api_client, db, run_id)
    message = _s01_message(run_row)
    message["to"] = "other@eval.test"

    patches = _gmail_patches(message)
    with patches[0], patches[1], patches[2]:
        response = api_client.post(
            f"/admin/live-eval/runs/{run_id}/process-delivery",
            headers={"X-Admin-API-Key": "test-admin-key"},
            json={
                "tenant_id": "TENANT_LIVE_EVAL",
                "recipient_gmail_message_id": "msg-recipient-s01",
            },
        )

    assert response.status_code == 400
    assert "recipient_mismatch" in response.json()["detail"]


def test_missing_intake_label_blocked(api_client, db):
    run_id = "run-2f2b-bad-label"
    _seed_eval_tenant_no_cutoff(db)
    run_row = _register(api_client, db, run_id)
    message = _s01_message(run_row)
    message["label_ids"] = ["other-label"]
    created = run_row.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    message["internal_date_ms"] = int(created.timestamp() * 1000)

    patches = _gmail_patches(message)
    with patches[0], patches[1], patches[2]:
        response = api_client.post(
            f"/admin/live-eval/runs/{run_id}/process-delivery",
            headers={"X-Admin-API-Key": "test-admin-key"},
            json={
                "tenant_id": "TENANT_LIVE_EVAL",
                "recipient_gmail_message_id": "msg-recipient-s01",
            },
        )

    assert response.status_code == 400
    assert "missing_intake_label" in response.json()["detail"]


def test_old_run_token_cannot_match_new_run(api_client, db):
    run_id = "run-2f2b-new"
    old_id = "run-2f2b-old"
    _seed_eval_tenant_no_cutoff(db)
    run_row = _register(api_client, db, run_id)
    message = _s01_message(run_row)
    message["subject"] = build_subject_with_token(
        evaluation_run_id=old_id,
        scenario_id=run_row.scenario_id,
        attempt_id=run_row.attempt_id,
        base_subject="Stale token",
    )

    patches = _gmail_patches(message)
    with patches[0], patches[1], patches[2]:
        response = api_client.post(
            f"/admin/live-eval/runs/{run_id}/process-delivery",
            headers={"X-Admin-API-Key": "test-admin-key"},
            json={
                "tenant_id": "TENANT_LIVE_EVAL",
                "recipient_gmail_message_id": "msg-recipient-s01",
            },
        )

    assert response.status_code == 400
    assert "evaluation_run_id_mismatch" in response.json()["detail"]


def test_observer_preserves_intake_skip_reason():
    observer = LiveEvalObserver(
        base_url="http://test",
        admin_api_key="key",
        tenant_id="TENANT_LIVE_EVAL",
    )
    mock_response = MagicMock()
    mock_response.status_code = 409
    mock_response.json.return_value = {
        "detail": {
            "error_code": "intake_skipped",
            "intake_result": "skipped",
            "intake_skip_reason": "missing_intake_cutoff",
            "evaluation_run_id": "run-obs",
            "failed_stage": "triggering_intake",
            "http_status": 409,
            "run_status": "registered",
            "root_claimed": False,
            "job_created": False,
            "retry_allowed": False,
            "diagnostic_code": "INTAKE_GATE_MISSING_CUTOFF",
        }
    }

    with patch("app.evaluation.live.observer.httpx.post", return_value=mock_response):
        with pytest.raises(LiveEvalIntakeSkippedError) as exc_info:
            observer.process_delivery("run-obs", "msg-1")

    assert exc_info.value.payload["intake_skip_reason"] == "missing_intake_cutoff"


def test_structured_payload_redacts_secrets():
    from app.evaluation.live.intake_errors import build_intake_skipped_payload
    from app.evaluation.live.redaction import redact_sensitive

    payload = build_intake_skipped_payload(
        evaluation_run_id="run-redact",
        raw_reason="missing_intake_cutoff",
        run_status="registered",
        root_claimed=False,
    ).model_dump()
    payload["body_text"] = "secret body sender@evil.com"
    payload["access_token"] = "tok_secret"
    redacted = redact_sensitive(payload)
    assert "body_text" not in redacted
    assert "access_token" not in redacted
    assert redacted["intake_skip_reason"] == "missing_intake_cutoff"
