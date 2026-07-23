"""Hermetic S01 pipeline completion through process-delivery."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.domain.workflows.statuses import JobStatus
from app.evaluation.live.errors import LiveEvalPipelinePollError
from app.evaluation.live.pipeline_poll import poll_pipeline_observation
from app.evaluation.live.routes import router as live_eval_router
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.database import Base
from app.repositories.postgres.decision_record_models import DecisionRecordRow
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.job_repository import JobRepository
from app.repositories.postgres.live_eval_models import LiveEvalExternalEventRow, LiveEvalRunRow
from app.repositories.postgres.tenant_config_models import TenantConfigRecord
from tests.evaluation.live.test_process_delivery_intake_gate import (
    _mock_delivery_chain,
    _register,
    _s01_message,
    _seed_eval_tenant_with_cutoff,
)


@pytest.fixture
def pipeline_db(live_eval_env):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[
            LiveEvalRunRow.__table__,
            LiveEvalExternalEventRow.__table__,
            AuditEventRecord.__table__,
            JobRecord.__table__,
            TenantConfigRecord.__table__,
            DecisionRecordRow.__table__,
            ApprovalRequestRecord.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def pipeline_client(pipeline_db, live_eval_env, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    monkeypatch.setenv("EXTERNAL_SIDE_EFFECT_TESTS", "yes")
    app = FastAPI()
    app.include_router(live_eval_router)
    app.dependency_overrides[get_db] = lambda: pipeline_db
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


def test_s01_process_delivery_reaches_awaiting_approval(pipeline_client, pipeline_db):
    run_id = "run-s01-complete"
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    _seed_eval_tenant_with_cutoff(pipeline_db, cutoff_at=cutoff)
    run_row = _register(pipeline_client, pipeline_db, run_id)
    message = _s01_message(run_row)

    with patch(
        "app.evaluation.live.routes.validate_delivery_candidate",
        return_value=(True, None),
    ), _mock_delivery_chain(message), patch(
        "app.evaluation.live.gmail_intake.post_pipeline_gmail_message_outcome",
        return_value={"marked_handled": False},
    ), patch(
        "app.evaluation.live.gmail_intake.dispatch_action",
    ):
        first = pipeline_client.post(
            f"/admin/live-eval/runs/{run_id}/process-delivery",
            headers={"X-Admin-API-Key": "test-admin-key"},
            json={
                "tenant_id": "TENANT_LIVE_EVAL",
                "recipient_gmail_message_id": "msg-recipient-s01",
            },
        )
        second = pipeline_client.post(
            f"/admin/live-eval/runs/{run_id}/process-delivery",
            headers={"X-Admin-API-Key": "test-admin-key"},
            json={
                "tenant_id": "TENANT_LIVE_EVAL",
                "recipient_gmail_message_id": "msg-recipient-s01",
            },
        )

    assert first.status_code == 200, first.text
    body = first.json()
    assert body["root_job_id"]
    assert body["job_status"] == "awaiting_approval"
    assert second.status_code == 200
    assert second.json().get("intake_status") == "skipped"

    # exactly one root job persisted
    jobs = pipeline_db.query(JobRecord).filter_by(tenant_id="TENANT_LIVE_EVAL").all()
    assert len(jobs) == 1
    domain_job = JobRepository.get_job_by_id(pipeline_db, "TENANT_LIVE_EVAL", body["root_job_id"])
    assert domain_job is not None
    assert domain_job.status == JobStatus.AWAITING_APPROVAL

    for entry in domain_job.processor_history:
        payload = (entry.get("result") or {}).get("payload") or {}
        assert payload.get("used_fallback") is not True

    observation = pipeline_client.get(
        f"/admin/live-eval/runs/{run_id}/observation",
        params={"tenant_id": "TENANT_LIVE_EVAL"},
        headers={"X-Admin-API-Key": "test-admin-key"},
    ).json()
    job_obs = observation["job"]
    assert job_obs["job_type"] == "lead"
    assert job_obs["job_status"] == "awaiting_approval"
    assert job_obs["has_pending_approvals"] is True
    assert job_obs["pending_approval_count"] == 1
    assert job_obs["classification"]["detected_job_type"] == "lead"
    assert job_obs["policy"]["policy_authorization"] == "approval_required"
    assert job_obs["policy"]["decision"] == "send_for_approval"


def test_poll_fail_fast_manual_review_and_failed():
    manual = {
        "run": {"root_job_id": "job-1", "tenant_id": "TENANT_LIVE_EVAL"},
        "job": {"job_status": "manual_review", "decision_records": []},
    }
    failed = {
        "run": {"root_job_id": "job-1", "tenant_id": "TENANT_LIVE_EVAL"},
        "job": {"job_status": "failed", "decision_records": []},
    }

    with pytest.raises(LiveEvalPipelinePollError) as manual_exc:
        poll_pipeline_observation(lambda: manual, timeout_seconds=5)
    assert manual_exc.value.timeout_reason == "unexpected_terminal_status"

    with pytest.raises(LiveEvalPipelinePollError) as failed_exc:
        poll_pipeline_observation(lambda: failed, timeout_seconds=5)
    assert failed_exc.value.timeout_reason == "pipeline_failed"
    assert failed_exc.value.job_snapshot["observed_status"] == "failed"
