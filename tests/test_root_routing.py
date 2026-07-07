from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import _openapi_urls_for, app


def _client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def test_root_returns_health_for_api_host():
    response = _client().get("/", headers={"host": "api.krowolf.se"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["status"] == "ok"


def test_root_returns_health_without_production_app_host():
    response = _client().get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["status"] == "ok"


def test_health_returns_public_health_payload():
    response = _client().get("/health")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert body["status"] == "ok"
    assert body["app_name"]
    assert body["env"]


def test_health_response_does_not_expose_secrets():
    response = _client().get("/health")

    assert response.status_code == 200
    body = response.json()
    forbidden_keys = {
        "admin_api_key",
        "admin_api_keys",
        "tenant_api_keys",
        "database_url",
        "session_secret_key",
        "google_mail_access_token",
        "google_oauth_refresh_token",
        "google_oauth_client_secret",
        "monday_api_key",
        "fortnox_access_token",
        "fortnox_client_secret",
    }
    assert forbidden_keys.isdisjoint({key.lower() for key in body})


def test_root_returns_ui_for_app_host():
    response = _client().get("/", headers={"host": "app.krowolf.se"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<!DOCTYPE html>" in response.text
    assert "<title>Internal Operator Console</title>" in response.text


def test_root_returns_ui_for_admin_host_with_port():
    response = _client().get("/", headers={"host": "admin.krowolf.se:443"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<!DOCTYPE html>" in response.text


def test_ui_route_still_returns_html():
    response = _client().get("/ui")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<!DOCTYPE html>" in response.text


def test_production_docs_remain_disabled():
    assert _openapi_urls_for(SimpleNamespace(ENV="production")) == {
        "docs_url": None,
        "redoc_url": None,
        "openapi_url": None,
    }
