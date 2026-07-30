"""Tests for profile semi-auto live execution harness."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from app.core.canonical_commit import resolve_canonical_commit
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.profile_testbot.campaign.readiness import (
    build_profile_testbot_readiness,
    require_live_semi_auto_runner_execution,
)
from app.evaluation.profile_testbot.campaign.semi_auto_contract import ContractSemiAutoBackend
from app.evaluation.profile_testbot.campaign.semi_auto_runner import (
    SemiAutoRunnerConfig,
    new_campaign_id,
    run_profile_semi_auto_campaign,
)
from app.evaluation.profile_testbot.campaign.semi_auto_store import (
    count_campaign_rows,
    load_campaign_state,
)
from app.evaluation.profile_testbot.constants import (
    OPERATOR_STOP_SEMI_AUTO_RUNNER,
    SEMI_AUTO_SCENARIO_TARGET,
    SEMI_AUTO_SEND_AFTER_APPROVAL_MIN,
)
from app.evaluation.profile_testbot.generator.profile_generator import generate_semi_auto_campaign
from app.evaluation.profile_testbot.harness.semi_auto_harness import evaluate_harness_decision
from app.evaluation.profile_testbot.oracles.hard_safety import HardSafetyContext
from app.evaluation.profile_testbot.oracles.runner import run_oracles
from app.evaluation.profile_testbot.profile_contract import load_customer_profile

SENDER = "eval-sender-ptb@gmail.com"
RECIPIENT = "eval-recipient-ptb@gmail.com"


@pytest.fixture
def runner_env(monkeypatch, tmp_path):
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("LIVE_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_EVAL_TENANT_IDS", "TENANT_LIVE_EVAL")
    monkeypatch.setenv("LIVE_EVAL_SENDER_EMAILS", SENDER)
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_EMAILS", RECIPIENT)
    monkeypatch.setenv("LIVE_EVAL_MAX_GMAIL_REPLIES", "25")
    monkeypatch.setenv("LIVE_EVAL_SENDER_GMAIL_REFRESH_TOKEN", "test-sender-token")
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_GMAIL_REFRESH_TOKEN", "test-recipient-token")
    monkeypatch.setenv("LIVE_EVAL_SENDER_GMAIL_CLIENT_ID", "sender-client-id")
    monkeypatch.setenv("LIVE_EVAL_SENDER_GMAIL_CLIENT_SECRET", "sender-client-secret")
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_GMAIL_CLIENT_ID", "recipient-client-id")
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_GMAIL_CLIENT_SECRET", "recipient-client-secret")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("LIVE_EVAL_PURGE_ALLOWED", "yes")
    monkeypatch.setenv("PROFILE_TESTBOT_OFFLINE_MAILBOX_CONTRACT", "yes")
    monkeypatch.delenv("LIVE_GMAIL_EVAL_ALLOWED", raising=False)
    monkeypatch.delenv("PROFILE_TESTBOT_LIVE_SEMI_AUTO_RUNNER_APPROVED", raising=False)
    monkeypatch.delenv("PROFILE_TESTBOT_LIVE_SEMI_AUTO_RUNNER_APPROVED_SHA", raising=False)
    monkeypatch.delenv("LIVE_EVAL_APP_BASE_URL", raising=False)
    monkeypatch.delenv("ADMIN_API_KEY", raising=False)
    state_root = tmp_path / "campaign_state"
    monkeypatch.chdir(tmp_path)
    from app.core.settings import get_settings
    from app.evaluation.live.config import get_live_eval_config

    get_settings.cache_clear()
    get_live_eval_config.cache_clear()
    yield state_root
    get_settings.cache_clear()
    get_live_eval_config.cache_clear()


def _runner_config(state_root, **kwargs) -> SemiAutoRunnerConfig:
    return SemiAutoRunnerConfig(
        campaign_id=kwargs.pop("campaign_id", new_campaign_id()),
        runtime_sha=kwargs.pop("runtime_sha", resolve_canonical_commit() or "test-sha"),
        state_root=state_root,
        sender_email=SENDER,
        recipient_email=RECIPIENT,
        **kwargs,
    )


def test_runner_requires_readiness_pass(runner_env):
    with patch(
        "app.evaluation.profile_testbot.campaign.semi_auto_runner.build_profile_testbot_readiness",
        return_value={"ready_for_live_semi_auto": False, "blocking_failures": ["blocked"]},
    ):
        with pytest.raises(LiveEvalSafetyError, match="readiness failed"):
            run_profile_semi_auto_campaign(_runner_config(runner_env))


def test_runtime_sha_mismatch_blocks_resume(runner_env):
    config = _runner_config(runner_env, runtime_sha="sha-a")
    with patch(
        "app.evaluation.profile_testbot.campaign.semi_auto_runner.delete_campaign_state",
        return_value=False,
    ):
        run_profile_semi_auto_campaign(config)
    config.runtime_sha = "sha-b"
    with pytest.raises(LiveEvalSafetyError, match="runtime SHA mismatch"):
        run_profile_semi_auto_campaign(config, resume=True)


def test_manifest_locked_to_40_scenarios(runner_env):
    profile = load_customer_profile("pilot-service-company-v1")
    scenarios = generate_semi_auto_campaign(profile, seed=0)
    assert len(scenarios) == SEMI_AUTO_SCENARIO_TARGET
    send_after = [s for s in scenarios if s.expected_send_behavior == "send_after_approval"]
    assert len(send_after) == SEMI_AUTO_SEND_AFTER_APPROVAL_MIN


def test_contract_campaign_passes_all_scenarios(runner_env):
    result = run_profile_semi_auto_campaign(_runner_config(runner_env))
    assert result.overall_status == "PASS"
    assert result.scenario_count == 40
    assert result.scenarios_passed == 40
    assert result.send_budget_used == 20
    assert result.qualification_status == "PENDING"
    assert result.contract_mode is True
    assert result.evidence_path


def test_resume_skips_completed_scenarios(runner_env):
    config = _runner_config(runner_env)
    with patch(
        "app.evaluation.profile_testbot.campaign.semi_auto_runner.delete_campaign_state",
        return_value=False,
    ):
        first = run_profile_semi_auto_campaign(config)
    assert first.overall_status == "PASS"
    with patch(
        "app.evaluation.profile_testbot.campaign.semi_auto_runner._execute_scenario"
    ) as execute:
        second = run_profile_semi_auto_campaign(config, resume=True)
        execute.assert_not_called()
    assert second.overall_status == "PASS"


def test_duplicate_test_send_blocked(runner_env):
    backend = ContractSemiAutoBackend(sender_email=SENDER, recipient_email=RECIPIENT)
    profile = load_customer_profile("pilot-service-company-v1")
    scenario = generate_semi_auto_campaign(profile, seed=0)[0]
    backend.send_test_message(campaign_id="c1", scenario=scenario, idempotency_key="key-1")
    with pytest.raises(LiveEvalSafetyError, match="duplicate test send"):
        backend.send_test_message(campaign_id="c1", scenario=scenario, idempotency_key="key-1")


def test_hold_scenario_zero_sends(runner_env):
    profile = load_customer_profile("pilot-service-company-v1")
    hold = next(
        s for s in generate_semi_auto_campaign(profile, seed=0) if s.expected_send_behavior == "hold"
    )
    backend = ContractSemiAutoBackend(sender_email=SENDER, recipient_email=RECIPIENT)
    backend.send_test_message(
        campaign_id="hold-campaign",
        scenario=hold,
        idempotency_key="hold-key",
    )
    reply = backend.verify_reply(scenario=hold, approved=False)
    assert reply.adapter_invocations == 0
    assert reply.execution_intents == 0


def test_harness_rejects_without_oracle_pass():
    profile = load_customer_profile("pilot-service-company-v1")
    scenario = next(
        s
        for s in generate_semi_auto_campaign(profile, seed=0)
        if s.expected_send_behavior == "send_after_approval"
    )
    evaluation = run_oracles(
        scenario=scenario,
        profile=profile,
        safety_context=HardSafetyContext(
            tenant_id="TENANT_PRODUCTION_PILOT_01",
            recipient_email=RECIPIENT,
            sender_allowlist={scenario.input.sender_email},
            recipient_allowlist={RECIPIENT},
        ),
    )
    decision = evaluate_harness_decision(
        scenario=scenario,
        evaluation=evaluation,
        approval_state="pending",
        send_budget_remaining=5,
        operation_id_valid=True,
        recipient_allowlisted=True,
    )
    assert decision.approved is False


def test_duplicate_harness_approval_blocked(runner_env):
    backend = ContractSemiAutoBackend(sender_email=SENDER, recipient_email=RECIPIENT)
    profile = load_customer_profile("pilot-service-company-v1")
    scenario = next(
        s
        for s in generate_semi_auto_campaign(profile, seed=0)
        if s.expected_send_behavior == "send_after_approval"
    )
    backend.send_test_message(campaign_id="c1", scenario=scenario, idempotency_key="k1")
    backend.approve_via_lifecycle(scenario_id=scenario.scenario_id, operation_id="op-1", decision="approve")
    approval = backend.approve_via_lifecycle(
        scenario_id=scenario.scenario_id, operation_id="op-1", decision="approve"
    )
    assert approval.already_resolved is True


def test_live_execution_requires_runner_sha_approval():
    blocked = require_live_semi_auto_runner_execution(runtime_sha="abc123")
    assert blocked == OPERATOR_STOP_SEMI_AUTO_RUNNER


def test_runner_sha_approval_matches(monkeypatch):
    monkeypatch.setenv("PROFILE_TESTBOT_LIVE_SEMI_AUTO_RUNNER_APPROVED", "yes")
    monkeypatch.setenv("PROFILE_TESTBOT_LIVE_SEMI_AUTO_RUNNER_APPROVED_SHA", "abc123")
    assert require_live_semi_auto_runner_execution(runtime_sha="abc123") is None


def test_production_pilot_tenant_blocked_in_runner(runner_env):
    with pytest.raises(LiveEvalSafetyError):
        run_profile_semi_auto_campaign(
            _runner_config(runner_env, tenant_id="TENANT_PRODUCTION_PILOT_01")
        )


def test_cleanup_removes_campaign_row_on_pass(runner_env):
    config = _runner_config(runner_env)
    result = run_profile_semi_auto_campaign(config)
    assert result.overall_status == "PASS"
    assert load_campaign_state(config.campaign_id, root=config.state_root) is None
    assert count_campaign_rows(root=config.state_root) == 0


def test_evidence_report_redacts_mailboxes(runner_env):
    result = run_profile_semi_auto_campaign(_runner_config(runner_env))
    text = open(result.evidence_path, encoding="utf-8").read()
    assert SENDER not in text
    assert RECIPIENT not in text


def test_readiness_includes_runner_ready_flags(runner_env):
    report = build_profile_testbot_readiness()
    assert report["runner_ready_for_contract_execution"] is True
    assert report["runner_ready_for_live_execution"] is False
    assert any(
        "PROFILE_TESTBOT_OFFLINE_MAILBOX_CONTRACT" in item
        for item in report.get("live_execution_blockers") or []
    )


def test_readiness_live_execution_requires_runner_sha(runner_env, monkeypatch):
    monkeypatch.delenv("PROFILE_TESTBOT_OFFLINE_MAILBOX_CONTRACT", raising=False)
    monkeypatch.setenv("LIVE_GMAIL_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_EVAL_APP_BASE_URL", "http://127.0.0.1:8010")
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin")
    monkeypatch.setenv("PROFILE_TESTBOT_LIVE_SEMI_AUTO_RUNNER_APPROVED", "yes")
    monkeypatch.setenv("PROFILE_TESTBOT_LIVE_SEMI_AUTO_RUNNER_APPROVED_SHA", "test-sha")
    from app.core.settings import get_settings
    from app.evaluation.live.config import get_live_eval_config

    get_settings.cache_clear()
    get_live_eval_config.cache_clear()
    with patch(
        "app.evaluation.profile_testbot.campaign.readiness.verify_profile_testbot_mailboxes",
        return_value={
            "sender_mailbox_hash": "sender-hash",
            "recipient_mailbox_hash": "recipient-hash",
            "sender_provider_verified": True,
            "recipient_deliverability_verified": True,
            "blocking_failures": [],
        },
    ), patch(
        "app.evaluation.profile_testbot.campaign.readiness._runtime_sha",
        return_value="test-sha",
    ):
        report = build_profile_testbot_readiness()
    assert report["runner_ready_for_live_execution"] is True
    get_settings.cache_clear()
    get_live_eval_config.cache_clear()


def test_cli_execute_contract_without_live_gmail(runner_env, monkeypatch, capsys):
    from scripts.run_profile_testbot_campaign import main

    exit_code = main(
        [
            "semi-auto-live",
            "--confirm-operator",
            "--execute-contract",
            "--campaign-id",
            "contract-campaign-001",
            "--runtime-sha",
            "test-runtime-sha",
            "--state-root",
            str(runner_env),
        ]
    )
    captured = capsys.readouterr().out
    assert exit_code == 0
    assert "PASS" in captured
    payload = json.loads(captured.split("PASS\n", 1)[1].strip())
    assert payload["qualification_status"] == "PENDING"


def test_cli_confirm_external_fails_without_live_readiness(runner_env, capsys):
    from scripts.run_profile_testbot_campaign import main

    exit_code = main(
        [
            "semi-auto-live",
            "--confirm-operator",
            "--confirm-external",
            "--runtime-sha",
            "abc",
            "--state-root",
            str(runner_env),
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "FAIL:" in captured.out


@pytest.mark.integration_db
def test_contract_campaign_with_sqlite_tenant_row(runner_env, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.repositories.postgres.database import Base
    from app.repositories.postgres.tenant_config_models import TenantConfigRecord

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine, tables=[TenantConfigRecord.__table__])
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(TenantConfigRecord(tenant_id="TENANT_LIVE_EVAL", auto_actions={}))
    db.commit()
    try:
        result = run_profile_semi_auto_campaign(_runner_config(runner_env))
        assert result.overall_status == "PASS"
        row = db.get(TenantConfigRecord, "TENANT_LIVE_EVAL")
        assert row is not None
    finally:
        db.close()
