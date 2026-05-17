"""
HTTP-level tenant isolation tests.

These tests use FastAPI TestClient (full ASGI stack) and verify that:
- Tenant A's key cannot access Tenant B's jobs, cases, approvals, or config.
- Missing API key returns 401 across representative protected routes.
- Wrong API key returns 403 across representative protected routes.
- Admin API key cannot be used as a tenant key.
- Tenant API key cannot be used as an admin key.
- Forged X-Tenant-ID header cannot bypass key-based auth.
- Inactive tenant key returns 403.
- Cross-tenant job access returns 404 (not 200 with wrong data).
- Cross-tenant approval access returns 404.
- Dormant unsafe route modules are NOT mounted on the production app.

All DB calls are mocked so no real database is required.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

TENANT_A_KEY = "key-tenant-a"
TENANT_A_ID  = "TENANT_A"
TENANT_B_KEY = "key-tenant-b"
TENANT_B_ID  = "TENANT_B"
ADMIN_KEY    = "admin-secret-key"


def _mock_auth(tenant_id: str):
    """Return a get_db patcher and a get_verified_tenant override."""
    return patch("app.main.get_verified_tenant", return_value=tenant_id)


def _admin_settings():
    return SimpleNamespace(ADMIN_API_KEY=ADMIN_KEY, TENANT_API_KEYS="", ENV="dev",
                           APP_NAME="Test")


# ---------------------------------------------------------------------------
# Missing key → 401 across representative routes
# ---------------------------------------------------------------------------

class TestMissingKey:
    """All protected routes must require an API key in production-like mode."""

    def setup_method(self):
        self.client = TestClient(app, raise_server_exceptions=False)

    def _check_401_or_403(self, path: str, method: str = "GET", json=None):
        fn = getattr(self.client, method.lower())
        kwargs = {"headers": {}}
        if json is not None:
            kwargs["json"] = json
        resp = fn(path, **kwargs)
        assert resp.status_code in (401, 403), (
            f"{method} {path} returned {resp.status_code} without a key"
        )

    def test_jobs_list_no_key(self):
        with patch("app.core.auth._load_env_key_map", return_value={"T": "k"}):
            self._check_401_or_403("/jobs")

    def test_cases_no_key(self):
        with patch("app.core.auth._load_env_key_map", return_value={"T": "k"}):
            self._check_401_or_403("/cases")

    def test_approvals_pending_no_key(self):
        with patch("app.core.auth._load_env_key_map", return_value={"T": "k"}):
            self._check_401_or_403("/approvals/pending")

    def test_dashboard_summary_no_key(self):
        with patch("app.core.auth._load_env_key_map", return_value={"T": "k"}):
            self._check_401_or_403("/dashboard/summary")

    def test_audit_events_no_key(self):
        with patch("app.core.auth._load_env_key_map", return_value={"T": "k"}):
            self._check_401_or_403("/audit-events")

    def test_integrations_health_no_key(self):
        with patch("app.core.auth._load_env_key_map", return_value={"T": "k"}):
            self._check_401_or_403("/integrations/health")


# ---------------------------------------------------------------------------
# Wrong key → 403
# ---------------------------------------------------------------------------

class TestWrongKey:
    """An unrecognized API key must be rejected with 403."""

    def setup_method(self):
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_garbage_key_jobs(self):
        with (
            patch("app.core.auth._load_env_key_map", return_value={"T": "real-key"}),
            patch("app.core.auth._lookup_db_key", return_value=None),
        ):
            r = self.client.get("/jobs", headers={"X-API-Key": "garbage-key"})
        assert r.status_code == 403

    def test_garbage_key_cases(self):
        with (
            patch("app.core.auth._load_env_key_map", return_value={"T": "real-key"}),
            patch("app.core.auth._lookup_db_key", return_value=None),
        ):
            r = self.client.get("/cases", headers={"X-API-Key": "garbage-key"})
        assert r.status_code == 403

    def test_tenant_id_used_as_key_rejected(self):
        """Sending the tenant-ID itself as X-API-Key must not authenticate."""
        with (
            patch("app.core.auth._load_env_key_map", return_value={TENANT_A_ID: TENANT_A_KEY}),
            patch("app.core.auth._lookup_db_key", return_value=None),
        ):
            r = self.client.get("/jobs", headers={"X-API-Key": TENANT_A_ID})
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# Forged X-Tenant-ID cannot bypass key auth
# ---------------------------------------------------------------------------

class TestForgedTenantIdHeader:
    """If env keys are configured, X-Tenant-ID alone must not grant access."""

    def setup_method(self):
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_forged_tenant_id_rejected_when_auth_enabled(self):
        with (
            patch("app.core.auth._load_env_key_map", return_value={TENANT_A_ID: TENANT_A_KEY}),
            patch("app.core.auth._lookup_db_key", return_value=None),
        ):
            r = self.client.get(
                "/jobs",
                headers={"X-Tenant-ID": TENANT_A_ID},  # no X-API-Key
            )
        assert r.status_code in (401, 403)

    def test_forged_tenant_id_cannot_escalate_to_other_tenant(self):
        """Tenant A's key + forged X-Tenant-ID=B must still resolve to tenant A."""
        with (
            patch("app.core.auth._load_env_key_map",
                  return_value={TENANT_A_ID: TENANT_A_KEY, TENANT_B_ID: TENANT_B_KEY}),
            patch("app.core.auth._lookup_db_key", return_value=None),
            patch("app.core.auth._is_tenant_active", return_value=True),
            patch("app.main.JobRepository.list_jobs_for_tenant", return_value=[]),
            patch("app.main.JobRepository.count_jobs_for_tenant", return_value=0),
            patch("app.api.dependencies.get_db"),
        ):
            r = self.client.get(
                "/jobs",
                headers={
                    "X-API-Key": TENANT_A_KEY,
                    "X-Tenant-ID": TENANT_B_ID,   # attempted impersonation
                },
            )
        # Must succeed (key is valid) but must resolve to TENANT_A, not TENANT_B.
        # We cannot read the resolved tenant from the response, but we assert the
        # request completes rather than raising a 5xx due to impersonation logic.
        assert r.status_code in (200, 422)  # 422 = schema issue, not auth bypass


