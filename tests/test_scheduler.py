"""Tests for GET /scheduler/status and POST /scheduler/run-once."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call

import pytest
from fastapi import HTTPException


# ── helpers ───────────────────────────────────────────────────────────────────

_REPO = "app.repositories.postgres.tenant_config_repository.TenantConfigRepository"

def _now():
    return datetime(2026, 4, 24, 10, 0, 0, tzinfo=timezone.utc)


def _status(tenant_id: str = "T1", stored: dict | None = None):
    from app.main import scheduler_status

    db = MagicMock()
    with patch(f"{_REPO}.get_settings", return_value=stored or {}):
        return scheduler_status(db=db, tenant_id=tenant_id)


def _run_once(
    tenant_id: str = "T1",
    all_records: list | None = None,
    stored_per_tenant: dict | None = None,
    inbox_raises: Exception | None = None,
    dispatch_raises: Exception | None = None,
    now_utc: datetime | None = None,
):
    from app.main import scheduler_run_once

    db = MagicMock()
    _now_utc = now_utc or _now()

    _stored = stored_per_tenant or {}

    records = all_records if all_records is not None else [_make_record("T1")]

    with (
        patch(f"{_REPO}.get_settings", side_effect=lambda db, tid: _stored.get(tid, {})),
        patch(f"{_REPO}.update_settings"),
        patch(f"{_REPO}.list_all", return_value=records),
        patch("app.main._run_gmail_inbox_sync",
              side_effect=inbox_raises if inbox_raises else lambda **kw: {
                  "processed": 2, "created_jobs": ["j1"], "continued_threads": 0,
                  "deduped": 0, "errors": [],
              }),
        patch("app.main._compute_summary", return_value={"leads_today": 1}),
        patch("app.main._compute_roi", return_value={"estimated_hours_saved": 0.1}),
        patch("app.main._build_digest_body", return_value=("Subject", "Body")),
        patch("app.main.dispatch_action",
              side_effect=dispatch_raises if dispatch_raises else None),
        patch("app.main.get_settings", return_value=_mock_settings(gmail=True)),
        patch("datetime.datetime") as mock_dt,
    ):
        mock_dt.now.return_value = _now_utc
        result = scheduler_run_once(db=db, tenant_id=tenant_id)
        return result


def _make_record(tenant_id: str):
    r = MagicMock()
    r.tenant_id = tenant_id
    return r


def _mock_settings(gmail: bool = True):
    s = MagicMock()
    s.GOOGLE_MAIL_ACCESS_TOKEN = "tok" if gmail else ""
    return s


def _pass(
    tenant_id: str = "T1",
    ctrl: dict | None = None,
    now_utc: datetime | None = None,
    inbox_raises: Exception | None = None,
    dispatch_raises: Exception | None = None,
    gmail_configured: bool = True,
):
    from app.main import _run_scheduler_pass

    db = MagicMock()
    _ctrl = ctrl or {}
    _now_utc = now_utc or _now()

    with (
        patch(f"{_REPO}.get_settings", return_value=_ctrl),
        patch(f"{_REPO}.update_settings") as mock_save,
        patch("app.main._run_gmail_inbox_sync",
              side_effect=inbox_raises if inbox_raises else lambda **kw: {
                  "processed": 1, "created_jobs": [], "continued_threads": 0,
                  "deduped": 0, "errors": [],
              }),
        patch("app.main._compute_summary", return_value={}),
        patch("app.main._compute_roi", return_value={}),
        patch("app.main._build_digest_body", return_value=("Subj", "Body")),
        patch("app.main.dispatch_action",
              side_effect=dispatch_raises if dispatch_raises else None),
        patch("app.main.get_settings", return_value=_mock_settings(gmail=gmail_configured)),
    ):
        result = _run_scheduler_pass(tenant_id, db, _now_utc)
        return result, mock_save


# ══════════════════════════════════════════════════════════════════════════════
# GET /scheduler/status — shape and defaults
# ══════════════════════════════════════════════════════════════════════════════

class TestSchedulerStatus:
    def test_returns_required_keys(self):
        r = _status()
        for k in ("run_mode", "notifications_enabled", "notifications_frequency",
                  "send_hour", "last_inbox_sync_at", "last_digest_sent_at",
                  "last_scheduler_run_at", "last_status", "last_error"):
            assert k in r, f"Missing: {k}"

    def test_default_run_mode_manual(self):
        assert _status()["run_mode"] == "manual"

    def test_default_last_status_never_run(self):
        assert _status()["last_status"] == "never_run"

    def test_default_nulls(self):
        r = _status()
        assert r["last_inbox_sync_at"]    is None
        assert r["last_digest_sent_at"]   is None
        assert r["last_scheduler_run_at"] is None
        assert r["last_error"]            is None

    def test_stored_scheduler_state_returned(self):
        stored = {
            "scheduler": {"run_mode": "scheduled"},
            "scheduler_state": {
                "last_status":           "success",
                "last_inbox_sync_at":    "2026-04-24T08:00:00+00:00",
                "last_digest_sent_at":   "2026-04-24T08:01:00+00:00",
                "last_scheduler_run_at": "2026-04-24T08:01:00+00:00",
                "last_error":            None,
            },
        }
        r = _status(stored=stored)
        assert r["run_mode"]              == "scheduled"
        assert r["last_status"]           == "success"
        assert r["last_inbox_sync_at"]    == "2026-04-24T08:00:00+00:00"
        assert r["last_digest_sent_at"]   == "2026-04-24T08:01:00+00:00"
        assert r["last_error"]            is None

    def test_notification_fields_reflected(self):
        stored = {
            "notifications": {"enabled": True, "frequency": "weekly", "send_hour": 9, "recipient_email": "a@b.com"}
        }
        r = _status(stored=stored)
        assert r["notifications_enabled"]   is True
        assert r["notifications_frequency"] == "weekly"
        assert r["send_hour"]               == 9

    def test_error_state_returned(self):
        stored = {"scheduler_state": {"last_status": "failed", "last_error": "SMTP failed"}}
        r = _status(stored=stored)
        assert r["last_status"] == "failed"
        assert r["last_error"]  == "SMTP failed"

    def test_tenant_id_passed_to_repo(self):
        from app.main import scheduler_status

        db = MagicMock()
        with patch(f"{_REPO}.get_settings", return_value={}) as mock_get:
            scheduler_status(db=db, tenant_id="XYZ")
            mock_get.assert_called_once_with(db, "XYZ")


# ══════════════════════════════════════════════════════════════════════════════
# _run_scheduler_pass — core logic unit tests
# ══════════════════════════════════════════════════════════════════════════════

class TestSchedulerPassRunMode:
    def test_manual_mode_skips_inbox(self):
        ctrl = {"scheduler": {"run_mode": "manual"}}
        result, _ = _pass(ctrl=ctrl)
        assert result["inbox_sync"]["skipped"] is True
        assert "manual" in result["inbox_sync"]["reason"]

    def test_paused_mode_skips_inbox(self):
        ctrl = {"scheduler": {"run_mode": "paused"}}
        result, _ = _pass(ctrl=ctrl)
        assert result["inbox_sync"]["skipped"] is True
        assert "paused" in result["inbox_sync"]["reason"]

    def test_scheduled_mode_runs_inbox(self):
        ctrl = {"scheduler": {"run_mode": "scheduled"}}
        result, _ = _pass(ctrl=ctrl)
        assert result["inbox_sync"]["skipped"] is False

    def test_scheduled_mode_no_gmail_skips(self):
        ctrl = {"scheduler": {"run_mode": "scheduled"}}
        result, _ = _pass(ctrl=ctrl, gmail_configured=False)
        assert result["inbox_sync"]["skipped"] is True
        assert "gmail_not_configured" in result["inbox_sync"]["reason"]

    def test_run_mode_in_result(self):
        ctrl = {"scheduler": {"run_mode": "scheduled"}}
        result, _ = _pass(ctrl=ctrl)
        assert result["run_mode"] == "scheduled"


class TestSchedulerPassDigest:
    def _notif_ctrl(self, enabled=True, email="ops@x.com", frequency="daily", send_hour=8):
        return {
            "scheduler": {"run_mode": "manual"},
            "notifications": {
                "enabled": enabled, "recipient_email": email,
                "frequency": frequency, "send_hour": send_hour,
            },
        }

    def test_digest_skipped_when_disabled(self):
        ctrl = self._notif_ctrl(enabled=False)
        result, _ = _pass(ctrl=ctrl)
        assert result["digest"]["skipped"] is True

    def test_digest_skipped_when_no_recipient(self):
        ctrl = self._notif_ctrl(email="")
        result, _ = _pass(ctrl=ctrl)
        assert result["digest"]["skipped"] is True

    def test_digest_skipped_when_frequency_off(self):
        ctrl = self._notif_ctrl(frequency="off")
        result, _ = _pass(ctrl=ctrl)
        assert result["digest"]["skipped"] is True

    def test_digest_skipped_before_send_hour(self):
        ctrl = self._notif_ctrl(send_hour=14)
        now = datetime(2026, 4, 24, 10, 0, 0, tzinfo=timezone.utc)  # hour=10 < 14
        result, _ = _pass(ctrl=ctrl, now_utc=now)
        assert result["digest"]["skipped"] is True
        assert "before_send_hour" in result["digest"]["reason"]

    def test_digest_sent_at_or_after_send_hour(self):
        ctrl = self._notif_ctrl(send_hour=8)
        now = datetime(2026, 4, 24, 10, 0, 0, tzinfo=timezone.utc)  # hour=10 >= 8
        result, _ = _pass(ctrl=ctrl, now_utc=now)
        assert result["digest"]["skipped"] is False
        assert result["digest"]["recipient"] == "ops@x.com"

    def test_digest_dedup_same_day(self):
        ctrl = self._notif_ctrl()
        ctrl["scheduler_state"] = {"last_digest_sent_at": "2026-04-24T08:00:00+00:00"}
        now = datetime(2026, 4, 24, 10, 0, 0, tzinfo=timezone.utc)
        result, _ = _pass(ctrl=ctrl, now_utc=now)
        assert result["digest"]["skipped"] is True
        assert "already_sent_today" in result["digest"]["reason"]

    def test_digest_sends_next_day(self):
        ctrl = self._notif_ctrl()
        ctrl["scheduler_state"] = {"last_digest_sent_at": "2026-04-23T08:00:00+00:00"}
        now = datetime(2026, 4, 24, 10, 0, 0, tzinfo=timezone.utc)
        result, _ = _pass(ctrl=ctrl, now_utc=now)
        assert result["digest"]["skipped"] is False


class TestSchedulerPassStatePersistence:
    def test_saves_scheduler_state(self):
        ctrl = {"scheduler": {"run_mode": "manual"}}
        _, mock_save = _pass(ctrl=ctrl)
        mock_save.assert_called_once()
        saved = mock_save.call_args[0][2]
        assert "scheduler_state" in saved

    def test_last_scheduler_run_at_saved(self):
        ctrl = {"scheduler": {"run_mode": "manual"}}
        now = _now()
        _, mock_save = _pass(ctrl=ctrl, now_utc=now)
        saved_state = mock_save.call_args[0][2]["scheduler_state"]
        assert saved_state["last_scheduler_run_at"] == now.isoformat()

    def test_last_inbox_sync_at_saved_when_run(self):
        ctrl = {"scheduler": {"run_mode": "scheduled"}}
        now = _now()
        _, mock_save = _pass(ctrl=ctrl, now_utc=now)
        saved_state = mock_save.call_args[0][2]["scheduler_state"]
        assert saved_state["last_inbox_sync_at"] == now.isoformat()

    def test_last_inbox_sync_at_not_saved_when_skipped(self):
        ctrl = {"scheduler": {"run_mode": "manual"}}
        _, mock_save = _pass(ctrl=ctrl)
        saved_state = mock_save.call_args[0][2]["scheduler_state"]
        assert "last_inbox_sync_at" not in saved_state or saved_state.get("last_inbox_sync_at") is None

    def test_last_status_success_on_ok(self):
        ctrl = {"scheduler": {"run_mode": "manual"}}
        _, mock_save = _pass(ctrl=ctrl)
        saved_state = mock_save.call_args[0][2]["scheduler_state"]
        assert saved_state["last_status"] == "success"

    def test_last_error_none_on_ok(self):
        ctrl = {"scheduler": {"run_mode": "manual"}}
        _, mock_save = _pass(ctrl=ctrl)
        saved_state = mock_save.call_args[0][2]["scheduler_state"]
        assert saved_state["last_error"] is None

    def test_existing_ctrl_keys_preserved(self):
        ctrl = {
            "scheduler": {"run_mode": "manual"},
            "automation": {"leads_enabled": True},
        }
        _, mock_save = _pass(ctrl=ctrl)
        saved = mock_save.call_args[0][2]
        assert saved.get("automation", {}).get("leads_enabled") is True


class TestSchedulerPassErrorHandling:
    def test_inbox_error_captured(self):
        ctrl = {"scheduler": {"run_mode": "scheduled"}}
        result, mock_save = _pass(ctrl=ctrl, inbox_raises=RuntimeError("timeout"))
        assert result["error"] == "timeout"

    def test_inbox_error_sets_failed_status(self):
        ctrl = {"scheduler": {"run_mode": "scheduled"}}
        _, mock_save = _pass(ctrl=ctrl, inbox_raises=RuntimeError("oops"))
        saved_state = mock_save.call_args[0][2]["scheduler_state"]
        assert saved_state["last_status"] == "failed"
        assert "oops" in saved_state["last_error"]

    def test_state_still_saved_on_error(self):
        ctrl = {"scheduler": {"run_mode": "scheduled"}}
        _, mock_save = _pass(ctrl=ctrl, inbox_raises=RuntimeError("fail"))
        mock_save.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════════
# POST /scheduler/run-once — aggregate behaviour
# ══════════════════════════════════════════════════════════════════════════════

class TestSchedulerRunOnce:
    def _run(self, records=None, stored_per_tenant=None, run_mode="scheduled",
             gmail=True, notif_enabled=False):
        from app.main import scheduler_run_once

        db = MagicMock()
        now = _now()
        recs = records or [_make_record("T1")]
        _stored = stored_per_tenant or {
            "T1": {
                "scheduler": {"run_mode": run_mode},
                "notifications": {
                    "enabled": notif_enabled,
                    "recipient_email": "ops@x.com" if notif_enabled else "",
                    "frequency": "daily",
                    "send_hour": 8,
                },
            }
        }

        with (
            patch(f"{_REPO}.get_settings", side_effect=lambda db, tid: _stored.get(tid, {})),
            patch(f"{_REPO}.update_settings"),
            patch(f"{_REPO}.list_all", return_value=recs),
            patch("app.main._run_gmail_inbox_sync", return_value={
                "processed": 1, "created_jobs": [], "continued_threads": 0,
                "deduped": 0, "errors": [],
            }),
            patch("app.main._compute_summary", return_value={}),
            patch("app.main._compute_roi", return_value={}),
            patch("app.main._build_digest_body", return_value=("S", "B")),
            patch("app.main.dispatch_action"),
            patch("app.main.get_settings", return_value=_mock_settings(gmail=gmail)),
        ):
            return scheduler_run_once(db=db, tenant_id="T1")

    def test_returns_required_keys(self):
        r = self._run()
        for k in ("status", "run_at", "tenants_checked", "inbox_syncs_run",
                  "digests_sent", "skipped", "errors", "tenant_results"):
            assert k in r, f"Missing: {k}"

    def test_tenants_checked_count(self):
        recs = [_make_record("T1"), _make_record("T2")]
        stored = {
            "T1": {"scheduler": {"run_mode": "manual"}},
            "T2": {"scheduler": {"run_mode": "manual"}},
        }
        r = self._run(records=recs, stored_per_tenant=stored)
        assert r["tenants_checked"] == 2

    def test_inbox_syncs_counted(self):
        r = self._run(run_mode="scheduled")
        assert r["inbox_syncs_run"] == 1

    def test_inbox_skipped_when_manual(self):
        r = self._run(run_mode="manual")
        assert r["inbox_syncs_run"] == 0

    def test_status_success_when_no_errors(self):
        r = self._run()
        assert r["status"] == "success"

    def test_errors_empty_on_clean_run(self):
        r = self._run()
        assert r["errors"] == []

    def test_tenant_results_list(self):
        r = self._run()
        assert isinstance(r["tenant_results"], list)
        assert len(r["tenant_results"]) == 1

    def test_run_at_is_iso_string(self):
        r = self._run()
        assert isinstance(r["run_at"], str)
        assert "T" in r["run_at"]

    def test_status_warning_when_errors(self):
        from app.main import scheduler_run_once

        db = MagicMock()
        recs = [_make_record("T1")]
        stored = {"T1": {"scheduler": {"run_mode": "scheduled"}}}

        with (
            patch(f"{_REPO}.get_settings", side_effect=lambda db, tid: stored.get(tid, {})),
            patch(f"{_REPO}.update_settings"),
            patch(f"{_REPO}.list_all", return_value=recs),
            patch("app.main._run_gmail_inbox_sync", side_effect=RuntimeError("fail")),
            patch("app.main._compute_summary", return_value={}),
            patch("app.main._compute_roi", return_value={}),
            patch("app.main._build_digest_body", return_value=("S", "B")),
            patch("app.main.dispatch_action"),
            patch("app.main.get_settings", return_value=_mock_settings(gmail=True)),
        ):
            r = scheduler_run_once(db=db, tenant_id="T1")
        assert r["status"] == "warning"
        assert len(r["errors"]) == 1
        assert r["errors"][0]["tenant_id"] == "T1"

    def test_digest_counted_when_sent(self):
        r = self._run(run_mode="manual", notif_enabled=True)
        assert r["digests_sent"] == 1

    def test_skipped_counted_when_both_skip(self):
        r = self._run(run_mode="manual", notif_enabled=False)
        assert r["skipped"] == 1
