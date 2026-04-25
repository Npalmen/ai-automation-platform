"""
Tests for WorkflowScannerEngine, GmailWorkflowScannerAdapter, and
the generic POST /workflow-scan/{system} endpoint.

Covers:
- Engine runs registered gmail adapter
- Engine persists result into memory.system_map and workflow_scan
- Engine merges workflow_scan.summary across multiple systems (no clobber)
- Engine preserves business_profile and routing_hints on success
- Engine preserves existing memory on adapter failure; sets status=failed
- Engine raises KeyError for unregistered system
- POST /workflow-scan/gmail delegates to engine (backwards compat)
- POST /workflow-scan/{system} works for gmail
- POST /workflow-scan/{system} returns 404 for unsupported system
- Tenant isolation: engine uses correct tenant_id in all repo calls
- ScanResult dataclass
- ADAPTER_REGISTRY contains gmail
- list_supported_systems returns gmail
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call
import pytest


# ---------------------------------------------------------------------------
# Shared record factory (matches test_gmail_scanner.py pattern)
# ---------------------------------------------------------------------------

def _make_record(
    tenant_id: str = "T1",
    job_type: str = "lead",
    sender_email: str = "alice@example.com",
    subject: str = "Offert förfrågan",
) -> MagicMock:
    r = MagicMock()
    r.tenant_id = tenant_id
    r.job_type = job_type
    r.input_data = {
        "subject": subject,
        "sender": {"email": sender_email, "name": "Alice"},
        "source": {"system": "gmail", "message_id": "msg-1", "thread_id": "thr-1"},
    }
    return r


def _make_db(records: list | None = None):
    db = MagicMock()
    chain = db.query.return_value.filter.return_value.order_by.return_value.limit.return_value
    chain.all.return_value = records or []
    return db


def _make_repo(existing: dict | None = None):
    repo = MagicMock()
    repo.get_settings.return_value = existing or {}
    return repo


# ---------------------------------------------------------------------------
# ScanResult dataclass
# ---------------------------------------------------------------------------

class TestScanResult:
    def test_defaults(self):
        from app.workflows.scanners.base import ScanResult
        r = ScanResult(system="gmail", status="completed", scanned_at="2026-04-26T00:00:00+00:00")
        assert r.data == {}
        assert r.summary == {}
        assert r.error is None

    def test_failed_result_holds_error(self):
        from app.workflows.scanners.base import ScanResult
        r = ScanResult(system="gmail", status="failed", scanned_at="2026-04-26T00:00:00+00:00",
                       error="DB exploded")
        assert r.error == "DB exploded"


# ---------------------------------------------------------------------------
# ADAPTER_REGISTRY and list_supported_systems
# ---------------------------------------------------------------------------

class TestAdapterRegistry:
    def test_gmail_registered(self):
        from app.workflows.scanners.engine import ADAPTER_REGISTRY
        assert "gmail" in ADAPTER_REGISTRY

    def test_list_supported_systems_returns_gmail(self):
        from app.workflows.scanners.engine import list_supported_systems
        assert "gmail" in list_supported_systems()

    def test_list_supported_systems_is_sorted(self):
        from app.workflows.scanners.engine import list_supported_systems
        systems = list_supported_systems()
        assert systems == sorted(systems)


# ---------------------------------------------------------------------------
# GmailWorkflowScannerAdapter
# ---------------------------------------------------------------------------

class TestGmailAdapter:
    def test_system_key_is_gmail(self):
        from app.workflows.scanners.gmail_adapter import GmailWorkflowScannerAdapter
        assert GmailWorkflowScannerAdapter.system_key == "gmail"

    def test_run_returns_scan_result(self):
        from app.workflows.scanners.gmail_adapter import GmailWorkflowScannerAdapter
        adapter = GmailWorkflowScannerAdapter()
        db = _make_db([_make_record()])
        result = adapter.run(db, "T1")
        assert result.system == "gmail"
        assert result.status == "completed"
        assert result.error is None

    def test_run_empty_mailbox(self):
        from app.workflows.scanners.gmail_adapter import GmailWorkflowScannerAdapter
        adapter = GmailWorkflowScannerAdapter()
        db = _make_db([])
        result = adapter.run(db, "T1")
        assert result.status == "completed"
        assert result.summary["messages_scanned"] == 0

    def test_run_populates_known_senders(self):
        from app.workflows.scanners.gmail_adapter import GmailWorkflowScannerAdapter
        adapter = GmailWorkflowScannerAdapter()
        db = _make_db([_make_record(sender_email="x@y.se")])
        result = adapter.run(db, "T1")
        assert any(s["email"] == "x@y.se" for s in result.data["known_senders"])

    def test_run_populates_detected_mail_types(self):
        from app.workflows.scanners.gmail_adapter import GmailWorkflowScannerAdapter
        adapter = GmailWorkflowScannerAdapter()
        db = _make_db([_make_record(job_type="invoice"), _make_record(job_type="lead")])
        result = adapter.run(db, "T1")
        assert "invoice" in result.data["detected_mail_types"]
        assert "lead" in result.data["detected_mail_types"]


# ---------------------------------------------------------------------------
# WorkflowScannerEngine — success path
# ---------------------------------------------------------------------------

class TestEngineSuccess:
    def _run_engine(self, records=None, existing=None, tenant_id="T1"):
        from app.workflows.scanners.engine import WorkflowScannerEngine
        db = _make_db(records)
        repo = _make_repo(existing)
        engine = WorkflowScannerEngine(db, tenant_id, repo)
        result = engine.run("gmail")
        return result, repo

    def test_returns_completed_result(self):
        result, _ = self._run_engine(records=[_make_record()])
        assert result.status == "completed"
        assert result.system == "gmail"

    def test_persists_system_map_gmail(self):
        _, repo = self._run_engine(records=[_make_record(sender_email="eng@co.se")])
        saved = repo.update_settings.call_args[0][2]
        gmail_map = saved["memory"]["system_map"]["gmail"]
        assert any(s["email"] == "eng@co.se" for s in gmail_map["known_senders"])

    def test_persists_workflow_scan_completed(self):
        _, repo = self._run_engine(records=[])
        saved = repo.update_settings.call_args[0][2]
        assert saved["workflow_scan"]["status"] == "completed"
        assert "gmail" in saved["workflow_scan"]["systems_scanned"]

    def test_does_not_clobber_business_profile(self):
        existing = {
            "memory": {"business_profile": {"company_name": "Acme AB"}},
            "notifications": {"enabled": True},
        }
        _, repo = self._run_engine(records=[], existing=existing)
        saved = repo.update_settings.call_args[0][2]
        assert saved["memory"]["business_profile"]["company_name"] == "Acme AB"
        assert saved["notifications"]["enabled"] is True

    def test_does_not_clobber_routing_hints(self):
        existing = {"memory": {"routing_hints": {"lead": "board-42"}}}
        _, repo = self._run_engine(records=[], existing=existing)
        saved = repo.update_settings.call_args[0][2]
        assert saved["memory"]["routing_hints"]["lead"] == "board-42"

    def test_merges_workflow_scan_summary_across_systems(self):
        """Running gmail scan must not clobber a previously stored monday summary."""
        existing = {
            "workflow_scan": {
                "last_scan_at": "2026-04-25T10:00:00+00:00",
                "systems_scanned": ["monday"],
                "status": "completed",
                "summary": {"monday": {"boards_scanned": 3}},
            }
        }
        _, repo = self._run_engine(records=[], existing=existing)
        saved = repo.update_settings.call_args[0][2]
        scan = saved["workflow_scan"]
        # gmail summary added
        assert "gmail" in scan["summary"]
        # monday summary preserved
        assert scan["summary"]["monday"]["boards_scanned"] == 3
        # both systems in list
        assert "gmail" in scan["systems_scanned"]
        assert "monday" in scan["systems_scanned"]

    def test_tenant_id_passed_to_repo(self):
        from app.workflows.scanners.engine import WorkflowScannerEngine
        db = _make_db([])
        repo = _make_repo()
        engine = WorkflowScannerEngine(db, "TENANT_XYZ", repo)
        engine.run("gmail")
        assert "TENANT_XYZ" in repo.get_settings.call_args[0]
        assert "TENANT_XYZ" in repo.update_settings.call_args[0]


# ---------------------------------------------------------------------------
# WorkflowScannerEngine — failure path
# ---------------------------------------------------------------------------

class TestEngineFailure:
    def test_raises_runtime_error_on_adapter_failure(self):
        from app.workflows.scanners.engine import WorkflowScannerEngine
        from app.workflows.scanners.gmail_adapter import GmailWorkflowScannerAdapter

        db = MagicMock()
        db.query.side_effect = RuntimeError("DB gone")
        repo = _make_repo()
        engine = WorkflowScannerEngine(db, "T1", repo)

        with pytest.raises(RuntimeError, match="gmail scan failed"):
            engine.run("gmail")

    def test_persists_failed_status_on_error(self):
        from app.workflows.scanners.engine import WorkflowScannerEngine

        db = MagicMock()
        db.query.side_effect = RuntimeError("DB gone")
        repo = _make_repo({"memory": {"business_profile": {"company_name": "Safe Co"}}})
        engine = WorkflowScannerEngine(db, "T1", repo)

        with pytest.raises(RuntimeError):
            engine.run("gmail")

        saved = repo.update_settings.call_args[0][2]
        assert saved["workflow_scan"]["status"] == "failed"

    def test_preserves_existing_memory_on_failure(self):
        from app.workflows.scanners.engine import WorkflowScannerEngine

        db = MagicMock()
        db.query.side_effect = RuntimeError("oops")
        existing = {
            "memory": {"business_profile": {"company_name": "Safe Co"}},
            "notifications": {"enabled": True},
        }
        repo = _make_repo(existing)
        engine = WorkflowScannerEngine(db, "T1", repo)

        with pytest.raises(RuntimeError):
            engine.run("gmail")

        saved = repo.update_settings.call_args[0][2]
        assert saved["memory"]["business_profile"]["company_name"] == "Safe Co"
        assert saved["notifications"]["enabled"] is True

    def test_raises_key_error_for_unregistered_system(self):
        from app.workflows.scanners.engine import WorkflowScannerEngine
        engine = WorkflowScannerEngine(_make_db(), "T1", _make_repo())
        with pytest.raises(KeyError, match="No scanner registered"):
            engine.run("visma")


# ---------------------------------------------------------------------------
# POST /workflow-scan/gmail (backwards compat)
# ---------------------------------------------------------------------------

def _call_scan_gmail(records=None, existing=None, tenant_id="T1"):
    from app.main import scan_gmail
    db = _make_db(records)
    with (
        patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
            return_value=existing or {},
        ),
        patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.update_settings"
        ) as mock_save,
    ):
        result = scan_gmail(db=db, tenant_id=tenant_id)
        return result, mock_save


class TestScanGmailEndpointBackwardsCompat:
    def test_returns_completed(self):
        result, _ = _call_scan_gmail(records=[_make_record()])
        assert result["status"] == "completed"

    def test_returns_gmail_in_systems_scanned(self):
        result, _ = _call_scan_gmail(records=[])
        assert "gmail" in result["systems_scanned"]

    def test_returns_gmail_summary(self):
        result, _ = _call_scan_gmail(records=[_make_record()])
        assert "gmail" in result["summary"]

    def test_updates_settings(self):
        _, mock_save = _call_scan_gmail(records=[])
        assert mock_save.called

    def test_empty_mailbox_ok(self):
        result, _ = _call_scan_gmail(records=[])
        assert result["status"] == "completed"
        assert result["summary"]["gmail"]["messages_scanned"] == 0


# ---------------------------------------------------------------------------
# POST /workflow-scan/{system} — generic endpoint
# ---------------------------------------------------------------------------

def _call_generic(system, records=None, existing=None, tenant_id="T1"):
    from app.main import scan_workflow_system
    db = _make_db(records)
    with (
        patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
            return_value=existing or {},
        ),
        patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.update_settings"
        ) as mock_save,
    ):
        result = scan_workflow_system(system=system, db=db, tenant_id=tenant_id)
        return result, mock_save


class TestGenericScanEndpoint:
    def test_gmail_works_via_generic_endpoint(self):
        result, _ = _call_generic("gmail", records=[_make_record()])
        assert result["status"] == "completed"
        assert "gmail" in result["systems_scanned"]

    def test_gmail_generic_returns_summary(self):
        result, _ = _call_generic("gmail", records=[])
        assert "gmail" in result["summary"]

    def test_unsupported_system_raises_404(self):
        from app.main import scan_workflow_system
        from fastapi import HTTPException
        db = _make_db()
        with pytest.raises(HTTPException) as exc_info:
            scan_workflow_system(system="visma", db=db, tenant_id="T1")
        assert exc_info.value.status_code == 404

    def test_unsupported_system_error_mentions_system(self):
        from app.main import scan_workflow_system
        from fastapi import HTTPException
        db = _make_db()
        with pytest.raises(HTTPException) as exc_info:
            scan_workflow_system(system="fortnox", db=db, tenant_id="T1")
        assert "fortnox" in exc_info.value.detail

    def test_generic_preserves_business_profile(self):
        existing = {"memory": {"business_profile": {"company_name": "Generic Corp"}}}
        _, mock_save = _call_generic("gmail", records=[], existing=existing)
        saved = mock_save.call_args[0][2]
        assert saved["memory"]["business_profile"]["company_name"] == "Generic Corp"

    def test_generic_tenant_isolation(self):
        from app.main import scan_workflow_system
        db = _make_db([])
        with (
            patch(
                "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
                return_value={},
            ) as mock_get,
            patch(
                "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.update_settings"
            ) as mock_save,
        ):
            scan_workflow_system(system="gmail", db=db, tenant_id="TENANT_ABC")
        assert "TENANT_ABC" in mock_get.call_args[0]
        assert "TENANT_ABC" in mock_save.call_args[0]
