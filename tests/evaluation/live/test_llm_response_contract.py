"""Hermetic tests for live LLM response contract (2F.3D.2)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.exceptions import LLMResponseError
from app.evaluation.fixture_ai import reset_active_prompt_name, set_active_prompt_name
from app.evaluation.live.context import live_eval_context
from app.evaluation.live.eval_llm_client import (
    EvalLLMClient,
    classify_finish_reason_failure,
)
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.llm_operations import reserve_live_llm_operation
from app.evaluation.live.llm_report import (
    LLM_FAILURE_REPORT_SCHEMA_VERSION,
    build_live_eval_llm_failure_report,
    write_llm_failure_report_atomic,
)
from app.evaluation.live.model_identity import (
    LIVE_EVAL_ALLOWED_RETURNED_MODELS,
    validate_returned_model_identity,
)
from app.evaluation.live.provider_redaction import sanitize_provider_error_message
from app.evaluation.live.schemas import TrustedLiveEvalSnapshot
from app.repositories.postgres.database import Base
from app.repositories.postgres.live_eval_models import (
    LiveEvalExternalEventRow,
    LiveEvalLlmOperationRow,
    LiveEvalRunRow,
)
from tests.evaluation.live.fake_llm_client import FakeEvalLLMDelegate


def _snapshot(run_id: str) -> TrustedLiveEvalSnapshot:
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


@pytest.fixture
def contract_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[
            LiveEvalRunRow.__table__,
            LiveEvalLlmOperationRow.__table__,
            LiveEvalExternalEventRow.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _seed_run(db, run_id: str):
    db.add(
        LiveEvalRunRow(
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
            status="active",
            created_by="test",
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
            config_hash="cfg",
        )
    )
    db.commit()


@pytest.mark.parametrize(
    ("returned", "should_pass"),
    [
        ("gpt-4o-mini", True),
        ("gpt-4o-mini-2024-07-18", True),
        ("gpt-4o-mini-2024-08-06", False),
        ("gpt-4o", False),
        ("", False),
    ],
)
def test_model_identity_allowlist(returned, should_pass):
    if should_pass:
        assert validate_returned_model_identity(
            requested_model="gpt-4o-mini",
            returned_model=returned,
        ) == returned
    else:
        with pytest.raises(LiveEvalSafetyError):
            validate_returned_model_identity(
                requested_model="gpt-4o-mini",
                returned_model=returned,
            )


def test_model_identity_rejects_unknown_requested_alias():
    with pytest.raises(LiveEvalSafetyError, match="not allowlisted"):
        validate_returned_model_identity(
            requested_model="gpt-4o",
            returned_model="gpt-4o",
        )


def test_model_identity_has_no_prefix_wildcards():
    allowed = LIVE_EVAL_ALLOWED_RETURNED_MODELS["gpt-4o-mini"]
    assert all("*" not in value and "?" not in value for value in allowed)


def test_eval_client_accepts_alias_and_snapshot(contract_db):
    for index, returned in enumerate(("gpt-4o-mini", "gpt-4o-mini-2024-07-18")):
        run_id = f"run-alias-snapshot-{index}"
        _seed_run(contract_db, run_id)
        snap = _snapshot(run_id)
        delegate = FakeEvalLLMDelegate(returned_model=returned)
        client = EvalLLMClient(delegate, snapshot=snap, db=contract_db)
        token = set_active_prompt_name("classification_v1")
        with live_eval_context(snap, db=contract_db):
            output = client.generate_json("classification_v1 prompt")
        reset_active_prompt_name(token)
        assert output["detected_job_type"] == "lead"
        row = contract_db.query(LiveEvalLlmOperationRow).filter_by(
            evaluation_run_id=run_id,
            prompt_name="classification_v1",
        ).one()
        assert row.status == "succeeded"
        assert row.returned_model == returned
        assert row.schema_validation_status == "passed"


def test_eval_client_schema_invalid_marks_failed_and_blocks_next(contract_db):
    run_id = "run-schema-fail"
    _seed_run(contract_db, run_id)
    snap = _snapshot(run_id)
    delegate = FakeEvalLLMDelegate(
        fixtures={
            "classification_v1": {"detected_job_type": "not-a-real-type", "confidence": 0.9, "reasons": []},
        }
    )
    client = EvalLLMClient(delegate, snapshot=snap, db=contract_db)
    token = set_active_prompt_name("classification_v1")
    with live_eval_context(snap, db=contract_db):
        with pytest.raises(ValidationError):
            client.generate_json("classification_v1 prompt")
    reset_active_prompt_name(token)
    row = contract_db.query(LiveEvalLlmOperationRow).filter_by(
        evaluation_run_id=run_id,
        prompt_name="classification_v1",
    ).one()
    assert row.status == "failed"
    assert row.failure_reason == "schema_validation"
    with pytest.raises(LiveEvalSafetyError, match="ordinal 2 blocked"):
        reserve_live_llm_operation(
            contract_db,
            snapshot=snap,
            prompt_name="entity_extraction_v1",
            requested_model="gpt-4o-mini",
        )


@pytest.mark.parametrize(
    ("finish_reason", "expected_failure"),
    [
        ("stop", None),
        ("length", "incomplete_finish_reason"),
        ("content_filter", "safety_refusal"),
        (None, "incomplete_finish_reason"),
        ("tool_calls", "incomplete_finish_reason"),
        ("weird", "incomplete_finish_reason"),
    ],
)
def test_finish_reason_contract(finish_reason, expected_failure):
    assert classify_finish_reason_failure(finish_reason) == expected_failure


def test_eval_client_rejects_non_stop_finish_reason(contract_db):
    run_id = "run-finish"
    _seed_run(contract_db, run_id)
    snap = _snapshot(run_id)
    delegate = FakeEvalLLMDelegate(finish_reason="length")
    client = EvalLLMClient(delegate, snapshot=snap, db=contract_db)
    token = set_active_prompt_name("classification_v1")
    with live_eval_context(snap, db=contract_db):
        with pytest.raises(LLMResponseError, match="finish_reason"):
            client.generate_json("classification_v1 prompt")
    reset_active_prompt_name(token)
    row = contract_db.query(LiveEvalLlmOperationRow).one()
    assert row.status == "failed"
    assert row.failure_reason == "incomplete_finish_reason"


def test_provider_error_redaction_strips_sensitive_payload():
    raw = (
        'LLM HTTPError 401: {"error":"invalid"} Authorization: Bearer sk-abcdefghijklmnop '
        "anna@example.com"
    )
    sanitized = sanitize_provider_error_message(raw)
    assert "Bearer" not in sanitized
    assert "sk-abcdefghijklmnop" not in sanitized
    assert "anna@example.com" not in sanitized
    assert "401" in sanitized


def test_failure_artifact_written_without_run_directory(tmp_path):
    payload = build_live_eval_llm_failure_report(
        evaluation_run_id=None,
        scenario_id="S01_lead_laddbox_quality",
        failure_stage="registration",
        failure_category="registration_failed",
        error='Bearer sk-testsecret1234567890 prompt body {"message_text":"secret"}',
    )
    target = tmp_path / "llm_failure_report.json"
    write_llm_failure_report_atomic(target, payload)
    saved = json.loads(target.read_text(encoding="utf-8"))
    assert saved["report_schema_version"] == LLM_FAILURE_REPORT_SCHEMA_VERSION
    assert saved["failure_stage"] == "registration"
    assert "sk-testsecret" not in json.dumps(saved)
    assert "Bearer" not in json.dumps(saved)
