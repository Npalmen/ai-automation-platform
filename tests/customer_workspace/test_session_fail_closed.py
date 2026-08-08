"""Session fail-closed adversarial tests for customer workspace API."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.core.admin_session import SESSION_COOKIE, create_session_token
from app.core.customer_session import CUSTOMER_SESSION_COOKIE
from app.repositories.postgres.customer_workspace_session_models import CustomerWorkspaceSessionRecord
from app.repositories.postgres.customer_workspace_user_repository import (
    USER_STATUS_DISABLED,
    CustomerWorkspaceUserRepository,
)
from app.repositories.postgres.tenant_config_models import TenantConfigRecord
from tests.customer_workspace.conftest import STRONG_PASSWORD, login, seed_user
from tests.customer_workspace.security_helpers import TENANT_A, TENANT_B, assert_error_body_sanitized


WORKSPACE_PATH = "/workspace/v1/context"
AUTH_ME_PATH = "/auth/customer/me"


@pytest.fixture()
def authed_token(client, db):
    user = seed_user(db, tenant_id=TENANT_A, email="viewer-a@example.com")
    response = login(client, email="viewer-a@example.com")
    assert response.status_code == 200
    token = response.cookies[CUSTOMER_SESSION_COOKIE]
    client.cookies.set(CUSTOMER_SESSION_COOKIE, token)
    return token, user


@pytest.mark.parametrize(
    "cookie_value",
    [None, "", "random-token", "not-a-valid-session"],
    ids=["missing", "empty", "random", "invalid"],
)
def test_workspace_requires_valid_customer_session(client, cookie_value):
    if cookie_value is not None:
        client.cookies.set(CUSTOMER_SESSION_COOKIE, cookie_value)
    assert client.get(WORKSPACE_PATH).status_code == 401


def test_revoked_session_denied_on_workspace(client, db, authed_token):
    token, _user = authed_token
    assert client.post("/auth/customer/logout", headers={"Origin": "http://testserver"}).status_code == 200
    client.cookies.set(CUSTOMER_SESSION_COOKIE, token)
    assert client.get(WORKSPACE_PATH).status_code == 401


def test_expired_session_denied_on_workspace(client, db, authed_token):
    token, user = authed_token
    session = db.query(CustomerWorkspaceSessionRecord).filter_by(user_id=user.id).one()
    session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    client.cookies.set(CUSTOMER_SESSION_COOKIE, token)
    assert client.get(WORKSPACE_PATH).status_code == 401


def test_disabled_user_denied_on_workspace(client, db, authed_token):
    token, user = authed_token
    CustomerWorkspaceUserRepository.set_status(db, user, USER_STATUS_DISABLED)
    client.cookies.set(CUSTOMER_SESSION_COOKIE, token)
    assert client.get(WORKSPACE_PATH).status_code == 401


def test_inactive_tenant_denied_on_workspace(client, db, authed_token):
    token, _user = authed_token
    tenant = db.query(TenantConfigRecord).filter_by(tenant_id=TENANT_A).one()
    tenant.status = "inactive"
    db.commit()
    response = client.get(WORKSPACE_PATH)
    assert response.status_code == 403
    assert response.json()["detail"] == "Tenant is inactive."


def test_missing_tenant_denied_on_workspace(client, db, authed_token):
    token, user = authed_token
    user.tenant_id = "MISSING_TENANT"
    db.commit()
    session = db.query(CustomerWorkspaceSessionRecord).filter_by(user_id=user.id).one()
    session.tenant_id = "MISSING_TENANT"
    db.commit()
    response = client.get(WORKSPACE_PATH)
    assert response.status_code == 403
    assert response.json()["detail"] == "Tenant is not available."


def test_session_tenant_mismatch_denied_on_workspace(client, db, authed_token):
    token, user = authed_token
    session = db.query(CustomerWorkspaceSessionRecord).filter_by(user_id=user.id).one()
    session.tenant_id = TENANT_B
    db.commit()
    client.cookies.set(CUSTOMER_SESSION_COOKIE, token)
    assert client.get(WORKSPACE_PATH).status_code == 401


def test_tenant_repository_failure_fail_closed_on_workspace(client, db, authed_token):
    token, _user = authed_token
    with patch(
        "app.customer_auth.tenant_access.TenantConfigRepository.get",
        side_effect=RuntimeError("db down"),
    ):
        response = client.get(WORKSPACE_PATH)
    assert response.status_code == 403
    assert response.json()["detail"] == "Tenant is not available."
    assert_error_body_sanitized(response)


def test_session_repository_failure_fail_closed_on_workspace(client, db, authed_token):
    token, _user = authed_token
    with patch(
        "app.core.customer_session.CustomerWorkspaceSessionRepository.get_active_by_token_hash",
        side_effect=RuntimeError("db down"),
    ):
        response = client.get(WORKSPACE_PATH)
    assert response.status_code == 401
    assert_error_body_sanitized(response)


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"X-API-Key": "tenant-key"},
        {"X-Admin-API-Key": "admin-key"},
        {"X-Tenant-ID": TENANT_B},
    ],
    ids=["none", "api_key", "admin_api_key", "tenant_header"],
)
def test_non_customer_auth_rejected_on_workspace(client, headers):
    assert client.get(WORKSPACE_PATH, headers=headers).status_code == 401


def test_admin_session_cookie_does_not_authorize_workspace(client):
    settings = SimpleNamespace(
        SESSION_SECRET_KEY="test-secret",
        ADMIN_USERNAME="admin",
        ADMIN_PASSWORD_HASH="hash",
        ENV="test",
    )
    token = create_session_token("admin", settings.SESSION_SECRET_KEY)
    client.cookies.set(SESSION_COOKIE, token)
    with patch("app.core.admin_session.get_settings", return_value=settings):
        assert client.get(WORKSPACE_PATH).status_code == 401


def test_workspace_context_matches_auth_me_tenant(client, db, authed_token):
    token, _user = authed_token
    client.cookies.set(CUSTOMER_SESSION_COOKIE, token)
    me = client.get(AUTH_ME_PATH)
    workspace = client.get(WORKSPACE_PATH, headers={"X-Tenant-ID": TENANT_B}, params={"tenant_id": TENANT_B})
    assert me.status_code == 200
    assert workspace.status_code == 200
    assert me.json()["tenant_id"] == TENANT_A
    assert workspace.json()["tenant_id"] == TENANT_A
