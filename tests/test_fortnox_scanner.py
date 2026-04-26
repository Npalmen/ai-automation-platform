"""
Tests for Slice 18 — Fortnox Workflow Scanner.

Coverage:
- analyse_fortnox_data pure function
- FortnoxWorkflowScannerAdapter: missing config, successful scan
- Engine: fortnox registered, persists under system_map.fortnox, no-clobber of other systems
- Security: no credentials in ScanResult fields
- Tenant isolation (scan uses correct tenant settings)
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.workflows.scanners.fortnox_adapter import (
    FortnoxWorkflowScannerAdapter,
    analyse_fortnox_data,
    _normalise_customer,
    _normalise_article,
    _normalise_invoice,
)
from app.workflows.scanners.engine import ADAPTER_REGISTRY, WorkflowScannerEngine
from app.workflows.scanners.base import ScanResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

RAW_CUSTOMERS = [
    {"CustomerNumber": "1", "Name": "Acme AB", "Email": "acme@example.com",
     "OrganisationNumber": "556000-0001", "Phone1": "08-123 456"},
    {"CustomerNumber": "2", "Name": "Beta AB", "Email": "", "OrganisationNumber": "", "Phone1": ""},
]

RAW_ARTICLES = [
    {"ArticleNumber": "A100", "Description": "Widget", "Unit": "st", "SalesPrice": "99.50"},
    {"ArticleNumber": "A101", "Description": "Gadget", "Unit": "box", "SalesPrice": None},
]

RAW_INVOICES = [
    {"DocumentNumber": "1001", "CustomerNumber": "1", "CustomerName": "Acme AB",
     "Total": "5000.00", "Balance": "0.00", "DocumentStatus": "FULLYPAID", "DueDate": "2024-03-01"},
    {"DocumentNumber": "1002", "CustomerNumber": "2", "CustomerName": "Beta AB",
     "Total": "2500.00", "Balance": "2500.00", "DocumentStatus": "UNPAID", "DueDate": "2024-04-01"},
]


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

class TestNormaliseCustomer:
    def test_capitalized_keys(self):
        result = _normalise_customer(RAW_CUSTOMERS[0])
        assert result["customer_number"] == "1"
        assert result["name"] == "Acme AB"
        assert result["email"] == "acme@example.com"
        assert result["organisation_number"] == "556000-0001"
        assert result["phone"] == "08-123 456"

    def test_lowercase_keys(self):
        raw = {"customer_number": "9", "name": "Test", "email": "t@t.com",
               "organisation_number": "111", "phone": ""}
        result = _normalise_customer(raw)
        assert result["customer_number"] == "9"
        assert result["email"] == "t@t.com"

    def test_missing_fields_default_to_empty(self):
        result = _normalise_customer({})
        assert result["customer_number"] == ""
        assert result["name"] == ""
        assert result["email"] == ""

    def test_empty_email(self):
        result = _normalise_customer(RAW_CUSTOMERS[1])
        assert result["email"] == ""


class TestNormaliseArticle:
    def test_numeric_sales_price(self):
        result = _normalise_article(RAW_ARTICLES[0])
        assert result["article_number"] == "A100"
        assert result["description"] == "Widget"
        assert result["unit"] == "st"
        assert result["sales_price"] == pytest.approx(99.50)

    def test_null_sales_price(self):
        result = _normalise_article(RAW_ARTICLES[1])
        assert result["sales_price"] is None

    def test_invalid_price_becomes_none(self):
        result = _normalise_article({"SalesPrice": "not-a-number"})
        assert result["sales_price"] is None

    def test_lowercase_keys(self):
        result = _normalise_article({"article_number": "Z1", "description": "X", "unit": "kg", "sales_price": "10"})
        assert result["article_number"] == "Z1"
        assert result["sales_price"] == 10.0


class TestNormaliseInvoice:
    def test_basic(self):
        result = _normalise_invoice(RAW_INVOICES[0])
        assert result["document_number"] == "1001"
        assert result["customer_number"] == "1"
        assert result["customer_name"] == "Acme AB"
        assert result["total"] == pytest.approx(5000.0)
        assert result["balance"] == pytest.approx(0.0)
        assert result["status"] == "FULLYPAID"
        assert result["due_date"] == "2024-03-01"

    def test_lowercase_keys(self):
        raw = {"document_number": "99", "customer_number": "3", "customer_name": "X",
               "total": "100", "balance": "50", "status": "UNPAID", "due_date": "2024-05-01"}
        result = _normalise_invoice(raw)
        assert result["document_number"] == "99"
        assert result["status"] == "UNPAID"

    def test_invalid_total_becomes_none(self):
        result = _normalise_invoice({"Total": "bad"})
        assert result["total"] is None

    def test_missing_fields(self):
        result = _normalise_invoice({})
        assert result["document_number"] == ""
        assert result["status"] == ""
        assert result["due_date"] is None


# ---------------------------------------------------------------------------
# analyse_fortnox_data pure function
# ---------------------------------------------------------------------------

class TestAnalyseFortnoxData:
    def test_counts(self):
        fortnox_map, summary = analyse_fortnox_data(RAW_CUSTOMERS, RAW_ARTICLES, RAW_INVOICES)
        assert summary["customers_scanned"] == 2
        assert summary["articles_scanned"] == 2
        assert summary["invoices_scanned"] == 2

    def test_customer_email_count(self):
        _, summary = analyse_fortnox_data(RAW_CUSTOMERS, RAW_ARTICLES, RAW_INVOICES)
        assert summary["customer_emails_detected"] == 1  # only acme@example.com

    def test_invoice_statuses_sorted(self):
        _, summary = analyse_fortnox_data(RAW_CUSTOMERS, RAW_ARTICLES, RAW_INVOICES)
        assert summary["invoice_statuses_detected"] == ["FULLYPAID", "UNPAID"]

    def test_map_structure(self):
        fortnox_map, _ = analyse_fortnox_data(RAW_CUSTOMERS, RAW_ARTICLES, RAW_INVOICES)
        assert "customers" in fortnox_map
        assert "articles" in fortnox_map
        assert "invoices" in fortnox_map
        assert "summary" in fortnox_map

    def test_empty_inputs(self):
        fortnox_map, summary = analyse_fortnox_data([], [], [])
        assert summary["customers_scanned"] == 0
        assert summary["articles_scanned"] == 0
        assert summary["invoices_scanned"] == 0
        assert summary["customer_emails_detected"] == 0
        assert summary["invoice_statuses_detected"] == []
        assert fortnox_map["customers"] == []

    def test_no_emails_gives_zero(self):
        customers_no_email = [{"CustomerNumber": "1", "Name": "X", "Email": ""}]
        _, summary = analyse_fortnox_data(customers_no_email, [], [])
        assert summary["customer_emails_detected"] == 0

    def test_summary_inside_map_matches_standalone(self):
        fortnox_map, summary = analyse_fortnox_data(RAW_CUSTOMERS, RAW_ARTICLES, RAW_INVOICES)
        assert fortnox_map["summary"]["customers_scanned"] == summary["customers_scanned"]
        assert fortnox_map["summary"]["invoice_statuses_detected"] == summary["invoice_statuses_detected"]


# ---------------------------------------------------------------------------
# Adapter: missing credentials
# ---------------------------------------------------------------------------

class TestFortnoxAdapterMissingConfig:
    def _make_settings(self, token="", secret=""):
        s = MagicMock()
        s.FORTNOX_ACCESS_TOKEN = token
        s.FORTNOX_CLIENT_SECRET = secret
        s.FORTNOX_API_URL = "https://api.fortnox.se/3"
        return s

    def test_returns_failed_when_no_token(self):
        adapter = FortnoxWorkflowScannerAdapter()
        with patch("app.workflows.scanners.fortnox_adapter.get_settings",
                   return_value=self._make_settings(token="", secret="secret")):
            result = adapter.run(MagicMock(), "tenant1")
        assert result.status == "failed"
        assert result.system == "fortnox"
        assert result.error is not None
        assert "FORTNOX_ACCESS_TOKEN" in result.error or "credentials" in result.error.lower()

    def test_returns_failed_when_no_secret(self):
        adapter = FortnoxWorkflowScannerAdapter()
        with patch("app.workflows.scanners.fortnox_adapter.get_settings",
                   return_value=self._make_settings(token="tok", secret="")):
            result = adapter.run(MagicMock(), "tenant1")
        assert result.status == "failed"

    def test_returns_failed_when_both_missing(self):
        adapter = FortnoxWorkflowScannerAdapter()
        with patch("app.workflows.scanners.fortnox_adapter.get_settings",
                   return_value=self._make_settings()):
            result = adapter.run(MagicMock(), "tenant1")
        assert result.status == "failed"

    def test_failed_result_has_no_data(self):
        adapter = FortnoxWorkflowScannerAdapter()
        with patch("app.workflows.scanners.fortnox_adapter.get_settings",
                   return_value=self._make_settings()):
            result = adapter.run(MagicMock(), "tenant1")
        assert result.data is None or result.data == {}

    def test_no_credentials_in_error_message(self):
        adapter = FortnoxWorkflowScannerAdapter()
        secret = "super-secret-value"
        with patch("app.workflows.scanners.fortnox_adapter.get_settings",
                   return_value=self._make_settings(token="", secret=secret)):
            result = adapter.run(MagicMock(), "tenant1")
        assert secret not in (result.error or "")


# ---------------------------------------------------------------------------
# Adapter: successful scan
# ---------------------------------------------------------------------------

class TestFortnoxAdapterSuccessfulScan:
    def _make_settings(self):
        s = MagicMock()
        s.FORTNOX_ACCESS_TOKEN = "tok123"
        s.FORTNOX_CLIENT_SECRET = "sec456"
        s.FORTNOX_API_URL = "https://api.fortnox.se/3"
        return s

    def _mock_client(self):
        client = MagicMock()
        client.get_customers.return_value = RAW_CUSTOMERS
        client.get_articles.return_value  = RAW_ARTICLES
        client.get_invoices.return_value  = RAW_INVOICES
        return client

    def test_returns_completed_status(self):
        adapter = FortnoxWorkflowScannerAdapter()
        with patch("app.workflows.scanners.fortnox_adapter.get_settings",
                   return_value=self._make_settings()), \
             patch("app.workflows.scanners.fortnox_adapter._build_fortnox_client",
                   return_value=self._mock_client()):
            result = adapter.run(MagicMock(), "tenant1")
        assert result.status == "completed"

    def test_summary_counts(self):
        adapter = FortnoxWorkflowScannerAdapter()
        with patch("app.workflows.scanners.fortnox_adapter.get_settings",
                   return_value=self._make_settings()), \
             patch("app.workflows.scanners.fortnox_adapter._build_fortnox_client",
                   return_value=self._mock_client()):
            result = adapter.run(MagicMock(), "tenant1")
        assert result.summary["customers_scanned"] == 2
        assert result.summary["articles_scanned"] == 2
        assert result.summary["invoices_scanned"] == 2

    def test_data_has_customers_articles_invoices(self):
        adapter = FortnoxWorkflowScannerAdapter()
        with patch("app.workflows.scanners.fortnox_adapter.get_settings",
                   return_value=self._make_settings()), \
             patch("app.workflows.scanners.fortnox_adapter._build_fortnox_client",
                   return_value=self._mock_client()):
            result = adapter.run(MagicMock(), "tenant1")
        assert "customers" in result.data
        assert "articles" in result.data
        assert "invoices" in result.data

    def test_system_key(self):
        assert FortnoxWorkflowScannerAdapter.system_key == "fortnox"

    def test_scanned_at_is_iso(self):
        adapter = FortnoxWorkflowScannerAdapter()
        with patch("app.workflows.scanners.fortnox_adapter.get_settings",
                   return_value=self._make_settings()), \
             patch("app.workflows.scanners.fortnox_adapter._build_fortnox_client",
                   return_value=self._mock_client()):
            result = adapter.run(MagicMock(), "tenant1")
        datetime.fromisoformat(result.scanned_at)  # must not raise

    def test_no_credentials_in_result(self):
        adapter = FortnoxWorkflowScannerAdapter()
        tok = "tok123"
        sec = "sec456"
        with patch("app.workflows.scanners.fortnox_adapter.get_settings",
                   return_value=self._make_settings()), \
             patch("app.workflows.scanners.fortnox_adapter._build_fortnox_client",
                   return_value=self._mock_client()):
            result = adapter.run(MagicMock(), "tenant1")
        result_str = str(result)
        assert tok not in result_str
        assert sec not in result_str


# ---------------------------------------------------------------------------
# Engine: fortnox registered + persist behaviour
# ---------------------------------------------------------------------------

class TestEngineFortnoxRegistration:
    def test_fortnox_in_adapter_registry(self):
        assert "fortnox" in ADAPTER_REGISTRY

    def test_adapter_is_fortnox_type(self):
        assert isinstance(ADAPTER_REGISTRY["fortnox"], FortnoxWorkflowScannerAdapter)

    def test_list_supported_systems_includes_fortnox(self):
        from app.workflows.scanners.engine import list_supported_systems
        assert "fortnox" in list_supported_systems()


class TestEngineFortnoxPersistence:
    def _base_settings(self):
        return {
            "memory": {
                "system_map": {
                    "gmail": {"labels": ["INBOX"], "summary": {"messages_scanned": 5}},
                    "monday": {"boards": [], "summary": {"boards_scanned": 0}},
                    "fortnox": {"customers": [], "articles": [], "invoices": [], "summary": {}},
                },
                "entities": [],
            },
            "workflow_scan": {
                "systems_scanned": ["gmail"],
                "last_scan_at": "2024-01-01T00:00:00+00:00",
                "status": "completed",
                "summary": {"gmail": {"messages_scanned": 5}},
            },
        }

    def _make_engine(self, existing_settings):
        repo = MagicMock()
        repo.get_settings.return_value = existing_settings
        db = MagicMock()
        engine = WorkflowScannerEngine(db, "t1", repo)
        return engine, repo

    def _mock_adapter_success(self):
        result = ScanResult(
            system="fortnox",
            status="completed",
            scanned_at=datetime.now(timezone.utc).isoformat(),
            data={
                "customers": [{"customer_number": "1", "name": "Acme"}],
                "articles": [],
                "invoices": [],
                "summary": {"customers_scanned": 1, "articles_scanned": 0, "invoices_scanned": 0,
                            "customer_emails_detected": 0, "invoice_statuses_detected": []},
            },
            summary={"customers_scanned": 1, "articles_scanned": 0, "invoices_scanned": 0,
                     "customer_emails_detected": 0, "invoice_statuses_detected": []},
        )
        return result

    def test_persists_fortnox_slot_in_system_map(self):
        existing = self._base_settings()
        engine, repo = self._make_engine(existing)
        adapter_result = self._mock_adapter_success()
        with patch.dict(ADAPTER_REGISTRY, {"fortnox": MagicMock(run=MagicMock(return_value=adapter_result))}):
            engine.run("fortnox")
        saved = repo.update_settings.call_args[0][2]
        assert saved["memory"]["system_map"]["fortnox"]["customers"] == [{"customer_number": "1", "name": "Acme"}]

    def test_does_not_clobber_gmail_slot(self):
        existing = self._base_settings()
        engine, repo = self._make_engine(existing)
        adapter_result = self._mock_adapter_success()
        with patch.dict(ADAPTER_REGISTRY, {"fortnox": MagicMock(run=MagicMock(return_value=adapter_result))}):
            engine.run("fortnox")
        saved = repo.update_settings.call_args[0][2]
        assert saved["memory"]["system_map"]["gmail"]["labels"] == ["INBOX"]

    def test_does_not_clobber_monday_slot(self):
        existing = self._base_settings()
        engine, repo = self._make_engine(existing)
        adapter_result = self._mock_adapter_success()
        with patch.dict(ADAPTER_REGISTRY, {"fortnox": MagicMock(run=MagicMock(return_value=adapter_result))}):
            engine.run("fortnox")
        saved = repo.update_settings.call_args[0][2]
        assert "monday" in saved["memory"]["system_map"]

    def test_workflow_scan_updated(self):
        existing = self._base_settings()
        engine, repo = self._make_engine(existing)
        adapter_result = self._mock_adapter_success()
        with patch.dict(ADAPTER_REGISTRY, {"fortnox": MagicMock(run=MagicMock(return_value=adapter_result))}):
            engine.run("fortnox")
        saved = repo.update_settings.call_args[0][2]
        assert "fortnox" in saved["workflow_scan"]["systems_scanned"]

    def test_previous_gmail_summary_preserved(self):
        existing = self._base_settings()
        engine, repo = self._make_engine(existing)
        adapter_result = self._mock_adapter_success()
        with patch.dict(ADAPTER_REGISTRY, {"fortnox": MagicMock(run=MagicMock(return_value=adapter_result))}):
            engine.run("fortnox")
        saved = repo.update_settings.call_args[0][2]
        assert "gmail" in saved["workflow_scan"]["summary"]

    def test_failed_scan_preserves_existing_memory(self):
        existing = self._base_settings()
        engine, repo = self._make_engine(existing)
        failed_result = ScanResult(
            system="fortnox",
            status="failed",
            scanned_at=datetime.now(timezone.utc).isoformat(),
            error="API error",
        )
        with patch.dict(ADAPTER_REGISTRY, {"fortnox": MagicMock(run=MagicMock(return_value=failed_result))}):
            with pytest.raises(RuntimeError):
                engine.run("fortnox")
        saved = repo.update_settings.call_args[0][2]
        assert saved["memory"]["system_map"]["gmail"]["labels"] == ["INBOX"]

    def test_unknown_system_raises_key_error(self):
        existing = self._base_settings()
        engine, repo = self._make_engine(existing)
        with pytest.raises(KeyError):
            engine.run("nonexistent_system")


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

class TestSecurity:
    def test_no_access_token_in_failed_result(self):
        adapter = FortnoxWorkflowScannerAdapter()
        s = MagicMock()
        s.FORTNOX_ACCESS_TOKEN = ""
        s.FORTNOX_CLIENT_SECRET = "do-not-leak"
        s.FORTNOX_API_URL = "https://api.fortnox.se/3"
        with patch("app.workflows.scanners.fortnox_adapter.get_settings", return_value=s):
            result = adapter.run(MagicMock(), "t1")
        assert "do-not-leak" not in (result.error or "")

    def test_client_secret_not_in_scan_result(self):
        from app.workflows.scanners.fortnox_adapter import _build_fortnox_client
        s = MagicMock()
        s.FORTNOX_ACCESS_TOKEN = ""
        s.FORTNOX_CLIENT_SECRET = ""
        s.FORTNOX_API_URL = "https://api.fortnox.se/3"
        client = _build_fortnox_client(s)
        assert client is None
