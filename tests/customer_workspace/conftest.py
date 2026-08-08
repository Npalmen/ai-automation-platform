"""Shared fixtures for customer workspace API tests."""

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
from app.core.customer_session import CUSTOMER_SESSION_COOKIE
from app.main import app
from app.repositories.postgres.action_execution_models import ActionExecutionRecord
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.customer_workspace_session_models import CustomerWorkspaceSessionRecord
from app.repositories.postgres.customer_workspace_user_models import CustomerWorkspaceUserRecord
from app.repositories.postgres.customer_workspace_user_repository import CustomerWorkspaceUserRepository
from app.repositories.postgres.database import Base
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.tenant_config_models import TenantConfigRecord

STRONG_PASSWORD = "fifteen-char-pass!"
TENANT_A = "TENANT_1001"
TENANT_B = "TENANT_2002"


def _test_settings():
    return SimpleNamespace(
        SESSION_SECRET_KEY="test-secret",
        ALLOWED_ORIGINS="",
        ENV="test",
        CUSTOMER_SESSION_MAX_AGE_SECONDS=28800,
    )


@pytest.fixture(autouse=True)
def _patch_needs_help():
    with patch("app.customer_workspace.adapters.overview.needs_help_job_ids", return_value=set()):
        with patch("app.customer_workspace.adapters.work_items.needs_help_job_ids", return_value=set()):
            yield


@pytest.fixture(autouse=True)
def _patch_health():
    with patch(
        "app.health.integration_health.get_integration_health",
        return_value={
            "overall_status": "healthy",
            "systems": {"gmail": {"status": "healthy"}},
        },
    ):
        yield


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [
        TenantConfigRecord.__table__,
        CustomerWorkspaceUserRecord.__table__,
        CustomerWorkspaceSessionRecord.__table__,
        JobRecord.__table__,
        ApprovalRequestRecord.__table__,
        ActionExecutionRecord.__table__,
    ]
    Base.metadata.create_all(bind=engine, tables=tables)
    session = sessionmaker(bind=engine)()
    now = datetime.now(timezone.utc)
    for tenant_id, name in ((TENANT_A, "Exempel AB"), (TENANT_B, "Annan AB")):
        session.add(
            TenantConfigRecord(
                tenant_id=tenant_id,
                name=name,
                status="active",
                lifecycle_status="active",
                settings={
                    "account": {
                        "company_name": name,
                        "contact_name": "Kontakt",
                        "contact_email": "kontakt@example.com",
                        "support_email": "support@example.com",
                        "language": "sv",
                        "region": "SE",
                    }
                },
                created_at=now,
                updated_at=now,
            )
        )
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
        patch("app.customer_workspace.read_sources.get_settings", return_value=settings),
    ):
        app.dependency_overrides[get_db] = lambda: db
        with TestClient(app, raise_server_exceptions=False) as test_client:
            yield test_client
        app.dependency_overrides.clear()


def seed_user(db, *, tenant_id=TENANT_A, email="viewer@example.com"):
    return CustomerWorkspaceUserRepository.create_user(
        db,
        tenant_id=tenant_id,
        email=email,
        password_hash=hash_password(STRONG_PASSWORD),
        display_name="Viewer",
    )


def login(client, email="viewer@example.com", password=STRONG_PASSWORD):
    return client.post(
        "/auth/customer/login",
        json={"email": email, "password": password},
        headers={"Origin": "http://testserver"},
    )


@pytest.fixture()
def authed_client(client, db):
    seed_user(db)
    response = login(client)
    assert response.status_code == 200, response.text
    client.cookies.set(CUSTOMER_SESSION_COOKIE, response.cookies[CUSTOMER_SESSION_COOKIE])
    return client


def seed_job(
    db,
    *,
    job_id: str,
    tenant_id: str = TENANT_A,
    job_type: str = "lead",
    status: str = "pending",
    subject: str = "Test subject",
    customer_name: str = "Erik Johansson",
    customer_email: str = "erik@example.com",
):
    now = datetime.now(timezone.utc)
    db.add(
        JobRecord(
            job_id=job_id,
            tenant_id=tenant_id,
            job_type=job_type,
            status=status,
            input_data={
                "subject": subject,
                "sender": {"name": customer_name, "email": customer_email},
                "received_at": now.isoformat(),
            },
            result={},
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()


def seed_approval(db, *, approval_id: str, job_id: str, tenant_id: str = TENANT_A):
    now = datetime.now(timezone.utc)
    db.add(
        ApprovalRequestRecord(
            approval_id=approval_id,
            tenant_id=tenant_id,
            job_id=job_id,
            job_type="lead",
            state="pending",
            channel="email",
            title="Godkänn utskick",
            summary="Kort sammanfattning",
            requested_at=now,
            request_payload={"secret": True},
            delivery_payload={"secret": True},
            next_on_approve="step",
            next_on_reject="step",
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()
