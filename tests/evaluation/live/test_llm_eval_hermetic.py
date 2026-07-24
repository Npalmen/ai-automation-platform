"""Hermetic tests for fixture_input + live_llm eval path."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.exceptions import LLMClientError
from app.ai.llm.client import LLMGenerationResult
from app.api.dependencies import get_db
from app.domain.workflows.statuses import JobStatus
from app.evaluation.live.constants import (
    S01_LOCKED_SCENARIO_HASH,
    TELEMETRY_APP_LIVE_LLM,
)
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.eval_llm_client import EvalLLMClient, classify_llm_provider_error
from app.evaluation.live.llm_assertions import assert_s01_live_llm_semantics
from app.evaluation.live.llm_operations import (
    count_llm_operations_for_run,
    reserve_live_llm_operation,
)
from app.evaluation.live.llm_readiness import run_llm_offline_readiness_checks
from app.evaluation.live.llm_report import build_live_eval_llm_report, write_llm_report_atomic
from app.evaluation.live.routes import router as live_eval_router
from app.evaluation.live.scenario_input import load_locked_scenario_input
from app.evaluation.live.write_policy import enforce_live_eval_write_policy
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.database import Base
from app.repositories.postgres.decision_record_models import DecisionRecordRow
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.job_repository import JobRepository
from app.repositories.postgres.live_eval_models import LiveEvalExternalEventRow, LiveEvalLlmOperationRow, LiveEvalRunRow
from app.repositories.postgres.tenant_config_models import TenantConfigRecord
from tests.evaluation.live.fake_llm_client import FakeEvalLLMDelegate
from tests.evaluation.live.test_process_delivery_intake_gate import (
    _seed_eval_tenant_with_cutoff,
)


@pytest.fixture
def llm_eval_env(live_eval_env, monkeypatch):
    monkeypatch.setenv("LIVE_LLM_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_EVAL_LLM_PROVIDER", "openai")
    monkeypatch.setenv("LIVE_EVAL_LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("LIVE_EVAL_LLM_TIMEOUT", "60")
    monkeypatch.setenv("LIVE_EVAL_LLM_MAX_TOKENS", "2048")
    monkeypatch.setenv("LIVE_EVAL_MAX_LLM_CALLS", "4")
    monkeypatch.setenv("LLM_API_URL", "https://api.openai.com/v1/chat/completions")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("LLM_RETRY_ATTEMPTS", "0")
    monkeypatch.setenv("LLM_TEMPERATURE", "0.0")
    monkeypatch.setenv("BUILD_GIT_SHA", "deadbeef1234567890abcdef1234567890abcdef")
    from app.core.settings import get_settings
    from app.evaluation.live.config import get_live_eval_config

    get_settings.cache_clear()
    get_live_eval_config.cache_clear()
    yield
    get_settings.cache_clear()
    get_live_eval_config.cache_clear()


@pytest.fixture
def llm_db(llm_eval_env):
    from sqlalchemy import event

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
            LiveEvalLlmOperationRow.__table__,
            AuditEventRecord.__table__,
            JobRecord.__table__,
            TenantConfigRecord.__table__,
            DecisionRecordRow.__table__,
            ApprovalRequestRecord.__table__,
        ],
    )

    @event.listens_for(DecisionRecordRow, "before_insert")
    def _assign_event_sequence(mapper, connection, target):
        if connection.dialect.name != "sqlite":
            return
        if getattr(target, "event_sequence", None) is None:
            result = connection.execute(
                DecisionRecordRow.__table__.select().with_only_columns(
                    DecisionRecordRow.event_sequence
                )
            )
            max_seq = 0
            for row in result:
                max_seq = max(max_seq, int(row[0] or 0))
            target.event_sequence = max_seq + 1

    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    event.remove(DecisionRecordRow, "before_insert", _assign_event_sequence)


@pytest.fixture
def llm_client(llm_db, llm_eval_env, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    app = FastAPI()
    app.include_router(live_eval_router)
    app.dependency_overrides[get_db] = lambda: llm_db
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


def _register_fixture_llm(client, db, run_id: str):
    with patch("app.evaluation.live.registry.emit_live_eval_audit"):
        response = client.post(
            "/admin/live-eval/runs",
            headers={"X-Admin-API-Key": "test-admin-key"},
            json={
                "evaluation_run_id": run_id,
                "tenant_id": "TENANT_LIVE_EVAL",
                "scenario_id": "S01_lead_laddbox_quality",
                "attempt_id": 1,
                "transport_mode": "fixture_input",
                "ai_mode": "live_llm",
                "llm_provider": "openai",
                "llm_requested_model": "gpt-4o-mini",
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


def _snapshot(run_id: str):
    from app.evaluation.live.schemas import TrustedLiveEvalSnapshot

    return TrustedLiveEvalSnapshot(
        evaluation_run_id=run_id,
        tenant_id="TENANT_LIVE_EVAL",
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        transport_mode="fixture_input",
        ai_mode="live_llm",
        fixture_bundle_id=None,
        expected_sender=None,
        expected_recipient=None,
        llm_provider="openai",
        llm_requested_model="gpt-4o-mini",
        llm_max_calls=4,
        config_hash="cfg",
        trusted=True,
    )


def test_locked_scenario_loader_verifies_hash():
    scenario = load_locked_scenario_input("S01_lead_laddbox_quality")
    assert scenario.scenario_id == "S01_lead_laddbox_quality"
    assert scenario.dataset_version == "k2e-v1"
    assert scenario.scenario_version == 1


def test_fixture_input_registration_without_gmail_fields(llm_client, llm_db):
    run_id = "run-fixture-no-gmail"
    row = _register_fixture_llm(llm_client, llm_db, run_id)
    assert row.fixture_bundle_id is None
    assert row.expected_sender is None
    assert row.expected_recipient is None
    assert row.llm_provider == "openai"
    assert row.llm_requested_model == "gpt-4o-mini"
    assert row.llm_max_calls == 4

    summary = llm_client.get(
        f"/admin/live-eval/runs/{run_id}/observation",
        params={"tenant_id": "TENANT_LIVE_EVAL"},
        headers={"X-Admin-API-Key": "test-admin-key"},
    ).json().get("run", {})
    assert "expected_sender" not in summary
    assert "expected_recipient" not in summary
    assert summary.get("fixture_bundle_id") is None


def test_live_gmail_registration_still_requires_gmail_fields(llm_client, llm_eval_env):
    response = llm_client.post(
        "/admin/live-eval/runs",
        headers={"X-Admin-API-Key": "test-admin-key"},
        json={
            "evaluation_run_id": "run-gmail-missing",
            "tenant_id": "TENANT_LIVE_EVAL",
            "scenario_id": "S01_lead_laddbox_quality",
            "attempt_id": 1,
            "transport_mode": "live_gmail",
            "ai_mode": "fixture_ai",
        },
    )
    assert response.status_code == 400


def test_fixture_input_registration_rejects_live_gmail_llm(llm_client):
    response = llm_client.post(
        "/admin/live-eval/runs",
        headers={"X-Admin-API-Key": "test-admin-key"},
        json={
            "evaluation_run_id": "run-bad-combo",
            "tenant_id": "TENANT_LIVE_EVAL",
            "scenario_id": "S01_lead_laddbox_quality",
            "attempt_id": 1,
            "transport_mode": "live_gmail",
            "ai_mode": "live_llm",
            "expected_sender": "sender@eval.test",
            "expected_recipient": "recipient@eval.test",
            "llm_provider": "openai",
            "llm_requested_model": "gpt-4o-mini",
        },
    )
    assert response.status_code == 400


def test_fixture_input_registration_requires_workflow_sha(llm_client, llm_eval_env, monkeypatch):
    monkeypatch.delenv("BUILD_GIT_SHA", raising=False)
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    response = llm_client.post(
        "/admin/live-eval/runs",
        headers={"X-Admin-API-Key": "test-admin-key"},
        json={
            "evaluation_run_id": "run-no-sha",
            "tenant_id": "TENANT_LIVE_EVAL",
            "scenario_id": "S01_lead_laddbox_quality",
            "attempt_id": 1,
            "transport_mode": "fixture_input",
            "ai_mode": "live_llm",
            "llm_provider": "openai",
            "llm_requested_model": "gpt-4o-mini",
        },
    )
    assert response.status_code == 400


def test_llm_readiness_has_zero_provider_calls(llm_eval_env):
    report = run_llm_offline_readiness_checks()
    assert report.checks.get("live_llm_calls") == 0
    assert report.checks.get("gmail_required") is False
    assert report.checks.get("gmail_secrets_required") is None or report.checks.get("gmail_secrets_required") is False
    assert report.ready is True


def test_llm_readiness_produces_redacted_artifact(llm_eval_env, tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
    monkeypatch.setenv("LIVE_EVAL_SEED_ALLOWED", "yes")
    monkeypatch.setenv("LLM_API_KEY", "eval-llm-secret-key")
    monkeypatch.setenv("ADMIN_API_KEY", "eval-admin-secret-key")
    from app.core.settings import get_settings
    from app.evaluation.live.llm_readiness import run_llm_readiness_checks
    from app.evaluation.live.llm_report import write_llm_report_atomic
    from app.repositories.postgres.database import Base
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    get_settings.cache_clear()
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    report = run_llm_readiness_checks(session, "TENANT_LIVE_EVAL")
    assert report.checks.get("live_llm_calls") == 0
    assert report.checks.get("gmail_secrets_required") is False
    path = write_llm_report_atomic(
        "readiness-run",
        build_live_eval_llm_report(
            evaluation_run_id="readiness-run",
            run={
                "scenario_id": "S01_lead_laddbox_quality",
                "transport_mode": "fixture_input",
                "ai_mode": "live_llm",
                "status": "preflight",
                "config_hash": "cfg",
                "llm_provider": "openai",
                "llm_requested_model": "gpt-4o-mini",
            },
            observation={"events": [], "job": {}},
            result="preflight",
            scenario_content_hash=S01_LOCKED_SCENARIO_HASH,
        ),
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["result"] == "preflight"
    assert "fixture-input" not in json.dumps(payload).lower()
    session.close()
    get_settings.cache_clear()


def test_eval_llm_client_requires_usage(db, llm_eval_env):
    snap = _snapshot("run-usage")
    db.add(
        LiveEvalRunRow(
            evaluation_run_id="run-usage",
            tenant_id="TENANT_LIVE_EVAL",
            scenario_id="S01_lead_laddbox_quality",
            attempt_id=1,
            transport_mode="fixture_input",
            ai_mode="live_llm",
            fixture_bundle_id=None,
            expected_sender=None,
            expected_recipient=None,
            llm_provider="openai",
            llm_requested_model="gpt-4o-mini",
            llm_max_calls=4,
            status="active",
            created_by="test",
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
            config_hash="cfg",
        )
    )
    db.commit()

    delegate = FakeEvalLLMDelegate(missing_usage=True)
    client = EvalLLMClient(delegate, snapshot=snap, db=db)
    from app.evaluation.fixture_ai import set_active_prompt_name, reset_active_prompt_name
    from app.evaluation.live.context import live_eval_context

    token = set_active_prompt_name("classification_v1")
    with live_eval_context(snap, db=db):
        with pytest.raises(LiveEvalSafetyError, match="missing token usage"):
            client.generate_json("classification_v1 prompt")
    reset_active_prompt_name(token)


def test_eval_llm_client_rejects_model_mismatch(db, llm_eval_env):
    snap = _snapshot("run-model")
    db.add(
        LiveEvalRunRow(
            evaluation_run_id="run-model",
            tenant_id="TENANT_LIVE_EVAL",
            scenario_id="S01_lead_laddbox_quality",
            attempt_id=1,
            transport_mode="fixture_input",
            ai_mode="live_llm",
            fixture_bundle_id=None,
            expected_sender=None,
            expected_recipient=None,
            llm_provider="openai",
            llm_requested_model="gpt-4o-mini",
            llm_max_calls=4,
            status="active",
            created_by="test",
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
            config_hash="cfg",
        )
    )
    db.commit()

    delegate = FakeEvalLLMDelegate(wrong_model=True)
    client = EvalLLMClient(delegate, snapshot=snap, db=db)
    from app.evaluation.fixture_ai import set_active_prompt_name, reset_active_prompt_name
    from app.evaluation.live.context import live_eval_context

    token = set_active_prompt_name("classification_v1")
    with live_eval_context(snap, db=db):
        with pytest.raises(LiveEvalSafetyError, match="model does not match"):
            client.generate_json("classification_v1 prompt")
    reset_active_prompt_name(token)


def test_live_llm_no_fallback_on_llm_error(db, llm_eval_env):
    from app.ai.schemas import ClassificationResponse
    from app.domain.workflows.enums import JobType
    from app.domain.workflows.models import Job
    from app.workflows.processors.ai_processor_utils import run_ai_step
    from app.evaluation.live.context import live_eval_context

    snap = _snapshot("run-nofallback")
    db.add(
        LiveEvalRunRow(
            evaluation_run_id="run-nofallback",
            tenant_id="TENANT_LIVE_EVAL",
            scenario_id="S01_lead_laddbox_quality",
            attempt_id=1,
            transport_mode="fixture_input",
            ai_mode="live_llm",
            fixture_bundle_id=None,
            expected_sender=None,
            expected_recipient=None,
            llm_provider="openai",
            llm_requested_model="gpt-4o-mini",
            llm_max_calls=4,
            status="active",
            created_by="test",
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
            config_hash="cfg",
        )
    )
    db.commit()

    job = Job(
        tenant_id="TENANT_LIVE_EVAL",
        job_type=JobType.LEAD,
        input_data={"live_eval": snap.model_dump(mode="json")},
    )

    class _BrokenDelegate:
        def generate_json_detailed(self, prompt, **kwargs):
            raise LLMClientError("broken")

    with live_eval_context(snap, db=db), patch(
        "app.evaluation.live.eval_llm_client.build_eval_llm_client",
        return_value=EvalLLMClient(_BrokenDelegate(), snapshot=snap, db=db),
    ):
        with pytest.raises(LLMClientError):
            run_ai_step(
                job=job,
                processor_name="classification_processor",
                prompt_name="classification_v1",
                context={"job_id": "job-1"},
                response_model=ClassificationResponse,
                success_summary="classified",
                success_payload_builder=lambda parsed: parsed.model_dump(),
                fallback_payload_builder=lambda _msg: {"used_fallback": True},
            )


def test_write_policy_blocks_auto_reply_for_fixture_llm(db, llm_eval_env):
    snap = _snapshot("run-write")
    db.add(
        LiveEvalRunRow(
            evaluation_run_id="run-write",
            tenant_id="TENANT_LIVE_EVAL",
            scenario_id="S01_lead_laddbox_quality",
            attempt_id=1,
            transport_mode="fixture_input",
            ai_mode="live_llm",
            fixture_bundle_id=None,
            expected_sender=None,
            expected_recipient=None,
            llm_provider="openai",
            llm_requested_model="gpt-4o-mini",
            llm_max_calls=4,
            status="active",
            created_by="test",
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
            config_hash="cfg",
        )
    )
    db.commit()

    from app.evaluation.live.context import live_eval_context

    with live_eval_context(snap, db=db), patch(
        "app.evaluation.live.write_policy.emit_live_eval_audit"
    ):
        with pytest.raises(LiveEvalSafetyError):
            enforce_live_eval_write_policy(
                {"type": "send_customer_auto_reply", "to": "customer@example.com"},
                db=db,
            )


def test_fixture_input_pipeline_reaches_awaiting_approval(llm_client, llm_db):
    run_id = "run-llm-s01-pipeline"
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    _seed_eval_tenant_with_cutoff(llm_db, cutoff_at=cutoff)
    _register_fixture_llm(llm_client, llm_db, run_id)
    delegate = FakeEvalLLMDelegate()

    with patch(
        "app.evaluation.live.eval_llm_client.build_eval_llm_client",
        side_effect=lambda snapshot=None, db=None: EvalLLMClient(
            delegate,
            snapshot=snapshot or _snapshot(run_id),
            db=db or llm_db,
        ),
    ):
        first = llm_client.post(
            f"/admin/live-eval/runs/{run_id}/process-fixture-input",
            headers={"X-Admin-API-Key": "test-admin-key"},
            json={"tenant_id": "TENANT_LIVE_EVAL"},
        )
        second = llm_client.post(
            f"/admin/live-eval/runs/{run_id}/process-fixture-input",
            headers={"X-Admin-API-Key": "test-admin-key"},
            json={"tenant_id": "TENANT_LIVE_EVAL"},
        )

    assert first.status_code == 200, first.text
    body = first.json()
    assert body["root_job_id"]
    assert body["job_status"] == "awaiting_approval"
    assert second.status_code == 200
    assert second.json().get("intake_status") == "skipped"
    assert count_llm_operations_for_run(llm_db, run_id) == 4
    assert delegate.call_count == 4

    second_ops = count_llm_operations_for_run(llm_db, run_id)
    assert second_ops == 4
    assert delegate.call_count == 4

    run_row = llm_db.query(LiveEvalRunRow).filter_by(evaluation_run_id=run_id).one()
    assert run_row.transport_mode == "fixture_input"
    assert run_row.ai_mode == "live_llm"
    assert run_row.fixture_bundle_id is None
    assert run_row.expected_sender is None
    assert run_row.expected_recipient is None
    assert run_row.llm_provider == "openai"
    assert run_row.llm_requested_model == "gpt-4o-mini"
    assert run_row.llm_max_calls == 4

    jobs = llm_db.query(JobRecord).filter_by(tenant_id="TENANT_LIVE_EVAL").all()
    assert len(jobs) == 1
    domain_job = JobRepository.get_job_by_id(llm_db, "TENANT_LIVE_EVAL", body["root_job_id"])
    assert domain_job is not None
    assert domain_job.status == JobStatus.AWAITING_APPROVAL

    approvals = llm_db.query(ApprovalRequestRecord).filter_by(tenant_id="TENANT_LIVE_EVAL").all()
    pending = [row for row in approvals if row.state == "pending"]
    assert len(pending) == 1

    observation = llm_client.get(
        f"/admin/live-eval/runs/{run_id}/observation",
        params={"tenant_id": "TENANT_LIVE_EVAL"},
        headers={"X-Admin-API-Key": "test-admin-key"},
    ).json()
    violations = assert_s01_live_llm_semantics(observation)
    assert violations == [], violations

    llm_events = [
        e for e in observation.get("events", [])
        if e.get("category") == TELEMETRY_APP_LIVE_LLM
    ]
    succeeded = [e for e in llm_events if e.get("outcome") == "succeeded"]
    assert len(succeeded) == 4
    assert not any(e.get("outcome") == "blocked" for e in llm_events)
    assert not any(e.get("outcome") == "outcome_unknown" for e in llm_events)
    assert not any(e.get("outcome") == "failed" for e in llm_events)
    prompt_names = [e.get("operation") for e in succeeded]
    assert prompt_names == [
        "classification_v1",
        "entity_extraction_v1",
        "lead_scoring_v1",
        "decisioning_v1",
    ]

    external_writes = [
        e for e in observation.get("events", [])
        if e.get("outcome") == "succeeded"
        and e.get("category") not in {
            TELEMETRY_APP_LIVE_LLM,
            "app_live_eval_intake_started",
            "app_live_eval_intake_succeeded",
            "app_external_write_blocked",
        }
        and not str(e.get("category", "")).startswith("testbot_")
    ]
    assert external_writes == []


def test_llm_report_redaction_excludes_secrets(llm_eval_env, tmp_path, monkeypatch):
    monkeypatch.setenv(
        "STORAGE_PATH",
        str(tmp_path),
    )
    from app.core.settings import get_settings

    get_settings.cache_clear()

    report = build_live_eval_llm_report(
        evaluation_run_id="run-redact",
        run={
            "scenario_id": "S01_lead_laddbox_quality",
            "transport_mode": "fixture_input",
            "ai_mode": "live_llm",
            "status": "active",
            "config_hash": "abc",
            "llm_provider": "openai",
            "llm_requested_model": "gpt-4o-mini",
        },
        observation={
            "job": {
                "job_status": "awaiting_approval",
                "pending_approval_count": 1,
            },
            "events": [],
        },
        semantic_assertions=[],
        result="passed",
        scenario_content_hash=S01_LOCKED_SCENARIO_HASH,
    )
    path = write_llm_report_atomic("run-redact", report)
    payload = json.loads(path.read_text(encoding="utf-8"))
    blob = json.dumps(payload)
    for pattern in (
        r"sk-[A-Za-z0-9]{20,}",
        "Bearer ",
        "anna@example.com",
        "Hej, jag vill installera",
    ):
        assert not re.search(pattern, blob), pattern


def test_classify_llm_provider_errors():
    assert classify_llm_provider_error(TimeoutError("timeout")) == "timeout"
    from app.ai.exceptions import LLMRequestError

    assert classify_llm_provider_error(LLMRequestError("HTTPError 429")) == "rate_limit"


def test_operation_reservation_blocks_duplicate_prompt(db, llm_eval_env):
    snap = _snapshot("run-dup-op")
    db.add(
        LiveEvalRunRow(
            evaluation_run_id="run-dup-op",
            tenant_id="TENANT_LIVE_EVAL",
            scenario_id="S01_lead_laddbox_quality",
            attempt_id=1,
            transport_mode="fixture_input",
            ai_mode="live_llm",
            fixture_bundle_id=None,
            expected_sender=None,
            expected_recipient=None,
            llm_provider="openai",
            llm_requested_model="gpt-4o-mini",
            llm_max_calls=4,
            status="registered",
            created_by="test",
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
            config_hash="cfg",
        )
    )
    db.commit()

    reserve_live_llm_operation(
        db,
        snapshot=snap,
        prompt_name="classification_v1",
        requested_model="gpt-4o-mini",
    )
    with pytest.raises(LiveEvalSafetyError, match="in progress|retry blocked"):
        reserve_live_llm_operation(
            db,
            snapshot=snap,
            prompt_name="classification_v1",
            requested_model="gpt-4o-mini",
        )
