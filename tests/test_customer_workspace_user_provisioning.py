"""Tests for customer workspace user provisioning (connected-b)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.core.admin_session import hash_password
from app.main import app
from app.repositories.postgres.customer_workspace_session_models import CustomerWorkspaceSessionRecord
from app.repositories.postgres.customer_workspace_user_models import CustomerWorkspaceUserRecord
from app.repositories.postgres.customer_workspace_user_repository import (
    USER_STATUS_ACTIVE,
    USER_STATUS_DISABLED,
    CustomerWorkspaceUserRepository,
)
from app.repositories.postgres.database import Base
from app.repositories.postgres.tenant_config_models import TenantConfigRecord

STRONG_PASSWORD = "fifteen-char-pass!"
ADMIN_HEADERS = {"X-Admin-API-Key": "test-admin-key"}


def _settings(role: str = "admin"):
    return SimpleNamespace(
        ADMIN_API_KEY="test-admin-key",
        ADMIN_API_KEYS="",
        ADMIN_ROLE=role,
        SESSION_SECRET_KEY="",
        ALLOWED_ORIGINS="",
        ENV="test",
        CUSTOMER_SESSION_MAX_AGE_SECONDS=28800,
    )


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
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.add(tenant)
    session.commit()
    yield session
    session.close()


@pytest.fixture()
def client(db):
    with (
        patch("app.main.Base.metadata.create_all"),
        patch("app.repositories.postgres.schema_migrations.ensure_runtime_schema"),
        patch("app.repositories.postgres.schema_migrations.provision_tenant_defaults"),
        patch("app.workflows.decision_trace_readiness.verify_decision_trace_readiness"),
        patch("app.core.admin_auth.get_settings", return_value=_settings("admin")),
        patch("app.core.admin_session.get_settings", return_value=_settings("admin")),
        patch("app.core.customer_session.get_settings", return_value=_settings("admin")),
    ):
        app.dependency_overrides[get_db] = lambda: db
        with TestClient(app, raise_server_exceptions=False) as test_client:
            yield test_client
        app.dependency_overrides.clear()


def _create_user(client, email="viewer@example.com", password=STRONG_PASSWORD):
    return client.post(
        "/admin/tenants/TENANT_1001/workspace-users",
        json={"email": email, "password": password, "display_name": "Viewer"},
        headers=ADMIN_HEADERS,
    )


class TestProvisioningRoles:
    @pytest.mark.parametrize(
        "role,expected_status",
        [
            ("read_only", 403),
            ("operations", 403),
            ("admin", 200),
            ("super_admin", 200),
        ],
    )
    def test_role_gate(self, client, role, expected_status):
        role_settings = _settings(role)
        with (
            patch("app.core.admin_auth.get_settings", return_value=role_settings),
            patch("app.core.admin_session.get_settings", return_value=role_settings),
            patch("app.core.customer_session.get_settings", return_value=role_settings),
        ):
            response = _create_user(client)
            assert response.status_code == expected_status
            if expected_status == 403:
                assert response.json()["detail"] == "Du saknar behörighet för denna åtgärd."


class TestProvisioningRules:
    def test_create_user_hashes_password(self, client, db):
        response = _create_user(client)
        assert response.status_code == 200
        body = response.json()
        assert "password" not in body
        user = db.query(CustomerWorkspaceUserRecord).one()
        assert user.password_hash != STRONG_PASSWORD
        assert user.role == "customer_viewer"

    def test_duplicate_active_email_blocked(self, client):
        assert _create_user(client, email="dup@example.com").status_code == 200
        assert _create_user(client, email="dup@example.com").status_code == 409

    def test_disabled_email_can_be_reused_until_reenabled(self, client, db):
        first = _create_user(client, email="reuse@example.com").json()["user_id"]
        client.patch(
            f"/admin/tenants/TENANT_1001/workspace-users/{first}",
            json={"status": "disabled"},
            headers=ADMIN_HEADERS,
        )
        assert _create_user(client, email="reuse@example.com").status_code == 200

    def test_reenable_conflicts_with_other_active_email(self, client, db):
        active = _create_user(client, email="active@example.com").json()["user_id"]
        disabled = _create_user(client, email="disabled@example.com").json()["user_id"]
        client.patch(
            f"/admin/tenants/TENANT_1001/workspace-users/{disabled}",
            json={"status": "disabled"},
            headers=ADMIN_HEADERS,
        )
        _create_user(client, email="disabled@example.com")
        response = client.patch(
            f"/admin/tenants/TENANT_1001/workspace-users/{disabled}",
            json={"status": "active"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 409

    def test_invalid_tenant_404(self, client):
        response = client.post(
            "/admin/tenants/UNKNOWN/workspace-users",
            json={"email": "a@b.co", "password": STRONG_PASSWORD, "display_name": "V"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 404

    def test_password_policy_enforced_on_create(self, client):
        response = client.post(
            "/admin/tenants/TENANT_1001/workspace-users",
            json={"email": "short@example.com", "password": "short", "display_name": "V"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 422

    def test_disable_revokes_sessions(self, client, db):
        created = _create_user(client).json()
        login = client.post(
            "/auth/customer/login",
            json={"email": "viewer@example.com", "password": STRONG_PASSWORD},
            headers={"Origin": "http://testserver"},
        )
        assert login.status_code == 200
        client.patch(
            f"/admin/tenants/TENANT_1001/workspace-users/{created['user_id']}",
            json={"status": "disabled"},
            headers=ADMIN_HEADERS,
        )
        client.cookies.set("customer_session", login.cookies["customer_session"])
        assert client.get("/auth/customer/me").status_code == 401

    def test_password_reset_revokes_sessions(self, client, db):
        created = _create_user(client).json()
        login = client.post(
            "/auth/customer/login",
            json={"email": "viewer@example.com", "password": STRONG_PASSWORD},
            headers={"Origin": "http://testserver"},
        )
        new_password = "another-pass-phrase"
        response = client.post(
            f"/admin/tenants/TENANT_1001/workspace-users/{created['user_id']}/reset-password",
            json={"password": new_password},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        client.cookies.set("customer_session", login.cookies["customer_session"])
        assert client.get("/auth/customer/me").status_code == 401
        assert (
            client.post(
                "/auth/customer/login",
                json={"email": "viewer@example.com", "password": new_password},
                headers={"Origin": "http://testserver"},
            ).status_code
            == 200
        )
