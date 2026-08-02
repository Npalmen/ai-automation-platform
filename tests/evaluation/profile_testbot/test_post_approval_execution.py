"""Post-approval Gmail execution chain — authorization, harness, and state-machine tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.context import live_eval_context
from app.evaluation.live.schemas import TrustedLiveEvalSnapshot
from app.evaluation.live.write_policy import enforce_live_eval_write_policy
from app.evaluation.profile_testbot.campaign.post_approval_execution import (
    JobActionExecutionSnapshot,
    ReplyExecutionEvidence,
    assert_reply_evidence_invariants,
    build_reply_execution_evidence,
    classify_reply_execution_status,
    poll_post_approval_reply_execution,
    provider_accepted,
)
from app.evaluation.profile_testbot.campaign.semi_auto_contract import ContractSemiAutoBackend
from app.evaluation.profile_testbot.campaign.semi_auto_runner import (
    CampaignState,
    SemiAutoRunnerConfig,
    _execute_scenario,
    new_campaign_id,
)
from app.evaluation.profile_testbot.campaign.semi_auto_state import (
    SemiAutoCampaignState,
    ScenarioExecutionState,
)
from app.evaluation.profile_testbot.constants import LIVE_EVAL_TENANT_ID
from app.evaluation.profile_testbot.generator.profile_generator import generate_semi_auto_campaign
from app.evaluation.profile_testbot.profile_contract import load_customer_profile
from app.repositories.postgres.tenant_config_models import TenantConfigRecord
from app.workflows.action_executor import execute_action
from app.workflows.live_eval_approval_reply_authorization import (
    allows_live_eval_approval_gated_customer_reply,
    is_approval_gated_customer_reply,
)
from app.workflows.safe_ack_eligibility import evaluate_safe_ack_eligibility
from app.workflows.processors.action_dispatch_processor import (
    _apply_dispatch_authorization,
    _build_inquiry_default_actions,
)

SENDER = "eval-sender-ptb@gmail.com"
RECIPIENT = "eval-recipient-ptb@gmail.com"
LIVE_EVAL_TENANT = LIVE_EVAL_TENANT_ID


def _safe_ack_action(*, execution_allowed: bool = False) -> dict:
    action = {
        "type": "send_customer_auto_reply",
        "tenant_id": LIVE_EVAL_TENANT,
        "to": RECIPIENT,
        "subject": "Re: test",
        "body": "Hej, tack för din förfrågan. Vi återkommer.",
        "_needs_approval": True,
        "_approval_reason": "safe_acknowledgement_requires_approval",
        "_safe_acknowledgement_path": True,
    }
    if execution_allowed:
        action["_authorization"] = "execution_allowed"
    return action


def _sqlite_tenant_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TenantConfigRecord.__table__.create(engine, checkfirst=True)
    session = sessionmaker(bind=engine)()
    now = datetime.now(timezone.utc)
    session.add(
        TenantConfigRecord(
            tenant_id=LIVE_EVAL_TENANT,
            name="Live Eval",
            slug="tenant-live-eval",
            status="active",
            lifecycle_status="active",
            is_test_tenant=True,
            allowed_integrations=["google_mail"],
            enabled_job_types=["lead"],
            auto_actions={},
            settings={
                "integrations": {
                    "enabled_external_writes": [],
                    "selections": {"google_mail": {}},
                },
            },
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    return session


def _send_after_scenario():
    profile = load_customer_profile("pilot-service-company-v1")
    return next(
        s
        for s in generate_semi_auto_campaign(profile, seed=0)
        if s.expected_send_behavior == "send_after_approval"
    )


def _hold_scenario():
    profile = load_customer_profile("pilot-service-company-v1")
    return next(
        s for s in generate_semi_auto_campaign(profile, seed=0) if s.expected_send_behavior == "hold"
    )


@pytest.fixture
def tenant_db():
    db = _sqlite_tenant_db()
    yield db
    db.close()


class TestCustomerInquirySafeAckLiveEval:
    def test_inquiry_default_actions_use_safe_ack_path_when_policy_allows(self):
        input_data = {
            "subject": "Status på ärende",
            "message_text": "Hej, hur går det med mitt ärende?",
            "sender": {"name": "Kund", "email": RECIPIENT},
            "live_eval": {"scenario_id": "PTB-Q96-0012"},
        }
        job = Job(
            tenant_id=LIVE_EVAL_TENANT,
            job_type=JobType.CUSTOMER_INQUIRY,
            input_data=input_data,
        )
        job.processor_history = [
            {
                "processor": "policy_processor",
                "result": {
                    "payload": {
                        "safe_acknowledgement_path": True,
                        "detected_job_type": "customer_inquiry",
                        "safe_ack_eligibility": evaluate_safe_ack_eligibility(
                            detected_job_type="customer_inquiry",
                            risk_detected=False,
                            risk_categories=[],
                            extraction_issues=[],
                            input_data=input_data,
                            recommendation=None,
                            recommendation_raw="auto_route",
                            low_confidence=False,
                            used_fallback=False,
                        ).to_dict(),
                    }
                },
            },
            {
                "processor": "classification_processor",
                "result": {"payload": {"detected_job_type": "customer_inquiry"}},
            },
            {
                "processor": "entity_extraction_processor",
                "result": {"payload": {"entities": {}, "validation": {"issues": []}}},
            },
        ]
        job.result = job.processor_history[-1]["result"]

        actions = _build_inquiry_default_actions(job, {"followups_enabled": True})
        reply = next(a for a in actions if a["type"] == "send_customer_auto_reply")
        assert reply.get("_safe_acknowledgement_path") is True
        assert reply.get("_needs_approval") is True
        assert reply.get("_approval_reason") == "safe_acknowledgement_requires_approval"
        assert reply.get("body")

    def test_inquiry_dispatch_materialize_allowed_without_external_writes(self, tenant_db, monkeypatch):
        monkeypatch.setenv("ENV", "test")
        monkeypatch.setenv("LIVE_EVAL_ALLOWED", "yes")
        monkeypatch.setenv("LIVE_GMAIL_EVAL_ALLOWED", "yes")
        from app.evaluation.live.config import get_live_eval_config

        get_live_eval_config.cache_clear()

        input_data = {
            "subject": "Status på ärende",
            "message_text": "Hej, hur går det med mitt ärende?",
            "sender": {"name": "Kund", "email": RECIPIENT},
            "live_eval": {"scenario_id": "PTB-Q96-0012"},
        }
        job = Job(
            tenant_id=LIVE_EVAL_TENANT,
            job_type=JobType.CUSTOMER_INQUIRY,
            input_data=input_data,
        )
        job.processor_history = [
            {
                "processor": "policy_processor",
                "result": {
                    "payload": {
                        "decision": "manual_review",
                        "detected_job_type": "customer_inquiry",
                        "safe_acknowledgement_path": True,
                        "safe_ack_eligibility": evaluate_safe_ack_eligibility(
                            detected_job_type="customer_inquiry",
                            risk_detected=False,
                            risk_categories=[],
                            extraction_issues=[],
                            input_data=input_data,
                            recommendation=None,
                            recommendation_raw="auto_route",
                            low_confidence=False,
                            used_fallback=False,
                        ).to_dict(),
                    }
                },
            },
            {
                "processor": "classification_processor",
                "result": {"payload": {"detected_job_type": "customer_inquiry"}},
            },
            {
                "processor": "entity_extraction_processor",
                "result": {"payload": {"entities": {}, "validation": {"issues": []}}},
            },
        ]
        job.result = job.processor_history[-1]["result"]

        built = _build_inquiry_default_actions(job, {"followups_enabled": True})
        authorized = _apply_dispatch_authorization(
            job,
            built,
            {"followups_enabled": True, "auto_actions": {"customer_inquiry": True}},
            db=tenant_db,
        )
        reply = next(a for a in authorized if a["type"] == "send_customer_auto_reply")
        assert not reply.get("_skip")
        assert is_approval_gated_customer_reply(reply)
        assert allows_live_eval_approval_gated_customer_reply(
            reply, LIVE_EVAL_TENANT, tenant_db, phase="dispatch_materialize"
        )


class TestLiveEvalApprovalReplyAuthorization:
    def test_dispatch_materialize_allowed_without_execution_allowed(self, tenant_db):
        action = _safe_ack_action(execution_allowed=False)
        assert allows_live_eval_approval_gated_customer_reply(
            action, LIVE_EVAL_TENANT, tenant_db, phase="dispatch_materialize"
        )

    def test_execute_denied_without_execution_allowed(self, tenant_db):
        action = _safe_ack_action(execution_allowed=False)
        assert not allows_live_eval_approval_gated_customer_reply(
            action, LIVE_EVAL_TENANT, tenant_db, phase="execute"
        )

    def test_execute_allowed_after_approval_marker(self, tenant_db):
        action = _safe_ack_action(execution_allowed=True)
        assert allows_live_eval_approval_gated_customer_reply(
            action, LIVE_EVAL_TENANT, tenant_db, phase="execute"
        )

    def test_wrong_tenant_denied(self, tenant_db):
        action = _safe_ack_action(execution_allowed=True)
        assert not allows_live_eval_approval_gated_customer_reply(
            action, "TENANT_PRODUCTION_PILOT_01", tenant_db, phase="execute"
        )

    def test_without_needs_approval_denied(self, tenant_db):
        action = _safe_ack_action(execution_allowed=True)
        action["_needs_approval"] = False
        assert not allows_live_eval_approval_gated_customer_reply(
            action, LIVE_EVAL_TENANT, tenant_db, phase="dispatch_materialize"
        )

    def test_non_safe_ack_denied(self, tenant_db):
        action = _safe_ack_action(execution_allowed=True)
        action.pop("_approval_reason")
        action.pop("_safe_acknowledgement_path")
        assert not allows_live_eval_approval_gated_customer_reply(
            action, LIVE_EVAL_TENANT, tenant_db, phase="execute"
        )

    def test_dispatch_and_execute_share_contract_for_safe_ack(self, tenant_db):
        action = _safe_ack_action(execution_allowed=True)
        materialize = allows_live_eval_approval_gated_customer_reply(
            action, LIVE_EVAL_TENANT, tenant_db, phase="dispatch_materialize"
        )
        execute = allows_live_eval_approval_gated_customer_reply(
            action, LIVE_EVAL_TENANT, tenant_db, phase="execute"
        )
        assert materialize and execute

    def test_dispatch_materialize_allowed_when_live_gmail_eval_enabled_without_tenant_integration(
        self, monkeypatch,
    ):
        monkeypatch.setenv("ENV", "test")
        monkeypatch.setenv("LIVE_EVAL_ALLOWED", "yes")
        monkeypatch.setenv("LIVE_GMAIL_EVAL_ALLOWED", "yes")
        from app.evaluation.live.config import get_live_eval_config

        get_live_eval_config.cache_clear()
        action = _safe_ack_action(execution_allowed=False)
        assert allows_live_eval_approval_gated_customer_reply(
            action, LIVE_EVAL_TENANT, None, phase="dispatch_materialize"
        )


class TestDispatchAuthorizationSymmetry:
    def test_materialize_not_skipped_when_execute_contract_would_allow(self, tenant_db):
        job = Job(
            tenant_id=LIVE_EVAL_TENANT,
            job_type=JobType.LEAD,
            input_data={"subject": "test"},
        )
        job.processor_history = [
            {
                "processor": "policy_processor",
                "result": {"payload": {"decision": "manual_review", "detected_job_type": "lead"}},
            }
        ]
        job.result = job.processor_history[-1]["result"]
        authorized = _apply_dispatch_authorization(
            job,
            [_safe_ack_action(execution_allowed=False)],
            {"followups_enabled": True, "auto_actions": {"lead": True}},
            db=tenant_db,
        )
        reply = authorized[0]
        assert not reply.get("_skip")
        assert is_approval_gated_customer_reply(reply)

    def test_without_needs_approval_still_integration_blocked(self, tenant_db):
        job = Job(
            tenant_id=LIVE_EVAL_TENANT,
            job_type=JobType.LEAD,
            input_data={"subject": "test"},
        )
        job.processor_history = [
            {
                "processor": "policy_processor",
                "result": {"payload": {"decision": "auto_execute", "detected_job_type": "lead"}},
            }
        ]
        job.result = job.processor_history[-1]["result"]
        authorized = _apply_dispatch_authorization(
            job,
            [
                {
                    "type": "send_customer_auto_reply",
                    "tenant_id": LIVE_EVAL_TENANT,
                    "to": RECIPIENT,
                    "subject": "Re: test",
                    "body": "Hej, tack för din förfrågan. Vi återkommer.",
                }
            ],
            {"followups_enabled": True, "auto_actions": {"lead": True}},
            db=tenant_db,
        )
        assert authorized[0].get("_skip") is True
        assert authorized[0].get("_skip_reason") == "integration_not_allowed"


class TestExecuteActionLiveEvalContract:
    def test_safe_ack_executes_after_approval_without_external_writes(self, tenant_db):
        action = _safe_ack_action(execution_allowed=True)
        mock_adapter = MagicMock(
            execute_action=MagicMock(
                return_value={
                    "status": "success",
                    "integration": "google_mail",
                    "provider": "google_mail",
                    "external_id": "reply-msg-1",
                    "payload": {"google_message_id": "reply-msg-1"},
                }
            )
        )
        with (
            patch(
                "app.workflows.action_executor.get_integration_adapter",
                return_value=mock_adapter,
            ),
            patch(
                "app.workflows.action_executor.get_integration_connection_config",
                return_value={"configured": True},
            ),
            patch(
                "app.workflows.action_executor.is_integration_configured",
                return_value=True,
            ),
        ):
            result = execute_action(action, db=tenant_db)

        mock_adapter.execute_action.assert_called_once()
        assert result.get("type") == "send_customer_auto_reply"
        assert result.get("integration_result", {}).get("skipped") is not True

    def test_action_before_approval_denied_at_execute(self, tenant_db):
        action = _safe_ack_action(execution_allowed=False)
        result = execute_action(action, db=tenant_db)
        assert result.get("integration_result", {}).get("skipped") is True
        assert result.get("integration_result", {}).get("reason") == "integration_not_allowed"


class TestWritePolicyEvalReply:
    def test_write_policy_allows_approval_gated_reply_without_external_writes(self, tenant_db):
        action = _safe_ack_action(execution_allowed=True)
        action["to"] = SENDER
        snapshot = TrustedLiveEvalSnapshot(
            evaluation_run_id="run-1",
            tenant_id=LIVE_EVAL_TENANT,
            scenario_id="PTB-SEM-0000",
            attempt_id=1,
            transport_mode="live_gmail",
            ai_mode="live_llm",
            expected_sender=SENDER,
            expected_recipient=RECIPIENT,
            config_hash="cfg",
            trusted=True,
        )
        with live_eval_context(snapshot, db=tenant_db):
            with (
                patch(
                    "app.evaluation.live.write_policy.validate_trusted_live_eval_context",
                    return_value=snapshot,
                ),
                patch("app.evaluation.live.write_policy.emit_live_eval_audit"),
            ):
                enforce_live_eval_write_policy(
                    action,
                    db=tenant_db,
                    job=Job(
                        job_id=str(uuid.uuid4()),
                        tenant_id=LIVE_EVAL_TENANT,
                        job_type=JobType.LEAD,
                        input_data={"evaluation_run_id": "run-1"},
                    ),
                )


class TestReplyExecutionEvidence:
    def test_inbound_reply_id_invariant_raises(self):
        evidence = ReplyExecutionEvidence(
            inbound_provider_message_id="same-id",
            reply_provider_message_id="same-id",
            reply_execution_status="succeeded",
        )
        with pytest.raises(LiveEvalSafetyError, match="inbound_provider_message_id equals"):
            assert_reply_evidence_invariants(evidence)

    def test_succeeded_requires_reply_provider_id(self):
        evidence = ReplyExecutionEvidence(
            reply_execution_status="succeeded",
            reply_provider_message_id=None,
        )
        with pytest.raises(LiveEvalSafetyError, match="succeeded execution without reply_provider_message_id"):
            assert_reply_evidence_invariants(evidence)

    def test_classify_skipped_from_job_actions(self):
        observation: dict = {"job": {"decision_records": [], "result": {}}}
        status = classify_reply_execution_status(
            observation,
            job_actions=[
                JobActionExecutionSnapshot(
                    action_type="send_customer_auto_reply",
                    status="skipped",
                    error_message="integration_not_allowed",
                )
            ],
        )
        assert status == "skipped"

    def test_classify_succeeded_from_execution_outcome(self):
        observation = {
            "job": {
                "decision_records": [
                    {
                        "record_type": "execution_outcome",
                        "execution_status": "succeeded",
                        "metadata": {
                            "provider_message_id": "reply-1",
                            "adapter_provider": "google_mail",
                            "adapter_status": "executed",
                        },
                    }
                ],
                "result": {},
            },
            "events": [],
        }
        assert classify_reply_execution_status(observation) == "succeeded"
        evidence = build_reply_execution_evidence(
            observation=observation,
            action_operation_id="op-1",
            inbound_provider_message_id="inbound-1",
            inbound_rfc_message_id="<inbound@test>",
        )
        assert evidence.reply_provider_message_id == "reply-1"
        assert provider_accepted(evidence)


class TestPostApprovalStateMachine:
    def test_happy_path_created_to_verified(self):
        backend = ContractSemiAutoBackend(sender_email=SENDER, recipient_email=RECIPIENT)
        scenario = _send_after_scenario()
        campaign_id = new_campaign_id()

        send = backend.send_test_message(
            campaign_id=campaign_id,
            scenario=scenario,
            idempotency_key="k1",
        )
        assert backend.gmail_sends == 0

        approval = backend.approve_via_lifecycle(
            scenario_id=scenario.scenario_id,
            operation_id="op-1",
            decision="approve",
        )
        assert approval.decision == "approved"
        assert backend.gmail_sends == 0

        reply = backend.verify_reply(
            scenario=scenario,
            approved=True,
            inbound_provider_message_id=send.inbound_provider_message_id,
        )
        assert reply.provider_accepted is True
        assert reply.recipient_verified is True
        assert reply.adapter_invocations == 1
        assert backend.gmail_sends == 1
        assert reply.reply_provider_message_id != send.inbound_provider_message_id

    def test_integration_denied_skipped_path(self):
        backend = ContractSemiAutoBackend(
            sender_email=SENDER,
            recipient_email=RECIPIENT,
            simulate_execution_skipped=True,
        )
        scenario = _send_after_scenario()
        send = backend.send_test_message(
            campaign_id="c1", scenario=scenario, idempotency_key="k1"
        )
        backend.approve_via_lifecycle(
            scenario_id=scenario.scenario_id, operation_id="op-1", decision="approve"
        )
        reply = backend.verify_reply(
            scenario=scenario,
            approved=True,
            inbound_provider_message_id=send.inbound_provider_message_id,
        )
        assert reply.reply_execution_status == "skipped"
        assert reply.adapter_invocations == 0
        assert backend.gmail_sends == 0

    def test_execution_failed_stops_before_recipient_observer(self):
        backend = ContractSemiAutoBackend(
            sender_email=SENDER,
            recipient_email=RECIPIENT,
            simulate_execution_failed=True,
        )
        scenario = _send_after_scenario()
        send = backend.send_test_message(
            campaign_id="c1", scenario=scenario, idempotency_key="k1"
        )
        backend.approve_via_lifecycle(
            scenario_id=scenario.scenario_id, operation_id="op-1", decision="approve"
        )
        reply = backend.verify_reply(
            scenario=scenario,
            approved=True,
            inbound_provider_message_id=send.inbound_provider_message_id,
        )
        assert reply.reply_execution_status == "failed"
        assert reply.recipient_verified is False
        assert backend.gmail_sends == 0

    def test_outcome_unknown_no_retry(self):
        backend = ContractSemiAutoBackend(
            sender_email=SENDER,
            recipient_email=RECIPIENT,
            simulate_execution_outcome_unknown=True,
        )
        scenario = _send_after_scenario()
        send = backend.send_test_message(
            campaign_id="c1", scenario=scenario, idempotency_key="k1"
        )
        backend.approve_via_lifecycle(
            scenario_id=scenario.scenario_id, operation_id="op-1", decision="approve"
        )
        reply = backend.verify_reply(
            scenario=scenario,
            approved=True,
            inbound_provider_message_id=send.inbound_provider_message_id,
        )
        assert reply.reply_execution_status == "outcome_unknown"
        assert reply.provider_accepted is False
        assert backend.gmail_sends == 0

    def test_duplicate_approval_idempotent(self):
        backend = ContractSemiAutoBackend(sender_email=SENDER, recipient_email=RECIPIENT)
        scenario = _send_after_scenario()
        backend.send_test_message(campaign_id="c1", scenario=scenario, idempotency_key="k1")
        first = backend.approve_via_lifecycle(
            scenario_id=scenario.scenario_id, operation_id="op-1", decision="approve"
        )
        second = backend.approve_via_lifecycle(
            scenario_id=scenario.scenario_id, operation_id="op-1", decision="approve"
        )
        assert first.already_resolved is False
        assert second.already_resolved is True
        reply = backend.verify_reply(scenario=scenario, approved=True)
        assert reply.adapter_invocations == 1
        assert backend.gmail_sends == 1

    def test_hold_scenario_zero_sends(self):
        backend = ContractSemiAutoBackend(sender_email=SENDER, recipient_email=RECIPIENT)
        scenario = _hold_scenario()
        backend.send_test_message(campaign_id="c1", scenario=scenario, idempotency_key="k1")
        reply = backend.verify_reply(scenario=scenario, approved=False)
        assert reply.adapter_invocations == 0
        assert backend.gmail_sends == 0

    def test_inbound_id_cannot_be_used_as_reply_id(self):
        backend = ContractSemiAutoBackend(sender_email=SENDER, recipient_email=RECIPIENT)
        scenario = _send_after_scenario()
        send = backend.send_test_message(
            campaign_id="c1", scenario=scenario, idempotency_key="k1"
        )
        backend.approve_via_lifecycle(
            scenario_id=scenario.scenario_id, operation_id="op-1", decision="approve"
        )
        evidence = backend.reply_execution[scenario.scenario_id]
        evidence.reply_provider_message_id = send.inbound_provider_message_id
        with pytest.raises(LiveEvalSafetyError, match="inbound_provider_message_id equals"):
            backend.verify_reply(
                scenario=scenario,
                approved=True,
                inbound_provider_message_id=send.inbound_provider_message_id,
            )

    def test_non_gmail_writes_remain_zero(self):
        backend = ContractSemiAutoBackend(sender_email=SENDER, recipient_email=RECIPIENT)
        scenario = _send_after_scenario()
        backend.send_test_message(campaign_id="c1", scenario=scenario, idempotency_key="k1")
        backend.approve_via_lifecycle(
            scenario_id=scenario.scenario_id, operation_id="op-1", decision="approve"
        )
        backend.verify_reply(scenario=scenario, approved=True)
        assert sum(backend.external_writes.values()) == 0
        assert backend.automatic_verify_link_merge == 0


class TestHarnessOutcomePolling:
    def test_poll_returns_terminal_skipped(self):
        calls = {"n": 0}

        def fetch_observation():
            calls["n"] += 1
            return {
                "job": {
                    "decision_records": [
                        {
                            "record_type": "execution_outcome",
                            "execution_status": "skipped",
                            "action_operation_id": "op-1",
                        }
                    ],
                    "result": {},
                }
            }

        evidence = poll_post_approval_reply_execution(
            fetch_observation,
            None,
            action_operation_id="op-1",
            inbound_provider_message_id="inbound-1",
            inbound_rfc_message_id=None,
            timeout_seconds=1.0,
            poll_interval_seconds=0.01,
        )
        assert evidence.reply_execution_status == "skipped"
        assert calls["n"] >= 1


class TestRunnerSkippedExecution:
    def test_runner_fails_fast_on_skipped_execution(self, tmp_path):
        profile = load_customer_profile("pilot-service-company-v1")
        scenario = _send_after_scenario()
        backend = ContractSemiAutoBackend(
            sender_email=SENDER,
            recipient_email=RECIPIENT,
            simulate_execution_skipped=True,
        )
        campaign_state = SemiAutoCampaignState(
            campaign_id="c1",
            runtime_sha="test-sha",
            profile_id="pilot-service-company-v1",
            profile_snapshot_hash="hash",
            manifest_hash="manifest",
            oracle_version="v1",
            tenant_id=LIVE_EVAL_TENANT,
        )
        scenario_state = ScenarioExecutionState(
            scenario_id=scenario.scenario_id,
            execution_id=str(uuid.uuid4()),
            state=CampaignState.SCENARIO_QUEUED,
        )
        config = SemiAutoRunnerConfig(
            campaign_id="c1",
            runtime_sha="test-sha",
            state_root=tmp_path,
            sender_email=SENDER,
            recipient_email=RECIPIENT,
            contract_mode=True,
        )

        with patch(
            "app.evaluation.profile_testbot.campaign.semi_auto_runner.run_oracles"
        ) as mock_oracles, patch(
            "app.evaluation.profile_testbot.campaign.semi_auto_runner.evaluate_harness_decision"
        ) as mock_harness:
            from app.evaluation.profile_testbot.oracles.runner import OracleEvaluation

            mock_oracles.return_value = OracleEvaluation()
            mock_harness.return_value = MagicMock(approved=True, decision="approve")

            result = _execute_scenario(
                config=config,
                campaign_state=campaign_state,
                scenario_state=scenario_state,
                scenario=scenario,
                backend=backend,
                profile=profile,
            )

        assert result["state"] == CampaignState.SEND_FAILED.value
        assert "skipped" in (result.get("failure_reason") or "")
        assert backend.gmail_sends == 0


class TestApprovalDeliveryMetadata:
    def test_delivery_payload_preserves_approval_gating_metadata(self):
        from app.workflows.processors.action_dispatch_processor import _approval_delivery_payload

        action = {
            "type": "send_customer_auto_reply",
            "to": RECIPIENT,
            "subject": "Re: test",
            "body": "Hej, tack för din förfrågan. Vi återkommer.",
            "_needs_approval": True,
            "_approval_reason": "safe_acknowledgement_requires_approval",
            "_safe_acknowledgement_path": True,
            "_action_operation_id": "op-123",
            "_skip": False,
        }
        delivery = _approval_delivery_payload(action)
        assert delivery["_needs_approval"] is True
        assert delivery["_approval_reason"] == "safe_acknowledgement_requires_approval"
        assert delivery["_safe_acknowledgement_path"] is True
        assert "_action_operation_id" not in delivery
        assert "_skip" not in delivery

    def test_write_policy_allows_post_approval_delivery_with_metadata(self, tenant_db):
        action = {
            "type": "send_customer_auto_reply",
            "to": SENDER,
            "_needs_approval": True,
            "_approval_reason": "safe_acknowledgement_requires_approval",
            "_safe_acknowledgement_path": True,
            "_authorization": "execution_allowed",
        }
        snapshot = TrustedLiveEvalSnapshot(
            evaluation_run_id="run-1",
            tenant_id=LIVE_EVAL_TENANT,
            scenario_id="PTB-SEM-0000",
            attempt_id=1,
            transport_mode="live_gmail",
            ai_mode="live_llm",
            expected_sender=SENDER,
            expected_recipient=RECIPIENT,
            config_hash="cfg",
            trusted=True,
        )
        with live_eval_context(snapshot, db=tenant_db):
            with (
                patch(
                    "app.evaluation.live.write_policy.validate_trusted_live_eval_context",
                    return_value=snapshot,
                ),
                patch("app.evaluation.live.write_policy.emit_live_eval_audit"),
            ):
                enforce_live_eval_write_policy(
                    action,
                    db=tenant_db,
                    job=Job(
                        job_id=str(uuid.uuid4()),
                        tenant_id=LIVE_EVAL_TENANT,
                        job_type=JobType.LEAD,
                        input_data={"evaluation_run_id": "run-1"},
                    ),
                )
