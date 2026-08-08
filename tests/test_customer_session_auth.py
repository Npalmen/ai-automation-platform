"""Tests for customer workspace session authentication (connected-b)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.core.admin_session import hash_password
from app.core.customer_session import CUSTOMER_SESSION_COOKIE, hash_session_token
from app.core.rate_limit import reset_rate_limits_for_tests
from app.main import app
from app.repositories.postgres.customer_workspace_session_models import CustomerWorkspaceSessionRecord
from app.repositories.postgres.customer_workspace_user_models import CustomerWorkspaceUserRecord
from app.repositories.postgres.customer_workspace_user_repository import (
    USER_STATUS_ACTIVE,
    USER_STATUS_DISABLED,
    CustomerWorkspaceUserRepository,
    normalize_email,
)
from app.repositories.postgres.database import Base
from app.repositories.postgres.tenant_config_models import TenantConfigRecord

STRONG_PASSWORD = "fifteen-char-pass!"
BLOCKED_PASSWORD = "passwordpassword"  # 16 chars, blocklisted


def _test_settings():
    return SimpleNamespace(
        SESSION_SECRET_KEY="",
        ALLOWED_ORIGINS="",
        ENV="test",
        CUSTOMER_SESSION_MAX_AGE_SECONDS=28800,
    )


@pytest.fixture(autouse=True)
def _reset_limits():
    reset_rate_limits_for_tests()
    yield
    reset_rate_limits_for_tests()


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[
            TenantConfigRecord.__table__,
            CustomerWorkspaceUserRecord.__table__,
            CustomerWorkspaceSessionRecord.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()
    tenant = TenantConfigRecord(
        tenant_id="TENANT_1001",
        name="Exempel AB",
        status="active",
        lifecycle_status="active",
        settings={"account": {"company_name": "Exempel El AB"}},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.add(tenant)
    session.commit()
    yield session
    session.close()


@pytest.fixture()
def client(db):
    settings = _test_settings()
    with (
        patch("app.main.Base.metadata.create_all"),
        patch("app.repositories.postgres.schema_migrations.ensure_runtime_schema"),
        patch("app.repositories.postgres.schema_migrations.provision_tenant_defaults"),
        patch("app.workflows.decision_trace_readiness.verify_decision_trace_readiness"),
        patch("app.core.admin_session.get_settings", return_value=settings),
        patch("app.core.customer_session.get_settings", return_value=settings),
    ):
        app.dependency_overrides[get_db] = lambda: db
        with TestClient(app, raise_server_exceptions=False) as test_client:
            yield test_client
        app.dependency_overrides.clear()


def _seed_user(db, *, email="viewer@example.com", status=USER_STATUS_ACTIVE, tenant_id="TENANT_1001"):
    return CustomerWorkspaceUserRepository.create_user(
        db,
        tenant_id=tenant_id,
        email=email,
        password_hash=hash_password(STRONG_PASSWORD),
        display_name="Viewer",
    )


def _login(client, email="viewer@example.com", password=STRONG_PASSWORD):
    return client.post(
        "/auth/customer/login",
        json={"email": email, "password": password},
        headers={"Origin": "http://testserver"},
    )


class TestEmailNormalization:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("  Viewer@Example.COM ", "viewer@example.com"),
            ("A@b.co", "a@b.co"),
        ],
    )
    def test_normalize_email(self, raw, expected):
        assert normalize_email(raw) == expected


class TestPasswordPolicy:
    def test_rejects_short_password(self):
        from app.customer_auth.password_policy import validate_customer_password, CustomerPasswordPolicyError

        with pytest.raises(CustomerPasswordPolicyError):
            validate_customer_password("short")

    def test_allows_15_char_passphrase_with_spaces(self):
        from app.customer_auth.password_policy import validate_customer_password

        validate_customer_password("a" * 14 + " ")  # 15 code points with space

    def test_supports_64_char_password(self):
        from app.customer_auth.password_policy import validate_customer_password

        validate_customer_password("x" * 64)

    def test_rejects_blocklisted_password(self):
        from app.customer_auth.password_policy import validate_customer_password, CustomerPasswordPolicyError

        with pytest.raises(CustomerPasswordPolicyError):
            validate_customer_password(BLOCKED_PASSWORD)


class TestLoginFlow:
    def test_login_success_sets_httponly_cookie(self, client, db):
        _seed_user(db)
        response = _login(client)
        assert response.status_code == 200
        cookie = response.cookies.get(CUSTOMER_SESSION_COOKIE)
        assert cookie
        set_cookie = response.headers.get("set-cookie", "")
        assert "httponly" in set_cookie.lower()
        assert "samesite=strict" in set_cookie.lower().replace(" ", "")

    def test_db_stores_only_token_hash(self, client, db):
        user = _seed_user(db)
        response = _login(client)
        raw = response.cookies[CUSTOMER_SESSION_COOKIE]
        session = db.query(CustomerWorkspaceSessionRecord).filter_by(user_id=user.id).one()
        assert session.token_hash == hash_session_token(raw)
        assert raw not in response.text

    def test_invalid_credentials_generic_401(self, client, db):
        _seed_user(db)
        assert _login(client, password="wrong-password-xx").status_code == 401
        assert _login(client, email="missing@example.com").status_code == 401

    def test_disabled_user_denied(self, client, db):
        user = _seed_user(db)
        CustomerWorkspaceUserRepository.set_status(db, user, USER_STATUS_DISABLED)
        response = _login(client)
        assert response.status_code == 401
        assert response.json()["detail"] == "Ogiltig e-postadress eller lösenord."

    def test_inactive_tenant_denied(self, client, db):
        _seed_user(db)
        tenant = db.query(TenantConfigRecord).filter_by(tenant_id="TENANT_1001").one()
        tenant.status = "inactive"
        db.commit()
        response = _login(client)
        assert response.status_code == 403
        assert response.json()["detail"] == "Tenant is inactive."

    def test_missing_tenant_record_denied(self, client, db):
        user = _seed_user(db)
        user.tenant_id = "MISSING_TENANT"
        db.commit()
        response = _login(client)
        assert response.status_code == 403
        assert response.json()["detail"] == "Tenant is not available."

    def test_tenant_repository_exception_fail_closed(self, client, db):
        _seed_user(db)
        with patch(
            "app.customer_auth.tenant_access.TenantConfigRepository.get",
            side_effect=RuntimeError("db down"),
        ):
            response = _login(client)
            assert response.status_code == 403
            assert response.json()["detail"] == "Tenant is not available."


class TestMeAndLogout:
    def test_me_returns_company_name_without_secrets(self, client, db):
        _seed_user(db)
        _login(client)
        me = client.get("/auth/customer/me")
        assert me.status_code == 200
        body = me.json()
        assert body["company_name"] == "Exempel El AB"
        assert "password" not in body
        assert "token" not in body

    def test_missing_cookie_401(self, client):
        assert client.get("/auth/customer/me").status_code == 401

    def test_logout_revokes_session(self, client, db):
        _seed_user(db)
        login = _login(client)
        token = login.cookies[CUSTOMER_SESSION_COOKIE]
        client.cookies.set(CUSTOMER_SESSION_COOKIE, token)
        assert client.post("/auth/customer/logout", headers={"Origin": "http://testserver"}).status_code == 200
        client.cookies.set(CUSTOMER_SESSION_COOKIE, token)
        assert client.get("/auth/customer/me").status_code == 401

    def test_expired_session_denied(self, client, db):
        user = _seed_user(db)
        login = _login(client)
        session = db.query(CustomerWorkspaceSessionRecord).filter_by(user_id=user.id).one()
        session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
        client.cookies.set(CUSTOMER_SESSION_COOKIE, login.cookies[CUSTOMER_SESSION_COOKIE])
        assert client.get("/auth/customer/me").status_code == 401

    def test_session_tenant_mismatch_denied(self, client, db):
        user = _seed_user(db)
        login = _login(client)
        session = db.query(CustomerWorkspaceSessionRecord).filter_by(user_id=user.id).one()
        session.tenant_id = "OTHER_TENANT"
        db.commit()
        client.cookies.set(CUSTOMER_SESSION_COOKIE, login.cookies[CUSTOMER_SESSION_COOKIE])
        assert client.get("/auth/customer/me").status_code == 401


class TestSecurityBoundaries:
    def test_x_tenant_id_ignored_on_login(self, client, db):
        _seed_user(db)
        response = _login(client)
        assert response.status_code == 200
        assert response.json()["tenant_id"] == "TENANT_1001"

    def test_workspace_v1_routes_are_get_only(self, client):
        schema = client.get("/openapi.json").json()
        workspace_paths = {
            path: methods
            for path, methods in schema.get("paths", {}).items()
            if path.startswith("/workspace/v1")
        }
        assert workspace_paths, "expected connected workspace routes"
        for path, methods in workspace_paths.items():
            http_methods = {m.lower() for m in methods if m.lower() not in {"parameters"}}
            assert http_methods == {"get"}, f"{path} must be GET-only, got {http_methods}"

    def test_wrong_origin_blocked(self, client, db):
        _seed_user(db)
        response = client.post(
            "/auth/customer/login",
            json={"email": "viewer@example.com", "password": STRONG_PASSWORD},
            headers={"Origin": "http://evil.example"},
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "Ogiltig origin."

    def test_dual_rate_limit_blocks_bruteforce(self, client, db):
        _seed_user(db)
        for _ in range(5):
            _login(client, password="wrong-password-xx")
        assert _login(client, password="wrong-password-xx").status_code == 429


class TestSessionDependency:
    def test_get_customer_session_tenant_returns_tenant(self, db):
        from app.core.customer_session import get_customer_session_tenant
        from app.core.customer_session_models import CustomerSessionContext

        ctx: CustomerSessionContext = {
            "user_id": "u1",
            "tenant_id": "TENANT_1001",
            "email": "a@b.co",
            "display_name": "A",
            "role": "customer_viewer",
        }
        assert get_customer_session_tenant(ctx) == "TENANT_1001"
