"""Trust-boundary tests for R3 frozen approval body binding."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.evaluation.live.routes import router as live_eval_router
from app.evaluation.profile_testbot.constants import LIVE_EVAL_TENANT_ID
from app.evaluation.profile_testbot.qualification.coworker_r3_frozen_bind import (
    R3FrozenBindError,
    R3FrozenBindRequest,
    bind_frozen_approval_body_record,
    validate_r3_frozen_bind_request,
)
from app.evaluation.profile_testbot.qualification.coworker_r3_frozen_bodies import (
    load_r3_approved_send_body_texts,
    r3_send_body_hash,
)
from app.evaluation.profile_testbot.qualification.coworker_r3_readiness import (
    R3_APPROVED_SEND_BODY_HASHES,
)
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.database import Base


CANONICAL_SCENARIO = "PTB-DCQ-0056"


@pytest.fixture
def live_eval_env(monkeypatch):
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("LIVE_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_EVAL_GMAIL_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_GMAIL_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_EVAL_TENANT_IDS", "TENANT_LIVE_EVAL")
    monkeypatch.setenv("LIVE_EVAL_SENDER_EMAILS", "sender@eval.test")
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_EMAILS", "recipient@eval.test")
    monkeypatch.setenv("LIVE_EVAL_GMAIL_LABEL", "krowolf-live-eval")
    monkeypatch.setenv("EXTERNAL_SIDE_EFFECT_TESTS", "yes")
    from app.core.settings import get_settings
    from app.evaluation.live.config import get_live_eval_config

    get_settings.cache_clear()
    get_live_eval_config.cache_clear()
    yield
    get_settings.cache_clear()
    get_live_eval_config.cache_clear()


@pytest.fixture
def bind_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine, tables=[ApprovalRequestRecord.__table__])
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _canonical_body(scenario_id: str = CANONICAL_SCENARIO) -> str:
    return load_r3_approved_send_body_texts()[scenario_id]


def _canonical_hash(scenario_id: str = CANONICAL_SCENARIO) -> str:
    return R3_APPROVED_SEND_BODY_HASHES[scenario_id]


def _seed_pending_approval(
    db,
    *,
    scenario_job_id: str | None = None,
    state: str = "pending",
    next_on_approve: str = "action_execute",
    delivery_body: str = "original",
) -> tuple[str, str]:
    approval_id = f"apr_{uuid.uuid4().hex[:12]}"
    job_id = scenario_job_id or str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    db.add(
        ApprovalRequestRecord(
            approval_id=approval_id,
            tenant_id=LIVE_EVAL_TENANT_ID,
            job_id=job_id,
            job_type="lead",
            state=state,
            channel="dashboard",
            title="R3 send",
            summary="pending",
            next_on_approve=next_on_approve,
            request_payload={"approval_id": approval_id},
            delivery_payload={"body": delivery_body},
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()
    return approval_id, job_id


def _bind_request(
    *,
    approval_id: str,
    job_id: str,
    scenario_id: str = CANONICAL_SCENARIO,
    frozen_body: str | None = None,
    expected_body_hash: str | None = None,
    tenant_id: str = LIVE_EVAL_TENANT_ID,
) -> R3FrozenBindRequest:
    body = frozen_body if frozen_body is not None else _canonical_body(scenario_id)
    digest = expected_body_hash if expected_body_hash is not None else _canonical_hash(scenario_id)
    return R3FrozenBindRequest(
        tenant_id=tenant_id,
        job_id=job_id,
        approval_id=approval_id,
        scenario_id=scenario_id,
        frozen_body=body,
        expected_body_hash=digest,
    )


def _delivery_body(db, approval_id: str) -> str:
    record = db.get(ApprovalRequestRecord, approval_id)
    assert record is not None
    return str((record.delivery_payload or {}).get("body", ""))


class TestR3FrozenBindService:
    def test_passes_canonical_pending_action_execute(self, bind_db):
        approval_id, job_id = _seed_pending_approval(bind_db)
        request = _bind_request(approval_id=approval_id, job_id=job_id)
        result = bind_frozen_approval_body_record(bind_db, request)
        assert result.bound is True
        assert result.body_hash == _canonical_hash()
        assert result.audit.body_source == "frozen_approved_body"
        record = bind_db.get(ApprovalRequestRecord, approval_id)
        assert record.delivery_payload["body"] == _canonical_body()
        assert record.delivery_payload["r3_frozen_bind"]["scenario_id"] == CANONICAL_SCENARIO

    def test_passes_canonical_pending_email_send(self, bind_db):
        approval_id, job_id = _seed_pending_approval(bind_db, next_on_approve="email_send")
        result = bind_frozen_approval_body_record(
            bind_db,
            _bind_request(approval_id=approval_id, job_id=job_id),
        )
        assert result.bound is True

    def test_blocks_arbitrary_text_with_self_matched_hash(self, bind_db):
        approval_id, job_id = _seed_pending_approval(bind_db, delivery_body="keep-me")
        arbitrary = "totally arbitrary operator text"
        arbitrary_hash = r3_send_body_hash(arbitrary)
        request = _bind_request(
            approval_id=approval_id,
            job_id=job_id,
            frozen_body=arbitrary,
            expected_body_hash=arbitrary_hash,
        )
        with pytest.raises(R3FrozenBindError, match="canonical approved hash"):
            bind_frozen_approval_body_record(bind_db, request)
        assert _delivery_body(bind_db, approval_id) == "keep-me"

    def test_blocks_wrong_scenario_id(self, bind_db):
        approval_id, job_id = _seed_pending_approval(bind_db, delivery_body="keep-me")
        request = R3FrozenBindRequest(
            tenant_id=LIVE_EVAL_TENANT_ID,
            job_id=job_id,
            approval_id=approval_id,
            scenario_id="PTB-DCQ-9999",
            frozen_body=_canonical_body(),
            expected_body_hash=_canonical_hash(),
        )
        with pytest.raises(R3FrozenBindError, match="canonical approved body hashes"):
            validate_r3_frozen_bind_request(
                request,
                record=bind_db.get(ApprovalRequestRecord, approval_id),
            )
        assert _delivery_body(bind_db, approval_id) == "keep-me"

    def test_blocks_wrong_expected_body_hash(self, bind_db):
        approval_id, job_id = _seed_pending_approval(bind_db, delivery_body="keep-me")
        request = _bind_request(
            approval_id=approval_id,
            job_id=job_id,
            expected_body_hash="0" * 64,
        )
        with pytest.raises(R3FrozenBindError, match="expected_body_hash"):
            bind_frozen_approval_body_record(bind_db, request)
        assert _delivery_body(bind_db, approval_id) == "keep-me"

    def test_blocks_wrong_tenant(self, bind_db):
        approval_id, job_id = _seed_pending_approval(bind_db, delivery_body="keep-me")
        request = _bind_request(
            approval_id=approval_id,
            job_id=job_id,
            tenant_id="TENANT_OTHER",
        )
        with pytest.raises(R3FrozenBindError, match="tenant not allowed"):
            bind_frozen_approval_body_record(bind_db, request)
        assert _delivery_body(bind_db, approval_id) == "keep-me"

    def test_blocks_approval_wrong_job_id(self, bind_db):
        approval_id, job_id = _seed_pending_approval(bind_db, delivery_body="keep-me")
        request = _bind_request(approval_id=approval_id, job_id=str(uuid.uuid4()))
        with pytest.raises(R3FrozenBindError, match="does not belong"):
            bind_frozen_approval_body_record(bind_db, request)
        assert _delivery_body(bind_db, approval_id) == "keep-me"

    def test_blocks_approval_not_pending(self, bind_db):
        approval_id, job_id = _seed_pending_approval(bind_db, state="approved", delivery_body="keep-me")
        request = _bind_request(approval_id=approval_id, job_id=job_id)
        with pytest.raises(R3FrozenBindError, match="not pending"):
            bind_frozen_approval_body_record(bind_db, request)
        assert _delivery_body(bind_db, approval_id) == "keep-me"

    def test_blocks_non_send_approval_type(self, bind_db):
        approval_id, job_id = _seed_pending_approval(
            bind_db,
            next_on_approve="manual_review",
            delivery_body="keep-me",
        )
        request = _bind_request(approval_id=approval_id, job_id=job_id)
        with pytest.raises(R3FrozenBindError, match="send-type"):
            bind_frozen_approval_body_record(bind_db, request)
        assert _delivery_body(bind_db, approval_id) == "keep-me"


@pytest.fixture
def r3_bind_client(bind_db, live_eval_env, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    monkeypatch.setenv("R3_FROZEN_APPROVAL_BIND_ALLOWED", "yes")
    app = FastAPI()
    app.include_router(live_eval_router)
    app.dependency_overrides[get_db] = lambda: bind_db
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


def test_route_blocks_without_env_flag(bind_db, live_eval_env, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    monkeypatch.delenv("R3_FROZEN_APPROVAL_BIND_ALLOWED", raising=False)
    app = FastAPI()
    app.include_router(live_eval_router)
    app.dependency_overrides[get_db] = lambda: bind_db
    approval_id, job_id = _seed_pending_approval(bind_db, delivery_body="keep-me")
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/admin/live-eval/r3/bind-frozen-approval-body",
            headers={"X-Admin-API-Key": "test-admin-key"},
            json={
                "tenant_id": LIVE_EVAL_TENANT_ID,
                "job_id": job_id,
                "approval_id": approval_id,
                "scenario_id": CANONICAL_SCENARIO,
                "frozen_body": _canonical_body(),
                "expected_body_hash": _canonical_hash(),
            },
        )
    assert response.status_code == 403
    assert _delivery_body(bind_db, approval_id) == "keep-me"
    app.dependency_overrides.clear()


def test_route_passes_canonical_bind(r3_bind_client, bind_db):
    approval_id, job_id = _seed_pending_approval(bind_db)
    response = r3_bind_client.post(
        "/admin/live-eval/r3/bind-frozen-approval-body",
        headers={"X-Admin-API-Key": "test-admin-key"},
        json={
            "tenant_id": LIVE_EVAL_TENANT_ID,
            "job_id": job_id,
            "approval_id": approval_id,
            "scenario_id": CANONICAL_SCENARIO,
            "frozen_body": _canonical_body(),
            "expected_body_hash": _canonical_hash(),
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["bound"] is True
    assert body["scenario_id"] == CANONICAL_SCENARIO
    assert body["audit"]["body_source"] == "frozen_approved_body"
    assert body["audit"]["canonical_body_hash"] == _canonical_hash()
