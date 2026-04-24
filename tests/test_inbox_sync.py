"""Tests for POST /dashboard/inbox-sync — wired to real Gmail processing logic.

Uses direct function calls with mocked settings and _run_gmail_inbox_sync.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_settings(google_token: str = ""):
    s = MagicMock()
    s.GOOGLE_MAIL_ACCESS_TOKEN = google_token
    return s


def _raw_result(
    scanned: int = 0,
    processed: int = 0,
    skipped: int = 0,
    failed: int = 0,
    created_jobs: list | None = None,
    skipped_messages: list | None = None,
    failed_messages: list | None = None,
) -> dict:
    return {
        "processed":        processed,
        "skipped":          skipped,
        "failed":           failed,
        "scanned":          scanned,
        "dry_run":          False,
        "query_used":       "is:unread",
        "max_results":      10,
        "created_jobs":     created_jobs or [],
        "skipped_messages": skipped_messages or [],
        "failed_messages":  failed_messages or [],
    }


def _sync(google_token: str = "tok", raw: dict | None = None, sync_raises: Exception | None = None):
    from app.main import trigger_inbox_sync

    db = MagicMock()
    s = _make_settings(google_token=google_token)

    with patch("app.main.get_settings", return_value=s):
        if sync_raises is not None:
            with patch("app.main._run_gmail_inbox_sync", side_effect=sync_raises):
                return trigger_inbox_sync(db=db, tenant_id="T1")
        with patch("app.main._run_gmail_inbox_sync", return_value=raw or _raw_result()):
            return trigger_inbox_sync(db=db, tenant_id="T1")


def _sync_503():
    """Call with no Gmail credentials — expect HTTPException."""
    from app.main import trigger_inbox_sync

    db = MagicMock()
    s = _make_settings(google_token="")
    with patch("app.main.get_settings", return_value=s):
        with pytest.raises(HTTPException) as exc_info:
            trigger_inbox_sync(db=db, tenant_id="T1")
    return exc_info.value


# ══════════════════════════════════════════════════════════════════════════════
# Missing credentials
# ══════════════════════════════════════════════════════════════════════════════

class TestInboxSyncMissingCredentials:
    def test_raises_503_when_no_gmail_token(self):
        exc = _sync_503()
        assert exc.status_code == 503

    def test_503_detail_is_dict(self):
        exc = _sync_503()
        assert isinstance(exc.detail, dict)

    def test_503_detail_status_failed(self):
        assert _sync_503().detail["status"] == "failed"

    def test_503_detail_has_message(self):
        exc = _sync_503()
        assert "message" in exc.detail
        assert "Gmail" in exc.detail["message"] or "gmail" in exc.detail["message"].lower()

    def test_503_detail_has_zero_counts(self):
        d = _sync_503().detail
        assert d["processed"] == 0
        assert d["created_jobs"] == 0
        assert d["continued_threads"] == 0
        assert d["deduped"] == 0

    def test_503_detail_errors_is_list(self):
        assert isinstance(_sync_503().detail["errors"], list)


# ══════════════════════════════════════════════════════════════════════════════
# Response shape
# ══════════════════════════════════════════════════════════════════════════════

class TestInboxSyncShape:
    def test_returns_all_required_keys(self):
        r = _sync()
        for key in ("status", "processed", "created_jobs", "continued_threads",
                    "deduped", "errors", "message"):
            assert key in r, f"Missing key: {key}"

    def test_status_is_valid_value(self):
        assert _sync()["status"] in ("success", "warning", "failed")

    def test_errors_is_list(self):
        assert isinstance(_sync()["errors"], list)

    def test_message_is_string(self):
        assert isinstance(_sync()["message"], str)

    def test_numeric_fields_are_ints(self):
        r = _sync()
        for key in ("processed", "created_jobs", "continued_threads", "deduped"):
            assert isinstance(r[key], int), f"{key} should be int"


# ══════════════════════════════════════════════════════════════════════════════
# Success path — count mapping
# ══════════════════════════════════════════════════════════════════════════════

class TestInboxSyncSuccessPath:
    def test_empty_inbox_returns_success(self):
        r = _sync(raw=_raw_result(scanned=0))
        assert r["status"] == "success"
        assert r["processed"] == 0
        assert r["created_jobs"] == 0

    def test_new_job_counted_in_created_jobs(self):
        raw = _raw_result(
            scanned=1, processed=1,
            created_jobs=[{"continued": False, "message_id": "M1", "job_id": "J1"}],
        )
        r = _sync(raw=raw)
        assert r["created_jobs"] == 1
        assert r["continued_threads"] == 0

    def test_continued_thread_counted_separately(self):
        raw = _raw_result(
            scanned=1, processed=1,
            created_jobs=[{"continued": True, "message_id": "M1", "job_id": "J1"}],
        )
        r = _sync(raw=raw)
        assert r["continued_threads"] == 1
        assert r["created_jobs"] == 0

    def test_deduped_count_from_duplicate_skips(self):
        raw = _raw_result(
            scanned=2, processed=0, skipped=2,
            skipped_messages=[
                {"message_id": "M1", "reason": "duplicate"},
                {"message_id": "M2", "reason": "duplicate"},
            ],
        )
        r = _sync(raw=raw)
        assert r["deduped"] == 2

    def test_type_gated_skip_not_counted_as_deduped(self):
        raw = _raw_result(
            scanned=1, processed=0, skipped=1,
            skipped_messages=[{"message_id": "M1", "reason": "lead_disabled"}],
        )
        r = _sync(raw=raw)
        assert r["deduped"] == 0

    def test_failed_messages_mapped_to_errors(self):
        raw = _raw_result(
            scanned=1, processed=0, failed=1,
            failed_messages=[{"message_id": "M1", "reason": "get_message failed"}],
        )
        r = _sync(raw=raw)
        assert len(r["errors"]) == 1
        assert "get_message failed" in r["errors"][0]["message"]

    def test_status_warning_when_some_failed_some_processed(self):
        raw = _raw_result(
            scanned=2, processed=1, failed=1,
            created_jobs=[{"continued": False, "message_id": "M1", "job_id": "J1"}],
            failed_messages=[{"message_id": "M2", "reason": "timeout"}],
        )
        r = _sync(raw=raw)
        assert r["status"] == "warning"

    def test_status_failed_when_all_failed(self):
        raw = _raw_result(
            scanned=1, processed=0, failed=1,
            failed_messages=[{"message_id": "M1", "reason": "timeout"}],
        )
        r = _sync(raw=raw)
        assert r["status"] == "failed"

    def test_message_mentions_scanned_count(self):
        raw = _raw_result(scanned=5, processed=3, skipped=2)
        r = _sync(raw=raw)
        assert "5" in r["message"]


# ══════════════════════════════════════════════════════════════════════════════
# Processor raises
# ══════════════════════════════════════════════════════════════════════════════

class TestInboxSyncProcessorRaises:
    def test_unexpected_exception_raises_500(self):
        with pytest.raises(HTTPException) as exc_info:
            _sync(sync_raises=RuntimeError("Unexpected crash"))
        assert exc_info.value.status_code == 500

    def test_500_detail_status_failed(self):
        with pytest.raises(HTTPException) as exc_info:
            _sync(sync_raises=RuntimeError("boom"))
        assert exc_info.value.detail["status"] == "failed"

    def test_httpe_passthrough(self):
        """An HTTPException from _run_gmail_inbox_sync passes through unchanged."""
        inner = HTTPException(status_code=503, detail="Gmail API down")
        with pytest.raises(HTTPException) as exc_info:
            _sync(sync_raises=inner)
        assert exc_info.value.status_code == 503


# ══════════════════════════════════════════════════════════════════════════════
# Tenant isolation
# ══════════════════════════════════════════════════════════════════════════════

class TestInboxSyncTenantIsolation:
    def test_run_gmail_called_with_correct_tenant(self):
        from app.main import trigger_inbox_sync

        db = MagicMock()
        s = _make_settings(google_token="tok")
        captured: list[str] = []

        def _capture(**kwargs):
            captured.append(kwargs.get("tenant_id", ""))
            return _raw_result()

        with (
            patch("app.main.get_settings", return_value=s),
            patch("app.main._run_gmail_inbox_sync", side_effect=_capture),
        ):
            trigger_inbox_sync(db=db, tenant_id="TENANT_XYZ")

        assert captured == ["TENANT_XYZ"]
