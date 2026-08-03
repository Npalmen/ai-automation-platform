"""Tests for read-only recipient Gmail readiness."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.evaluation.live.recipient_gmail_readiness import run_recipient_gmail_readiness
from app.integrations.google.mail_client import GmailMessageListResult, TokenRefreshResult


@pytest.fixture
def single_address_env(live_eval_env, monkeypatch):
    monkeypatch.setenv("LIVE_EVAL_SENDER_EMAILS", "sender@eval.test")
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_EMAILS", "recipient@eval.test")
    from app.evaluation.live.config import get_live_eval_config

    get_live_eval_config.cache_clear()
    yield
    get_live_eval_config.cache_clear()


def test_recipient_readiness_passes_with_live_api_calls(single_address_env):
    client = MagicMock()
    client.get_profile_email.return_value = "recipient@eval.test"
    client.list_labels.return_value = [{"id": "INBOX", "name": "INBOX"}]
    client.list_messages_page.return_value = GmailMessageListResult(message_ids=[], truncated=False)
    refresh = TokenRefreshResult(
        access_token="access-token",
        granted_scopes=frozenset({"https://www.googleapis.com/auth/gmail.readonly"}),
    )

    with (
        patch(
            "app.evaluation.live.recipient_gmail_readiness.refresh_access_token_with_metadata",
            return_value=refresh,
        ),
        patch(
            "app.evaluation.live.recipient_gmail_readiness.load_recipient_credentials",
            return_value=MagicMock(
                refresh_token="rt",
                client_id="cid",
                client_secret="sec",
                user_id="me",
                api_url="https://gmail.googleapis.com/gmail/v1",
            ),
        ),
        patch(
            "app.integrations.google.mail_client.GoogleMailClient",
            return_value=client,
        ),
    ):
        report = run_recipient_gmail_readiness(expected_recipient="recipient@eval.test")

    assert report.ready is True
    assert report.recipient_delivery_observation_ready is True
    assert report.recipient_token_refresh_passed is True
    assert report.recipient_list_labels_passed is True
    assert report.recipient_read_query_passed is True


def test_recipient_readiness_fails_when_refresh_fails(single_address_env):
    with patch(
        "app.evaluation.live.recipient_gmail_readiness.refresh_access_token_with_metadata",
        side_effect=RuntimeError("invalid_grant"),
    ), patch(
        "app.evaluation.live.recipient_gmail_readiness.load_recipient_credentials",
        return_value=MagicMock(
            refresh_token="rt",
            client_id="cid",
            client_secret="sec",
            user_id="me",
            api_url="https://gmail.googleapis.com/gmail/v1",
        ),
    ):
        report = run_recipient_gmail_readiness(expected_recipient="recipient@eval.test")

    assert report.ready is False
    assert report.recipient_token_refresh_passed is False
    assert any("refresh failed" in blocker for blocker in report.blockers)


def test_recipient_readiness_fails_when_list_labels_401(single_address_env):
    client = MagicMock()
    client.get_profile_email.return_value = "recipient@eval.test"
    client.list_labels.side_effect = RuntimeError("Gmail API error (401)")
    refresh = TokenRefreshResult(
        access_token="access-token",
        granted_scopes=frozenset({"https://www.googleapis.com/auth/gmail.readonly"}),
    )

    with (
        patch(
            "app.evaluation.live.recipient_gmail_readiness.refresh_access_token_with_metadata",
            return_value=refresh,
        ),
        patch(
            "app.evaluation.live.recipient_gmail_readiness.load_recipient_credentials",
            return_value=MagicMock(
                refresh_token="rt",
                client_id="cid",
                client_secret="sec",
                user_id="me",
                api_url="https://gmail.googleapis.com/gmail/v1",
            ),
        ),
        patch(
            "app.integrations.google.mail_client.GoogleMailClient",
            return_value=client,
        ),
    ):
        report = run_recipient_gmail_readiness(expected_recipient="recipient@eval.test")

    assert report.ready is False
    assert report.recipient_list_labels_passed is False


def test_recipient_readiness_fails_on_mailbox_identity_mismatch(single_address_env):
    client = MagicMock()
    client.get_profile_email.return_value = "other@eval.test"
    refresh = TokenRefreshResult(
        access_token="access-token",
        granted_scopes=frozenset({"https://www.googleapis.com/auth/gmail.readonly"}),
    )

    with (
        patch(
            "app.evaluation.live.recipient_gmail_readiness.refresh_access_token_with_metadata",
            return_value=refresh,
        ),
        patch(
            "app.evaluation.live.recipient_gmail_readiness.load_recipient_credentials",
            return_value=MagicMock(
                refresh_token="rt",
                client_id="cid",
                client_secret="sec",
                user_id="me",
                api_url="https://gmail.googleapis.com/gmail/v1",
            ),
        ),
        patch(
            "app.integrations.google.mail_client.GoogleMailClient",
            return_value=client,
        ),
    ):
        report = run_recipient_gmail_readiness(expected_recipient="recipient@eval.test")

    assert report.ready is False
    assert report.recipient_mailbox_identity_match is False


def test_recipient_readiness_fails_when_scopes_missing(single_address_env):
    client = MagicMock()
    client.get_profile_email.return_value = "recipient@eval.test"
    refresh = TokenRefreshResult(access_token="access-token", granted_scopes=frozenset())

    with (
        patch(
            "app.evaluation.live.recipient_gmail_readiness.refresh_access_token_with_metadata",
            return_value=refresh,
        ),
        patch(
            "app.evaluation.live.recipient_gmail_readiness.load_recipient_credentials",
            return_value=MagicMock(
                refresh_token="rt",
                client_id="cid",
                client_secret="sec",
                user_id="me",
                api_url="https://gmail.googleapis.com/gmail/v1",
            ),
        ),
        patch(
            "app.integrations.google.mail_client.GoogleMailClient",
            return_value=client,
        ),
    ):
        report = run_recipient_gmail_readiness(expected_recipient="recipient@eval.test")

    assert report.ready is False
    assert report.recipient_required_scopes_present is False


def test_delivery_endpoint_fail_closed_when_recipient_not_ready(live_eval_env, db, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.dependencies import get_db
    from app.evaluation.live.recipient_gmail_readiness import RecipientGmailReadinessResult
    from app.evaluation.live.routes import router as live_eval_router
    from app.repositories.postgres.live_eval_models import LiveEvalRunRow

    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    now = datetime.now(timezone.utc)
    run = LiveEvalRunRow(
        evaluation_run_id="run-delivery-readiness",
        tenant_id="TENANT_LIVE_EVAL",
        scenario_id="PTB-DCQ-0000",
        attempt_id=1,
        transport_mode="live_gmail",
        ai_mode="r3_frozen_approved_body",
        fixture_bundle_id="k2f_bundle_s01",
        expected_sender="sender@eval.test",
        expected_recipient="recipient@eval.test",
        status="registered",
        created_by="test",
        created_at=now,
        expires_at=now + timedelta(hours=2),
        config_hash="abc",
    )
    db.add(run)
    db.commit()

    app = FastAPI()
    app.include_router(live_eval_router)
    app.dependency_overrides[get_db] = lambda: db
    with (
        TestClient(app, raise_server_exceptions=False) as client,
        patch(
            "app.evaluation.live.recipient_gmail_readiness.run_recipient_gmail_readiness",
            return_value=RecipientGmailReadinessResult(
                recipient_oauth_configured=True,
                blockers=["recipient list_labels failed"],
            ),
        ),
    ):
        response = client.get(
            "/admin/live-eval/runs/run-delivery-readiness/delivery",
            params={"tenant_id": "TENANT_LIVE_EVAL"},
            headers={"X-Admin-API-Key": "test-admin-key"},
        )
    app.dependency_overrides.clear()
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["failure_stage"] == "delivery_observation"
    assert detail["recipient_delivery_observation_ready"] is False
    assert detail["blockers"]