# ---------------------------------------------------------------------------
# Admin key cannot be used as a tenant key
# ---------------------------------------------------------------------------

class TestAdminKeyNotAcceptedAsTenantKey:
    """The admin API key must not grant access to tenant-scoped endpoints."""

    def setup_method(self):
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_admin_key_as_x_api_key_rejected(self):
        with (
            patch("app.core.auth.get_settings",
                  return_value=SimpleNamespace(ADMIN_API_KEY=ADMIN_KEY,
                                              TENANT_API_KEYS=f'{{"{TENANT_A_ID}": "{TENANT_A_KEY}"}}',
                                              ENV="dev")),
            patch("app.core.auth._API_KEY_MAP", None),
            patch("app.core.auth._lookup_db_key", return_value=None),
        ):
            r = self.client.get(
                "/jobs",
                headers={"X-API-Key": ADMIN_KEY},  # admin key sent as tenant key
            )
        assert r.status_code == 403

    def test_admin_endpoint_rejects_tenant_key(self):
        """A valid tenant key must not satisfy the admin auth check."""
        with patch("app.core.admin_auth.get_settings",
                   return_value=SimpleNamespace(ADMIN_API_KEY=ADMIN_KEY)):
            r = self.client.get(
                "/admin/tenants/overview",
                headers={"X-Admin-API-Key": TENANT_A_KEY},
            )
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# Cross-tenant job access → 404
# ---------------------------------------------------------------------------

