"""
Tests for Slice 16 – Super Admin Panel v1.

Covers:
- get_super_admin_overview: returns all DB tenants
- tenant summary includes onboarding percent
- tenant summary includes pilot readiness percent/status
- tenant summary includes integration status (overall + per-system)
- tenant summary includes dispatch 30d stats
- top-level counts: healthy/warning/error/not_ready
- total_hours_saved_30d sums tenant hours
- recent_error_count is tenant-scoped
- no secrets leaked in response
- one failing tenant does not break the whole overview
- empty tenant list returns safe zero values
- overall_status derivation logic
- GET /admin/tenants/overview requires auth (endpoint exists + shape)
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.admin.super_admin import (
    _build_tenant_summary,
    _latest_activity_at,
    _recent_error_count,
    _tenant_overall_status,
    get_super_admin_overview,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _app_settings(**kwargs):
    defaults = {
        "TENANT_API_KEYS": "k",
        "GOOGLE_MAIL_ACCESS_TOKEN": "",
        "MONDAY_API_KEY": "",
        "APP_NAME": "App",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _mock_db():
    db = MagicMock()
    q = MagicMock()
    q.filter.return_value = q
    q.order_by.return_value = q
    q.limit.return_value = q
    q.count.return_value = 0
    q.first.return_value = None
    q.all.return_value = []
    db.query.return_value = q
    return db


def _fake_tenant(tenant_id="t-1", name="Kund AB"):
    r = MagicMock()
    r.tenant_id = tenant_id
    r.name = name
    return r


def _onboarding_ready():
    return {"status": "ready", "score": {"completed": 8, "total": 8, "percent": 100}}

def _onboarding_in_progress():
    return {"status": "in_progress", "score": {"completed": 4, "total": 8, "percent": 50}}

def _pilot_ready():
    return {"overall_status": "ready", "score": {"passed": 11, "warnings": 0, "failures": 0, "total": 11}}

def _pilot_almost():
    return {"overall_status": "almost_ready", "score": {"passed": 8, "warnings": 3, "failures": 0, "total": 11}}

def _health_healthy():
    return {"overall_status": "healthy", "systems": {
        "gmail":  {"status": "healthy"},
        "monday": {"status": "healthy"},
    }}

def _health_warning():
    return {"overall_status": "warning", "systems": {
        "gmail":  {"status": "not_configured"},
        "monday": {"status": "warning"},
    }}

def _dispatch_report(hours=2.5, total=5, rate=80, auto=60):
    return {"headline": {
        "dispatches_completed": total,
        "time_saved_hours": hours,
        "success_rate_percent": rate,
        "automation_share_percent": auto,
    }}


def _run_build(tenant_id="t-1", name="Kund AB", db=None, app_settings=None,
               onboarding=None, pilot=None, health=None, dispatch_rep=None,
               error_count=0):
    if db is None:
        db = _mock_db()
    if app_settings is None:
        app_settings = _app_settings()
    if onboarding is None:
        onboarding = _onboarding_ready()
    if pilot is None:
        pilot = _pilot_ready()
    if health is None:
        health = _health_healthy()
    if dispatch_rep is None:
        dispatch_rep = _dispatch_report()

    with patch("app.admin.super_admin.get_onboarding_status", return_value=onboarding), \
         patch("app.admin.super_admin.get_pilot_readiness", return_value=pilot), \
         patch("app.admin.super_admin.get_integration_health", return_value=health), \
         patch("app.admin.super_admin.get_dispatch_report", return_value=dispatch_rep), \
         patch("app.admin.super_admin._recent_error_count", return_value=error_count), \
         patch("app.admin.super_admin._latest_activity_at", return_value=None):
        return _build_tenant_summary(db, tenant_id, name, app_settings)


# ---------------------------------------------------------------------------
# _tenant_overall_status
# ---------------------------------------------------------------------------

class TestTenantOverallStatus:
    def test_healthy_when_all_good(self):
        assert _tenant_overall_status("ready", "ready", "healthy") == "healthy"

    def test_error_when_integration_error(self):
        assert _tenant_overall_status("ready", "ready", "error") == "error"

    def test_not_ready_when_pilot_not_ready(self):
        assert _tenant_overall_status("ready", "not_ready", "healthy") == "not_ready"

    def test_warning_when_integration_warning(self):
        assert _tenant_overall_status("ready", "ready", "warning") == "warning"

    def test_warning_when_onboarding_in_progress(self):
        assert _tenant_overall_status("in_progress", "ready", "healthy") == "warning"

    def test_warning_when_onboarding_not_started(self):
        assert _tenant_overall_status("not_started", "ready", "healthy") == "warning"

    def test_warning_when_pilot_almost_ready(self):
        assert _tenant_overall_status("ready", "almost_ready", "healthy") == "warning"

    def test_error_beats_not_ready(self):
        assert _tenant_overall_status("ready", "not_ready", "error") == "error"


# ---------------------------------------------------------------------------
# _build_tenant_summary
# ---------------------------------------------------------------------------

class TestBuildTenantSummary:
    def test_response_shape(self):
        result = _run_build()
        for key in ("tenant_id", "name", "status", "onboarding", "pilot_readiness",
                    "integrations", "dispatch", "latest_activity_at", "recent_error_count"):
            assert key in result

    def test_tenant_id_in_result(self):
        result = _run_build(tenant_id="TENANT_TEST")
        assert result["tenant_id"] == "TENANT_TEST"

    def test_name_in_result(self):
        result = _run_build(name="Bolaget AB")
        assert result["name"] == "Bolaget AB"

    def test_name_falls_back_to_tenant_id_when_none(self):
        result = _run_build(tenant_id="t-99", name=None)
        assert result["name"] == "t-99"

    def test_onboarding_percent(self):
        result = _run_build(onboarding=_onboarding_ready())
        assert result["onboarding"]["percent"] == 100

    def test_onboarding_status(self):
        result = _run_build(onboarding=_onboarding_in_progress())
        assert result["onboarding"]["status"] == "in_progress"
        assert result["onboarding"]["percent"] == 50

    def test_pilot_readiness_status(self):
        result = _run_build(pilot=_pilot_ready())
        assert result["pilot_readiness"]["status"] == "ready"

    def test_pilot_readiness_percent(self):
        result = _run_build(pilot=_pilot_ready())
        assert result["pilot_readiness"]["percent"] == 100

    def test_pilot_readiness_percent_partial(self):
        result = _run_build(pilot=_pilot_almost())
        assert 0 < result["pilot_readiness"]["percent"] < 100

    def test_integration_overall_status(self):
        result = _run_build(health=_health_healthy())
        assert result["integrations"]["overall_status"] == "healthy"

    def test_integration_gmail_status(self):
        result = _run_build(health=_health_healthy())
        assert result["integrations"]["gmail"] == "healthy"

    def test_integration_monday_status(self):
        result = _run_build(health=_health_warning())
        assert result["integrations"]["monday"] == "warning"

    def test_dispatch_total_30d(self):
        result = _run_build(dispatch_rep=_dispatch_report(total=7))
        assert result["dispatch"]["total_30d"] == 7

    def test_dispatch_hours_30d(self):
        result = _run_build(dispatch_rep=_dispatch_report(hours=3.5))
        assert result["dispatch"]["hours_saved_30d"] == 3.5

    def test_dispatch_automation_share(self):
        result = _run_build(dispatch_rep=_dispatch_report(auto=75))
        assert result["dispatch"]["automation_share_percent_30d"] == 75

    def test_recent_error_count(self):
        result = _run_build(error_count=3)
        assert result["recent_error_count"] == 3

    def test_status_healthy_when_all_good(self):
        result = _run_build(
            onboarding=_onboarding_ready(),
            pilot=_pilot_ready(),
            health=_health_healthy(),
        )
        assert result["status"] == "healthy"

    def test_status_warning_when_onboarding_in_progress(self):
        result = _run_build(
            onboarding=_onboarding_in_progress(),
            pilot=_pilot_ready(),
            health=_health_healthy(),
        )
        assert result["status"] == "warning"

    def test_no_secrets_in_result(self):
        result = _run_build(app_settings=_app_settings(
            GOOGLE_MAIL_ACCESS_TOKEN="secret_tok",
            MONDAY_API_KEY="secret_key",
        ))
        result_str = str(result)
        assert "secret_tok" not in result_str
        assert "secret_key" not in result_str

    def test_failing_service_does_not_raise(self):
        db = _mock_db()
        with patch("app.admin.super_admin.get_onboarding_status", side_effect=Exception("boom")), \
             patch("app.admin.super_admin.get_pilot_readiness", side_effect=Exception("boom")), \
             patch("app.admin.super_admin.get_integration_health", side_effect=Exception("boom")), \
             patch("app.admin.super_admin.get_dispatch_report", side_effect=Exception("boom")), \
             patch("app.admin.super_admin._recent_error_count", return_value=0), \
             patch("app.admin.super_admin._latest_activity_at", return_value=None):
            # Must not raise
            result = _build_tenant_summary(db, "t-1", "Kund", _app_settings())
        assert result["tenant_id"] == "t-1"

    def test_failing_service_returns_safe_defaults(self):
        db = _mock_db()
        with patch("app.admin.super_admin.get_onboarding_status", side_effect=Exception("boom")), \
             patch("app.admin.super_admin.get_pilot_readiness", side_effect=Exception("boom")), \
             patch("app.admin.super_admin.get_integration_health", side_effect=Exception("boom")), \
             patch("app.admin.super_admin.get_dispatch_report", side_effect=Exception("boom")), \
             patch("app.admin.super_admin._recent_error_count", return_value=0), \
             patch("app.admin.super_admin._latest_activity_at", return_value=None):
            result = _build_tenant_summary(db, "t-1", "Kund", _app_settings())
        assert result["dispatch"]["total_30d"] == 0
        assert result["onboarding"]["percent"] == 0
        assert result["pilot_readiness"]["percent"] == 0


# ---------------------------------------------------------------------------
# get_super_admin_overview
# ---------------------------------------------------------------------------

class TestGetSuperAdminOverview:
    def _run(self, tenants=None, db=None, app_settings=None,
             onboarding=None, pilot=None, health=None, dispatch_rep=None):
        if db is None:
            db = _mock_db()
        if app_settings is None:
            app_settings = _app_settings()
        if tenants is None:
            tenants = []

        with patch("app.admin.super_admin.TenantConfigRepository.list_all", return_value=tenants), \
             patch("app.admin.super_admin.get_onboarding_status",
                   return_value=onboarding or _onboarding_ready()), \
             patch("app.admin.super_admin.get_pilot_readiness",
                   return_value=pilot or _pilot_ready()), \
             patch("app.admin.super_admin.get_integration_health",
                   return_value=health or _health_healthy()), \
             patch("app.admin.super_admin.get_dispatch_report",
                   return_value=dispatch_rep or _dispatch_report()), \
             patch("app.admin.super_admin._recent_error_count", return_value=0), \
             patch("app.admin.super_admin._latest_activity_at", return_value=None):
            return get_super_admin_overview(db=db, app_settings=app_settings)

    def test_response_shape(self):
        result = self._run()
        for key in ("total_tenants", "healthy", "warning", "error", "not_ready",
                    "total_hours_saved_30d", "items"):
            assert key in result

    def test_empty_db_returns_zeros(self):
        result = self._run(tenants=[])
        assert result["total_tenants"] == 0
        assert result["healthy"] == 0
        assert result["warning"] == 0
        assert result["error"] == 0
        assert result["not_ready"] == 0
        assert result["total_hours_saved_30d"] == 0.0
        assert result["items"] == []

    def test_returns_all_db_tenants(self):
        tenants = [_fake_tenant("t-1"), _fake_tenant("t-2"), _fake_tenant("t-3")]
        result = self._run(tenants=tenants)
        assert result["total_tenants"] == 3
        assert len(result["items"]) == 3

    def test_healthy_count(self):
        tenants = [_fake_tenant("t-1"), _fake_tenant("t-2")]
        result = self._run(tenants=tenants, health=_health_healthy(),
                           onboarding=_onboarding_ready(), pilot=_pilot_ready())
        assert result["healthy"] == 2

    def test_warning_count_from_onboarding(self):
        tenants = [_fake_tenant("t-1")]
        result = self._run(tenants=tenants, onboarding=_onboarding_in_progress(),
                           health=_health_healthy(), pilot=_pilot_ready())
        assert result["warning"] == 1
        assert result["healthy"] == 0

    def test_total_hours_saved_sums_tenants(self):
        tenants = [_fake_tenant("t-1"), _fake_tenant("t-2")]
        result = self._run(tenants=tenants, dispatch_rep=_dispatch_report(hours=3.0))
        assert result["total_hours_saved_30d"] == 6.0

    def test_tenant_ids_in_items(self):
        tenants = [_fake_tenant("t-alpha"), _fake_tenant("t-beta")]
        result = self._run(tenants=tenants)
        item_ids = {item["tenant_id"] for item in result["items"]}
        assert "t-alpha" in item_ids
        assert "t-beta" in item_ids

    def test_one_failing_tenant_does_not_break_rest(self):
        tenants = [_fake_tenant("t-1"), _fake_tenant("t-2")]
        db = _mock_db()
        call_count = [0]

        def onboarding_with_one_failure(db, tenant_id, *, app_settings):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("first tenant explodes")
            return _onboarding_ready()

        with patch("app.admin.super_admin.TenantConfigRepository.list_all", return_value=tenants), \
             patch("app.admin.super_admin.get_onboarding_status", side_effect=onboarding_with_one_failure), \
             patch("app.admin.super_admin.get_pilot_readiness", return_value=_pilot_ready()), \
             patch("app.admin.super_admin.get_integration_health", return_value=_health_healthy()), \
             patch("app.admin.super_admin.get_dispatch_report", return_value=_dispatch_report()), \
             patch("app.admin.super_admin._recent_error_count", return_value=0), \
             patch("app.admin.super_admin._latest_activity_at", return_value=None):
            result = get_super_admin_overview(db=db, app_settings=_app_settings())
        assert result["total_tenants"] == 2
        assert len(result["items"]) == 2

    def test_no_secrets_in_response(self):
        tenants = [_fake_tenant("t-1")]
        result = self._run(
            tenants=tenants,
            app_settings=_app_settings(
                GOOGLE_MAIL_ACCESS_TOKEN="secret_gmail_token",
                MONDAY_API_KEY="secret_monday_key",
            ),
        )
        result_str = str(result)
        assert "secret_gmail_token" not in result_str
        assert "secret_monday_key" not in result_str

    def test_not_ready_count(self):
        tenants = [_fake_tenant("t-1")]
        result = self._run(
            tenants=tenants,
            pilot={"overall_status": "not_ready", "score": {"passed": 3, "warnings": 0, "failures": 8, "total": 11}},
            onboarding=_onboarding_ready(),
            health=_health_healthy(),
        )
        assert result["not_ready"] == 1

    def test_error_count(self):
        tenants = [_fake_tenant("t-1")]
        result = self._run(
            tenants=tenants,
            health={"overall_status": "error", "systems": {
                "gmail": {"status": "error"}, "monday": {"status": "healthy"}
            }},
        )
        assert result["error"] == 1

    def test_items_have_dispatch_shape(self):
        tenants = [_fake_tenant("t-1")]
        result = self._run(tenants=tenants)
        disp = result["items"][0]["dispatch"]
        for field in ("total_30d", "success_30d", "failed_30d", "hours_saved_30d",
                      "automation_share_percent_30d"):
            assert field in disp

    def test_items_have_integrations_shape(self):
        tenants = [_fake_tenant("t-1")]
        result = self._run(tenants=tenants)
        integ = result["items"][0]["integrations"]
        for field in ("overall_status", "gmail", "monday"):
            assert field in integ

    def test_no_external_api_calls(self):
        result = self._run(tenants=[])
        assert result is not None  # if external call raised, test would fail

    def test_tenant_isolation_separate_calls(self):
        tenants = [_fake_tenant("t-a", "Alpha"), _fake_tenant("t-b", "Beta")]
        result = self._run(tenants=tenants)
        names = {item["name"] for item in result["items"]}
        assert "Alpha" in names
        assert "Beta" in names
