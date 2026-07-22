"""API-level smoke gates mirroring onboarding browser scenarios."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.settings import get_settings
from app.main import app


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def admin_headers():
    key = get_settings().ADMIN_API_KEY.strip()
    if not key:
        pytest.skip("ADMIN_API_KEY not configured")
    return {
        "X-Admin-API-Key": key,
        "Origin": "http://testserver",
    }


class TestReadOnlyWriteBlock:
    def test_read_only_cannot_patch_onboarding_identity(self, client, admin_headers):
        with patch.dict(os.environ, {"ADMIN_ROLE": "read_only"}, clear=False):
            get_settings.cache_clear()
            response = client.patch(
                "/admin/onboarding/session-1/identity",
                headers=admin_headers,
                json={"version": 1, "company_name": "X"},
            )
            get_settings.cache_clear()
        assert response.status_code == 403


class TestSuperAdminDeletionSmoke:
    def test_non_test_tenant_not_deletable(self):
        from app.admin.tenant_lifecycle.deletion_service import TenantDeletionService

        db = MagicMock()
        record = SimpleNamespace(is_test_tenant=False)
        db.query.return_value.filter.return_value.first.return_value = record
        dry = TenantDeletionService.dry_run(db, "T_REAL", require_test_tenant=True)
        assert dry.deletable is False
        assert dry.blocked_reason == "not_test_tenant"


class TestOnboardingRegistriesSmoke:
    def test_registries_include_industries_and_services(self, client, admin_headers):
        response = client.get("/admin/onboarding/registries", headers=admin_headers)
        assert response.status_code == 200
        body = response.json()
        assert "industries" in body
        assert "service_profiles" in body
        assert len(body["service_profiles"]) > 0


class TestSuperAdminOnboardingAccess:
    def test_super_admin_can_read_registries(self, client, admin_headers):
        with patch("app.core.admin_auth.resolve_authenticated_operator") as resolve:
            resolve.return_value = {
                "id": "operator-super",
                "display_name": "Super",
                "role": "super_admin",
            }
            response = client.get("/admin/onboarding/registries", headers=admin_headers)
        assert response.status_code == 200

    def test_read_only_still_blocked_from_create(self, client, admin_headers):
        with patch("app.core.admin_auth.resolve_authenticated_operator") as resolve:
            resolve.return_value = {
                "id": "operator-read",
                "display_name": "Read",
                "role": "read_only",
            }
            response = client.post(
                "/admin/onboarding",
                headers=admin_headers,
                json={"company_name": "Acme", "slug": "acme"},
            )
        assert response.status_code == 403