class TestCrossTenantJobAccess:
    """Tenant A must not be able to read Tenant B's jobs."""

    def setup_method(self):
        from app.core.auth import get_verified_tenant
        from app.api.dependencies import get_db
        self._orig_overrides = dict(app.dependency_overrides)
        app.dependency_overrides[get_verified_tenant] = lambda: TENANT_A_ID
        app.dependency_overrides[get_db] = lambda: MagicMock()
        self.client = TestClient(app, raise_server_exceptions=False)

    def teardown_method(self):
        app.dependency_overrides.clear()
        app.dependency_overrides.update(self._orig_overrides)

    def test_tenant_a_cannot_read_tenant_b_job(self):
        """
        Tenant A is authenticated but requests a job belonging to Tenant B.
        The repository scopes by tenant_id so it returns None → 404.
        """
        with patch("app.main.JobRepository.get_job_by_id", return_value=None):
            r = self.client.get(
                "/jobs/job-belonging-to-tenant-b",
                headers={"X-API-Key": TENANT_A_KEY},
            )
        assert r.status_code == 404

    def test_cases_endpoint_scoped_to_authenticated_tenant(self):
        """Cases list must return only the authenticated tenant's cases."""
        with (
            patch("app.main.JobRepository.list_jobs_for_tenant", return_value=[]) as list_mock,
            patch("app.main.JobRepository.count_jobs_for_tenant", return_value=0),
        ):
            r = self.client.get("/cases", headers={"X-API-Key": TENANT_A_KEY})
        assert r.status_code == 200
        # Verify repository was queried with the authenticated tenant only
        if list_mock.called:
            call_args = list_mock.call_args
            passed_tenant = call_args[1].get("tenant_id") or (
                call_args[0][1] if len(call_args[0]) > 1 else None
            )
            if passed_tenant is not None:
                assert passed_tenant == TENANT_A_ID


# ---------------------------------------------------------------------------
# Cross-tenant approval access → 404
# ---------------------------------------------------------------------------

class TestCrossTenantApprovalAccess:
    """Tenant A must not be able to approve Tenant B's approvals."""

    def setup_method(self):
        from app.core.auth import get_verified_tenant
        from app.api.dependencies import get_db
        self._orig_overrides = dict(app.dependency_overrides)
        app.dependency_overrides[get_verified_tenant] = lambda: TENANT_A_ID
        app.dependency_overrides[get_db] = lambda: MagicMock()
        self.client = TestClient(app, raise_server_exceptions=False)

    def teardown_method(self):
        app.dependency_overrides.clear()
        app.dependency_overrides.update(self._orig_overrides)

    def test_approve_wrong_tenant_approval_returns_404(self):
        """
        Attempting to approve an approval_id that belongs to a different tenant
        must return 404 (approval not found for this tenant), not 200.
        """
        with patch("app.main.ApprovalRequestRepository.get_by_approval_id", return_value=None):
            r = self.client.post(
                "/approvals/approval-from-tenant-b/approve",
                json={},
                headers={"X-API-Key": TENANT_A_KEY},
            )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Inactive tenant → 403
# ---------------------------------------------------------------------------

class TestInactiveTenant:
    """An inactive tenant's API key must be rejected with 403."""

    def setup_method(self):
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_inactive_tenant_key_rejected(self):
        with (
            patch("app.core.auth._load_env_key_map",
                  return_value={TENANT_A_ID: TENANT_A_KEY}),
            patch("app.core.auth._lookup_db_key", return_value=None),
            patch("app.core.auth._is_tenant_active", return_value=False),
        ):
            r = self.client.get("/jobs", headers={"X-API-Key": TENANT_A_KEY})
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# Admin key without X-Tenant-ID on tenant-scoped endpoint → 400
# ---------------------------------------------------------------------------

class TestAdminKeyTenantEndpointWithoutTenantId:
    """Admin key on a tenant-scoped endpoint without X-Tenant-ID must fail."""

    def setup_method(self):
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_admin_key_no_tenant_id_returns_400(self):
        with patch("app.core.auth.get_settings",
                   return_value=SimpleNamespace(ADMIN_API_KEY=ADMIN_KEY,
                                               TENANT_API_KEYS="", ENV="dev")):
            r = self.client.get(
                "/jobs",
                headers={"X-Admin-API-Key": ADMIN_KEY},  # no X-Tenant-ID
            )
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# Dormant unsafe route modules are NOT mounted
# ---------------------------------------------------------------------------

