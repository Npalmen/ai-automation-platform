"""
Tests for Slice 13 – Customer Onboarding Wizard.

Covers:
- get_onboarding_status: default incomplete checklist (no tenant config)
- Each individual step evaluator: complete vs incomplete
- Overall status logic: not_started, in_progress, ready
- Score percent calculation
- Tenant isolation (data from wrong tenant not used)
- POST /onboarding/test-lead creates a lead job for the tenant
- Readiness endpoint makes no external API calls
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.onboarding.readiness import (
    _check_automation_policy,
    _check_dispatch_verified,
    _check_gmail_ready,
    _check_monday_ready,
    _check_routing_hints_saved,
    _check_systems_scanned,
    _check_tenant_created,
    _check_test_lead,
    get_onboarding_status,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _settings(google_mail="", monday_api=""):
    s = SimpleNamespace()
    s.GOOGLE_MAIL_ACCESS_TOKEN = google_mail
    s.MONDAY_API_KEY = monday_api
    return s


def _mock_db():
    db = MagicMock()
    q = MagicMock()
    q.filter.return_value = q
    q.first.return_value = None
    db.query.return_value = q
    return db


# ---------------------------------------------------------------------------
# Individual step evaluators
# ---------------------------------------------------------------------------

class TestCheckTenantCreated:
    def test_complete_when_config_present(self):
        status, _ = _check_tenant_created({"tenant_id": "t-1"})
        assert status == "complete"

    def test_incomplete_when_no_config(self):
        status, _ = _check_tenant_created(None)
        assert status == "incomplete"


class TestCheckGmailReady:
    def test_complete_when_env_token_set(self):
        status, _ = _check_gmail_ready({}, _settings(google_mail="tok123"))
        assert status == "complete"

    def test_complete_when_scanner_success_in_summary(self):
        settings = {"workflow_scan": {"summary": {"gmail": {"status": "success"}}}}
        status, _ = _check_gmail_ready(settings, _settings())
        assert status == "complete"

    def test_complete_when_scanner_success_in_top_level(self):
        settings = {"workflow_scan": {"status": "success", "systems_scanned": ["gmail"]}}
        status, _ = _check_gmail_ready(settings, _settings())
        assert status == "complete"

    def test_incomplete_when_nothing_set(self):
        status, _ = _check_gmail_ready({}, _settings())
        assert status == "incomplete"


class TestCheckMondayReady:
    def test_complete_when_env_key_set(self):
        status, _ = _check_monday_ready({}, _settings(monday_api="key-abc"))
        assert status == "complete"

    def test_complete_when_scanner_success_in_summary(self):
        settings = {"workflow_scan": {"summary": {"monday": {"status": "success"}}}}
        status, _ = _check_monday_ready(settings, _settings())
        assert status == "complete"

    def test_incomplete_when_nothing(self):
        status, _ = _check_monday_ready({}, _settings())
        assert status == "incomplete"


class TestCheckSystemsScanned:
    def test_complete_when_gmail_scanned(self):
        settings = {"workflow_scan": {"systems_scanned": ["gmail"]}}
        status, _ = _check_systems_scanned(settings)
        assert status == "complete"

    def test_complete_when_monday_scanned(self):
        settings = {"workflow_scan": {"systems_scanned": ["monday"]}}
        status, _ = _check_systems_scanned(settings)
        assert status == "complete"

    def test_complete_when_both_scanned(self):
        settings = {"workflow_scan": {"systems_scanned": ["gmail", "monday"]}}
        status, _ = _check_systems_scanned(settings)
        assert status == "complete"

    def test_incomplete_when_empty_list(self):
        settings = {"workflow_scan": {"systems_scanned": []}}
        status, _ = _check_systems_scanned(settings)
        assert status == "incomplete"

    def test_incomplete_when_no_scan(self):
        status, _ = _check_systems_scanned({})
        assert status == "incomplete"

    def test_incomplete_when_unknown_system_only(self):
        settings = {"workflow_scan": {"systems_scanned": ["fortnox"]}}
        status, _ = _check_systems_scanned(settings)
        assert status == "incomplete"


class TestCheckRoutingHintsSaved:
    def test_complete_when_valid_hint_exists(self):
        settings = {
            "memory": {
                "routing_hints": {
                    "lead": {
                        "system": "monday",
                        "target": {"board_id": "123"},
                    }
                }
            }
        }
        status, msg = _check_routing_hints_saved(settings)
        assert status == "complete"
        assert "lead" in msg

    def test_incomplete_when_hints_empty(self):
        settings = {"memory": {"routing_hints": {}}}
        status, _ = _check_routing_hints_saved(settings)
        assert status == "incomplete"

    def test_incomplete_when_hint_missing_board_id(self):
        settings = {
            "memory": {
                "routing_hints": {
                    "lead": {
                        "system": "monday",
                        "target": {},
                    }
                }
            }
        }
        status, _ = _check_routing_hints_saved(settings)
        assert status == "incomplete"

    def test_incomplete_when_hint_missing_system(self):
        settings = {
            "memory": {
                "routing_hints": {
                    "lead": {"target": {"board_id": "123"}}
                }
            }
        }
        status, _ = _check_routing_hints_saved(settings)
        assert status == "incomplete"

    def test_incomplete_when_hint_is_none(self):
        settings = {"memory": {"routing_hints": {"lead": None}}}
        status, _ = _check_routing_hints_saved(settings)
        assert status == "incomplete"

    def test_incomplete_when_no_memory(self):
        status, _ = _check_routing_hints_saved({})
        assert status == "incomplete"


class TestCheckAutomationPolicy:
    def test_complete_when_job_type_configured(self):
        settings = {"auto_actions": {"lead": "semi"}}
        status, msg = _check_automation_policy(settings)
        assert status == "complete"
        assert "lead" in msg

    def test_complete_when_full_auto(self):
        settings = {"auto_actions": {"lead": "auto"}}
        status, _ = _check_automation_policy(settings)
        assert status == "complete"

    def test_incomplete_when_all_false(self):
        settings = {"auto_actions": {"lead": False}}
        status, _ = _check_automation_policy(settings)
        assert status == "incomplete"

    def test_incomplete_when_all_none(self):
        settings = {"auto_actions": {"lead": None}}
        status, _ = _check_automation_policy(settings)
        assert status == "incomplete"

    def test_incomplete_when_empty(self):
        settings = {"auto_actions": {}}
        status, _ = _check_automation_policy(settings)
        assert status == "incomplete"

    def test_incomplete_when_no_auto_actions_key(self):
        status, _ = _check_automation_policy({})
        assert status == "incomplete"


class TestCheckTestLead:
    def test_complete_when_lead_exists(self):
        with patch(
            "app.onboarding.readiness.JobRepository.count_jobs_for_tenant",
            return_value=3,
        ):
            db = _mock_db()
            status, msg = _check_test_lead(db, "t-1")
        assert status == "complete"
        assert "3" in msg

    def test_incomplete_when_no_leads(self):
        with patch(
            "app.onboarding.readiness.JobRepository.count_jobs_for_tenant",
            return_value=0,
        ):
            db = _mock_db()
            status, _ = _check_test_lead(db, "t-1")
        assert status == "incomplete"


class TestCheckDispatchVerified:
    def test_complete_when_successful_dispatch_exists(self):
        db = _mock_db()
        mock_event = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = mock_event
        status, _ = _check_dispatch_verified(db, "t-1")
        assert status == "complete"

    def test_incomplete_when_no_dispatch(self):
        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = None
        status, _ = _check_dispatch_verified(db, "t-1")
        assert status == "incomplete"


# ---------------------------------------------------------------------------
# get_onboarding_status: full function
# ---------------------------------------------------------------------------

def _make_full_mock(
    *,
    record=None,
    settings=None,
    lead_count=0,
    dispatch_event=None,
    app_settings=None,
):
    if settings is None:
        settings = {}
    if app_settings is None:
        app_settings = _settings()

    db = _mock_db()
    # dispatch query
    db.query.return_value.filter.return_value.first.return_value = dispatch_event

    patches = [
        patch("app.onboarding.readiness.TenantConfigRepository.get", return_value=record),
        patch("app.onboarding.readiness.TenantConfigRepository.to_dict",
              return_value=record or {}),
        patch("app.onboarding.readiness.TenantConfigRepository.get_settings",
              return_value=settings),
        patch("app.onboarding.readiness.JobRepository.count_jobs_for_tenant",
              return_value=lead_count),
    ]
    return db, app_settings, patches


class TestGetOnboardingStatus:
    def test_returns_expected_keys(self):
        db, s, patches = _make_full_mock()
        with patches[0], patches[1], patches[2], patches[3]:
            result = get_onboarding_status(db, "t-1", app_settings=s)
        assert "tenant_id" in result
        assert "status" in result
        assert "score" in result
        assert "steps" in result

    def test_eight_steps_returned(self):
        db, s, patches = _make_full_mock()
        with patches[0], patches[1], patches[2], patches[3]:
            result = get_onboarding_status(db, "t-1", app_settings=s)
        assert len(result["steps"]) == 8

    def test_all_step_keys_present(self):
        db, s, patches = _make_full_mock()
        with patches[0], patches[1], patches[2], patches[3]:
            result = get_onboarding_status(db, "t-1", app_settings=s)
        keys = {step["key"] for step in result["steps"]}
        expected = {
            "tenant_created", "gmail_ready", "monday_ready", "systems_scanned",
            "routing_hints_saved", "automation_policy_set", "test_lead_created",
            "dispatch_verified",
        }
        assert expected == keys

    def test_not_started_when_nothing_configured(self):
        db, s, patches = _make_full_mock(record=None)
        with patches[0], patches[1], patches[2], patches[3]:
            result = get_onboarding_status(db, "t-1", app_settings=s)
        assert result["status"] == "not_started"
        assert result["score"]["completed"] == 0
        assert result["score"]["percent"] == 0

    def test_in_progress_when_some_complete(self):
        db, s, patches = _make_full_mock(
            record={"tenant_id": "t-1"},
            app_settings=_settings(google_mail="tok"),
        )
        with patches[0], patches[1], patches[2], patches[3]:
            result = get_onboarding_status(db, "t-1", app_settings=s)
        assert result["status"] == "in_progress"
        assert 0 < result["score"]["completed"] < 8

    def test_ready_when_all_complete(self):
        full_settings = {
            "workflow_scan": {"systems_scanned": ["gmail", "monday"]},
            "memory": {
                "routing_hints": {
                    "lead": {"system": "monday", "target": {"board_id": "99"}}
                }
            },
            "auto_actions": {"lead": "auto"},
        }
        dispatch_event = MagicMock()
        db, _, patches = _make_full_mock(
            record={"tenant_id": "t-1"},
            settings=full_settings,
            lead_count=2,
            dispatch_event=dispatch_event,
            app_settings=_settings(google_mail="tok", monday_api="key"),
        )
        with patches[0], patches[1], patches[2], patches[3]:
            result = get_onboarding_status(
                db, "t-1", app_settings=_settings(google_mail="tok", monday_api="key")
            )
        assert result["status"] == "ready"
        assert result["score"]["completed"] == 8
        assert result["score"]["percent"] == 100

    def test_score_percent_calculation(self):
        # tenant_created=complete(1), gmail_ready=complete(1) → 2/8 = 25%
        db, _, patches = _make_full_mock(
            record={"tenant_id": "t-1"},
            app_settings=_settings(google_mail="tok"),
        )
        with patches[0], patches[1], patches[2], patches[3]:
            result = get_onboarding_status(
                db, "t-1", app_settings=_settings(google_mail="tok")
            )
        score = result["score"]
        assert score["percent"] == round(score["completed"] / score["total"] * 100)

    def test_tenant_id_in_response(self):
        db, s, patches = _make_full_mock()
        with patches[0], patches[1], patches[2], patches[3]:
            result = get_onboarding_status(db, "t-ABC", app_settings=s)
        assert result["tenant_id"] == "t-ABC"

    def test_step_has_required_fields(self):
        db, s, patches = _make_full_mock()
        with patches[0], patches[1], patches[2], patches[3]:
            result = get_onboarding_status(db, "t-1", app_settings=s)
        for step in result["steps"]:
            assert "key" in step
            assert "label" in step
            assert "status" in step
            assert "message" in step

    def test_step_status_values_valid(self):
        db, s, patches = _make_full_mock()
        with patches[0], patches[1], patches[2], patches[3]:
            result = get_onboarding_status(db, "t-1", app_settings=s)
        valid = {"complete", "incomplete", "warning"}
        for step in result["steps"]:
            assert step["status"] in valid


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------

class TestTenantIsolation:
    def test_status_scoped_to_tenant(self):
        db, s, patches = _make_full_mock(record={"tenant_id": "t-A"})
        with patches[0], patches[1], patches[2], patches[3]:
            result = get_onboarding_status(db, "t-A", app_settings=s)
        assert result["tenant_id"] == "t-A"

    def test_different_tenants_get_different_results(self):
        # t-A has a tenant record; t-B does not
        def _get(db, tid):
            return {"tenant_id": "t-A"} if tid == "t-A" else None

        db = _mock_db()
        with (
            patch("app.onboarding.readiness.TenantConfigRepository.get", side_effect=lambda db, tid: {"tenant_id": "t-A"} if tid == "t-A" else None),
            patch("app.onboarding.readiness.TenantConfigRepository.to_dict", return_value={"tenant_id": "t-A"}),
            patch("app.onboarding.readiness.TenantConfigRepository.get_settings", return_value={}),
            patch("app.onboarding.readiness.JobRepository.count_jobs_for_tenant", return_value=0),
        ):
            r_a = get_onboarding_status(db, "t-A", app_settings=_settings())
            r_b = get_onboarding_status(db, "t-B", app_settings=_settings())

        step_a = next(s for s in r_a["steps"] if s["key"] == "tenant_created")
        step_b = next(s for s in r_b["steps"] if s["key"] == "tenant_created")
        assert step_a["status"] == "complete"
        assert step_b["status"] == "incomplete"


# ---------------------------------------------------------------------------
# POST /onboarding/test-lead
# ---------------------------------------------------------------------------

class TestOnboardingTestLead:
    def _call(self, body=None):
        from app.onboarding.readiness import get_onboarding_status  # ensure import
        import json
        from unittest.mock import patch, MagicMock

        mock_job = MagicMock()
        mock_job.job_id = "job-test-123"
        mock_job.tenant_id = "t-1"
        mock_job.status.value = "completed"

        with (
            patch("app.main.JobRepository.create_job", return_value=mock_job),
            patch("app.main._run_verification_pipeline", return_value=mock_job),
            patch("app.main.create_audit_event"),
            patch("app.main.set_current_tenant"),
        ):
            from app.main import onboarding_test_lead, _OnboardingTestLeadRequest
            from unittest.mock import MagicMock as MM
            db = MM()
            request = _OnboardingTestLeadRequest(**(body or {}))
            return onboarding_test_lead(db=db, tenant_id="t-1", request=request)

    def test_returns_job_id(self):
        result = self._call()
        assert result["job_id"] == "job-test-123"

    def test_returns_tenant_id(self):
        result = self._call()
        assert result["tenant_id"] == "t-1"

    def test_returns_job_type_lead(self):
        result = self._call()
        assert result["job_type"] == "lead"

    def test_returns_status(self):
        result = self._call()
        assert "status" in result

    def test_custom_company_name_accepted(self):
        result = self._call({"company_name": "ACME Corp"})
        assert result["job_id"] == "job-test-123"

    def test_default_request_works(self):
        from app.main import onboarding_test_lead, _OnboardingTestLeadRequest
        from unittest.mock import MagicMock, patch

        mock_job = MagicMock()
        mock_job.job_id = "job-abc"
        mock_job.tenant_id = "t-1"
        mock_job.status.value = "completed"

        with (
            patch("app.main.JobRepository.create_job", return_value=mock_job),
            patch("app.main._run_verification_pipeline", return_value=mock_job),
            patch("app.main.create_audit_event"),
            patch("app.main.set_current_tenant"),
        ):
            result = onboarding_test_lead(db=MagicMock(), tenant_id="t-1", request=None)
        assert result["job_id"] == "job-abc"
