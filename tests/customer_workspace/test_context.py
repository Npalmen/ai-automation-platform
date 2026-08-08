"""Tests for GET /workspace/v1/context."""

from __future__ import annotations

from tests.customer_workspace.conftest import TENANT_A


FORBIDDEN_KEYS = {
    "demo_mode",
    "auto_actions",
    "allowed_integrations",
    "api_key",
    "password",
    "token",
}


def test_context_requires_session(client):
    response = client.get("/workspace/v1/context")
    assert response.status_code == 401


def test_context_returns_tenant_metadata(authed_client):
    response = authed_client.get("/workspace/v1/context")
    assert response.status_code == 200
    body = response.json()
    assert body["tenant_id"] == TENANT_A
    assert body["company_name"] == "Exempel AB"
    assert body["workspace_mode"] == "connected"
    assert body["feature_flags"]["connected_api"] is True
    assert body["feature_flags"]["customer_workspace_writes"] is False
    for key in FORBIDDEN_KEYS:
        assert key not in body


def test_context_rejects_api_key_only(client, db):
    from tests.customer_workspace.conftest import seed_user

    seed_user(db)
    response = client.get(
        "/workspace/v1/context",
        headers={"X-API-Key": "secret", "X-Tenant-ID": TENANT_A},
    )
    assert response.status_code == 401


def test_context_ignores_tenant_header(authed_client):
    response = authed_client.get(
        "/workspace/v1/context",
        headers={"X-Tenant-ID": "OTHER_TENANT"},
    )
    assert response.status_code == 200
    assert response.json()["tenant_id"] == TENANT_A