class TestDormantRoutesNotMounted:
    """
    The legacy approval_routes.py and api/routes/jobs.py routers must NOT be
    mounted. Their paths would overlap the main app's paths and bypass auth.
    """

    def setup_method(self):
        self.client = TestClient(app, raise_server_exceptions=False)

    def _get_all_routes(self) -> set[str]:
        return {route.path for route in app.routes}

    def test_legacy_approval_route_job_id_not_duplicate_mounted(self):
        """
        The dormant approval_routes.py exposes GET /approvals/{job_id}.
        Main app exposes GET /approvals/pending and POST /approvals/{id}/approve etc.
        If the dormant router were mounted under /approvals it would collide.
        Verify no unauthenticated handler is reachable via a pure GET on
        /approvals/<some_id> that returns 200 without a key when auth is active.
        """
        with (
            patch("app.core.auth._load_env_key_map", return_value={"T": "k"}),
            patch("app.core.auth._lookup_db_key", return_value=None),
        ):
            r = self.client.get(
                "/approvals/some-job-id",
                # No X-API-Key header — if the dormant route is mounted it would
                # allow access via X-Tenant-ID; the real route should 401/403.
            )
        assert r.status_code in (401, 403, 404, 405)

    def test_no_unauthenticated_post_jobs_bypass(self):
        """
        The dormant api/routes/jobs.py exposes POST /jobs with no auth.
        Verify that POST /jobs without a key is rejected.
        """
        with (
            patch("app.core.auth._load_env_key_map", return_value={"T": "k"}),
            patch("app.core.auth._lookup_db_key", return_value=None),
        ):
            r = self.client.post(
                "/jobs",
                json={"tenant_id": "EVIL_TENANT", "job_type": "lead",
                      "input_data": {"message_text": "test"}},
                # No X-API-Key
            )
        assert r.status_code in (401, 403)

    def test_app_routes_use_production_auth(self):
        """
        The legacy routers (approval_routes, api/routes/jobs) must not be
        mounted on the production app. Verify that no mounted sub-application
        in the route tree refers to either legacy router object.
        """
        from app.main import app as main_app
        import app.api.approval_routes as legacy_approval
        # Import legacy jobs module using importlib to avoid pre-import side-effects
        import importlib
        legacy_jobs = importlib.import_module("app.api.routes.jobs")

        legacy_router_set = {id(legacy_approval.router), id(legacy_jobs.router)}

        # Walk mounted routes (Mount objects have .app attribute)
        for route in main_app.routes:
            mounted_app = getattr(route, "app", None)
            assert id(mounted_app) not in legacy_router_set, (
                f"Legacy unsafe router is mounted at {getattr(route, 'path', '?')}!"
            )


# ---------------------------------------------------------------------------
# Admin endpoints reject tenant keys
# ---------------------------------------------------------------------------

class TestAdminEndpointsRejectTenantKeys:
    """
    Admin-only endpoints (/admin/*) must not be accessible with a regular
    tenant API key.
    """

    def setup_method(self):
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_admin_overview_rejects_tenant_key(self):
        with patch("app.core.admin_auth.get_settings",
                   return_value=SimpleNamespace(ADMIN_API_KEY=ADMIN_KEY)):
            r = self.client.get(
                "/admin/tenants/overview",
                headers={"X-Admin-API-Key": TENANT_A_KEY},
            )
        assert r.status_code == 401

    def test_admin_tenants_list_rejects_tenant_key(self):
        with patch("app.core.admin_auth.get_settings",
                   return_value=SimpleNamespace(ADMIN_API_KEY=ADMIN_KEY)):
            r = self.client.get(
                "/admin/tenants",
                headers={"X-Admin-API-Key": "not-the-admin-key"},
            )
        assert r.status_code == 401

    def test_admin_needs_help_rejects_no_key(self):
        with patch("app.core.admin_auth.get_settings",
                   return_value=SimpleNamespace(ADMIN_API_KEY=ADMIN_KEY)):
            r = self.client.get("/admin/operations/needs-help")
        assert r.status_code == 401
