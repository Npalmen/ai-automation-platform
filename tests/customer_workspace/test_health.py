"""Tests for GET /workspace/v1/health."""

from __future__ import annotations

SECRET_KEYS = {
    "password",
    "token",
    "refresh_token",
    "access_token",
    "api_key",
    "credential",
}


def test_health_requires_session(client):
    assert client.get("/workspace/v1/health").status_code == 401


def test_health_safe_response(authed_client):
    response = authed_client.get("/workspace/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert "overall_status" in body
    assert "message" in body
    assert "systems" in body
    lowered = response.text.lower()
    for key in SECRET_KEYS:
        assert key not in lowered
