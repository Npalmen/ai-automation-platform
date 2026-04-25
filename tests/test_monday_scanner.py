"""
Tests for Monday workflow scanner adapter and its integration with the engine.

Covers:
- analyse_boards() pure analysis function
- detect_board_purpose() keyword mapping (lead, invoice, support, etc.)
- MondayWorkflowScannerAdapter: system_key, run() success, missing API key
- ADAPTER_REGISTRY contains "monday"
- POST /workflow-scan/monday via engine
- Monday scan persists under tenant_memory.system_map.monday
- Monday scan does NOT clobber system_map.gmail
- Monday scan does NOT clobber business_profile or routing_hints
- workflow_scan.summary merges gmail + monday (no clobber)
- Failed Monday scan (missing token) preserves existing memory
- Failed Monday scan sets workflow_scan.status = "failed"
- Tenant isolation
- get_boards added to MondayClient (read-only)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest


# ---------------------------------------------------------------------------
# Board factory helpers
# ---------------------------------------------------------------------------

def _make_board(
    id: str = "1",
    name: str = "Test Board",
    description: str = "",
    groups: list | None = None,
    columns: list | None = None,
) -> dict:
    return {
        "id": id,
        "name": name,
        "description": description,
        "groups": groups or [{"id": "topics", "title": "Incoming"}],
        "columns": columns or [{"id": "status", "title": "Status", "type": "status"}],
    }


def _make_db():
    return MagicMock()


def _make_repo(existing: dict | None = None):
    repo = MagicMock()
    repo.get_settings.return_value = existing or {}
    return repo


# ---------------------------------------------------------------------------
# analyse_boards — pure analysis helper
# ---------------------------------------------------------------------------

class TestAnalyseBoards:
    def test_empty_boards_returns_zeroes(self):
        from app.workflows.scanners.monday_adapter import analyse_boards
        monday_map, summary = analyse_boards([])
        assert summary["boards_scanned"] == 0
        assert summary["groups_detected"] == 0
        assert summary["columns_detected"] == 0
        assert summary["detected_purposes"] == []
        assert monday_map["boards"] == []
        assert monday_map["groups"] == []
        assert monday_map["columns"] == []

    def test_single_board_extracted(self):
        from app.workflows.scanners.monday_adapter import analyse_boards
        board = _make_board(id="10", name="Leads", groups=[{"id": "g1", "title": "Active"}],
                            columns=[{"id": "c1", "title": "Status", "type": "status"}])
        monday_map, summary = analyse_boards([board])
        assert summary["boards_scanned"] == 1
        assert len(monday_map["boards"]) == 1
        assert monday_map["boards"][0]["id"] == "10"
        assert monday_map["boards"][0]["name"] == "Leads"

    def test_flattened_groups_include_board_ref(self):
        from app.workflows.scanners.monday_adapter import analyse_boards
        board = _make_board(id="5", name="Sales",
                            groups=[{"id": "g1", "title": "New Leads"}])
        monday_map, _ = analyse_boards([board])
        assert len(monday_map["groups"]) == 1
        g = monday_map["groups"][0]
        assert g["board_id"] == "5"
        assert g["board_name"] == "Sales"
        assert g["id"] == "g1"
        assert g["title"] == "New Leads"

    def test_flattened_columns_include_board_ref(self):
        from app.workflows.scanners.monday_adapter import analyse_boards
        board = _make_board(id="7", name="Support",
                            columns=[{"id": "c2", "title": "Priority", "type": "dropdown"}])
        monday_map, _ = analyse_boards([board])
        assert len(monday_map["columns"]) == 1
        c = monday_map["columns"][0]
        assert c["board_id"] == "7"
        assert c["board_name"] == "Support"
        assert c["type"] == "dropdown"

    def test_multiple_boards_flattened_correctly(self):
        from app.workflows.scanners.monday_adapter import analyse_boards
        b1 = _make_board(id="1", name="A", groups=[{"id": "g1", "title": "G1"}])
        b2 = _make_board(id="2", name="B", groups=[{"id": "g2", "title": "G2"}, {"id": "g3", "title": "G3"}])
        monday_map, summary = analyse_boards([b1, b2])
        assert summary["boards_scanned"] == 2
        assert summary["groups_detected"] == 3

    def test_detected_purposes_sorted_unique(self):
        from app.workflows.scanners.monday_adapter import analyse_boards
        b1 = _make_board(name="Leads board")
        b2 = _make_board(name="Another Leads")
        b3 = _make_board(name="Faktura system")
        monday_map, summary = analyse_boards([b1, b2, b3])
        assert "lead" in summary["detected_purposes"]
        assert "invoice" in summary["detected_purposes"]
        assert summary["detected_purposes"] == sorted(summary["detected_purposes"])
        assert summary["detected_purposes"].count("lead") == 1  # deduped

    def test_board_has_detected_purpose_field(self):
        from app.workflows.scanners.monday_adapter import analyse_boards
        board = _make_board(name="Sales Pipeline")
        monday_map, _ = analyse_boards([board])
        assert "detected_purpose" in monday_map["boards"][0]


# ---------------------------------------------------------------------------
# detect_board_purpose — keyword mapping
# ---------------------------------------------------------------------------

class TestDetectBoardPurpose:
    def _detect(self, name="", description="", groups=None, columns=None):
        from app.workflows.scanners.monday_adapter import detect_board_purpose
        return detect_board_purpose({
            "name": name,
            "description": description,
            "groups": groups or [],
            "columns": columns or [],
        })

    def test_lead_from_name_leads(self):
        assert self._detect(name="Leads") == "lead"

    def test_lead_from_name_sales(self):
        assert self._detect(name="Sales Pipeline") == "lead"

    def test_lead_from_name_offert(self):
        assert self._detect(name="Offert hantering") == "lead"

    def test_lead_from_name_quote(self):
        assert self._detect(name="Quote board") == "lead"

    def test_invoice_from_name_faktura(self):
        assert self._detect(name="Faktura hantering") == "invoice"

    def test_invoice_from_name_billing(self):
        assert self._detect(name="Billing System") == "invoice"

    def test_invoice_from_name_ekonomi(self):
        assert self._detect(name="Ekonomi") == "invoice"

    def test_support_from_name_support(self):
        assert self._detect(name="Customer Support") == "support"

    def test_support_from_name_ticket(self):
        assert self._detect(name="Ticket System") == "support"

    def test_support_from_name_helpdesk(self):
        assert self._detect(name="Helpdesk") == "support"

    def test_partnership_from_name(self):
        assert self._detect(name="Partnership Tracker") == "partnership"

    def test_supplier_from_name(self):
        assert self._detect(name="Leverantör Board") == "supplier"

    def test_internal_from_name(self):
        assert self._detect(name="Intern admin") == "internal"

    def test_unknown_fallback(self):
        assert self._detect(name="Misc Stuff 2024") == "unknown"

    def test_detects_from_group_title(self):
        assert self._detect(name="General", groups=[{"title": "Leads incoming"}]) == "lead"

    def test_detects_from_column_title(self):
        assert self._detect(name="Board", columns=[{"title": "Invoice number", "type": "text"}]) == "invoice"

    def test_detects_from_description(self):
        assert self._detect(name="Board", description="Tracks all support tickets") == "support"


# ---------------------------------------------------------------------------
# MondayWorkflowScannerAdapter
# ---------------------------------------------------------------------------

class TestMondayAdapter:
    def test_system_key_is_monday(self):
        from app.workflows.scanners.monday_adapter import MondayWorkflowScannerAdapter
        assert MondayWorkflowScannerAdapter.system_key == "monday"

    def test_run_success_returns_completed(self):
        from app.workflows.scanners.monday_adapter import MondayWorkflowScannerAdapter
        adapter = MondayWorkflowScannerAdapter()
        mock_settings = MagicMock()
        mock_settings.MONDAY_API_KEY = "test-key"
        mock_settings.MONDAY_API_URL = "https://api.monday.com/v2"

        mock_client = MagicMock()
        mock_client.get_boards.return_value = [_make_board(name="Leads")]

        with (
            patch("app.workflows.scanners.monday_adapter.get_settings", return_value=mock_settings),
            patch("app.workflows.scanners.monday_adapter._build_monday_client", return_value=mock_client),
        ):
            result = adapter.run(_make_db(), "T1")

        assert result.status == "completed"
        assert result.system == "monday"
        assert result.error is None

    def test_run_missing_api_key_returns_failed(self):
        from app.workflows.scanners.monday_adapter import MondayWorkflowScannerAdapter
        adapter = MondayWorkflowScannerAdapter()
        mock_settings = MagicMock()
        mock_settings.MONDAY_API_KEY = ""

        with patch("app.workflows.scanners.monday_adapter.get_settings", return_value=mock_settings):
            result = adapter.run(_make_db(), "T1")

        assert result.status == "failed"
        assert result.error is not None
        assert "MONDAY_API_KEY" in result.error

    def test_run_populates_boards_in_data(self):
        from app.workflows.scanners.monday_adapter import MondayWorkflowScannerAdapter
        adapter = MondayWorkflowScannerAdapter()
        mock_settings = MagicMock()
        mock_settings.MONDAY_API_KEY = "key"
        mock_settings.MONDAY_API_URL = "https://api.monday.com/v2"

        mock_client = MagicMock()
        mock_client.get_boards.return_value = [_make_board(id="99", name="Sales")]

        with (
            patch("app.workflows.scanners.monday_adapter.get_settings", return_value=mock_settings),
            patch("app.workflows.scanners.monday_adapter._build_monday_client", return_value=mock_client),
        ):
            result = adapter.run(_make_db(), "T1")

        assert len(result.data["boards"]) == 1
        assert result.data["boards"][0]["name"] == "Sales"

    def test_run_no_boards_returns_completed_empty(self):
        from app.workflows.scanners.monday_adapter import MondayWorkflowScannerAdapter
        adapter = MondayWorkflowScannerAdapter()
        mock_settings = MagicMock()
        mock_settings.MONDAY_API_KEY = "key"
        mock_settings.MONDAY_API_URL = "https://api.monday.com/v2"

        mock_client = MagicMock()
        mock_client.get_boards.return_value = []

        with (
            patch("app.workflows.scanners.monday_adapter.get_settings", return_value=mock_settings),
            patch("app.workflows.scanners.monday_adapter._build_monday_client", return_value=mock_client),
        ):
            result = adapter.run(_make_db(), "T1")

        assert result.status == "completed"
        assert result.summary["boards_scanned"] == 0


# ---------------------------------------------------------------------------
# ADAPTER_REGISTRY includes monday
# ---------------------------------------------------------------------------

class TestAdapterRegistryMonday:
    def test_monday_in_registry(self):
        from app.workflows.scanners.engine import ADAPTER_REGISTRY
        assert "monday" in ADAPTER_REGISTRY

    def test_list_supported_includes_monday(self):
        from app.workflows.scanners.engine import list_supported_systems
        assert "monday" in list_supported_systems()


# ---------------------------------------------------------------------------
# Engine + POST /workflow-scan/monday
# ---------------------------------------------------------------------------

def _call_monday_scan(
    boards: list | None = None,
    existing: dict | None = None,
    tenant_id: str = "T1",
    api_key: str = "test-key",
):
    from app.main import scan_workflow_system
    db = _make_db()
    mock_settings = MagicMock()
    mock_settings.MONDAY_API_KEY = api_key
    mock_settings.MONDAY_API_URL = "https://api.monday.com/v2"

    mock_client = MagicMock()
    mock_client.get_boards.return_value = boards if boards is not None else []

    with (
        patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
            return_value=existing or {},
        ),
        patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.update_settings"
        ) as mock_save,
        patch("app.workflows.scanners.monday_adapter.get_settings", return_value=mock_settings),
        patch("app.workflows.scanners.monday_adapter._build_monday_client", return_value=mock_client),
    ):
        result = scan_workflow_system(system="monday", db=db, tenant_id=tenant_id)
        return result, mock_save


class TestMondayScanEndpoint:
    def test_returns_completed(self):
        result, _ = _call_monday_scan(boards=[_make_board()])
        assert result["status"] == "completed"

    def test_returns_monday_in_systems_scanned(self):
        result, _ = _call_monday_scan()
        assert "monday" in result["systems_scanned"]

    def test_returns_monday_summary(self):
        result, _ = _call_monday_scan(boards=[_make_board()])
        assert "monday" in result["summary"]
        s = result["summary"]["monday"]
        assert "boards_scanned" in s
        assert "groups_detected" in s
        assert "columns_detected" in s
        assert "detected_purposes" in s

    def test_persists_system_map_monday(self):
        _, mock_save = _call_monday_scan(boards=[_make_board(id="55", name="Leads")])
        saved = mock_save.call_args[0][2]
        monday_map = saved["memory"]["system_map"]["monday"]
        assert len(monday_map["boards"]) == 1
        assert monday_map["boards"][0]["id"] == "55"

    def test_does_not_clobber_system_map_gmail(self):
        existing = {
            "memory": {
                "system_map": {
                    "gmail": {"known_senders": [{"email": "a@b.se", "count": 3}]},
                }
            }
        }
        _, mock_save = _call_monday_scan(boards=[], existing=existing)
        saved = mock_save.call_args[0][2]
        assert saved["memory"]["system_map"]["gmail"]["known_senders"][0]["email"] == "a@b.se"

    def test_does_not_clobber_business_profile(self):
        existing = {
            "memory": {"business_profile": {"company_name": "Preserved Co"}}
        }
        _, mock_save = _call_monday_scan(boards=[], existing=existing)
        saved = mock_save.call_args[0][2]
        assert saved["memory"]["business_profile"]["company_name"] == "Preserved Co"

    def test_does_not_clobber_routing_hints(self):
        existing = {
            "memory": {"routing_hints": {"lead": "board-999"}}
        }
        _, mock_save = _call_monday_scan(boards=[], existing=existing)
        saved = mock_save.call_args[0][2]
        assert saved["memory"]["routing_hints"]["lead"] == "board-999"

    def test_merges_workflow_scan_summary_with_gmail(self):
        existing = {
            "workflow_scan": {
                "last_scan_at": "2026-04-26T09:00:00+00:00",
                "systems_scanned": ["gmail"],
                "status": "completed",
                "summary": {"gmail": {"messages_scanned": 10}},
            }
        }
        _, mock_save = _call_monday_scan(boards=[], existing=existing)
        saved = mock_save.call_args[0][2]
        scan = saved["workflow_scan"]
        assert "gmail" in scan["systems_scanned"]
        assert "monday" in scan["systems_scanned"]
        assert scan["summary"]["gmail"]["messages_scanned"] == 10
        assert "monday" in scan["summary"]

    def test_empty_boards_handled_safely(self):
        result, _ = _call_monday_scan(boards=[])
        assert result["status"] == "completed"
        assert result["summary"]["monday"]["boards_scanned"] == 0

    def test_tenant_isolation(self):
        from app.main import scan_workflow_system
        db = _make_db()
        mock_settings = MagicMock()
        mock_settings.MONDAY_API_KEY = "key"
        mock_settings.MONDAY_API_URL = "https://api.monday.com/v2"
        mock_client = MagicMock()
        mock_client.get_boards.return_value = []

        with (
            patch(
                "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
                return_value={},
            ) as mock_get,
            patch(
                "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.update_settings"
            ) as mock_save,
            patch("app.workflows.scanners.monday_adapter.get_settings", return_value=mock_settings),
            patch("app.workflows.scanners.monday_adapter._build_monday_client", return_value=mock_client),
        ):
            scan_workflow_system(system="monday", db=db, tenant_id="TENANT_XYZ")

        assert "TENANT_XYZ" in mock_get.call_args[0]
        assert "TENANT_XYZ" in mock_save.call_args[0]


class TestMondayScanFailure:
    def test_missing_api_key_returns_http_500(self):
        from app.main import scan_workflow_system
        from fastapi import HTTPException
        db = _make_db()
        mock_settings = MagicMock()
        mock_settings.MONDAY_API_KEY = ""  # missing

        with (
            patch(
                "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
                return_value={},
            ),
            patch(
                "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.update_settings"
            ),
            patch("app.workflows.scanners.monday_adapter.get_settings", return_value=mock_settings),
        ):
            with pytest.raises(HTTPException) as exc_info:
                scan_workflow_system(system="monday", db=db, tenant_id="T1")

        assert exc_info.value.status_code == 500

    def test_failed_scan_sets_workflow_scan_failed(self):
        from app.main import scan_workflow_system
        from fastapi import HTTPException
        db = _make_db()
        mock_settings = MagicMock()
        mock_settings.MONDAY_API_KEY = ""
        captured = {}

        def fake_update(db, tenant_id, settings):
            captured.update(settings)

        with (
            patch(
                "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
                return_value={"memory": {"business_profile": {"company_name": "Safe"}}},
            ),
            patch(
                "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.update_settings",
                side_effect=fake_update,
            ),
            patch("app.workflows.scanners.monday_adapter.get_settings", return_value=mock_settings),
        ):
            with pytest.raises(HTTPException):
                scan_workflow_system(system="monday", db=db, tenant_id="T1")

        assert captured.get("workflow_scan", {}).get("status") == "failed"
        assert captured.get("memory", {}).get("business_profile", {}).get("company_name") == "Safe"

    def test_failed_scan_preserves_existing_monday_system_map(self):
        from app.main import scan_workflow_system
        from fastapi import HTTPException
        db = _make_db()
        mock_settings = MagicMock()
        mock_settings.MONDAY_API_KEY = ""
        captured = {}

        existing = {
            "memory": {
                "system_map": {
                    "monday": {"boards": [{"id": "old", "name": "Old Board"}]}
                }
            }
        }

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
            patch("app.workflows.scanners.monday_adapter.get_settings", return_value=mock_settings),
        ):
            with pytest.raises(HTTPException):
                scan_workflow_system(system="monday", db=db, tenant_id="T1")

        # Existing monday system_map preserved (engine's preserve_memory=True path)
        saved_monday = captured.get("memory", {}).get("system_map", {}).get("monday", {})
        assert saved_monday.get("boards", [{}])[0].get("id") == "old"


# ---------------------------------------------------------------------------
# MondayClient.get_boards — read-only method
# ---------------------------------------------------------------------------

class TestMondayClientGetBoards:
    def test_get_boards_issues_correct_graphql(self):
        from app.integrations.monday.client import MondayClient
        client = MondayClient(api_key="key")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "data": {"boards": [{"id": "1", "name": "Test", "description": "",
                                 "groups": [], "columns": []}]}
        }
        with patch("app.integrations.monday.client.requests.post", return_value=mock_response) as mock_post:
            boards = client.get_boards(limit=10)

        assert len(boards) == 1
        assert boards[0]["id"] == "1"
        call_json = mock_post.call_args[1]["json"]
        assert "boards" in call_json["query"]
        assert call_json["variables"]["limit"] == 10

    def test_get_boards_returns_empty_list_on_no_data(self):
        from app.integrations.monday.client import MondayClient
        client = MondayClient(api_key="key")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"data": {"boards": None}}
        with patch("app.integrations.monday.client.requests.post", return_value=mock_response):
            boards = client.get_boards()
        assert boards == []
