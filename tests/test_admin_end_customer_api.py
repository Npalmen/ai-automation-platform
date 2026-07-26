"""Tests for operator-scoped end-customer read API."""

from __future__ import annotations

import importlib
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.settings import get_settings
from app.domain.customer.api_schemas import EndCustomerListViewResponse
from app.services.end_customer_read_service import EndCustomerReadService


def _reload_main(enabled: bool):
    os.environ["END_CUSTOMER_READ_API_ENABLED"] = "true" if enabled else "false"
    get_settings.cache_clear()
    import app.main as main_mod

    importlib.reload(main_mod)
    return main_mod.app


@pytest.fixture()
def enabled_client():
    app = _reload_main(True)
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
    return {"X-Admin-API-Key": key, "Origin": "http://testserver"}


class TestOperatorApi:
    def test_unauthenticated_denied(self, enabled_client):
        response = enabled_client.get("/admin/tenants/TENANT_X/end-customers")
        assert response.status_code == 401

    def test_read_only_can_list(self, enabled_client, admin_headers):
        payload = EndCustomerListViewResponse(items=[], total=0, limit=50, offset=0)
        with (
            patch.dict(os.environ, {"ADMIN_ROLE": "read_only"}, clear=False),
            patch(
                "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
                return_value=object(),
            ),
            patch.object(EndCustomerReadService, "list_customers", return_value=payload),
        ):
            get_settings.cache_clear()
            response = enabled_client.get(
                "/admin/tenants/TENANT_X/end-customers",
                headers=admin_headers,
            )
        assert response.status_code == 200

    def test_unknown_tenant_404(self, enabled_client, admin_headers):
        with patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
            return_value=None,
        ):
            response = enabled_client.get(
                "/admin/tenants/T_MISSING/end-customers",
                headers=admin_headers,
            )
        assert response.status_code == 404

    def test_cross_tenant_customer_404(self, enabled_client, admin_headers):
        with (
            patch(
                "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
                return_value=object(),
            ),
            patch.object(EndCustomerReadService, "get_customer_card", return_value=None),
        ):
            response = enabled_client.get(
                "/admin/tenants/TENANT_A/end-customers/cust-other",
                headers=admin_headers,
            )
        assert response.status_code == 404

    def test_router_does_not_import_main(self):
        import app.api.routes.end_customers as routes_mod

        source = open(routes_mod.__file__, encoding="utf-8").read()
        assert "from app.main" not in source
        assert "import app.main" not in source

    def test_no_write_routes(self, enabled_client, admin_headers):
        response = enabled_client.post(
            "/admin/tenants/TENANT_A/end-customers",
            headers=admin_headers,
            json={},
        )
        assert response.status_code == 405
