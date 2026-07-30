"""Live LLM reservation contract tests for profile semi-auto PTB-SEM campaigns."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.evaluation.live.constants import S01_LLM_MAX_CALLS, S01_LLM_PROMPT_ORDER
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.llm_operations import reserve_live_llm_operation
from app.evaluation.live.schemas import TrustedLiveEvalSnapshot
from app.evaluation.profile_testbot.campaign.llm_reservation import (
    validate_profile_testbot_live_llm_reservation,
)
from app.evaluation.profile_testbot.campaign.semi_auto_manifest import (
    LOCKED_PTB_SEM_MANIFEST_HASH,
    LOCKED_PTB_SEM_SCENARIO_IDS,
    is_locked_ptb_sem_scenario_id,
)
from app.evaluation.profile_testbot.constants import LIVE_EVAL_TENANT_ID
from app.evaluation.profile_testbot.oracles.reply_contract import evaluate_reply_contract
from app.evaluation.profile_testbot.oracles.runner import run_oracles
from app.evaluation.profile_testbot.oracles.hard_safety import HardSafetyContext
from app.evaluation.profile_testbot.generator.profile_generator import generate_semi_auto_campaign
from app.evaluation.profile_testbot.profile_contract import load_customer_profile
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.database import Base
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.live_eval_models import (
    LiveEvalExternalEventRow,
    LiveEvalLlmOperationRow,
    LiveEvalRunRow,
)
from app.repositories.postgres.tenant_config_models import TenantConfigRecord


_APPROVED_SHA = "deadbeef1234567890abcdef1234567890abcdef"


@pytest.fixture
def ptb_llm_env(monkeypatch):
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("LIVE_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_GMAIL_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_LLM_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_EVAL_TENANT_IDS", LIVE_EVAL_TENANT_ID)
    monkeypatch.setenv("PROFILE_TESTBOT_LIVE_SEMI_AUTO_RUNNER_APPROVED", "yes")
    monkeypatch.setenv("PROFILE_TESTBOT_LIVE_SEMI_AUTO_RUNNER_APPROVED_SHA", _APPROVED_SHA)
    monkeypatch.setenv("BUILD_COMMIT_SHA", _APPROVED_SHA)
    from app.core.settings import get_settings
    from app.evaluation.live.config import get_live_eval_config

    get_settings.cache_clear()
    get_live_eval_config.cache_clear()
    yield
    get_settings.cache_clear()
    get_live_eval_config.cache_clear()


@pytest.fixture
def db(ptb_llm_env):
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
        ],
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _snapshot(
    *,
    scenario_id: str = "PTB-SEM-0000",
    tenant_id: str = LIVE_EVAL_TENANT_ID,
    llm_max_calls: int = 20,
) -> TrustedLiveEvalSnapshot:
    return TrustedLiveEvalSnapshot(
        evaluation_run_id=str(uuid4()),
        tenant_id=tenant_id,
        scenario_id=scenario_id,
        attempt_id=1,
        transport_mode="live_gmail",
        ai_mode="live_llm",
        fixture_bundle_id=None,
        expected_sender="sender@eval.test",
        expected_recipient="recipient@eval.test",
        llm_provider="openai",
        llm_requested_model="gpt-4o-mini",
        llm_max_calls=llm_max_calls,
        config_hash="cfg",
        trusted=True,
    )


def _seed_run(db, snapshot: TrustedLiveEvalSnapshot) -> None:
    db.add(
        LiveEvalRunRow(
            evaluation_run_id=snapshot.evaluation_run_id,
            tenant_id=snapshot.tenant_id,
            scenario_id=snapshot.scenario_id,
            attempt_id=snapshot.attempt_id,
            transport_mode=snapshot.transport_mode,
            ai_mode=snapshot.ai_mode,
            fixture_bundle_id=None,
            expected_sender=snapshot.expected_sender,
            expected_recipient=snapshot.expected_recipient,
            llm_provider=snapshot.llm_provider,
            llm_requested_model=snapshot.llm_requested_model,
            llm_max_calls=snapshot.llm_max_calls,
            status="registered",
            created_by="test",
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
            config_hash="cfg",
        )
    )
    db.commit()


def test_locked_manifest_has_40_scenarios():
    assert len(LOCKED_PTB_SEM_SCENARIO_IDS) == 40
    assert is_locked_ptb_sem_scenario_id("PTB-SEM-0000")
    assert is_locked_ptb_sem_scenario_id("PTB-SEM-0039")
    assert LOCKED_PTB_SEM_MANIFEST_HASH == (
        "1a8cf8c8ad8ca97038b657d4563fedfe3f69efa7e43bfc8fb83192119ea847ea"
    )


@pytest.mark.parametrize("scenario_id", sorted(LOCKED_PTB_SEM_SCENARIO_IDS))
def test_all_locked_scenarios_can_reserve_classification(db, ptb_llm_env, scenario_id):
    snap = _snapshot(scenario_id=scenario_id)
    _seed_run(db, snap)
    validate_profile_testbot_live_llm_reservation(snap)
    op_key = reserve_live_llm_operation(
        db,
        snapshot=snap,
        prompt_name=S01_LLM_PROMPT_ORDER[0],
        requested_model="gpt-4o-mini",
    )
    assert op_key.startswith(f"{snap.evaluation_run_id}:app_live_llm:{S01_LLM_PROMPT_ORDER[0]}:")


def test_unknown_ptb_pattern_denied(ptb_llm_env):
    snap = _snapshot(scenario_id="PTB-SEM-0040")
    with pytest.raises(LiveEvalSafetyError, match="not defined"):
        validate_profile_testbot_live_llm_reservation(snap)


def test_non_manifest_scenario_denied(ptb_llm_env):
    snap = _snapshot(scenario_id="S01_lead_laddbox_quality")
    with pytest.raises(LiveEvalSafetyError, match="not defined"):
        validate_profile_testbot_live_llm_reservation(snap)


@pytest.mark.parametrize(
    "tenant_id",
    [
        "T_NIKLAS_DEMO_001",
        "TENANT_PRODUCTION_PILOT_01",
        "TENANT_OTHER",
    ],
)
def test_blocked_or_wrong_tenant_denied(db, ptb_llm_env, tenant_id):
    snap = _snapshot(tenant_id=tenant_id)
    with pytest.raises(LiveEvalSafetyError, match="TENANT_LIVE_EVAL|blocked|not in"):
        validate_profile_testbot_live_llm_reservation(snap)


def test_missing_operator_authorization_denied(db, monkeypatch):
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("LIVE_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("PROFILE_TESTBOT_LIVE_SEMI_AUTO_RUNNER_APPROVED", "no")
    monkeypatch.delenv("PROFILE_TESTBOT_LIVE_SEMI_AUTO_RUNNER_APPROVED_SHA", raising=False)
    from app.core.settings import get_settings
    from app.evaluation.live.config import get_live_eval_config

    get_settings.cache_clear()
    get_live_eval_config.cache_clear()
    snap = _snapshot()
    with pytest.raises(LiveEvalSafetyError, match="OPERATOR ACTION REQUIRED"):
        validate_profile_testbot_live_llm_reservation(snap)


def test_wrong_sha_denied(db, ptb_llm_env, monkeypatch):
    monkeypatch.setenv("PROFILE_TESTBOT_LIVE_SEMI_AUTO_RUNNER_APPROVED_SHA", _APPROVED_SHA)
    monkeypatch.setenv("BUILD_COMMIT_SHA", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    snap = _snapshot()
    with pytest.raises(LiveEvalSafetyError, match="OPERATOR ACTION REQUIRED"):
        validate_profile_testbot_live_llm_reservation(snap)


def test_budget_exhausted_blocks_further_reservations(db, ptb_llm_env):
    snap = _snapshot(llm_max_calls=S01_LLM_MAX_CALLS)
    _seed_run(db, snap)
    for prompt_name in S01_LLM_PROMPT_ORDER:
        reserve_live_llm_operation(
            db,
            snapshot=snap,
            prompt_name=prompt_name,
            requested_model="gpt-4o-mini",
        )
        from app.evaluation.live.llm_operations import record_live_llm_operation_result
        from app.evaluation.live.constants import EVENT_OUTCOME_SUCCEEDED

        record_live_llm_operation_result(
            db,
            operation_key=f"{snap.evaluation_run_id}:app_live_llm:{prompt_name}:{S01_LLM_PROMPT_ORDER.index(prompt_name)+1}",
            snapshot=snap,
            prompt_name=prompt_name,
            outcome=EVENT_OUTCOME_SUCCEEDED,
            requested_model="gpt-4o-mini",
        )
    with pytest.raises(LiveEvalSafetyError, match="budget exhausted"):
        reserve_live_llm_operation(
            db,
            snapshot=snap,
            prompt_name=S01_LLM_PROMPT_ORDER[0],
            requested_model="gpt-4o-mini",
        )


def test_duplicate_reservation_blocked(db, ptb_llm_env):
    snap = _snapshot()
    _seed_run(db, snap)
    reserve_live_llm_operation(
        db,
        snapshot=snap,
        prompt_name=S01_LLM_PROMPT_ORDER[0],
        requested_model="gpt-4o-mini",
    )
    with pytest.raises(LiveEvalSafetyError, match="in progress|retry blocked"):
        reserve_live_llm_operation(
            db,
            snapshot=snap,
            prompt_name=S01_LLM_PROMPT_ORDER[0],
            requested_model="gpt-4o-mini",
        )


def test_empty_draft_fails_send_after_approval_oracle():
    profile = load_customer_profile("pilot-service-company-v1")
    scenario = next(
        s
        for s in generate_semi_auto_campaign(profile, seed=0)
        if s.scenario_id == "PTB-SEM-0000"
    )
    evaluation = run_oracles(
        scenario=scenario,
        profile=profile,
        safety_context=HardSafetyContext(
            tenant_id=LIVE_EVAL_TENANT_ID,
            recipient_email="recipient@eval.test",
            sender_allowlist={scenario.input.sender_email},
            recipient_allowlist={"recipient@eval.test"},
            draft_text="",
            reply_text="",
        ),
        reply_text="",
    )
    assert not evaluation.passed
    assert "required_fact_acknowledgement" in evaluation.blockers


def test_hold_scenario_oracle_expects_no_reply():
    profile = load_customer_profile("pilot-service-company-v1")
    scenario = next(
        s
        for s in generate_semi_auto_campaign(profile, seed=0)
        if s.expected_send_behavior == "hold"
    )
    results = evaluate_reply_contract(
        scenario=scenario,
        profile=profile,
        reply_text="Vi har tagit emot ditt meddelande och återkommer.",
    )
    assert any(r.name == "no_reply_expected" and r.status == "fail" for r in results)
