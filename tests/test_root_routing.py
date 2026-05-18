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


def test_root_returns_ui_for_app_host():
    response = _client().get("/", headers={"host": "app.krowolf.se"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<!DOCTYPE html>" in response.text
    assert "<title>AI Automation Platform</title>" in response.text


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
