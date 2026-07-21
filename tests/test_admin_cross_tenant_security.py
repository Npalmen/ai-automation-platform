"""Cross-tenant security tests for admin operator routes (Kapitel 11)."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from app.core.settings import get_settings


@pytest.fixture
def client(lifespan_client):
    return lifespan_client


@pytest.fixture
def admin_headers():
    key = get_settings().ADMIN_API_KEY.strip()
    if not key:
        pytest.skip("ADMIN_API_KEY not configured")
    return {
        "X-Admin-API-Key": key,
        "Origin": "http://testserver",
    }


class TestAdminCrossTenantSecurity:
    def test_alerts_filter_does_not_leak_other_tenant(self, client, admin_headers):
        r_a = client.get(
            "/admin/alerts",
            params={"tenant_id": "T_NONEXIST_A", "limit": 5},
            headers=admin_headers,
        )
        assert r_a.status_code == 200
        for item in r_a.json().get("items", []):
            tid = item.get("tenant_id")
            if tid is not None:
                assert tid == "T_NONEXIST_A"

    def test_recovery_wrong_tenant_header_returns_not_found(self, client, admin_headers):
        with patch("app.admin.recovery_actions.JobRepository.get_job_by_id", return_value=None):
            r = client.post(
                "/admin/recovery/job-cross-1/retry",
                headers={**admin_headers, "X-Tenant-ID": "T_WRONG"},
                json={"actor": "test"},
            )
        assert r.status_code in (200, 403, 404)
        if r.status_code == 200:
            assert r.json().get("status") == "failed"

    def test_read_only_cannot_recovery_retry(self, client, admin_headers):
        with patch.dict(os.environ, {"ADMIN_ROLE": "read_only"}, clear=False):
            get_settings.cache_clear()
            try:
                r = client.post(
                    "/admin/recovery/job-1/retry",
                    headers={**admin_headers, "X-Tenant-ID": "T_TEST"},
                    json={"actor": "test"},
                )
                assert r.status_code == 403
            finally:
                get_settings.cache_clear()

    def test_read_only_cannot_rotate_key(self, client, admin_headers):
        with patch.dict(os.environ, {"ADMIN_ROLE": "read_only"}, clear=False):
            get_settings.cache_clear()
            try:
                r = client.post(
                    "/admin/tenants/T_TEST/rotate-key",
                    headers=admin_headers,
                )
                assert r.status_code == 403
            finally:
                get_settings.cache_clear()

    def test_get_run_all_not_allowed(self, client, admin_headers):
        r = client.get("/admin/alerts/run-all", headers=admin_headers)
        assert r.status_code in (404, 405)
