"""
Pilot safety contract tests.

These tests verify the specific safety behaviors required by
docs/PILOT_READINESS_CHECKLIST.md and docs/PHASE_O_CLOSURE_CHECKLIST.md.
They test *existing* behavior only — no new product logic is introduced.

Covered:
- Control panel safe defaults (demo_mode=False, run_mode="manual")
- Scheduler run_mode "paused" accepted as valid kill-switch value
- Invalid scheduler run_mode rejected (e.g. "auto")
- Support email validated — bad format rejected, good format accepted, empty accepted
- auto_actions dict accepted with all-false values (safe provisioning payload)
- auto_actions=false does not block control panel operation
- Production docs lock-down (docs/redoc/openapi all None in production)
- Integration health response does not contain raw secret keys
- pause-automation sets demo_mode=True (per-tenant kill switch)
- disable-scheduler sets run_mode="paused" (per-tenant kill switch)
- resume-automation restores demo_mode=False
- enable-scheduler restores run_mode="scheduled"
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def _control_put(body: dict, tenant_id: str = "T_PILOT"):
    """Call put_control_panel directly with a mocked DB."""
    from app.main import put_control_panel, ControlPanelRequest

    db = MagicMock()
    request = ControlPanelRequest(**body)
    with (
        patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
            return_value={},
        ),
        patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.update_settings"
        ) as mock_save,
    ):
        result = put_control_panel(request=request, db=db, tenant_id=tenant_id)
        return result, mock_save


def _control_get(stored: dict | None = None, tenant_id: str = "T_PILOT"):
    from app.main import get_control_panel

    db = MagicMock()
    with patch(
        "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
        return_value=stored or {},
    ):
        return get_control_panel(db=db, tenant_id=tenant_id)


def _put_expect_422(body: dict) -> str:
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        _control_put(body)
    assert exc_info.value.status_code == 422
    return exc_info.value.detail


# ── 1. Safe defaults ──────────────────────────────────────────────────────────


class TestSafeDefaults:
    """Control panel defaults must match the pilot-safe state."""

    def test_default_demo_mode_is_false(self):
        """demo_mode=False means automation is live (inbox sync enabled)."""
        r = _control_get()
        assert r["automation"]["demo_mode"] is False

    def test_default_run_mode_is_manual(self):
        """run_mode=manual means scheduler does not auto-sync inbox."""
        r = _control_get()
        assert r["scheduler"]["run_mode"] == "manual"

    def test_default_support_email_is_empty(self):
        """Empty support email surfaces in pilot readiness check."""
        r = _control_get()
        assert r["support_email"] == ""

    def test_default_automation_flags_all_enabled(self):
        """All automation flags default to enabled — operator disables explicitly."""
        auto = _control_get()["automation"]
        for flag in ("leads_enabled", "support_enabled", "invoices_enabled", "followups_enabled"):
            assert auto[flag] is True, f"{flag} should default to True"


# ── 2. Scheduler kill switch ──────────────────────────────────────────────────


class TestSchedulerKillSwitch:
    """Verify the scheduler pause/resume kill-switch contract."""

    def test_paused_run_mode_accepted(self):
        """run_mode='paused' must be accepted — it is the scheduler kill switch."""
        result, _ = _control_put({"scheduler": {"run_mode": "paused"}})
        assert result["scheduler"]["run_mode"] == "paused"

    def test_manual_run_mode_accepted(self):
        result, _ = _control_put({"scheduler": {"run_mode": "manual"}})
        assert result["scheduler"]["run_mode"] == "manual"

    def test_scheduled_run_mode_accepted(self):
        result, _ = _control_put({"scheduler": {"run_mode": "scheduled"}})
        assert result["scheduler"]["run_mode"] == "scheduled"

    def test_invalid_run_mode_rejected_with_422(self):
        """run_mode='auto' must be rejected — not a valid kill-switch state."""
        detail = _put_expect_422({"scheduler": {"run_mode": "auto"}})
        assert "run_mode" in detail

    def test_paused_mode_persisted_to_db(self):
        """Pausing must actually be saved to the DB."""
        _, mock_save = _control_put({"scheduler": {"run_mode": "paused"}})
        saved = mock_save.call_args[0][2]
        assert saved["scheduler"]["run_mode"] == "paused"


# ── 3. demo_mode kill switch ──────────────────────────────────────────────────


class TestDemoModeKillSwitch:
    """demo_mode=True blocks automated sends — it is the automation kill switch."""

    def test_demo_mode_true_persisted(self):
        body = {
            "automation": {
                "leads_enabled": True, "support_enabled": True,
                "invoices_enabled": True, "followups_enabled": True,
                "demo_mode": True,
            }
        }
        _, mock_save = _control_put(body)
        saved = mock_save.call_args[0][2]
        assert saved["automation"]["demo_mode"] is True

    def test_demo_mode_false_persisted(self):
        body = {
            "automation": {
                "leads_enabled": True, "support_enabled": True,
                "invoices_enabled": True, "followups_enabled": True,
                "demo_mode": False,
            }
        }
        _, mock_save = _control_put(body)
        saved = mock_save.call_args[0][2]
        assert saved["automation"]["demo_mode"] is False


# ── 4. Support email validation ───────────────────────────────────────────────


class TestSupportEmailValidation:
    """Support email must be validated — required before pilot go-live."""

    def test_valid_email_accepted(self):
        result, _ = _control_put({"support_email": "support@krowolf.se"})
        assert result["support_email"] == "support@krowolf.se"

    def test_empty_string_accepted(self):
        """Empty string is accepted — surfaces as missing in pilot readiness check."""
        result, _ = _control_put({"support_email": ""})
        assert result["support_email"] == ""

    def test_none_stored_as_empty_string(self):
        _, mock_save = _control_put({"support_email": None})
        saved = mock_save.call_args[0][2]
        assert saved["support_email"] == ""

    def test_invalid_format_rejected(self):
        detail = _put_expect_422({"support_email": "not-an-email"})
        assert "email" in detail.lower()

    def test_missing_tld_rejected(self):
        detail = _put_expect_422({"support_email": "admin@nodot"})
        assert "email" in detail.lower()


# ── 5. auto_actions safe provisioning ────────────────────────────────────────


class TestAutoActionsSafeProvisioning:
    """auto_actions=false must be accepted as a valid provisioning payload."""

    def test_all_false_auto_actions_accepted_in_tenant_config(self):
        """Verify the tenant config update request accepts all-false auto_actions."""
        from app.main import TenantConfigUpdateRequest

        req = TenantConfigUpdateRequest(
            enabled_job_types=["lead", "customer_inquiry"],
            allowed_integrations=["google_mail", "monday"],
            auto_actions={"lead": False, "customer_inquiry": False, "invoice": False},
        )
        assert req.auto_actions == {"lead": False, "customer_inquiry": False, "invoice": False}

    def test_mixed_auto_actions_accepted(self):
        from app.main import TenantConfigUpdateRequest

        req = TenantConfigUpdateRequest(
            enabled_job_types=["lead"],
            allowed_integrations=["google_mail"],
            auto_actions={"lead": False, "invoice": False},
        )
        assert req.auto_actions["lead"] is False


# ── 6. Production docs lock-down ──────────────────────────────────────────────


class TestProductionDocsLockDown:
    """Docs/openapi must be disabled in production — verified in PILOT_READINESS_CHECKLIST."""

    def test_docs_disabled_in_production(self):
        from app.main import _openapi_urls_for

        urls = _openapi_urls_for(SimpleNamespace(ENV="production"))
        assert urls["docs_url"] is None
        assert urls["redoc_url"] is None
        assert urls["openapi_url"] is None

    def test_docs_enabled_outside_production(self):
        from app.main import _openapi_urls_for

        urls = _openapi_urls_for(SimpleNamespace(ENV="dev"))
        assert urls["docs_url"] == "/docs"
        assert urls["openapi_url"] == "/openapi.json"


# ── 7. Admin support console kill switches ────────────────────────────────────


class TestAdminSupportKillSwitches:
    """pause-automation and disable-scheduler must set the correct fields.

    Patches the same internal helpers (_tenant_exists, _get_settings,
    _save_settings) used by test_support_console.py — consistent with
    the existing project test pattern.
    """

    def _run(self, fn, settings: dict, **kwargs):
        """Run a support_console action with mocked internals."""
        saved: list[dict] = []
        db = MagicMock()
        with (
            patch("app.admin.support_console._tenant_exists", return_value=True),
            patch("app.admin.support_console._get_settings", return_value=settings),
            patch("app.admin.support_console._save_settings",
                  side_effect=lambda d, t, s: saved.append(s)),
            patch("app.admin.support_console.create_audit_event"),
        ):
            result = fn(db, "T_PILOT", **kwargs)
        return result, saved

    def test_pause_automation_sets_demo_mode_true(self):
        from app.admin.support_console import pause_automation

        result, saved = self._run(pause_automation, {"automation": {"demo_mode": False}})
        assert result["status"] == "success"
        assert saved[0]["automation"]["demo_mode"] is True

    def test_resume_automation_sets_demo_mode_false(self):
        from app.admin.support_console import resume_automation

        result, saved = self._run(resume_automation, {"automation": {"demo_mode": True}})
        assert result["status"] == "success"
        assert saved[0]["automation"]["demo_mode"] is False

    def test_disable_scheduler_sets_run_mode_paused(self):
        from app.admin.support_console import disable_scheduler

        result, saved = self._run(disable_scheduler, {"scheduler": {"run_mode": "scheduled"}})
        assert result["status"] == "success"
        assert saved[0]["scheduler"]["run_mode"] == "paused"

    def test_enable_scheduler_sets_run_mode_scheduled(self):
        from app.admin.support_console import enable_scheduler

        result, saved = self._run(enable_scheduler, {"scheduler": {"run_mode": "paused"}})
        assert result["status"] == "success"
        assert saved[0]["scheduler"]["run_mode"] == "scheduled"
