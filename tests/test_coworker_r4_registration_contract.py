"""Focused tests for R4 reviewed-live registration contract."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.evaluation.live.constants import ALLOWED_AI_MODES, REVIEWED_LIVE_LLM_BODY
from app.evaluation.live.delivery_mailbox_reader import (
    is_r4_reviewed_live_eval_run,
    is_reviewed_live_eval_run,
)
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.safety import (
    validate_live_gmail_registration,
    validate_live_gmail_run_for_mutation,
    validate_registration_request,
)
from app.evaluation.live.schemas import LiveEvalRunRegisterRequest
from app.evaluation.profile_testbot.qualification.coworker_r4_attempt1_orphan import (
    ATTEMPT1_CAMPAIGN_ID,
    assert_r4_campaign_not_quarantined,
    attempt1_orphan_record,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_mutation_contract import (
    R4_MUTATION_PROCESS_DELIVERY,
    validate_r4_mutation_operation,
    validate_r4_mutation_operation_for_row,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_registration_contract import (
    R4RegistrationContext,
    R4RegistrationContractRequest,
    validate_r4_registration_contract,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_registration_readiness import (
    evaluate_r4_registration_readiness,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (
    R4_EXECUTION_MODE,
    R4_LIVE_QUALITY_CAMPAIGN_TYPE,
    R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH,
    R4_LOCKED_CANDIDATE_RUNTIME_SHA,
    R4_LOCKED_MANIFEST_SEMANTIC_HASH,
    R4_LOCKED_REVIEW_ARTIFACT_SHA256,
    R4_NO_SEND_SCENARIO_IDS,
    R4_SEND_SCENARIO_IDS,
    R4_TENANT_ID,
)
from app.repositories.postgres.live_eval_models import LiveEvalRunRow

EXEC = "1" * 40


@pytest.fixture
def r4_env(monkeypatch):
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("LIVE_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_GMAIL_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_EVAL_TENANT_IDS", R4_TENANT_ID)
    monkeypatch.setenv("LIVE_EVAL_SENDER_EMAILS", "sender@eval.test")
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_EMAILS", "niklas.palm@sol-f.se")
    monkeypatch.setenv("BUILD_GIT_SHA", EXEC)
    from app.core.settings import get_settings
    from app.evaluation.live.config import get_live_eval_config

    get_settings.cache_clear()
    get_live_eval_config.cache_clear()
    yield
    get_settings.cache_clear()
    get_live_eval_config.cache_clear()


def _send_ctx(**overrides) -> R4RegistrationContext:
    base = {
        "candidate_runtime_sha": R4_LOCKED_CANDIDATE_RUNTIME_SHA,
        "executor_runtime_sha": EXEC,
        "candidate_package_semantic_hash": R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH,
        "human_review_sha256": R4_LOCKED_REVIEW_ARTIFACT_SHA256,
        "planned_gmail_send": True,
        "plan_hash": "plan-hash",
        "reviewed_body_hash": "a" * 64,
        "review_status": "PASS",
        "renderer_type": "constrained_llm_v1",
        "model_id": "gpt-4o-mini-2024-07-18",
        "prompt_version": "coworker_constrained_llm_v5",
        "automatic_gmail": False,
        "production_activation": False,
    }
    base.update(overrides)
    return R4RegistrationContext(**base)


def _no_send_ctx(**overrides) -> R4RegistrationContext:
    base = {
        "candidate_runtime_sha": R4_LOCKED_CANDIDATE_RUNTIME_SHA,
        "executor_runtime_sha": EXEC,
        "candidate_package_semantic_hash": R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH,
        "human_review_sha256": R4_LOCKED_REVIEW_ARTIFACT_SHA256,
        "planned_gmail_send": False,
        "automatic_gmail": False,
        "production_activation": False,
    }
    base.update(overrides)
    return R4RegistrationContext(**base)


def _req(**overrides) -> R4RegistrationContractRequest:
    base = {
        "tenant_id": R4_TENANT_ID,
        "scenario_id": "PTB-DCQ-0000",
        "transport_mode": "live_gmail",
        "ai_mode": REVIEWED_LIVE_LLM_BODY,
        "campaign_type": R4_LIVE_QUALITY_CAMPAIGN_TYPE,
        "execution_mode": R4_EXECUTION_MODE,
        "expected_sender": "sender@eval.test",
        "expected_recipient": "niklas.palm@sol-f.se",
        "manifest_hash": R4_LOCKED_MANIFEST_SEMANTIC_HASH,
        "campaign_id": str(uuid4()),
        "evaluation_run_id": str(uuid4()),
        "registration_context": _send_ctx(),
        "sender_allowlist": {"sender@eval.test"},
        "recipient_allowlist": {"niklas.palm@sol-f.se"},
    }
    base.update(overrides)
    return R4RegistrationContractRequest(**base)


def _row(**overrides) -> LiveEvalRunRow:
    base = {
        "evaluation_run_id": str(uuid4()),
        "tenant_id": R4_TENANT_ID,
        "scenario_id": "PTB-DCQ-0000",
        "attempt_id": 1,
        "transport_mode": "live_gmail",
        "ai_mode": REVIEWED_LIVE_LLM_BODY,
        "status": "registered",
        "created_by": "test",
        "expires_at": datetime.now(timezone.utc),
        "config_hash": "0" * 64,
        "campaign_type": R4_LIVE_QUALITY_CAMPAIGN_TYPE,
        "execution_mode": R4_EXECUTION_MODE,
        "manifest_hash": R4_LOCKED_MANIFEST_SEMANTIC_HASH,
        "registration_context": _send_ctx().model_dump(),
        "expected_sender": "sender@eval.test",
        "expected_recipient": "niklas.palm@sol-f.se",
    }
    base.update(overrides)
    return LiveEvalRunRow(**base)


def test_schema_accepts_reviewed_live_llm_body():
    req = LiveEvalRunRegisterRequest(
        evaluation_run_id=str(uuid4()),
        tenant_id=R4_TENANT_ID,
        scenario_id="PTB-DCQ-0000",
        attempt_id=1,
        ai_mode=REVIEWED_LIVE_LLM_BODY,
        campaign_type=R4_LIVE_QUALITY_CAMPAIGN_TYPE,
        execution_mode=R4_EXECUTION_MODE,
        registration_context=_send_ctx(),
    )
    assert req.ai_mode == REVIEWED_LIVE_LLM_BODY


def test_schema_rejects_unknown_ai_mode():
    with pytest.raises(ValidationError):
        LiveEvalRunRegisterRequest(
            evaluation_run_id=str(uuid4()),
            tenant_id=R4_TENANT_ID,
            scenario_id="PTB-DCQ-0000",
            attempt_id=1,
            ai_mode="not_a_mode",  # type: ignore[arg-type]
        )


def test_allowed_ai_modes_contains_r4():
    assert REVIEWED_LIVE_LLM_BODY in ALLOWED_AI_MODES


def test_exact_r4_registration_pass(r4_env):
    result = validate_r4_registration_contract(_req())
    assert result.registration_contract_valid
    assert result.registration_blockers == []


@pytest.mark.parametrize(
    "field,value,needle",
    [
        ("campaign_type", "wrong", "campaign_type"),
        ("execution_mode", "wrong", "execution_mode"),
        ("manifest_hash", "0" * 64, "manifest_hash"),
        ("tenant_id", "OTHER", "tenant"),
        ("expected_recipient", "other@x.com", "recipient"),
        ("scenario_id", "PTB-UNKNOWN-0001", "not in R4 registry"),
    ],
)
def test_registration_blockers(r4_env, field, value, needle):
    result = validate_r4_registration_contract(_req(**{field: value}))
    assert not result.registration_contract_valid
    assert any(needle in b for b in result.registration_blockers)


def test_send_missing_reviewed_context_blocks(r4_env):
    result = validate_r4_registration_contract(_req(registration_context=None))
    assert not result.registration_contract_valid
    assert any("registration_context missing" in b for b in result.registration_blockers)


def test_send_body_hash_required(r4_env):
    ctx = _send_ctx(reviewed_body_hash=None)
    # Pydantic may reject None if typed as str|None - field allows None
    result = validate_r4_registration_contract(_req(registration_context=ctx))
    assert not result.registration_contract_valid
    assert any("reviewed_body_hash" in b for b in result.registration_blockers)


def test_send_review_fail_blocks(r4_env):
    result = validate_r4_registration_contract(
        _req(registration_context=_send_ctx(review_status="FAIL"))
    )
    assert not result.registration_contract_valid


def test_no_send_with_body_blocks(r4_env):
    sid = next(iter(R4_NO_SEND_SCENARIO_IDS))
    result = validate_r4_registration_contract(
        _req(
            scenario_id=sid,
            registration_context=_no_send_ctx(reviewed_body_hash="b" * 64),
        )
    )
    assert not result.registration_contract_valid


def test_no_send_outside_registry_blocks(r4_env):
    result = validate_r4_registration_contract(
        _req(scenario_id="PTB-SEM-9999", registration_context=_no_send_ctx())
    )
    assert not result.registration_contract_valid


def test_unknown_context_fields_blocked():
    with pytest.raises(ValidationError):
        R4RegistrationContext(
            **_send_ctx().model_dump(),
            secret_token="nope",  # type: ignore[call-arg]
        )


def test_config_hash_changes_with_body_hash():
    from app.evaluation.live.registry import _compute_config_hash

    a = _compute_config_hash({"registration_context": _send_ctx().model_dump()})
    b = _compute_config_hash(
        {"registration_context": _send_ctx(reviewed_body_hash="b" * 64).model_dump()}
    )
    assert a != b


def test_config_hash_changes_with_candidate_hash():
    from app.evaluation.live.registry import _compute_config_hash

    a = _compute_config_hash({"registration_context": _send_ctx().model_dump()})
    other = _send_ctx().model_dump()
    other["candidate_package_semantic_hash"] = "f" * 64
    b = _compute_config_hash({"registration_context": other})
    assert a != b


def test_mutation_accepts_exact_r4_row(r4_env):
    row = _row()
    result = validate_r4_mutation_operation_for_row(
        row, tenant_id=R4_TENANT_ID, operation=R4_MUTATION_PROCESS_DELIVERY
    )
    assert result.allowed


def test_mutation_blocks_generic_ai_mode_only(r4_env):
    result = validate_r4_mutation_operation(
        operation=R4_MUTATION_PROCESS_DELIVERY,
        tenant_id=R4_TENANT_ID,
        campaign_type=None,
        execution_mode=None,
        ai_mode=REVIEWED_LIVE_LLM_BODY,
    )
    assert not result.allowed


def test_is_r4_reviewed_live_eval_run(r4_env):
    row = _row()
    assert is_r4_reviewed_live_eval_run(row)
    assert is_reviewed_live_eval_run(row)


def test_validate_registration_request_r4_branch(r4_env):
    validate_registration_request(
        tenant_id=R4_TENANT_ID,
        transport_mode="live_gmail",
        ai_mode=REVIEWED_LIVE_LLM_BODY,
        scenario_id="PTB-DCQ-0000",
        expected_sender="sender@eval.test",
        expected_recipient="niklas.palm@sol-f.se",
        campaign_type=R4_LIVE_QUALITY_CAMPAIGN_TYPE,
        execution_mode=R4_EXECUTION_MODE,
        manifest_hash=R4_LOCKED_MANIFEST_SEMANTIC_HASH,
        campaign_id=str(uuid4()),
        evaluation_run_id=str(uuid4()),
        registration_context=_send_ctx(),
    )


def test_validate_live_gmail_registration_r4_before_r3_overlap(r4_env):
    # Overlapping scenario ID must accept R4 ai_mode.
    validate_live_gmail_registration(
        transport_mode="live_gmail",
        scenario_id="PTB-DCQ-0000",
        ai_mode=REVIEWED_LIVE_LLM_BODY,
        campaign_type=R4_LIVE_QUALITY_CAMPAIGN_TYPE,
    )


def test_r3_path_unchanged(r4_env):
    validate_live_gmail_registration(
        transport_mode="live_gmail",
        scenario_id="PTB-DCQ-0000",
        ai_mode="r3_frozen_approved_body",
        campaign_type="coworker_r3_frozen_live_canary",
    )


def test_attempt1_reuse_blocked():
    with pytest.raises(LiveEvalSafetyError):
        assert_r4_campaign_not_quarantined(ATTEMPT1_CAMPAIGN_ID)
    rec = attempt1_orphan_record()
    assert rec.reuse_blocked is True
    assert rec.exclude_from_r4_pass is True
    assert rec.resume_forbidden is True


def test_registration_readiness_20_16(r4_env):
    report = evaluate_r4_registration_readiness(executor_runtime_sha=EXEC)
    assert report["send_registration_ready"] == "20/20"
    assert report["no_send_registration_ready"] == "16/16"
    assert report["mutation_contract_ready"] == "36/36"
    assert report["automatic_gmail"] is False
    assert report["production_activation"] is False
    assert report["passed"] is True


def test_live_llm_quality_rule_still_requires_live_llm(r4_env):
    with pytest.raises(LiveEvalSafetyError):
        validate_live_gmail_registration(
            transport_mode="live_gmail",
            scenario_id="PTB-Q96-0000",
            ai_mode=REVIEWED_LIVE_LLM_BODY,
            campaign_type=None,
        )
