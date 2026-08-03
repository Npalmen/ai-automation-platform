"""Tests for R3 frozen live-canary registration contract."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.safety import (
    validate_live_gmail_registration,
    validate_registration_request,
)
from app.evaluation.profile_testbot.constants import LIVE_EVAL_TENANT_ID
from app.evaluation.profile_testbot.qualification.coworker_live_canary_manifest import (
    COWORKER_LIVE_CANARY_MANIFEST_HASH,
    COWORKER_LIVE_CANARY_SCENARIO_IDS,
    COWORKER_LIVE_CANARY_SEND_MAX,
)
from app.evaluation.profile_testbot.qualification.coworker_r3_frozen_bodies import (
    load_r3_approved_send_body_texts,
)
from app.evaluation.profile_testbot.qualification.coworker_r3_registration_contract import (
    R3_FROZEN_EXECUTION_MODE,
    R3_FROZEN_LIVE_CANARY_CAMPAIGN_TYPE,
    R3_NO_SEND_SCENARIO_IDS,
    R3_SEND_SCENARIO_IDS,
    R3RegistrationContractRequest,
    validate_r3_campaign_registration_contract,
    validate_r3_campaign_scenario_registry,
    validate_r3_registration_contract,
)
from app.evaluation.profile_testbot.qualification.coworker_r3_readiness import (
    R3_APPROVED_SEND_BODY_HASHES,
)


@pytest.fixture
def r3_env(monkeypatch):
    sha = "2" * 40
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("LIVE_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_GMAIL_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_EVAL_TENANT_IDS", LIVE_EVAL_TENANT_ID)
    monkeypatch.setenv("LIVE_EVAL_SENDER_EMAILS", "sender@eval.test")
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_EMAILS", "niklas@sol-f.se")
    monkeypatch.setenv("BUILD_GIT_SHA", sha)
    monkeypatch.setenv("BUILD_COMMIT_SHA", sha)
    monkeypatch.setenv("GIT_COMMIT", sha)
    from app.core.settings import get_settings
    from app.evaluation.live.config import get_live_eval_config

    get_settings.cache_clear()
    get_live_eval_config.cache_clear()
    yield sha
    get_settings.cache_clear()
    get_live_eval_config.cache_clear()


def _contract_request(**overrides):
    base = {
        "tenant_id": LIVE_EVAL_TENANT_ID,
        "scenario_id": "PTB-DCQ-0000",
        "transport_mode": "live_gmail",
        "ai_mode": R3_FROZEN_EXECUTION_MODE,
        "campaign_type": R3_FROZEN_LIVE_CANARY_CAMPAIGN_TYPE,
        "execution_mode": R3_FROZEN_EXECUTION_MODE,
        "expected_sender": "sender@eval.test",
        "expected_recipient": "niklas@sol-f.se",
        "manifest_hash": COWORKER_LIVE_CANARY_MANIFEST_HASH,
        "scenario_ids": list(COWORKER_LIVE_CANARY_SCENARIO_IDS),
        "planned_gmail_send": True,
        "frozen_body": load_r3_approved_send_body_texts()["PTB-DCQ-0000"],
    }
    base.update(overrides)
    return R3RegistrationContractRequest(**base)


def _manifest(**overrides):
    payload = {
        "campaign_type": R3_FROZEN_LIVE_CANARY_CAMPAIGN_TYPE,
        "execution_mode": R3_FROZEN_EXECUTION_MODE,
        "manifest_hash": COWORKER_LIVE_CANARY_MANIFEST_HASH,
        "tenant_id": LIVE_EVAL_TENANT_ID,
        "scenario_ids": list(COWORKER_LIVE_CANARY_SCENARIO_IDS),
        "send_budget": COWORKER_LIVE_CANARY_SEND_MAX,
        "hold_reject_no_reply_count": 7,
        "approved_send_body_hashes": dict(R3_APPROVED_SEND_BODY_HASHES),
        "approved_send_body_texts": load_r3_approved_send_body_texts(),
        "runner_sha": "2" * 40,
    }
    payload.update(overrides)
    return payload


class TestR3RegistrationContract:
    def test_global_live_gmail_live_llm_remains_blocked(self, r3_env):
        with pytest.raises(LiveEvalSafetyError, match="live_gmail \\+ live_llm is not allowed"):
            validate_registration_request(
                tenant_id=LIVE_EVAL_TENANT_ID,
                transport_mode="live_gmail",
                ai_mode="live_llm",
                scenario_id="PTB-DCQ-0000",
                expected_sender="sender@eval.test",
                expected_recipient="niklas@sol-f.se",
            )

    def test_r3_frozen_campaign_and_mode_allowed(self, r3_env):
        result = validate_r3_registration_contract(_contract_request())
        assert result.registration_contract_valid is True
        validate_registration_request(
            tenant_id=LIVE_EVAL_TENANT_ID,
            transport_mode="live_gmail",
            ai_mode=R3_FROZEN_EXECUTION_MODE,
            scenario_id="PTB-DCQ-0000",
            campaign_type=R3_FROZEN_LIVE_CANARY_CAMPAIGN_TYPE,
            execution_mode=R3_FROZEN_EXECUTION_MODE,
            expected_sender="sender@eval.test",
            expected_recipient="niklas@sol-f.se",
            manifest_hash=COWORKER_LIVE_CANARY_MANIFEST_HASH,
        )
        validate_live_gmail_registration(
            transport_mode="live_gmail",
            scenario_id="PTB-DCQ-0000",
            ai_mode=R3_FROZEN_EXECUTION_MODE,
            campaign_type=R3_FROZEN_LIVE_CANARY_CAMPAIGN_TYPE,
        )

    def test_ptb_dcq_0000_registers_within_contract(self, r3_env):
        assert validate_r3_registration_contract(_contract_request()).registration_contract_valid

    def test_ptb_dcq_0000_blocked_outside_r3_campaign(self, r3_env):
        result = validate_r3_registration_contract(
            _contract_request(campaign_type="semi-auto-core")
        )
        assert not result.registration_contract_valid

    def test_extra_scenario_blocked(self):
        extra = list(COWORKER_LIVE_CANARY_SCENARIO_IDS) + ["PTB-DCQ-9999"]
        assert validate_r3_campaign_scenario_registry(extra)

    def test_missing_scenario_blocked(self):
        missing = list(COWORKER_LIVE_CANARY_SCENARIO_IDS[:-1])
        assert validate_r3_campaign_scenario_registry(missing)

    def test_wrong_tenant_blocked(self, r3_env):
        result = validate_r3_registration_contract(_contract_request(tenant_id="T_OTHER"))
        assert not result.registration_contract_valid

    def test_wrong_recipient_blocked(self, r3_env):
        result = validate_r3_registration_contract(
            _contract_request(expected_recipient="other@sol-f.se")
        )
        assert not result.registration_contract_valid

    def test_wrong_manifest_hash_blocked(self, r3_env):
        result = validate_r3_registration_contract(_contract_request(manifest_hash="0" * 64))
        assert not result.registration_contract_valid

    def test_wrong_runtime_sha_blocked_in_campaign_validation(self, r3_env):
        manifest = _manifest(runner_sha="1" * 40)
        rows = [
            {
                "scenario_id": sid,
                "planned_gmail_send": sid in R3_SEND_SCENARIO_IDS,
                "frozen_customer_text": load_r3_approved_send_body_texts().get(sid, ""),
                "final_customer_text": load_r3_approved_send_body_texts().get(sid, ""),
            }
            for sid in COWORKER_LIVE_CANARY_SCENARIO_IDS
        ]
        result = validate_r3_campaign_registration_contract(
            manifest=manifest,
            runtime_sha="2" * 40,
            recipient_email="niklas@sol-f.se",
            render_rows=rows,
        )
        assert not result.registration_contract_valid

    def test_tampered_frozen_body_blocked(self, r3_env):
        result = validate_r3_registration_contract(
            _contract_request(frozen_body="tampered body text")
        )
        assert not result.registration_contract_valid

    def test_send_no_send_mismatch_blocked(self, r3_env):
        result = validate_r3_registration_contract(
            _contract_request(scenario_id="PTB-DCQ-0032", planned_gmail_send=True)
        )
        assert not result.registration_contract_valid

    def test_dry_run_uses_same_registration_validator(self, r3_env, tmp_path):
        from app.evaluation.profile_testbot.qualification.coworker_r3_execution import (
            run_r3_live_canary,
        )

        manifest_path = tmp_path / "manifest.json"
        approval_path = tmp_path / "approval.json"
        manifest_path.write_text(
            __import__("json").dumps(_manifest()),
            encoding="utf-8",
        )
        approval_path.write_text(
            __import__("json").dumps(
                {
                    "approval_type": "R3_LIVE_CANARY_MANUAL_SEND",
                    "tenant_id": LIVE_EVAL_TENANT_ID,
                    "send_scenario_ids": sorted(R3_SEND_SCENARIO_IDS),
                    "body_hashes_approved": True,
                    "human_render_rereview_required": False,
                    "gmail_sent_at_approval": False,
                    "gmail_drafts_at_approval": False,
                }
            ),
            encoding="utf-8",
        )
        with patch(
            "app.evaluation.profile_testbot.qualification.coworker_r3_execution.evaluate_coworker_r3_readiness"
        ) as mock_ready:
            mock_ready.return_value = MagicMock(
                postdeploy_preflight_pass=True,
                runtime_sha_consistent=True,
                runner_sha_auditable=True,
                human_render_rereview_required=False,
                stop_conditions=[],
                to_dict=lambda: {},
            )
            result = run_r3_live_canary(
                mode="dry_run",
                manifest_path=manifest_path,
                approval_path=approval_path,
                expected_runtime_sha="2" * 40,
                repo_root=tmp_path,
            )
        assert result.readiness.get("registration_contract_valid") is True

    def test_dry_run_detects_missing_campaign_registry(self, r3_env, tmp_path):
        from app.evaluation.profile_testbot.qualification.coworker_r3_execution import (
            run_r3_live_canary,
        )

        bad_manifest = _manifest(campaign_type="coworker-reply-live-canary")
        manifest_path = tmp_path / "manifest.json"
        approval_path = tmp_path / "approval.json"
        manifest_path.write_text(__import__("json").dumps(bad_manifest), encoding="utf-8")
        approval_path.write_text(
            __import__("json").dumps(
                {
                    "approval_type": "R3_LIVE_CANARY_MANUAL_SEND",
                    "tenant_id": LIVE_EVAL_TENANT_ID,
                    "send_scenario_ids": sorted(R3_SEND_SCENARIO_IDS),
                    "body_hashes_approved": True,
                    "human_render_rereview_required": False,
                    "gmail_sent_at_approval": False,
                    "gmail_drafts_at_approval": False,
                }
            ),
            encoding="utf-8",
        )
        with patch(
            "app.evaluation.profile_testbot.qualification.coworker_r3_execution.evaluate_coworker_r3_readiness"
        ) as mock_ready:
            mock_ready.return_value = MagicMock(
                postdeploy_preflight_pass=True,
                runtime_sha_consistent=True,
                runner_sha_auditable=True,
                human_render_rereview_required=False,
                stop_conditions=[],
                to_dict=lambda: {},
            )
            result = run_r3_live_canary(
                mode="dry_run",
                manifest_path=manifest_path,
                approval_path=approval_path,
                expected_runtime_sha="2" * 40,
                repo_root=tmp_path,
            )
        assert result.overall_status == "BLOCKED"
        assert result.readiness.get("registration_contract_valid") is False

    def test_execute_stops_before_gmail_on_registration_failure(self, r3_env, tmp_path):
        from app.evaluation.profile_testbot.qualification.coworker_r3_execution import (
            run_r3_live_canary,
        )

        manifest_path = tmp_path / "manifest.json"
        approval_path = tmp_path / "approval.json"
        manifest_path.write_text(__import__("json").dumps(_manifest()), encoding="utf-8")
        approval_path.write_text(
            __import__("json").dumps(
                {
                    "approval_type": "R3_LIVE_CANARY_MANUAL_SEND",
                    "tenant_id": LIVE_EVAL_TENANT_ID,
                    "send_scenario_ids": sorted(R3_SEND_SCENARIO_IDS),
                    "body_hashes_approved": True,
                    "human_render_rereview_required": False,
                    "gmail_sent_at_approval": False,
                    "gmail_drafts_at_approval": False,
                }
            ),
            encoding="utf-8",
        )
        backend = MagicMock()
        backend.gmail_sends = 0
        with patch(
            "app.evaluation.profile_testbot.qualification.coworker_r3_execution.evaluate_coworker_r3_readiness"
        ) as mock_ready:
            mock_ready.return_value = MagicMock(
                postdeploy_preflight_pass=False,
                runtime_sha_consistent=False,
                runner_sha_auditable=False,
                human_render_rereview_required=False,
                stop_conditions=["registration blocked"],
                to_dict=lambda: {},
            )
            result = run_r3_live_canary(
                mode="execute",
                manifest_path=manifest_path,
                approval_path=approval_path,
                expected_runtime_sha="2" * 40,
                repo_root=tmp_path,
                backend=backend,
            )
        assert result.overall_status == "BLOCKED"
        backend.send_test_message.assert_not_called()

    def test_no_send_cannot_create_send_intent(self, r3_env):
        for scenario_id in R3_NO_SEND_SCENARIO_IDS:
            result = validate_r3_registration_contract(
                _contract_request(
                    scenario_id=scenario_id,
                    planned_gmail_send=True,
                    frozen_body="",
                )
            )
            assert not result.registration_contract_valid

    def test_semi_auto_scenario_gate_unchanged(self, r3_env):
        from app.evaluation.profile_testbot.campaign.scenario_gate import (
            is_profile_testbot_semi_auto_scenario,
        )

        assert is_profile_testbot_semi_auto_scenario("PTB-SEM-0001")
        assert not is_profile_testbot_semi_auto_scenario("PTB-DCQ-0000")

    def test_execute_handles_registration_http_error_without_gmail(self, r3_env, tmp_path):
        from app.evaluation.profile_testbot.qualification.coworker_r3_execution import (
            _execute_live_scenario,
        )
        from app.evaluation.profile_testbot.qualification.coworker_r3_execution import (
            build_r3_frozen_execution_rows,
        )
        from app.evaluation.profile_testbot.qualification.coworker_r3_execution import (
            build_coworker_live_canary_manifest,
        )
        from app.evaluation.profile_testbot.profile_contract import load_customer_profile

        profile = load_customer_profile("niklas-demo-live-eval-v1")
        built = build_coworker_live_canary_manifest(profile_id="niklas-demo-live-eval-v1", seed=0)
        scenario = next(s for s in built.scenarios if s.scenario_id == "PTB-DCQ-0000")
        rows = build_r3_frozen_execution_rows(manifest=_manifest(), campaign_id="camp")
        row = next(r for r in rows if r["scenario_id"] == "PTB-DCQ-0000")
        backend = MagicMock()
        backend.gmail_sends = 0
        response = httpx.Response(400, json={"detail": "blocked"})
        backend.send_test_message.side_effect = httpx.HTTPStatusError(
            "blocked", request=MagicMock(), response=response
        )
        outcome = _execute_live_scenario(
            campaign_id="camp",
            scenario=scenario,
            backend=backend,
            render_row=row,
            recipient_email="niklas@sol-f.se",
            claimed_operations=set(),
            gmail_send_budget_remaining=8,
        )
        assert outcome.status == "failed"
        assert "live_run_registration" in (outcome.failure_reason or "")
