"""Tests for tenant-scoped end-customer read API."""

from __future__ import annotations

import importlib
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.auth import get_verified_tenant
from app.core.settings import get_settings
from app.domain.customer.api_schemas import (
    CustomerCurrentState,
    DuplicateCandidateListViewResponse,
    EndCustomerCardDetailResponse,
    EndCustomerListViewResponse,
    LinkedJobsViewResponse,
    TimelineViewResponse,
)
from app.services.end_customer_read_service import EndCustomerReadService


def _reload_main(enabled: bool):
    os.environ["END_CUSTOMER_READ_API_ENABLED"] = "true" if enabled else "false"
    get_settings.cache_clear()
    import app.main as main_mod

    importlib.reload(main_mod)
    return main_mod.app


@pytest.fixture()
def disabled_client():
    app = _reload_main(False)
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
def tenant_client(enabled_client):
    tenant_id = "TENANT_API"
    enabled_client.app.dependency_overrides[get_verified_tenant] = lambda: tenant_id
    yield enabled_client, tenant_id
    enabled_client.app.dependency_overrides.pop(get_verified_tenant, None)


class TestFeatureFlag:
    def test_disabled_route_missing(self, disabled_client):
        response = disabled_client.get("/end-customers")
        assert response.status_code == 404

    def test_disabled_openapi_has_no_end_customer_paths(self, disabled_client):
        schema = disabled_client.get("/openapi.json").json()
        paths = schema.get("paths", {})
        assert "/end-customers" not in paths
        assert "/end-customer-duplicates" not in paths

    def test_enabled_openapi_has_only_get_paths(self, enabled_client):
        schema = enabled_client.get("/openapi.json").json()
        paths = schema.get("paths", {})
        for path in (
            "/end-customers",
            "/end-customers/search",
            "/end-customers/{customer_id}",
            "/end-customer-duplicates",
        ):
            assert path in paths
            for method in paths[path]:
                assert method.lower() == "get"


class TestTenantApi:
    def test_auth_required_in_production_mode(self, enabled_client):
        with patch("app.core.auth.get_settings") as mock_settings:
            mock_settings.return_value.ENV = "production"
            mock_settings.return_value.TENANT_API_KEYS = '{"TENANT_API":"secret"}'
            response = enabled_client.get("/end-customers")
        assert response.status_code == 401

    def test_list_returns_service_payload(self, tenant_client):
        client, tenant_id = tenant_client
        payload = EndCustomerListViewResponse(items=[], total=0, limit=50, offset=0)
        with patch.object(EndCustomerReadService, "list_customers", return_value=payload):
            response = client.get("/end-customers")
        assert response.status_code == 200
        assert response.json()["total"] == 0

    def test_cross_tenant_customer_returns_404(self, tenant_client):
        client, tenant_id = tenant_client
        with patch.object(EndCustomerReadService, "get_customer_card", return_value=None):
            response = client.get("/end-customers/other-customer-id")
        assert response.status_code == 404
        detail = response.json()["detail"]
        assert detail["code"] == "CUSTOMER_NOT_FOUND"

    def test_detail_returns_card(self, tenant_client):
        client, tenant_id = tenant_client
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        from app.domain.customer.api_schemas import EndCustomerCardView

        from app.domain.customer.enums import CustomerType

        card = EndCustomerCardDetailResponse(
            card=EndCustomerCardView(
                customer_id="cust-1",
                customer_type=CustomerType.PRIVATE,
                display_name="Anna",
                status="active",
                version=1,
                created_at=now,
                updated_at=now,
            ),
            identities=[],
            current_state=CustomerCurrentState(),
        )
        with patch.object(EndCustomerReadService, "get_customer_card", return_value=card):
            response = client.get("/end-customers/cust-1")
        assert response.status_code == 200
        assert response.json()["card"]["customer_id"] == "cust-1"
        assert "tenant_id" not in response.json()["card"]

    def test_timeline_endpoint(self, tenant_client):
        client, tenant_id = tenant_client
        payload = TimelineViewResponse(
            customer_id="cust-1", items=[], total=0, limit=50, offset=0
        )
        with patch.object(EndCustomerReadService, "list_timeline", return_value=payload):
            response = client.get("/end-customers/cust-1/timeline")
        assert response.status_code == 200

    def test_jobs_endpoint_no_raw_payload(self, tenant_client):
        client, tenant_id = tenant_client
        payload = LinkedJobsViewResponse(
            customer_id="cust-1", items=[], total=0, limit=50, offset=0
        )
        with patch.object(EndCustomerReadService, "list_jobs", return_value=payload):
            response = client.get("/end-customers/cust-1/jobs")
        assert response.status_code == 200
        body = response.json()
        assert "input_data" not in body

    def test_duplicates_read_only(self, tenant_client):
        client, tenant_id = tenant_client
        payload = DuplicateCandidateListViewResponse(
            items=[], total=0, limit=50, offset=0
        )
        with patch.object(
            EndCustomerReadService, "list_duplicates", return_value=payload
        ):
            response = client.get("/end-customer-duplicates")
        assert response.status_code == 200

    def test_post_not_allowed(self, tenant_client):
        client, tenant_id = tenant_client
        response = client.post("/end-customers", json={})
        assert response.status_code == 405

    def test_invalid_sort_returns_422(self, tenant_client):
        client, tenant_id = tenant_client
        response = client.get("/end-customers", params={"sort": "bad_sort"})
        assert response.status_code == 422

    def test_search_route_not_captured_as_customer_id(self, tenant_client):
        client, tenant_id = tenant_client
        with patch.object(
            EndCustomerReadService,
            "search",
            return_value=__import__(
                "app.domain.customer.api_schemas",
                fromlist=["EndCustomerSearchResponse"],
            ).EndCustomerSearchResponse(items=[], total=0, limit=50, offset=0),
        ):
            response = client.get("/end-customers/search", params={"q": "anna"})
        assert response.status_code == 200
