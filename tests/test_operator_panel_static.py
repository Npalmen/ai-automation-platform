from pathlib import Path

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import app.core.auth as auth_module
import app.main as main_module
from app.core.settings import get_settings
from app.main import app


def _client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def ops_dist_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    dist_dir = tmp_path / "dist"
    assets_dir = dist_dir / "assets"
    assets_dir.mkdir(parents=True)
    (dist_dir / "index.html").write_text(
        "<!DOCTYPE html><html><body>ops-foundation</body></html>",
        encoding="utf-8",
    )
    (assets_dir / "fake.js").write_text("console.log('fake');", encoding="utf-8")
    monkeypatch.setattr(main_module, "_OPS_DIST_DIR", dist_dir)
    return dist_dir


def test_ops_root_serves_index_html(ops_dist_dir):
    response = _client().get("/ops")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "ops-foundation" in response.text


def test_ops_subpath_serves_spa_fallback(ops_dist_dir):
    response = _client().get("/ops/foundation")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "ops-foundation" in response.text


def test_ops_unknown_subpath_still_serves_index_html(ops_dist_dir):
    response = _client().get("/ops/some/deep/path")

    assert response.status_code == 200
    assert "ops-foundation" in response.text


def test_ops_asset_serves_exact_file(ops_dist_dir):
    response = _client().get("/ops/assets/fake.js")

    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    assert response.text == "console.log('fake');"


def test_ops_missing_asset_returns_404(ops_dist_dir):
    response = _client().get("/ops/assets/does-not-exist.js")

    assert response.status_code == 404


def test_ops_asset_path_traversal_is_blocked(ops_dist_dir):
    (ops_dist_dir / "secret.txt").write_text("secret-content", encoding="utf-8")

    response = _client().get("/ops/assets/..%2fsecret.txt")

    assert response.status_code == 404
    assert "secret-content" not in response.text


def test_ops_returns_503_when_build_missing(monkeypatch: pytest.MonkeyPatch):
    missing_dir = Path("/nonexistent/ops-dist-for-test")
    monkeypatch.setattr(main_module, "_OPS_DIST_DIR", missing_dir)

    response = _client().get("/ops")

    assert response.status_code == 503
    assert "Frontend build not found" in response.json()["detail"]
    assert str(missing_dir) not in response.text


def test_ops_subpath_returns_503_when_build_missing(monkeypatch: pytest.MonkeyPatch):
    missing_dir = Path("/nonexistent/ops-dist-for-test")
    monkeypatch.setattr(main_module, "_OPS_DIST_DIR", missing_dir)

    response = _client().get("/ops/foundation")

    assert response.status_code == 503
    assert "Frontend build not found" in response.json()["detail"]
    assert str(missing_dir) not in response.text


def test_health_route_unchanged():
    response = _client().get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ui_route_unchanged():
    response = _client().get("/ui")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<!DOCTYPE html>" in response.text


def test_root_api_host_unchanged():
    response = _client().get("/", headers={"host": "api.krowolf.se"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["status"] == "ok"


def test_jobs_route_unchanged(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TENANT_API_KEYS", '{"TENANT_1001":"test-tenant-key"}')
    get_settings.cache_clear()
    monkeypatch.setattr(auth_module, "_API_KEY_MAP", None)

    with (
        patch("app.main.JobRepository.list_jobs", return_value=[]),
        patch("app.main.JobRepository.count_jobs", return_value=0),
        patch("app.main.get_db", return_value=MagicMock()),
    ):
        response = _client().get(
            "/jobs",
            headers={
                "X-Tenant-ID": "TENANT_1001",
                "X-API-Key": "test-tenant-key",
            },
        )

    assert response.status_code == 200


def test_ops_login_serves_spa_fallback(ops_dist_dir):
    response = _client().get("/ops/login")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "ops-foundation" in response.text


@pytest.mark.parametrize(
    "path",
    [
        "/ops/needs-help",
        "/ops/customers",
        "/ops/incidents",
        "/ops/usage",
        "/ops/system",
    ],
)
def test_ops_protected_paths_serve_spa_fallback(ops_dist_dir, path: str):
    response = _client().get(path)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "ops-foundation" in response.text


def test_ops_design_reference_serves_spa_fallback(ops_dist_dir):
    response = _client().get("/ops/design-reference")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "ops-foundation" in response.text
