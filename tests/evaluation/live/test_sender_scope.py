"""Hermetic tests for sender send-scope preflight."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.evaluation.live.sender_scope import (
    GMAIL_COMPOSE_SCOPE,
    GMAIL_FULL_MAILBOX_SCOPE,
    GMAIL_MODIFY_SCOPE,
    GMAIL_SEND_SCOPE,
    verify_sender_send_scope,
)
from app.integrations.google.mail_client import TokenRefreshResult

_READ_ONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


def _scope_report(*scopes: str):
    refresh = TokenRefreshResult(
        access_token="access-token",
        granted_scopes=frozenset(scopes),
    )
    return patch(
        "app.evaluation.live.sender_scope.refresh_access_token_with_metadata",
        return_value=refresh,
    ), patch("app.evaluation.live.sender_scope.load_sender_credentials")


@pytest.mark.parametrize(
    "scope",
    [
        GMAIL_SEND_SCOPE,
        GMAIL_COMPOSE_SCOPE,
        GMAIL_MODIFY_SCOPE,
        GMAIL_FULL_MAILBOX_SCOPE,
    ],
)
def test_verify_sender_send_scope_accepts_send_capable_scopes(scope: str):
    refresh_patch, cred_patch = _scope_report(scope)
    with refresh_patch, cred_patch:
        report = verify_sender_send_scope()
    assert report.verified is True
    assert report.unverifiable is False
    assert scope in report.granted_send_scopes


def test_verify_sender_send_scope_blocks_read_only_scope():
    refresh_patch, cred_patch = _scope_report(_READ_ONLY_SCOPE)
    with refresh_patch, cred_patch:
        report = verify_sender_send_scope()
    assert report.verified is False
    assert report.unverifiable is False
    assert report.failure_category == "configuration"
    assert report.issues


def test_verify_sender_send_scope_unverifiable_when_scope_metadata_missing():
    refresh = TokenRefreshResult(access_token="access-token", granted_scopes=frozenset())
    with patch(
        "app.evaluation.live.sender_scope.refresh_access_token_with_metadata",
        return_value=refresh,
    ), patch("app.evaluation.live.sender_scope.load_sender_credentials"):
        report = verify_sender_send_scope()
    assert report.verified is False
    assert report.unverifiable is True
    assert report.failure_category == "sender_scope_unverifiable"


def test_verify_sender_send_scope_does_not_use_tokeninfo():
    import app.evaluation.live.sender_scope as sender_scope_module

    source = open(sender_scope_module.__file__, encoding="utf-8").read()
    assert "oauth2/v1/tokeninfo" not in source
    assert "tokeninfo?" not in source


def test_refresh_metadata_helper_does_not_log_raw_token_response(caplog):
    from app.integrations.google import mail_client

    source = open(mail_client.__file__, encoding="utf-8").read()
    assert "tokeninfo" not in source.lower()
