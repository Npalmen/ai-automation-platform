from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app


def _client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def customer_dist_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    dist_dir = tmp_path / "dist-customer"
    assets_dir = dist_dir / "assets"
    assets_dir.mkdir(parents=True)
    (dist_dir / "index.html").write_text(
        "<!DOCTYPE html><html><body>customer-workspace</body></html>",
        encoding="utf-8",
    )
    (assets_dir / "app.js").write_text("console.log('customer');", encoding="utf-8")
    monkeypatch.setattr(main_module, "_CUSTOMER_DIST_DIR", dist_dir)
    return dist_dir


def test_customer_root_serves_index_html(customer_dist_dir):
    response = _client().get("/app")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "customer-workspace" in response.text


def test_customer_root_slash_serves_index_html(customer_dist_dir):
    response = _client().get("/app/")

    assert response.status_code == 200
    assert "customer-workspace" in response.text


def test_customer_subpath_serves_spa_fallback(customer_dist_dir):
    response = _client().get("/app/leads")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "customer-workspace" in response.text


def test_customer_work_detail_deep_link_serves_index_html(customer_dist_dir):
    response = _client().get("/app/work/example-id")

    assert response.status_code == 200
    assert "customer-workspace" in response.text


def test_customer_asset_serves_exact_file(customer_dist_dir):
    response = _client().get("/app/assets/app.js")

    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    assert response.text == "console.log('customer');"


def test_customer_missing_asset_returns_404(customer_dist_dir):
    response = _client().get("/app/assets/does-not-exist.js")

    assert response.status_code == 404


def test_customer_asset_path_traversal_is_blocked(customer_dist_dir):
    (customer_dist_dir / "secret.txt").write_text("secret-content", encoding="utf-8")

    response = _client().get("/app/assets/..%2fsecret.txt")

    assert response.status_code == 404
    assert "secret-content" not in response.text


def test_customer_returns_503_when_build_missing(monkeypatch: pytest.MonkeyPatch):
    missing_dir = Path("/nonexistent/customer-dist-for-test")
    monkeypatch.setattr(main_module, "_CUSTOMER_DIST_DIR", missing_dir)

    response = _client().get("/app")

    assert response.status_code == 503
    assert "Customer frontend build not found" in response.json()["detail"]
    assert str(missing_dir) not in response.text


def test_customer_subpath_returns_503_when_build_missing(monkeypatch: pytest.MonkeyPatch):
    missing_dir = Path("/nonexistent/customer-dist-for-test")
    monkeypatch.setattr(main_module, "_CUSTOMER_DIST_DIR", missing_dir)

    response = _client().get("/app/leads")

    assert response.status_code == 503
    assert "Customer frontend build not found" in response.json()["detail"]


def test_customer_missing_asset_does_not_fallback_to_index_html(customer_dist_dir):
    response = _client().get("/app/assets/missing.js")

    assert response.status_code == 404
    assert "customer-workspace" not in response.text
