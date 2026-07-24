"""Hermetic tests for live LLM response contract (2F.3D.2)."""

from __future__ import annotations

import hashlib
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
from app.evaluation.live.llm_operations import _hash_validated_output, reserve_live_llm_operation
from app.evaluation.live.llm_provider import PROMPT_RESPONSE_MODELS
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


def _normalized_validated_output(prompt_name: str, raw_output: dict) -> dict:
    response_model = PROMPT_RESPONSE_MODELS[prompt_name]
    validated = response_model.model_validate(raw_output)
    return json.loads(validated.model_dump_json())


def _run_classification_operation(
    contract_db,
    *,
    run_id: str,
    fixture_output: dict,
    returned_model: str = "gpt-4o-mini",
    finish_reason: str | None = "stop",
) -> tuple[LiveEvalLlmOperationRow, dict]:
    _seed_run(contract_db, run_id)
    snap = _snapshot(run_id)
    delegate = FakeEvalLLMDelegate(
        returned_model=returned_model,
        finish_reason=finish_reason,
        fixtures={"classification_v1": fixture_output},
    )
    client = EvalLLMClient(delegate, snapshot=snap, db=contract_db)
    token = set_active_prompt_name("classification_v1")
    with live_eval_context(snap, db=contract_db):
        output = client.generate_json("classification_v1 prompt")
    reset_active_prompt_name(token)
    row = contract_db.query(LiveEvalLlmOperationRow).filter_by(
        evaluation_run_id=run_id,
        prompt_name="classification_v1",
    ).one()
    return row, output


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


def test_output_hash_matches_pydantic_normalized_output(contract_db):
    fixture_output = {
        "detected_job_type": "lead",
        "confidence": 0.9,
        "reasons": ["keyword_match"],
    }
    row, output = _run_classification_operation(
        contract_db,
        run_id="run-output-hash",
        fixture_output=fixture_output,
        returned_model="gpt-4o-mini-2024-07-18",
    )

    assert row.status == "succeeded"
    assert row.schema_validation_status == "passed"
    assert output == _normalized_validated_output("classification_v1", fixture_output)

    expected_hash = _hash_validated_output(output)
    assert row.output_hash == expected_hash

    raw_json_hash = hashlib.sha256(json.dumps(fixture_output).encode("utf-8")).hexdigest()
    assert row.output_hash != raw_json_hash

    transport_wrapper_hash = hashlib.sha256(
        json.dumps(
            {
                "choices": [{"message": {"content": json.dumps(fixture_output)}}],
                "usage": row.input_tokens,
                "model": row.returned_model,
                "finish_reason": row.finish_reason,
            }
        ).encode("utf-8")
    ).hexdigest()
    assert row.output_hash != transport_wrapper_hash


def test_output_hash_invariant_across_raw_key_order(contract_db):
    fixture_a = {
        "detected_job_type": "lead",
        "confidence": 0.9,
        "reasons": ["keyword_match"],
    }
    fixture_b = {
        "reasons": ["keyword_match"],
        "confidence": 0.9,
        "detected_job_type": "lead",
    }

    row_a, _ = _run_classification_operation(
        contract_db,
        run_id="run-hash-order-a",
        fixture_output=fixture_a,
        returned_model="gpt-4o-mini",
    )
    row_b, _ = _run_classification_operation(
        contract_db,
        run_id="run-hash-order-b",
        fixture_output=fixture_b,
        returned_model="gpt-4o-mini-2024-07-18",
    )

    normalized_a = _normalized_validated_output("classification_v1", fixture_a)
    normalized_b = _normalized_validated_output("classification_v1", fixture_b)
    assert normalized_a == normalized_b
    assert row_a.output_hash == row_b.output_hash == _hash_validated_output(normalized_a)


def test_output_hash_changes_when_validated_output_differs(contract_db):
    base_fixture = {
        "detected_job_type": "lead",
        "confidence": 0.9,
        "reasons": ["keyword_match"],
    }
    changed_fixture = {
        "detected_job_type": "lead",
        "confidence": 0.91,
        "reasons": ["keyword_match", "follow_up"],
    }

    row_base, _ = _run_classification_operation(
        contract_db,
        run_id="run-hash-base",
        fixture_output=base_fixture,
    )
    row_changed, _ = _run_classification_operation(
        contract_db,
        run_id="run-hash-changed",
        fixture_output=changed_fixture,
    )

    assert row_base.output_hash != row_changed.output_hash
    assert row_base.output_hash == _hash_validated_output(
        _normalized_validated_output("classification_v1", base_fixture)
    )
    assert row_changed.output_hash == _hash_validated_output(
        _normalized_validated_output("classification_v1", changed_fixture)
    )


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
