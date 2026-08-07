"""Focused tests for R4 context-bound live-Gmail scenario eligibility."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.safety import (
    require_scenario_allowed_for_live_gmail,
    validate_live_gmail_registration,
    validate_registration_request,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_live_gmail_eligibility import (
    R4_LOCAL_QUARANTINE_SCENARIO_IDS,
    evaluate_r4_live_gmail_scenario_eligibility_matrix,
    require_r4_reviewed_live_gmail_scenario_eligible,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_registration_contract import (
    REVIEWED_LIVE_LLM_BODY,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_registration_payload import (
    build_r4_live_eval_register_request,
    evaluate_exact_r4_registration_payload_matrix,
    r4_registration_campaign_bindings,
    send_registration_fields_from_candidate,
    validate_exact_r4_registration_payload,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (
    R4_EXECUTE_AI_MODE,
    R4_EXECUTION_MODE,
    R4_LIVE_QUALITY_CAMPAIGN_TYPE,
    R4_LOCKED_CANDIDATE_RUNTIME_SHA,
    R4_LOCKED_MANIFEST_SEMANTIC_HASH,
    R4_NO_SEND_SCENARIO_IDS,
    R4_SCENARIO_IDS,
    R4_SEND_SCENARIO_IDS,
    R4_TENANT_ID,
)
from tests.test_r4_exact_registration_payload import (
    EXEC,
    RECIPIENT,
    SENDER,
    _synthetic_locked_artifacts,
)

PTB_SEM_0024 = "PTB-SEM-0024"


@pytest.fixture
def r4_env(monkeypatch):
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("LIVE_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_GMAIL_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_EVAL_TENANT_IDS", R4_TENANT_ID)
    monkeypatch.setenv("LIVE_EVAL_SENDER_EMAILS", SENDER)
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_EMAILS", RECIPIENT)
    monkeypatch.setenv("BUILD_GIT_SHA", EXEC)
    from app.core.settings import get_settings
    from app.evaluation.live.config import get_live_eval_config

    get_settings.cache_clear()
    get_live_eval_config.cache_clear()
    yield
    get_settings.cache_clear()
    get_live_eval_config.cache_clear()


def _bindings():
    return r4_registration_campaign_bindings(
        campaign_id=str(uuid4()),
        candidate_runtime_sha=R4_LOCKED_CANDIDATE_RUNTIME_SHA,
        executor_runtime_sha=EXEC,
        expected_sender=SENDER,
        expected_recipient=RECIPIENT,
        manifest_semantic_hash=R4_LOCKED_MANIFEST_SEMANTIC_HASH,
    )


def _r4_gmail_kwargs(scenario_id: str) -> dict:
    return {
        "transport_mode": "live_gmail",
        "scenario_id": scenario_id,
        "ai_mode": REVIEWED_LIVE_LLM_BODY,
        "campaign_type": R4_LIVE_QUALITY_CAMPAIGN_TYPE,
        "execution_mode": R4_EXECUTION_MODE,
        "tenant_id": R4_TENANT_ID,
    }


def test_d1_attempt6_regression_0000_then_0002(r4_env):
    candidates, human_review = _synthetic_locked_artifacts()
    bindings = _bindings()
    cand_by_id = {c["scenario_id"]: c for c in candidates["send_candidates"]}
    review_by_id = {r["scenario_id"]: r for r in human_review["reviews"]}
    for sid in ("PTB-DCQ-0000", "PTB-DCQ-0002"):
        fields = send_registration_fields_from_candidate(cand_by_id[sid], review_by_id[sid])
        request = build_r4_live_eval_register_request(
            bindings,
            scenario_id=sid,
            evaluation_run_id=str(uuid4()),
            planned_gmail_send=True,
            send_fields=fields,
        )
        row = validate_exact_r4_registration_payload(request)
        assert row["registration_contract_valid"] is True
        assert row["live_gmail_scenario_eligible"] is True
        assert row["passed"] is True
        validate_live_gmail_registration(**_r4_gmail_kwargs(sid))


def test_d2_exhaustive_r4_eligibility_36_of_36(r4_env):
    matrix = evaluate_r4_live_gmail_scenario_eligibility_matrix()
    assert matrix["r4_live_gmail_scenario_eligibility"] == "36/36"
    assert matrix["r4_send_scenario_eligibility"] == "20/20"
    assert matrix["r4_no_send_scenario_eligibility"] == "16/16"
    assert matrix["r4_live_trigger_scenario_eligibility"] == "35/35"
    assert matrix["r4_local_quarantine_scenario_eligibility"] == "1/1"
    assert matrix["passed"] is True


def test_d3_negative_mutations(r4_env):
    base = _r4_gmail_kwargs("PTB-DCQ-0002")
    with pytest.raises(LiveEvalSafetyError):
        require_r4_reviewed_live_gmail_scenario_eligible(
            "PTB-DCQ-9999",
            transport_mode=base["transport_mode"],
            ai_mode=base["ai_mode"],
            campaign_type=base["campaign_type"],
            execution_mode=base["execution_mode"],
            tenant_id=base["tenant_id"],
        )
    with pytest.raises(LiveEvalSafetyError):
        validate_live_gmail_registration(**{**base, "ai_mode": "fixture_ai"})
    with pytest.raises(LiveEvalSafetyError):
        validate_live_gmail_registration(**{**base, "campaign_type": "semi-auto-core"})
    with pytest.raises(LiveEvalSafetyError):
        validate_live_gmail_registration(**{**base, "tenant_id": "T_OTHER"})
    with pytest.raises(LiveEvalSafetyError):
        validate_live_gmail_registration(**{**base, "execution_mode": "wrong_mode"})
    with pytest.raises(LiveEvalSafetyError, match="2F.2 or campaign"):
        require_scenario_allowed_for_live_gmail("PTB-DCQ-0002")
    with pytest.raises(LiveEvalSafetyError):
        validate_registration_request(
            tenant_id="T_OTHER",
            transport_mode="live_gmail",
            ai_mode=R4_EXECUTE_AI_MODE,
            scenario_id="PTB-DCQ-0002",
            campaign_type=R4_LIVE_QUALITY_CAMPAIGN_TYPE,
            execution_mode=R4_EXECUTION_MODE,
            expected_sender=SENDER,
            expected_recipient=RECIPIENT,
            manifest_hash=R4_LOCKED_MANIFEST_SEMANTIC_HASH,
        )


def test_d4_legacy_2f2_and_r3_unchanged(r4_env, monkeypatch):
    monkeypatch.setenv("FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED", "yes")
    require_scenario_allowed_for_live_gmail("S01_lead_laddbox_quality")
    from app.evaluation.profile_testbot.qualification.coworker_r3_registration_contract import (
        R3_FROZEN_EXECUTION_MODE,
        R3_FROZEN_LIVE_CANARY_CAMPAIGN_TYPE,
    )

    validate_live_gmail_registration(
        transport_mode="live_gmail",
        scenario_id="PTB-DCQ-0000",
        ai_mode=R3_FROZEN_EXECUTION_MODE,
        campaign_type=R3_FROZEN_LIVE_CANARY_CAMPAIGN_TYPE,
    )


def test_d5_ptb_sem_0024_eligibility_without_legacy_gate(r4_env):
    assert PTB_SEM_0024 in R4_SCENARIO_IDS
    assert PTB_SEM_0024 in R4_NO_SEND_SCENARIO_IDS
    assert PTB_SEM_0024 in R4_LOCAL_QUARANTINE_SCENARIO_IDS
    validate_live_gmail_registration(**_r4_gmail_kwargs(PTB_SEM_0024))
    with pytest.raises(LiveEvalSafetyError):
        require_scenario_allowed_for_live_gmail(PTB_SEM_0024)


def test_d6_pr174_exact_payload_invariants(r4_env):
    candidates, human_review = _synthetic_locked_artifacts()
    matrix = evaluate_exact_r4_registration_payload_matrix(
        bindings=_bindings(),
        candidates=candidates,
        human_review=human_review,
    )
    assert matrix["exact_send_registration_payload_ready"] == "20/20"
    assert matrix["exact_no_send_registration_payload_ready"] == "16/16"
    assert matrix["passed"] is True
    bindings = _bindings()
    request = build_r4_live_eval_register_request(
        bindings,
        scenario_id=R4_NO_SEND_SCENARIO_IDS[0],
        evaluation_run_id=str(uuid4()),
        planned_gmail_send=False,
    )
    assert request.registration_context.planned_gmail_send is False
