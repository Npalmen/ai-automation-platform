"""Secret scan and sanitization tests for customer workspace API."""

from __future__ import annotations

import pytest

pytest_plugins = ["tests.customer_workspace.conftest"]

from unittest.mock import patch

import pytest
from sqlalchemy import event

from tests.customer_workspace.conftest import seed_user, login
from tests.customer_workspace.security_helpers import (
    CROSS_TENANT_SENTINEL_B,
    SECRET_SENTINELS,
    TENANT_A,
    WorkspaceSeedContext,
    assert_error_body_sanitized,
    assert_json_free_of,
    assert_partial_errors_sanitized,
    get_workspace,
    is_write_sql,
    seed_tenant_a_canary_bundle,
    seed_tenant_b_canary_bundle,
    workspace_endpoint_specs,
    workspace_openapi_methods,
)
from app.core.customer_session import CUSTOMER_SESSION_COOKIE


@pytest.fixture()
def ctx():
    return WorkspaceSeedContext()


@pytest.fixture()
def authed_a(client, db, ctx):
    seed_tenant_a_canary_bundle(db, ctx)
    seed_tenant_b_canary_bundle(db, ctx)
    seed_user(db, tenant_id=TENANT_A, email="viewer-a@example.com")
    response = login(client, email="viewer-a@example.com")
    assert response.status_code == 200
    client.cookies.set(CUSTOMER_SESSION_COOKIE, response.cookies[CUSTOMER_SESSION_COOKIE])
    return client


@pytest.mark.parametrize("spec", workspace_endpoint_specs(), ids=lambda spec: spec.name)
def test_workspace_responses_have_no_secrets(authed_a, ctx, spec):
    response = get_workspace(authed_a, spec, ctx)
    assert response.status_code == 200
    assert_json_free_of(
        response.json(),
        forbidden_values=list(SECRET_SENTINELS.values()) + [CROSS_TENANT_SENTINEL_B],
    )


def test_workspace_openapi_is_get_only(client):
    methods_by_path = workspace_openapi_methods(client)
    assert methods_by_path
    for path, methods in methods_by_path.items():
        assert methods <= {"get", "head"}, f"{path} exposes {methods}"


def test_partial_errors_are_sanitized(authed_a, ctx, monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("triage down with sqlalchemy SELECT * FROM jobs")

    monkeypatch.setattr("app.customer_workspace.adapters.overview.needs_help_job_ids", boom)
    response = authed_a.get("/workspace/v1/overview")
    assert response.status_code == 200
    assert_partial_errors_sanitized(response.json())


def test_full_dependency_failure_is_sanitized(authed_a, monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("db exploded with sqlalchemy")

    monkeypatch.setattr("app.customer_workspace.adapters.account.build_account_context", boom)
    response = authed_a.get("/workspace/v1/context")
    assert response.status_code == 500
    assert_error_body_sanitized(response)


def test_workspace_get_does_not_execute_business_writes(db, client, ctx):
    seed_tenant_a_canary_bundle(db, ctx)
    seed_user(db, tenant_id=TENANT_A, email="viewer-a@example.com")
    response = login(client, email="viewer-a@example.com")
    client.cookies.set(CUSTOMER_SESSION_COOKIE, response.cookies[CUSTOMER_SESSION_COOKIE])

    writes: list[str] = []

    def _capture(conn, cursor, statement, parameters, context, executemany):
        if is_write_sql(statement):
            writes.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", _capture)
    try:
        for spec in workspace_endpoint_specs():
            assert get_workspace(client, spec, ctx).status_code == 200
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", _capture)

    business_writes = [
        sql
        for sql in writes
        if any(table in sql.lower() for table in ("jobs", "approval_requests", "action_executions", "tenant_configs"))
    ]
    assert business_writes == []


def test_workspace_health_has_no_provider_http_side_effects(authed_a, ctx, monkeypatch):
    calls: list[str] = []

    def _track_integration_health(*_args, **_kwargs):
        calls.append("integration_health")
        return {"overall_status": "healthy", "systems": {"gmail": {"status": "healthy"}}}

    monkeypatch.setattr(
        "app.health.integration_health.get_integration_health",
        _track_integration_health,
    )
    response = authed_a.get("/workspace/v1/health")
    assert response.status_code == 200
    assert calls == ["integration_health"]
