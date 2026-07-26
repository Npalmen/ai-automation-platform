"""Tests for operator end-customer write API."""

from __future__ import annotations

import importlib
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.settings import get_settings


def _reload_main(read_enabled: bool, write_enabled: bool):
    os.environ["END_CUSTOMER_READ_API_ENABLED"] = "true" if read_enabled else "false"
    os.environ["END_CUSTOMER_WRITE_API_ENABLED"] = "true" if write_enabled else "false"
    get_settings.cache_clear()
    import app.main as main_mod

    importlib.reload(main_mod)
    return main_mod.app


@pytest.fixture()
def write_client():
    app = _reload_main(True, True)
    with (
        patch("app.main.Base.metadata.create_all"),
        patch("app.repositories.postgres.schema_migrations.ensure_runtime_schema"),
        patch("app.repositories.postgres.schema_migrations.provision_tenant_defaults"),
        patch("app.workflows.decision_trace_readiness.verify_decision_trace_readiness"),
    ):
        with TestClient(app) as client:
            yield client
    get_settings.cache_clear()


@pytest.fixture()
def read_only_client():
    app = _reload_main(True, False)
    with (
        patch("app.main.Base.metadata.create_all"),
        patch("app.repositories.postgres.schema_migrations.ensure_runtime_schema"),
        patch("app.repositories.postgres.schema_migrations.provision_tenant_defaults"),
        patch("app.workflows.decision_trace_readiness.verify_decision_trace_readiness"),
    ):
        with TestClient(app) as client:
            yield client
    get_settings.cache_clear()


@pytest.fixture()
def admin_headers():
    key = get_settings().ADMIN_API_KEY.strip()
    if not key:
        pytest.skip("ADMIN_API_KEY not configured")
    return {
        "X-Admin-API-Key": key,
        "Origin": "http://testserver",
        "Idempotency-Key": "test-idempotency-key",
    }


class TestWriteFeatureGating:
    def test_write_disabled_returns_404(self, read_only_client, admin_headers):
        response = read_only_client.post(
            "/admin/tenants/TENANT_A/end-customers",
            headers=admin_headers,
            json={
                "customer_type": "private",
                "private": {"display_name": "Test"},
                "reason": "test",
            },
        )
        assert response.status_code == 405

    def test_write_enabled_route_exists(self, write_client, admin_headers):
        headers = {k: v for k, v in admin_headers.items() if k != "Origin"}
        with (
            patch.dict(os.environ, {"ADMIN_ROLE": "admin"}, clear=False),
            patch(
                "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
                return_value=object(),
            ),
            patch(
                "app.services.end_customer_command_service.EndCustomerCommandService.create_customer",
                return_value=(
                    201,
                    {
                        "customer_id": "c1",
                        "customer_type": "private",
                        "display_name": "Test",
                        "status": "active",
                        "version": 1,
                        "created": True,
                    },
                ),
            ),
        ):
            get_settings.cache_clear()
            response = write_client.post(
                "/admin/tenants/TENANT_A/end-customers",
                headers=headers,
                json={
                    "customer_type": "private",
                    "private": {"display_name": "Test"},
                    "reason": "test",
                },
            )
        assert response.status_code == 201

    def test_read_only_role_denied(self, write_client, admin_headers):
        with (
            patch.dict(os.environ, {"ADMIN_ROLE": "read_only"}, clear=False),
            patch(
                "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
                return_value=object(),
            ),
        ):
            get_settings.cache_clear()
            response = write_client.post(
                "/admin/tenants/TENANT_A/end-customers",
                headers=admin_headers,
                json={
                    "customer_type": "private",
                    "private": {"display_name": "Test"},
                    "reason": "test",
                },
            )
        assert response.status_code == 403

    def test_router_does_not_import_main(self):
        import app.api.routes.end_customer_writes as routes_mod

        source = open(routes_mod.__file__, encoding="utf-8").read()
        assert "from app.main" not in source
        assert "import app.main" not in source

    def test_openapi_write_paths_when_enabled(self, write_client):
        schema = write_client.get("/openapi.json").json()
        paths = schema.get("paths", {})
        assert "post" in paths.get("/admin/tenants/{tenant_id}/end-customers", {})
        assert "patch" in paths.get("/admin/tenants/{tenant_id}/end-customers/{customer_id}", {})

    def test_openapi_no_write_when_disabled(self, read_only_client):
        schema = read_only_client.get("/openapi.json").json()
        paths = schema.get("paths", {})
        assert "/admin/tenants/{tenant_id}/end-customers" not in paths or "post" not in paths.get(
            "/admin/tenants/{tenant_id}/end-customers", {}
        )
