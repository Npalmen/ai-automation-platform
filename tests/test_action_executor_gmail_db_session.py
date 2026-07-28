"""PostgreSQL-style reproduction: Gmail adapter requires DB session for tenant OAuth."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.evaluation.live.provider_recipient_verification import provider_execution_outcome_ready
from app.repositories.postgres.oauth_credential_models import OAuthCredentialRecord
from app.workflows.action_executor import _build_email_result, execute_action
from app.workflows.external_write_trace import _adapter_outcome_metadata, is_real_provider_execution_result


@pytest.fixture()
def oauth_db():
    engine = create_engine("sqlite:///:memory:")
    OAuthCredentialRecord.__table__.create(engine, checkfirst=True)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _seed_oauth(session, *, tenant_id: str = "TENANT_LIVE_EVAL") -> None:
    session.add(
        OAuthCredentialRecord(
            tenant_id=tenant_id,
            provider="google_mail",
            access_token="tenant-access-token",
            refresh_token="tenant-refresh-token",
            expires_at=datetime.now(timezone.utc),
            scopes="gmail.send",
            metadata_json={"email": "tenant@eval.test"},
            connected_at=datetime.now(timezone.utc),
        )
    )
    session.commit()


def _reply_action(*, tenant_id: str = "TENANT_LIVE_EVAL") -> dict:
    return {
        "type": "send_customer_auto_reply",
        "tenant_id": tenant_id,
        "to": "sender@eval.test",
        "subject": "Re: test",
        "body": "Thanks",
        "from_email": "app@eval.test",
        "_action_operation_id": "op-reply-1",
    }


def _gmail_adapter_result() -> dict:
    return {
        "status": "success",
        "integration": "google_mail",
        "provider": "google_mail",
        "action": "send_email",
        "external_id": "gmail-msg-123",
        "payload": {
            "google_message_id": "gmail-msg-123",
            "thread_id": "thread-1",
            "rfc_message_id": "<rfc@test>",
        },
    }


class TestGmailDbSessionDispatch:
    def test_build_email_result_without_db_ignores_tenant_oauth(self, oauth_db):
        _seed_oauth(oauth_db)
        action = _reply_action()

        with (
            patch("app.workflows.action_executor._integration_allowed_for_action", return_value=True),
            patch("app.workflows.action_executor.get_integration_adapter") as mock_adapter,
            patch(
                "app.workflows.action_executor.get_integration_connection_config",
                return_value={
                    "api_url": "https://gmail.googleapis.com/gmail/v1",
                    "access_token": "",
                    "user_id": "me",
                    "credential_source": "platform_env",
                },
            ),
        ):
            result = _build_email_result(action, db=None)

        mock_adapter.assert_not_called()
        assert result["status"] == "executed"
        assert str(result.get("integration_result", {}).get("provider")) == "internal_stub"
        assert is_real_provider_execution_result(result) is False

    def test_build_email_result_with_db_uses_tenant_oauth(self, oauth_db):
        _seed_oauth(oauth_db)
        action = _reply_action()
        job = Job(
            job_id="job-1",
            tenant_id="TENANT_LIVE_EVAL",
            job_type=JobType.LEAD,
            input_data={"evaluation_run_id": "run-1"},
        )

        with (
            patch("app.workflows.action_executor._integration_allowed_for_action", return_value=True),
            patch("app.workflows.action_executor.get_integration_adapter") as mock_adapter,
            patch(
                "app.integrations.google.oauth_token_resolver.resolve_google_mail_connection_config",
                return_value={
                    "api_url": "https://gmail.googleapis.com/gmail/v1",
                    "access_token": "tenant-access-token",
                    "user_id": "tenant@eval.test",
                    "refresh_token": "tenant-refresh-token",
                    "credential_source": "tenant_oauth",
                },
            ),
        ):
            mock_adapter.return_value.execute_action.return_value = _gmail_adapter_result()
            result = _build_email_result(action, db=oauth_db)

        mock_adapter.return_value.execute_action.assert_called_once()
        assert is_real_provider_execution_result(result) is True
        metadata = _adapter_outcome_metadata(result, action=action)
        assert metadata["provider_message_id"] == "gmail-msg-123"
        assert metadata["adapter_recipient"] == "sender@eval.test"

    def test_execute_action_with_db_invokes_gmail_adapter_once(self, oauth_db):
        _seed_oauth(oauth_db)
        action = _reply_action()

        with (
            patch("app.workflows.action_executor._integration_allowed_for_action", return_value=True),
            patch("app.workflows.action_executor.get_integration_adapter") as mock_adapter,
            patch(
                "app.integrations.google.oauth_token_resolver.resolve_google_mail_connection_config",
                return_value={
                    "api_url": "https://gmail.googleapis.com/gmail/v1",
                    "access_token": "tenant-access-token",
                    "user_id": "tenant@eval.test",
                    "refresh_token": "tenant-refresh-token",
                    "credential_source": "tenant_oauth",
                },
            ),
        ):
            mock_adapter.return_value.execute_action.return_value = _gmail_adapter_result()
            result = execute_action(action, db=oauth_db)

        mock_adapter.return_value.execute_action.assert_called_once()
        assert result["type"] == "send_customer_auto_reply"
        assert is_real_provider_execution_result(result) is True

    def test_provider_ready_rejects_internal_stub_metadata(self):
        observation = {
            "job": {
                "decision_records": [
                    {
                        "record_type": "execution_outcome",
                        "execution_status": "succeeded",
                        "metadata": {
                            "provider_message_id": "fake",
                            "adapter_recipient": "sender@eval.test",
                            "adapter_status": "executed",
                            "adapter_provider": "internal_stub",
                        },
                    }
                ]
            },
            "events": [],
        }
        assert provider_execution_outcome_ready(observation) is False

    def test_db_session_without_oauth_row_is_fail_closed(self, oauth_db):
        from app.integrations.google.oauth_token_resolver import resolve_google_mail_connection_config

        config = resolve_google_mail_connection_config("TENANT_LIVE_EVAL", db=oauth_db)
        assert config.get("credential_source") == "tenant_missing"
        assert not config.get("access_token")

    def test_send_customer_auto_reply_maps_to_google_mail_integration(self):
        from app.workflows.action_authorization import classify_action

        spec = classify_action("send_customer_auto_reply")
        assert spec is not None
        assert spec.integration == "google_mail"
