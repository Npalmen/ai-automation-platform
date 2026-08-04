"""Focused tests for R3 real reply-provider contract (no Gmail send)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.profile_testbot.qualification.coworker_r3_execution import (
    ORPHANED_R3_INBOUND_TRIGGERS,
)
from app.evaluation.profile_testbot.qualification.coworker_r3_mutation_contract import (
    R3_ORPHAN_ATTEMPT_EVALUATION_RUN_IDS,
)
from app.evaluation.profile_testbot.qualification.coworker_r3_reply_provider import (
    ORPHANED_ATTEMPT_6_EVALUATION_RUN_ID,
    R3LiveReplyProviderResolution,
    build_r3_email_result_from_resolution,
    is_r3_frozen_customer_reply_context,
    probe_orphaned_attempt_6_reply,
    resolve_r3_live_reply_provider,
    run_r3_live_reply_provider_readiness,
)
from app.workflows.action_executor import _build_email_result, _build_stub_result
from app.workflows.external_write_trace import (
    _classify_adapter_result_status,
    is_real_provider_execution_result,
)
from app.workflows.decision_record import ExecutionStatus


def _r3_job(*, evaluation_run_id: str = "11111111-1111-4111-8111-111111111111"):
    return SimpleNamespace(
        tenant_id="TENANT_LIVE_EVAL",
        job_id="job-r3-1",
        input_data={
            "live_eval": {
                "evaluation_run_id": evaluation_run_id,
                "tenant_id": "TENANT_LIVE_EVAL",
                "scenario_id": "PTB-DCQ-0000",
                "attempt_id": 1,
                "transport_mode": "live_gmail",
                "ai_mode": "r3_frozen_approved_body",
                "config_hash": "cfg",
                "expected_sender": "sender@eval.test",
                "expected_recipient": "recipient@eval.test",
                "trusted": True,
            }
        },
    )


def _r3_action(**overrides):
    action = {
        "type": "send_customer_auto_reply",
        "tenant_id": "TENANT_LIVE_EVAL",
        "to": "sender@eval.test",
        "subject": "Re: offer",
        "body": "Frozen body",
        "thread_id": "thread-1",
        "in_reply_to": "<root@mail>",
        "references": "<root@mail>",
        "_authorization": "execution_allowed",
        "_action_operation_id": "op-r3-1",
        "_approval_id": "appr-1",
    }
    action.update(overrides)
    return action


def _ready_resolution(**overrides) -> R3LiveReplyProviderResolution:
    adapter = MagicMock()
    adapter.execute_action.return_value = {
        "status": "success",
        "provider": "google_mail",
        "external_id": "gmail-msg-1",
        "payload": {
            "google_message_id": "gmail-msg-1",
            "thread_id": "thread-1",
            "rfc_message_id": "<rfc@test>",
        },
    }
    base = R3LiveReplyProviderResolution(
        provider_adapter=adapter,
        provider_source="live_eval_recipient_env",
        provider_name="google_mail",
        sender_mailbox_identity_redacted="re…@eval.test",
        expected_reply_recipient_redacted="se…@eval.test",
        send_scope_verified=True,
        read_scope_verified=True,
        thread_binding_valid=True,
        approval_binding_valid=True,
        frozen_body_binding_valid=True,
        tenant_google_mail_used=False,
        stub_fallback_possible=False,
        ready=True,
        blockers=[],
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


class TestR3ReplyProviderSelection:
    def test_r3_context_detected(self):
        assert is_r3_frozen_customer_reply_context(
            action=_r3_action(), job=_r3_job(), db=None
        )

    def test_normal_tenant_not_r3(self):
        job = SimpleNamespace(tenant_id="TENANT_1001", input_data={})
        action = _r3_action(tenant_id="TENANT_1001")
        assert not is_r3_frozen_customer_reply_context(action=action, job=job, db=None)

    def test_r3_uses_recipient_env_not_tenant_gmail(self):
        resolution = _ready_resolution()
        with patch(
            "app.evaluation.profile_testbot.qualification.coworker_r3_reply_provider.resolve_r3_live_reply_provider",
            return_value=resolution,
        ), patch(
            "app.evaluation.profile_testbot.qualification.coworker_r3_reply_provider.is_r3_frozen_customer_reply_context",
            return_value=True,
        ), patch(
            "app.workflows.action_executor.get_integration_connection_config"
        ) as tenant_cfg:
            result = _build_email_result(_r3_action(), db=MagicMock(), job=_r3_job())
            tenant_cfg.assert_not_called()
            assert result["provider"] == "google_mail"
            assert result["r3_reply_provider_source"] == "live_eval_recipient_env"
            assert result["external_id"] == "gmail-msg-1"

    def test_r3_cannot_return_stub(self):
        with patch(
            "app.evaluation.profile_testbot.qualification.coworker_r3_reply_provider.is_r3_frozen_customer_reply_context",
            return_value=True,
        ), patch(
            "app.evaluation.profile_testbot.qualification.coworker_r3_reply_provider.resolve_r3_live_reply_provider",
            return_value=_ready_resolution(ready=False, blockers=["no oauth"], provider_adapter=None),
        ):
            with pytest.raises(LiveEvalSafetyError, match="not ready"):
                _build_email_result(_r3_action(), db=MagicMock(), job=_r3_job())

    def test_missing_oauth_blocks_readiness(self):
        with patch(
            "app.evaluation.profile_testbot.qualification.coworker_r3_reply_provider.load_recipient_credentials",
            side_effect=LiveEvalSafetyError("missing LIVE_EVAL_RECIPIENT_GMAIL_REFRESH_TOKEN"),
        ), patch(
            "app.evaluation.live.config.get_live_eval_config",
            return_value=SimpleNamespace(
                recipient_emails=frozenset({"recipient@eval.test"}),
                sender_emails=frozenset({"sender@eval.test"}),
            ),
        ):
            report = run_r3_live_reply_provider_readiness(
                expected_recipient="recipient@eval.test",
                expected_sender="sender@eval.test",
            )
            assert report["reply_provider_ready"] is False
            assert any("REFRESH_TOKEN" in b or "missing" in b.lower() for b in report["blockers"])

    def test_wrong_mailbox_identity_blocks(self):
        creds = SimpleNamespace(
            refresh_token="rt",
            client_id="cid",
            client_secret="sec",
            api_url="https://gmail.googleapis.com/gmail/v1",
            user_id="me",
        )
        client = MagicMock()
        client.access_token = "tok"
        client.get_profile_email.return_value = "wrong@eval.test"
        with patch(
            "app.evaluation.profile_testbot.qualification.coworker_r3_reply_provider.load_recipient_credentials",
            return_value=creds,
        ), patch(
            "app.evaluation.profile_testbot.qualification.coworker_r3_reply_provider.refresh_access_token_with_metadata",
            return_value=SimpleNamespace(
                granted_scopes=frozenset(
                    {
                        "https://www.googleapis.com/auth/gmail.modify",
                        "https://www.googleapis.com/auth/gmail.readonly",
                    }
                )
            ),
        ), patch(
            "app.evaluation.profile_testbot.qualification.coworker_r3_reply_provider.build_recipient_client",
            return_value=client,
        ):
            resolution = resolve_r3_live_reply_provider(
                db=None,
                job=_r3_job(),
                action=_r3_action(),
                probe_only=True,
            )
            assert resolution.ready is False
            assert any("mailbox identity" in b for b in resolution.blockers)

    def test_missing_send_scope_blocks(self):
        creds = SimpleNamespace(
            refresh_token="rt",
            client_id="cid",
            client_secret="sec",
            api_url="https://gmail.googleapis.com/gmail/v1",
            user_id="me",
        )
        with patch(
            "app.evaluation.profile_testbot.qualification.coworker_r3_reply_provider.load_recipient_credentials",
            return_value=creds,
        ), patch(
            "app.evaluation.profile_testbot.qualification.coworker_r3_reply_provider.refresh_access_token_with_metadata",
            return_value=SimpleNamespace(
                granted_scopes=frozenset({"https://www.googleapis.com/auth/gmail.readonly"})
            ),
        ):
            resolution = resolve_r3_live_reply_provider(
                db=None,
                job=_r3_job(),
                action=_r3_action(),
                probe_only=True,
            )
            assert resolution.ready is False
            assert any("send" in b or "modify" in b for b in resolution.blockers)

    def test_valid_recipient_env_without_tenant_gmail_passes_resolution(self):
        creds = SimpleNamespace(
            refresh_token="rt",
            client_id="cid",
            client_secret="sec",
            api_url="https://gmail.googleapis.com/gmail/v1",
            user_id="me",
        )
        client = MagicMock()
        client.access_token = "tok"
        client.get_profile_email.return_value = "recipient@eval.test"
        with patch(
            "app.evaluation.profile_testbot.qualification.coworker_r3_reply_provider.load_recipient_credentials",
            return_value=creds,
        ), patch(
            "app.evaluation.profile_testbot.qualification.coworker_r3_reply_provider.refresh_access_token_with_metadata",
            return_value=SimpleNamespace(
                granted_scopes=frozenset(
                    {
                        "https://www.googleapis.com/auth/gmail.modify",
                        "https://www.googleapis.com/auth/gmail.readonly",
                    }
                )
            ),
        ), patch(
            "app.evaluation.profile_testbot.qualification.coworker_r3_reply_provider.build_recipient_client",
            return_value=client,
        ):
            resolution = resolve_r3_live_reply_provider(
                db=None,
                job=_r3_job(),
                action=_r3_action(),
                probe_only=True,
            )
            assert resolution.ready is True
            assert resolution.provider_source == "live_eval_recipient_env"
            assert resolution.provider_name == "google_mail"
            assert resolution.tenant_google_mail_used is False
            assert resolution.stub_fallback_possible is False

    def test_invalid_recipient_env_does_not_fallback_to_tenant(self):
        with patch(
            "app.evaluation.profile_testbot.qualification.coworker_r3_reply_provider.load_recipient_credentials",
            side_effect=LiveEvalSafetyError("recipient oauth missing"),
        ):
            resolution = resolve_r3_live_reply_provider(
                db=None,
                job=_r3_job(),
                action=_r3_action(),
                probe_only=True,
            )
            assert resolution.ready is False
            assert resolution.provider_adapter is None
            assert resolution.tenant_google_mail_used is False

    def test_normal_tenant_still_uses_stub_when_unconfigured(self):
        action = {
            "type": "send_email",
            "tenant_id": "TENANT_1001",
            "to": "a@b.test",
            "subject": "Hi",
            "body": "Hello",
        }
        with patch(
            "app.workflows.action_executor.get_integration_connection_config",
            return_value={},
        ), patch(
            "app.workflows.action_executor.is_integration_configured",
            return_value=False,
        ):
            result = _build_email_result(action, db=None, job=None)
            assert result["provider"] == "internal_stub"
            assert is_real_provider_execution_result(result) is False


class TestExternalWriteOutcomeSemantics:
    def test_stub_not_succeeded(self):
        stub = _build_stub_result(
            "send_customer_auto_reply",
            "a@b.test",
            {"to": "a@b.test"},
            "email",
            "stub",
        )
        status, meta = _classify_adapter_result_status(stub, action=_r3_action())
        assert status == ExecutionStatus.FAILED
        assert meta.get("reconciliation_required") is True
        assert is_real_provider_execution_result(stub) is False

    def test_real_provider_with_message_id_succeeded(self):
        result = {
            "type": "send_customer_auto_reply",
            "status": "executed",
            "provider": "google_mail",
            "external_id": "gmail-msg-1",
            "integration_result": {
                "provider": "google_mail",
                "status": "success",
                "external_id": "gmail-msg-1",
                "payload": {
                    "google_message_id": "gmail-msg-1",
                    "thread_id": "thread-1",
                    "rfc_message_id": "<rfc@test>",
                },
            },
        }
        status, meta = _classify_adapter_result_status(result, action=_r3_action())
        assert status == ExecutionStatus.SUCCEEDED
        assert meta["provider_message_id"] == "gmail-msg-1"
        assert meta["provider_thread_id"] == "thread-1"
        assert meta["provider_rfc_message_id"] == "<rfc@test>"

    def test_real_provider_missing_message_id_unknown(self):
        result = {
            "type": "send_customer_auto_reply",
            "status": "executed",
            "provider": "google_mail",
            "integration_result": {
                "provider": "google_mail",
                "status": "success",
                "payload": {"thread_id": "thread-1"},
            },
        }
        status, meta = _classify_adapter_result_status(result, action=_r3_action())
        assert status == ExecutionStatus.OUTCOME_UNKNOWN
        assert meta.get("reconciliation_required") is True

    def test_build_r3_result_rejects_stub_adapter(self):
        adapter = MagicMock()
        adapter.execute_action.return_value = {
            "status": "stubbed",
            "provider": "internal_stub",
        }
        resolution = _ready_resolution(provider_adapter=adapter)
        with pytest.raises(LiveEvalSafetyError, match="stub"):
            build_r3_email_result_from_resolution(_r3_action(), resolution)

    def test_threading_fields_passed_to_adapter(self):
        resolution = _ready_resolution()
        build_r3_email_result_from_resolution(_r3_action(), resolution)
        payload = resolution.provider_adapter.execute_action.call_args.kwargs["payload"]
        assert payload["thread_id"] == "thread-1"
        assert payload["in_reply_to"] == "<root@mail>"
        assert payload["references"] == "<root@mail>"


class TestOrphanAttempt6:
    def test_orphan_registered(self):
        orphan = next(
            o for o in ORPHANED_R3_INBOUND_TRIGGERS if o["orphan_id"] == "orphaned_attempt_6"
        )
        assert orphan["evaluation_run_id"] == ORPHANED_ATTEMPT_6_EVALUATION_RUN_ID
        assert orphan["never_retry"] is True
        assert orphan["reuse_blocked"] is True
        assert ORPHANED_ATTEMPT_6_EVALUATION_RUN_ID in R3_ORPHAN_ATTEMPT_EVALUATION_RUN_IDS

    def test_orphan_probe_read_only_verified(self):
        db = MagicMock()
        row = SimpleNamespace(
            evaluation_run_id=ORPHANED_ATTEMPT_6_EVALUATION_RUN_ID,
            scenario_id="PTB-DCQ-0000",
            status="aborted",
            root_gmail_message_id="19fc7f4e",
        )
        job = SimpleNamespace(
            job_id="56968051-2b0e-4b76-9304-acc0971489bb",
            input_data={
                "live_eval": {
                    "evaluation_run_id": ORPHANED_ATTEMPT_6_EVALUATION_RUN_ID,
                    "trusted": True,
                }
            },
        )
        approval = SimpleNamespace(approval_id="77df0230", delivery_payload={})
        execution = SimpleNamespace(
            action_type="send_customer_auto_reply",
            provider="internal_stub",
            external_id=None,
            status="executed",
            result_payload={
                "integration_result": {"provider": "internal_stub", "status": "stubbed"}
            },
        )
        with patch(
            "app.repositories.postgres.live_eval_repository.LiveEvalRunRepository.get_run",
            return_value=row,
        ), patch(
            "app.repositories.postgres.job_repository.JobRepository.list_jobs_for_tenant",
            return_value=[job],
        ), patch(
            "app.repositories.postgres.approval_repository.ApprovalRequestRepository.get_latest_for_job",
            return_value=approval,
        ), patch(
            "app.repositories.postgres.action_execution_repository.ActionExecutionRepository.list_for_job",
            return_value=[execution],
        ):
            report = probe_orphaned_attempt_6_reply(db)
            assert report["orphaned_attempt_6_reply_probe_verified"] is True
            assert report["never_retry"] is True
            assert report["automatic_retry"] is False
            assert report["gmail_mutations_performed"] is False
            assert report["adapter_provider"] == "internal_stub"
            assert report["reply_provider_message_id"] is None
