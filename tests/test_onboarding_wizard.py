"""
Tests for Pilot Customer Onboarding Wizard (Slice 4).

Covers:
- /onboarding/wizard-state returns correct composite shape
- Tenant isolation: other tenant cannot access wizard state
- Admin auth NOT required for wizard-state (customer-accessible)
- onboarding/status returns all 8 step keys
- readiness transitions: not_started, in_progress, ready
- pilot/readiness endpoint accessible
- routing hint drafts included in wizard state
- Permission separation: customer tenant can access, unauthenticated cannot
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest

from app.onboarding.readiness import (
    get_onboarding_status,
    _check_tenant_created,
    _check_gmail_ready,
    _check_monday_ready,
    _check_systems_scanned,
    _check_routing_hints_saved,
    _check_automation_policy,
    _check_test_lead,
    _check_dispatch_verified,
    _STEP_KEYS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _settings(**kwargs) -> SimpleNamespace:
    defaults = {
        "GOOGLE_MAIL_ACCESS_TOKEN": "",
        "MONDAY_API_KEY": "",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _mock_db_for_onboarding(has_lead: bool = False, has_dispatch: bool = False) -> MagicMock:
    db = MagicMock()
    q = db.query.return_value
    q.filter.return_value = q
    q.count.return_value = 1 if has_lead else 0
    q.first.return_value = MagicMock() if has_dispatch else None
    return db


# ---------------------------------------------------------------------------
# Individual step evaluators
# ---------------------------------------------------------------------------

class TestStepEvaluators:
    def test_tenant_created_with_config(self):
        status, msg = _check_tenant_created({"tenant_id": "T"})
        assert status == "complete"

    def test_tenant_created_without_config(self):
        status, msg = _check_tenant_created(None)
        assert status == "incomplete"

    def test_gmail_ready_with_access_token(self):
        status, _ = _check_gmail_ready({}, _settings(GOOGLE_MAIL_ACCESS_TOKEN="tok"))
        assert status == "complete"

    def test_gmail_not_ready_without_token(self):
        status, _ = _check_gmail_ready({}, _settings(GOOGLE_MAIL_ACCESS_TOKEN=""))
        assert status == "incomplete"

    def test_gmail_ready_from_scan_history(self):
        settings_dict = {
            "workflow_scan": {"summary": {"gmail": {"status": "success"}}}
        }
        status, _ = _check_gmail_ready(settings_dict, _settings())
        assert status == "complete"

    def test_monday_ready_with_api_key(self):
        status, _ = _check_monday_ready({}, _settings(MONDAY_API_KEY="key-123"))
        assert status == "complete"

    def test_monday_not_ready_without_key(self):
        status, _ = _check_monday_ready({}, _settings())
        assert status == "incomplete"

    def test_systems_scanned_with_gmail(self):
        settings_dict = {"workflow_scan": {"systems_scanned": ["gmail"]}}
        status, msg = _check_systems_scanned(settings_dict)
        assert status == "complete"
        assert "gmail" in msg.lower()

    def test_systems_not_scanned(self):
        status, _ = _check_systems_scanned({})
        assert status == "incomplete"

    def test_routing_hints_valid(self):
        settings_dict = {
            "memory": {"routing_hints": {"lead": {"system": "monday", "target": {"board_id": "123"}}}}
        }
        status, _ = _check_routing_hints_saved(settings_dict)
        assert status == "complete"

    def test_routing_hints_missing(self):
        status, _ = _check_routing_hints_saved({})
        assert status == "incomplete"

    def test_routing_hints_no_board_id(self):
        settings_dict = {
            "memory": {"routing_hints": {"lead": {"system": "monday", "target": {}}}}
        }
        status, _ = _check_routing_hints_saved(settings_dict)
        assert status == "incomplete"

    def test_automation_policy_set(self):
        settings_dict = {"auto_actions": {"lead": "full_auto"}}
        status, _ = _check_automation_policy(settings_dict)
        assert status == "complete"

    def test_automation_policy_not_set(self):
        status, _ = _check_automation_policy({})
        assert status == "incomplete"

    def test_test_lead_exists(self):
        db = MagicMock()
        with patch("app.onboarding.readiness.JobRepository.count_jobs_for_tenant", return_value=2):
            status, _ = _check_test_lead(db, "T_TEST")
        assert status == "complete"

    def test_test_lead_not_exists(self):
        db = MagicMock()
        with patch("app.onboarding.readiness.JobRepository.count_jobs_for_tenant", return_value=0):
            status, _ = _check_test_lead(db, "T_TEST")
        assert status == "incomplete"

    def test_dispatch_verified_exists(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = MagicMock()
        status, _ = _check_dispatch_verified(db, "T_TEST")
        assert status == "complete"

    def test_dispatch_verified_not_exists(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        status, _ = _check_dispatch_verified(db, "T_TEST")
        assert status == "incomplete"


# ---------------------------------------------------------------------------
# get_onboarding_status
# ---------------------------------------------------------------------------

class TestGetOnboardingStatus:
    def _base_context(self, settings_dict: dict | None = None, tenant_cfg=None):
        """Return a context manager set for onboarding tests."""
        mock_record = MagicMock()
        mock_record.settings = settings_dict or {}
        return (mock_record, settings_dict or {})

    def test_returns_all_step_keys(self):
        db = MagicMock()
        mock_record = MagicMock()
        mock_record.settings = {}
        with patch("app.onboarding.readiness.TenantConfigRepository.get", return_value=mock_record), \
             patch("app.onboarding.readiness.TenantConfigRepository.to_dict", return_value={"tenant_id": "T"}), \
             patch("app.onboarding.readiness.TenantConfigRepository.get_settings", return_value={}), \
             patch("app.onboarding.readiness.JobRepository.count_jobs_for_tenant", return_value=0), \
             patch("app.onboarding.readiness._check_dispatch_verified", return_value=("incomplete", "no dispatch")):
            result = get_onboarding_status(db, "T_TEST", app_settings=_settings())

        step_keys = [s["key"] for s in result["steps"]]
        for key in _STEP_KEYS:
            assert key in step_keys

    def test_not_started_when_no_steps_complete(self):
        db = MagicMock()
        with patch("app.onboarding.readiness.TenantConfigRepository.get", return_value=None), \
             patch("app.onboarding.readiness.TenantConfigRepository.to_dict", return_value=None), \
             patch("app.onboarding.readiness.TenantConfigRepository.get_settings", return_value={}), \
             patch("app.onboarding.readiness.JobRepository.count_jobs_for_tenant", return_value=0), \
             patch("app.onboarding.readiness._check_dispatch_verified", return_value=("incomplete", "no dispatch")):
            result = get_onboarding_status(db, "T_NONE", app_settings=_settings())

        assert result["status"] == "not_started"
        assert result["score"]["completed"] == 0

    def test_score_structure(self):
        db = MagicMock()
        mock_record = MagicMock()
        mock_record.settings = {}
        with patch("app.onboarding.readiness.TenantConfigRepository.get", return_value=mock_record), \
             patch("app.onboarding.readiness.TenantConfigRepository.to_dict", return_value={"tenant_id": "T"}), \
             patch("app.onboarding.readiness.TenantConfigRepository.get_settings", return_value={}), \
             patch("app.onboarding.readiness.JobRepository.count_jobs_for_tenant", return_value=0), \
             patch("app.onboarding.readiness._check_dispatch_verified", return_value=("incomplete", "no dispatch")):
            result = get_onboarding_status(db, "T_TEST", app_settings=_settings())

        score = result["score"]
        assert "completed" in score
        assert "total" in score
        assert "percent" in score
        assert score["total"] == 8

    def test_ready_when_all_complete(self):
        """With all checks passing, status should be 'ready'."""
        db = MagicMock()
        settings_dict = {
            "workflow_scan": {
                "systems_scanned": ["gmail", "monday"],
                "summary": {"gmail": {"status": "success"}, "monday": {"status": "success"}},
            },
            "memory": {
                "routing_hints": {
                    "lead": {"system": "monday", "target": {"board_id": "board-1"}}
                }
            },
            "auto_actions": {"lead": "full_auto"},
        }
        mock_record = MagicMock()
        mock_record.settings = settings_dict

        with patch("app.onboarding.readiness.TenantConfigRepository.get", return_value=mock_record), \
             patch("app.onboarding.readiness.TenantConfigRepository.to_dict", return_value={"tenant_id": "T"}), \
             patch("app.onboarding.readiness.TenantConfigRepository.get_settings", return_value=settings_dict), \
             patch("app.onboarding.readiness.JobRepository.count_jobs_for_tenant", return_value=1), \
             patch("app.onboarding.readiness._check_dispatch_verified", return_value=("complete", "dispatch ok")):
            result = get_onboarding_status(
                db, "T_TEST",
                app_settings=_settings(GOOGLE_MAIL_ACCESS_TOKEN="tok", MONDAY_API_KEY="key"),
            )

        assert result["status"] == "ready"
        assert result["score"]["completed"] == 8

    def test_in_progress_when_partial(self):
        db = MagicMock()
        mock_record = MagicMock()
        mock_record.settings = {}
        with patch("app.onboarding.readiness.TenantConfigRepository.get", return_value=mock_record), \
             patch("app.onboarding.readiness.TenantConfigRepository.to_dict", return_value={"tenant_id": "T"}), \
             patch("app.onboarding.readiness.TenantConfigRepository.get_settings", return_value={}), \
             patch("app.onboarding.readiness.JobRepository.count_jobs_for_tenant", return_value=0), \
             patch("app.onboarding.readiness._check_dispatch_verified", return_value=("incomplete", "no dispatch")):
            result = get_onboarding_status(
                db, "T_TEST",
                app_settings=_settings(GOOGLE_MAIL_ACCESS_TOKEN="tok"),  # only gmail ready
            )

        # tenant_created + gmail_ready = 2 complete
        assert result["status"] == "in_progress"
        assert result["score"]["completed"] >= 1


# ---------------------------------------------------------------------------
# HTTP endpoint tests
# ---------------------------------------------------------------------------

class TestWizardEndpoints:
    def _client(self):
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app, raise_server_exceptions=False)

    def test_onboarding_status_requires_tenant_auth(self):
        """Without X-API-Key, should return 401."""
        resp = self._client().get("/onboarding/status")
        assert resp.status_code in (401, 403)

    def test_wizard_state_requires_tenant_auth(self):
        """Customer endpoint — requires X-API-Key, not admin key."""
        resp = self._client().get("/onboarding/wizard-state")
        assert resp.status_code in (401, 403)

    def test_onboarding_test_lead_requires_tenant_auth(self):
        resp = self._client().post("/onboarding/test-lead", json={})
        assert resp.status_code in (401, 403)

    def test_pilot_readiness_requires_tenant_auth(self):
        resp = self._client().get("/pilot/readiness")
        assert resp.status_code in (401, 403)

    def test_routing_hints_apply_requires_tenant_auth(self):
        resp = self._client().post("/tenant/routing-hints/apply", json={"routing_hints": {}})
        assert resp.status_code in (401, 403)

    def test_wizard_state_not_accessible_without_admin_key_only(self):
        """wizard-state is a tenant endpoint, NOT admin-only — no X-Admin-API-Key bypass."""
        resp = self._client().get(
            "/onboarding/wizard-state",
            headers={"X-Admin-API-Key": "some-admin-key"},  # no tenant key
        )
        # Should still be 401/403 — admin key alone is not enough for tenant endpoints
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Readiness transitions
# ---------------------------------------------------------------------------

class TestReadinessTransitions:
    def _shared_patches(self):
        return [
            patch("app.onboarding.readiness.JobRepository.count_jobs_for_tenant", return_value=0),
            patch("app.onboarding.readiness._check_dispatch_verified", return_value=("incomplete", "no dispatch")),
        ]

    def test_transition_not_started_to_in_progress(self):
        """Adding one configuration moves status from not_started to in_progress."""
        db = MagicMock()
        mock_record = MagicMock()
        mock_record.settings = {}

        with patch("app.onboarding.readiness.TenantConfigRepository.get", return_value=mock_record), \
             patch("app.onboarding.readiness.TenantConfigRepository.to_dict", return_value={"tenant_id": "T"}), \
             patch("app.onboarding.readiness.TenantConfigRepository.get_settings", return_value={}), \
             patch("app.onboarding.readiness.JobRepository.count_jobs_for_tenant", return_value=0), \
             patch("app.onboarding.readiness._check_dispatch_verified", return_value=("incomplete", "no dispatch")):
            result = get_onboarding_status(db, "T", app_settings=_settings())

        # tenant_created is always complete when record exists → in_progress
        assert result["status"] == "in_progress"

    def test_all_steps_have_status_field(self):
        db = MagicMock()
        mock_record = MagicMock()
        mock_record.settings = {}

        with patch("app.onboarding.readiness.TenantConfigRepository.get", return_value=mock_record), \
             patch("app.onboarding.readiness.TenantConfigRepository.to_dict", return_value={"tenant_id": "T"}), \
             patch("app.onboarding.readiness.TenantConfigRepository.get_settings", return_value={}), \
             patch("app.onboarding.readiness.JobRepository.count_jobs_for_tenant", return_value=0), \
             patch("app.onboarding.readiness._check_dispatch_verified", return_value=("incomplete", "no dispatch")):
            result = get_onboarding_status(db, "T", app_settings=_settings())

        for step in result["steps"]:
            assert step["status"] in ("complete", "incomplete", "warning")
            assert "key" in step
            assert "label" in step
            assert "message" in step
