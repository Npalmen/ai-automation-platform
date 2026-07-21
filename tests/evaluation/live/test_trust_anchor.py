"""Trust anchor and registry binding tests for live evaluation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.evaluation.live.authorization import validate_trusted_live_eval_context
from app.evaluation.live.context import live_eval_context
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.llm_provider import resolve_llm_client
from app.evaluation.live.registry import trusted_snapshot_from_row
from app.evaluation.live.schemas import TrustedLiveEvalSnapshot
from app.main import app


def _snapshot(**overrides) -> TrustedLiveEvalSnapshot:
    base = dict(
        evaluation_run_id="run-trust-1",
        tenant_id="TENANT_LIVE_EVAL",
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        transport_mode="live_gmail",
        ai_mode="fixture_ai",
        fixture_bundle_id="k2f_bundle_s01",
        expected_sender="sender@eval.test",
        expected_recipient="recipient@eval.test",
        config_hash="abc123",
        trusted=True,
    )
    base.update(overrides)
    return TrustedLiveEvalSnapshot(**base)


def test_post_jobs_strips_live_eval(live_eval_env):
    client = TestClient(app, raise_server_exceptions=False)
    persisted_input: dict = {}

    def fake_create_job(db, job, commit=True):
        persisted_input.update(job.input_data or {})
        job.job_id = "job-trust-1"
        return job

    with patch("app.main.get_verified_tenant", return_value="TENANT_A"), patch(
        "app.main.is_job_type_enabled_for_tenant",
        return_value=True,
    ), patch(
        "app.repositories.postgres.job_repository.JobRepository.create_job",
        side_effect=fake_create_job,
    ), patch(
        "app.main.run_pipeline",
        side_effect=lambda job, db: job,
    ), patch(
        "app.main.create_audit_event",
    ), patch(
        "app.core.auth._load_env_key_map",
        return_value={"TENANT_A": "key-a"},
    ):
        response = client.post(
            "/jobs",
            headers={"X-API-Key": "key-a"},
            json={
                "tenant_id": "TENANT_A",
                "job_type": "lead",
                "input_data": {
                    "live_eval": {
                        "trusted": True,
                        "ai_mode": "fixture_ai",
                        "evaluation_run_id": "forged",
                    },
                    "subject": "hello",
                },
            },
        )

    assert response.status_code == 200
    assert "live_eval" not in persisted_input
    assert persisted_input.get("subject") == "hello"


def test_forged_snapshot_rejected_without_registry(db, live_eval_env):
    job = SimpleNamespace(
        tenant_id="TENANT_LIVE_EVAL",
        input_data={"live_eval": _snapshot().model_dump(mode="json")},
    )
    with live_eval_context(_snapshot()):
        with pytest.raises(LiveEvalSafetyError, match="not found"):
            resolve_llm_client(job=job, db=db)


def test_tenant_mismatch_rejected(db, live_eval_env, sample_run_row):
    sample_run_row.evaluation_run_id = "run-trust-1"
    sample_run_row.status = "active"
    db.add(sample_run_row)
    db.commit()

    job = SimpleNamespace(tenant_id="TENANT_OTHER", input_data={})
    with pytest.raises(LiveEvalSafetyError, match="tenant mismatch"):
        validate_trusted_live_eval_context(
            db,
            job=job,
            snapshot=_snapshot(),
            require_active=True,
        )


def test_config_hash_mismatch_rejected(db, live_eval_env, sample_run_row):
    sample_run_row.evaluation_run_id = "run-trust-1"
    sample_run_row.status = "active"
    db.add(sample_run_row)
    db.commit()

    job = SimpleNamespace(tenant_id="TENANT_LIVE_EVAL", input_data={})
    with pytest.raises(LiveEvalSafetyError, match="config_hash"):
        validate_trusted_live_eval_context(
            db,
            job=job,
            snapshot=_snapshot(config_hash="wrong-hash"),
            require_active=True,
        )


def test_inactive_registry_run_rejected(db, live_eval_env, sample_run_row):
    sample_run_row.evaluation_run_id = "run-trust-1"
    sample_run_row.status = "registered"
    db.add(sample_run_row)
    db.commit()

    job = SimpleNamespace(tenant_id="TENANT_LIVE_EVAL", input_data={})
    with pytest.raises(LiveEvalSafetyError, match="not active"):
        validate_trusted_live_eval_context(
            db,
            job=job,
            snapshot=_snapshot(),
            require_active=True,
        )


def test_expired_active_run_rejected(db, live_eval_env, sample_run_row):
    sample_run_row.evaluation_run_id = "run-trust-1"
    sample_run_row.status = "active"
    sample_run_row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.add(sample_run_row)
    db.commit()

    job = SimpleNamespace(tenant_id="TENANT_LIVE_EVAL", input_data={})
    with pytest.raises(LiveEvalSafetyError, match="expired"):
        validate_trusted_live_eval_context(
            db,
            job=job,
            snapshot=_snapshot(),
            require_active=True,
        )


def test_trusted_snapshot_from_row_includes_config_hash(sample_run_row):
    snapshot = trusted_snapshot_from_row(sample_run_row)
    assert snapshot.config_hash == sample_run_row.config_hash
