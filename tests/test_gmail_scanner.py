"""
Tests for POST /workflow-scan/gmail and the _scan_gmail_jobs analysis helper.

Pattern: direct function calls with mocked DB — consistent with repo test pattern.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Helpers — lightweight JobRecord stand-in for unit tests
# ---------------------------------------------------------------------------

def _make_record(
    tenant_id: str = "T1",
    job_type: str = "lead",
    sender_email: str = "alice@example.com",
    subject: str = "Offert förfrågan",
    source_system: str = "gmail",
) -> MagicMock:
    r = MagicMock()
    r.tenant_id = tenant_id
    r.job_type = job_type
    r.input_data = {
        "subject": subject,
        "sender": {"email": sender_email, "name": "Alice"},
        "source": {"system": source_system, "message_id": "msg-1", "thread_id": "thr-1"},
    }
    return r


def _make_db_with_records(records: list, settings: dict | None = None):
    """Return a mocked DB whose query chain returns `records`."""
    db = MagicMock()
    chain = db.query.return_value.filter.return_value.order_by.return_value.limit.return_value
    chain.all.return_value = records
    return db


def _scan(tenant_id: str = "T1", records: list | None = None, existing_settings: dict | None = None):
    from app.main import scan_gmail
    db = _make_db_with_records(records or [])
    with (
        patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
            return_value=existing_settings or {},
        ),
        patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.update_settings"
        ) as mock_save,
    ):
        result = scan_gmail(db=db, tenant_id=tenant_id)
        return result, mock_save


# ---------------------------------------------------------------------------
# Unit tests — _scan_gmail_jobs pure helper
# ---------------------------------------------------------------------------

class TestScanGmailJobsHelper:
    def test_empty_records_returns_zeroes(self):
        from app.main import _scan_gmail_jobs
        gmail_map, summary = _scan_gmail_jobs([])
        assert summary["messages_scanned"] == 0
        assert summary["senders_detected"] == 0
        assert summary["patterns_detected"] == 0
        assert summary["mail_types_detected"] == []
        assert gmail_map["known_senders"] == []
        assert gmail_map["subject_patterns"] == []
        assert gmail_map["detected_mail_types"] == []

    def test_single_record_extracted(self):
        from app.main import _scan_gmail_jobs
        r = _make_record(sender_email="bob@co.se", subject="Offert", job_type="lead")
        gmail_map, summary = _scan_gmail_jobs([r])
        assert summary["messages_scanned"] == 1
        assert any(s["email"] == "bob@co.se" for s in gmail_map["known_senders"])
        assert "lead" in gmail_map["detected_mail_types"]

    def test_known_senders_counts_correctly(self):
        from app.main import _scan_gmail_jobs
        records = [
            _make_record(sender_email="a@b.se"),
            _make_record(sender_email="a@b.se"),
            _make_record(sender_email="c@d.se"),
        ]
        gmail_map, summary = _scan_gmail_jobs(records)
        senders = {s["email"]: s["count"] for s in gmail_map["known_senders"]}
        assert senders["a@b.se"] == 2
        assert senders["c@d.se"] == 1
        assert summary["senders_detected"] == 2

    def test_subject_patterns_strip_re_prefix(self):
        from app.main import _scan_gmail_jobs
        r1 = _make_record(subject="Re: Offert förfrågan")
        r2 = _make_record(subject="Offert förfrågan")
        gmail_map, _ = _scan_gmail_jobs([r1, r2])
        patterns = {p["pattern"]: p["count"] for p in gmail_map["subject_patterns"]}
        # Both should normalise to "Offert förfrågan"
        assert "Offert förfrågan" in patterns
        assert patterns["Offert förfrågan"] == 2

    def test_subject_patterns_strip_fwd_prefix(self):
        from app.main import _scan_gmail_jobs
        r = _make_record(subject="Fwd: Faktura 2024")
        gmail_map, _ = _scan_gmail_jobs([r])
        patterns = [p["pattern"] for p in gmail_map["subject_patterns"]]
        assert "Faktura 2024" in patterns

    def test_subject_patterns_strip_sv_prefix(self):
        from app.main import _scan_gmail_jobs
        r = _make_record(subject="Sv: Fråga om service")
        gmail_map, _ = _scan_gmail_jobs([r])
        patterns = [p["pattern"] for p in gmail_map["subject_patterns"]]
        assert "Fråga om service" in patterns

    def test_detected_mail_types_sorted(self):
        from app.main import _scan_gmail_jobs
        records = [
            _make_record(job_type="invoice"),
            _make_record(job_type="lead"),
            _make_record(job_type="invoice"),
        ]
        gmail_map, summary = _scan_gmail_jobs(records)
        assert "invoice" in gmail_map["detected_mail_types"]
        assert "lead" in gmail_map["detected_mail_types"]
        assert gmail_map["detected_mail_types"] == sorted(gmail_map["detected_mail_types"])

    def test_known_senders_limited_to_top_20(self):
        from app.main import _scan_gmail_jobs
        records = [_make_record(sender_email=f"user{i}@co.se") for i in range(30)]
        gmail_map, _ = _scan_gmail_jobs(records)
        assert len(gmail_map["known_senders"]) <= 20

    def test_subject_patterns_limited_to_top_20(self):
        from app.main import _scan_gmail_jobs
        records = [_make_record(subject=f"Unik ämnesrad nummer {i}") for i in range(30)]
        gmail_map, _ = _scan_gmail_jobs(records)
        assert len(gmail_map["subject_patterns"]) <= 20

    def test_flat_sender_email_fallback(self):
        """Records with flat sender_email key (not nested sender dict) are parsed correctly."""
        from app.main import _scan_gmail_jobs
        r = MagicMock()
        r.job_type = "lead"
        r.input_data = {
            "subject": "Test",
            "sender_email": "flat@example.com",
            "sender": {},
            "source": {"system": "gmail"},
        }
        gmail_map, _ = _scan_gmail_jobs([r])
        assert any(s["email"] == "flat@example.com" for s in gmail_map["known_senders"])

    def test_missing_sender_does_not_crash(self):
        from app.main import _scan_gmail_jobs
        r = MagicMock()
        r.job_type = "lead"
        r.input_data = {"subject": "No sender", "source": {"system": "gmail"}}
        gmail_map, summary = _scan_gmail_jobs([r])
        assert summary["messages_scanned"] == 1
        assert gmail_map["known_senders"] == []


# ---------------------------------------------------------------------------
# POST /workflow-scan/gmail — endpoint tests
# ---------------------------------------------------------------------------

class TestScanGmailEndpoint:
    def test_returns_completed_status(self):
        result, _ = _scan(records=[_make_record()])
        assert result["status"] == "completed"

    def test_returns_gmail_in_systems_scanned(self):
        result, _ = _scan(records=[])
        assert "gmail" in result["systems_scanned"]

    def test_returns_last_scan_at_iso_string(self):
        result, _ = _scan(records=[])
        assert result["last_scan_at"] is not None
        # Must be parseable as ISO datetime
        datetime.fromisoformat(result["last_scan_at"].replace("Z", "+00:00"))

    def test_returns_gmail_summary(self):
        result, _ = _scan(records=[_make_record()])
        assert "gmail" in result["summary"]
        s = result["summary"]["gmail"]
        assert "messages_scanned" in s
        assert "senders_detected" in s
        assert "patterns_detected" in s
        assert "mail_types_detected" in s

    def test_updates_system_map_gmail_in_settings(self):
        _, mock_save = _scan(records=[_make_record(sender_email="x@y.se")])
        assert mock_save.called
        saved_settings = mock_save.call_args[0][2]
        assert "memory" in saved_settings
        gmail_map = saved_settings["memory"]["system_map"]["gmail"]
        assert any(s["email"] == "x@y.se" for s in gmail_map["known_senders"])

    def test_updates_workflow_scan_in_settings(self):
        _, mock_save = _scan(records=[])
        saved_settings = mock_save.call_args[0][2]
        assert "workflow_scan" in saved_settings
        assert saved_settings["workflow_scan"]["status"] == "completed"
        assert "gmail" in saved_settings["workflow_scan"]["systems_scanned"]

    def test_empty_mailbox_handled_safely(self):
        result, mock_save = _scan(records=[])
        assert result["status"] == "completed"
        assert result["summary"]["gmail"]["messages_scanned"] == 0
        assert mock_save.called

    def test_does_not_clobber_existing_business_profile(self):
        existing = {
            "memory": {
                "business_profile": {"company_name": "Acme AB", "industry": "Bygg"},
                "routing_hints": {"lead": "board-111"},
            },
            "notifications": {"enabled": True},
        }
        _, mock_save = _scan(records=[], existing_settings=existing)
        saved = mock_save.call_args[0][2]
        assert saved["memory"]["business_profile"]["company_name"] == "Acme AB"
        assert saved["memory"]["routing_hints"]["lead"] == "board-111"
        assert saved["notifications"]["enabled"] is True

    def test_does_not_clobber_routing_hints(self):
        existing = {
            "memory": {"routing_hints": {"invoice": "board-999"}}
        }
        _, mock_save = _scan(records=[], existing_settings=existing)
        saved = mock_save.call_args[0][2]
        assert saved["memory"]["routing_hints"]["invoice"] == "board-999"

    def test_tenant_isolation(self):
        from app.main import scan_gmail
        db = _make_db_with_records([])
        with (
            patch(
                "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
                return_value={},
            ) as mock_get,
            patch(
                "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.update_settings"
            ) as mock_save,
        ):
            scan_gmail(db=db, tenant_id="TENANT_XYZ")

        assert "TENANT_XYZ" in mock_get.call_args[0]
        assert "TENANT_XYZ" in mock_save.call_args[0]

    def test_scan_failure_preserves_existing_memory(self):
        """When DB query raises, existing memory is not destroyed and status=failed."""
        from app.main import scan_gmail
        import pytest
        from fastapi import HTTPException

        db = MagicMock()
        # Make db.query raise to simulate DB error
        db.query.side_effect = RuntimeError("DB exploded")

        existing = {
            "memory": {"business_profile": {"company_name": "Safe Co"}},
            "notifications": {"enabled": False},
        }
        captured = {}

        def fake_update(db, tenant_id, settings):
            captured.update(settings)

        with (
            patch(
                "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
                return_value=existing,
            ),
            patch(
                "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.update_settings",
                side_effect=fake_update,
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                scan_gmail(db=db, tenant_id="T1")

        assert exc_info.value.status_code == 500
        # Existing memory must be intact
        assert captured.get("memory", {}).get("business_profile", {}).get("company_name") == "Safe Co"
        # workflow_scan status must be failed
        assert captured.get("workflow_scan", {}).get("status") == "failed"

    def test_scan_sets_detected_mail_types(self):
        records = [
            _make_record(job_type="lead"),
            _make_record(job_type="invoice"),
            _make_record(job_type="lead"),
        ]
        result, _ = _scan(records=records)
        types = result["summary"]["gmail"]["mail_types_detected"]
        assert "lead" in types
        assert "invoice" in types


# ---------------------------------------------------------------------------
# GET /workflow-scan/status — returns persisted state after scan
# ---------------------------------------------------------------------------

class TestWorkflowScanStatusAfterScan:
    def test_status_returns_completed_after_scan(self):
        from app.main import workflow_scan_status
        stored = {
            "workflow_scan": {
                "last_scan_at": "2026-04-26T12:00:00+00:00",
                "systems_scanned": ["gmail"],
                "status": "completed",
                "summary": {"gmail": {"messages_scanned": 42, "senders_detected": 5,
                                      "patterns_detected": 8, "mail_types_detected": ["lead"]}},
            }
        }
        db = MagicMock()
        with patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
            return_value=stored,
        ):
            result = workflow_scan_status(db=db, tenant_id="T1")

        assert result["status"] == "completed"
        assert result["last_scan_at"] == "2026-04-26T12:00:00+00:00"
        assert "gmail" in result["systems_scanned"]
        assert result["summary"]["gmail"]["messages_scanned"] == 42

    def test_status_returns_failed_after_failed_scan(self):
        from app.main import workflow_scan_status
        stored = {
            "workflow_scan": {
                "last_scan_at": "2026-04-26T12:00:00+00:00",
                "systems_scanned": ["gmail"],
                "status": "failed",
                "summary": {"error": "DB exploded"},
            }
        }
        db = MagicMock()
        with patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
            return_value=stored,
        ):
            result = workflow_scan_status(db=db, tenant_id="T1")
        assert result["status"] == "failed"
