"""
Tests for Slice 19 — Fortnox Customer + Invoice Action Endpoints.

Pattern: call route functions and _get_fortnox_client_or_raise directly (no httpx).
Patches app.main.get_settings and app.main._get_fortnox_client_or_raise.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.main import (
    _get_fortnox_client_or_raise,
    fortnox_customer_lookup,
    fortnox_customer_create,
    fortnox_invoice_lookup,
)


def _make_settings(token="tok123", secret="sec456", api_url="https://api.fortnox.se/3"):
    s = MagicMock()
    s.FORTNOX_ACCESS_TOKEN  = token
    s.FORTNOX_CLIENT_SECRET = secret
    s.FORTNOX_API_URL       = api_url
    return s


def _db():
    return MagicMock()


# ---------------------------------------------------------------------------
# _get_fortnox_client_or_raise
# ---------------------------------------------------------------------------

class TestGetFortnoxClientOrRaise:
    def test_returns_client_when_configured(self):
        with patch("app.main.get_settings", return_value=_make_settings()):
            client = _get_fortnox_client_or_raise()
        from app.integrations.fortnox.client import FortnoxClient
        assert isinstance(client, FortnoxClient)

    def test_raises_503_when_no_token(self):
        with patch("app.main.get_settings", return_value=_make_settings(token="")):
            with pytest.raises(HTTPException) as exc_info:
                _get_fortnox_client_or_raise()
        assert exc_info.value.status_code == 503

    def test_raises_503_when_no_secret(self):
        with patch("app.main.get_settings", return_value=_make_settings(secret="")):
            with pytest.raises(HTTPException) as exc_info:
                _get_fortnox_client_or_raise()
        assert exc_info.value.status_code == 503

    def test_raises_503_when_both_missing(self):
        with patch("app.main.get_settings", return_value=_make_settings(token="", secret="")):
            with pytest.raises(HTTPException) as exc_info:
                _get_fortnox_client_or_raise()
        assert exc_info.value.status_code == 503

    def test_503_detail_does_not_leak_credentials(self):
        with patch("app.main.get_settings", return_value=_make_settings(token="", secret="my-secret")):
            with pytest.raises(HTTPException) as exc_info:
                _get_fortnox_client_or_raise()
        assert "my-secret" not in str(exc_info.value.detail)


# ---------------------------------------------------------------------------
# Customer lookup
# ---------------------------------------------------------------------------

class TestFortnoxCustomerLookup:
    def _mock_client(self, by_email=None, by_name=None):
        c = MagicMock()
        c.find_customer_by_email.return_value = by_email
        c.find_customer_by_name.return_value  = by_name
        return c

    def test_lookup_by_email_found(self):
        customer = {"CustomerNumber": "1", "Name": "Acme AB", "Email": "acme@example.com"}
        mock_client = self._mock_client(by_email=customer)
        with patch("app.main._get_fortnox_client_or_raise", return_value=mock_client):
            result = fortnox_customer_lookup({"email": "acme@example.com"}, db=_db(), tenant_id="t1")
        assert result["customer"]["Name"] == "Acme AB"

    def test_lookup_by_email_not_found_returns_none(self):
        mock_client = self._mock_client(by_email=None, by_name=None)
        with patch("app.main._get_fortnox_client_or_raise", return_value=mock_client):
            result = fortnox_customer_lookup({"email": "nobody@x.com"}, db=_db(), tenant_id="t1")
        assert result["customer"] is None

    def test_lookup_by_name_fallback_when_email_misses(self):
        customer = {"CustomerNumber": "2", "Name": "Beta AB"}
        mock_client = self._mock_client(by_email=None, by_name=customer)
        with patch("app.main._get_fortnox_client_or_raise", return_value=mock_client):
            result = fortnox_customer_lookup({"email": "nope@x.com", "name": "Beta"}, db=_db(), tenant_id="t1")
        assert result["customer"]["CustomerNumber"] == "2"

    def test_lookup_by_name_only(self):
        customer = {"CustomerNumber": "3", "Name": "Gamma"}
        mock_client = self._mock_client(by_name=customer)
        with patch("app.main._get_fortnox_client_or_raise", return_value=mock_client):
            result = fortnox_customer_lookup({"name": "Gamma"}, db=_db(), tenant_id="t1")
        assert result["customer"]["CustomerNumber"] == "3"
        mock_client.find_customer_by_email.assert_not_called()

    def test_missing_both_fields_raises_422(self):
        with patch("app.main._get_fortnox_client_or_raise", return_value=MagicMock()):
            with pytest.raises(HTTPException) as exc_info:
                fortnox_customer_lookup({}, db=_db(), tenant_id="t1")
        assert exc_info.value.status_code == 422

    def test_missing_credentials_raises_503(self):
        with patch("app.main.get_settings", return_value=_make_settings(token="", secret="")):
            with pytest.raises(HTTPException) as exc_info:
                fortnox_customer_lookup({"email": "x@x.com"}, db=_db(), tenant_id="t1")
        assert exc_info.value.status_code == 503

    def test_503_detail_does_not_leak_credentials(self):
        with patch("app.main.get_settings", return_value=_make_settings(token="", secret="super-secret")):
            with pytest.raises(HTTPException) as exc_info:
                fortnox_customer_lookup({"email": "x@x.com"}, db=_db(), tenant_id="t1")
        assert "super-secret" not in str(exc_info.value.detail)

    def test_find_by_email_called_with_email(self):
        mock_client = self._mock_client(by_email={"CustomerNumber": "1"})
        with patch("app.main._get_fortnox_client_or_raise", return_value=mock_client):
            fortnox_customer_lookup({"email": "test@x.com"}, db=_db(), tenant_id="t1")
        mock_client.find_customer_by_email.assert_called_once_with("test@x.com")

    def test_empty_string_fields_treated_as_missing(self):
        with patch("app.main._get_fortnox_client_or_raise", return_value=MagicMock()):
            with pytest.raises(HTTPException) as exc_info:
                fortnox_customer_lookup({"email": "", "name": "   "}, db=_db(), tenant_id="t1")
        assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# Customer create
# ---------------------------------------------------------------------------

class TestFortnoxCustomerCreate:
    def _mock_client(self, return_value=None):
        c = MagicMock()
        c.create_customer.return_value = return_value or {"Customer": {"CustomerNumber": "99", "Name": "New Co"}}
        return c

    def test_create_minimal(self):
        mock_client = self._mock_client()
        with patch("app.main._get_fortnox_client_or_raise", return_value=mock_client):
            result = fortnox_customer_create({"name": "New Co"}, db=_db(), tenant_id="t1")
        assert result["customer"]["CustomerNumber"] == "99"

    def test_create_full_payload(self):
        mock_client = self._mock_client({"Customer": {"CustomerNumber": "100"}})
        with patch("app.main._get_fortnox_client_or_raise", return_value=mock_client):
            fortnox_customer_create({
                "name": "Full Co",
                "email": "full@co.se",
                "organisation_number": "556000-0001",
                "phone": "08-555 666",
            }, db=_db(), tenant_id="t1")
        call_payload = mock_client.create_customer.call_args[0][0]
        assert call_payload["Email"] == "full@co.se"
        assert call_payload["OrganisationNumber"] == "556000-0001"
        assert call_payload["Phone1"] == "08-555 666"

    def test_create_name_in_payload(self):
        mock_client = self._mock_client()
        with patch("app.main._get_fortnox_client_or_raise", return_value=mock_client):
            fortnox_customer_create({"name": "My Corp"}, db=_db(), tenant_id="t1")
        call_payload = mock_client.create_customer.call_args[0][0]
        assert call_payload["Name"] == "My Corp"

    def test_create_optional_fields_absent_when_not_provided(self):
        mock_client = self._mock_client()
        with patch("app.main._get_fortnox_client_or_raise", return_value=mock_client):
            fortnox_customer_create({"name": "Minimal"}, db=_db(), tenant_id="t1")
        call_payload = mock_client.create_customer.call_args[0][0]
        assert "Email" not in call_payload
        assert "OrganisationNumber" not in call_payload
        assert "Phone1" not in call_payload

    def test_missing_name_raises_422(self):
        with patch("app.main._get_fortnox_client_or_raise", return_value=MagicMock()):
            with pytest.raises(HTTPException) as exc_info:
                fortnox_customer_create({"email": "x@x.com"}, db=_db(), tenant_id="t1")
        assert exc_info.value.status_code == 422

    def test_empty_name_raises_422(self):
        with patch("app.main._get_fortnox_client_or_raise", return_value=MagicMock()):
            with pytest.raises(HTTPException) as exc_info:
                fortnox_customer_create({"name": "   "}, db=_db(), tenant_id="t1")
        assert exc_info.value.status_code == 422

    def test_missing_credentials_raises_503(self):
        with patch("app.main.get_settings", return_value=_make_settings(token="", secret="")):
            with pytest.raises(HTTPException) as exc_info:
                fortnox_customer_create({"name": "X"}, db=_db(), tenant_id="t1")
        assert exc_info.value.status_code == 503

    def test_response_unwraps_customer_key(self):
        mock_client = self._mock_client({"Customer": {"CustomerNumber": "77", "Name": "Wrapped"}})
        with patch("app.main._get_fortnox_client_or_raise", return_value=mock_client):
            result = fortnox_customer_create({"name": "Wrapped"}, db=_db(), tenant_id="t1")
        assert result["customer"]["CustomerNumber"] == "77"


# ---------------------------------------------------------------------------
# Invoice lookup
# ---------------------------------------------------------------------------

class TestFortnoxInvoiceLookup:
    def test_lookup_by_document_number_found(self):
        invoice = {"DocumentNumber": "1001", "CustomerName": "Acme"}
        mock_client = MagicMock()
        mock_client.find_invoice_by_document_number.return_value = invoice
        with patch("app.main._get_fortnox_client_or_raise", return_value=mock_client):
            result = fortnox_invoice_lookup({"document_number": "1001"}, db=_db(), tenant_id="t1")
        assert result["invoice"]["DocumentNumber"] == "1001"

    def test_lookup_by_document_number_not_found(self):
        mock_client = MagicMock()
        mock_client.find_invoice_by_document_number.return_value = None
        with patch("app.main._get_fortnox_client_or_raise", return_value=mock_client):
            result = fortnox_invoice_lookup({"document_number": "9999"}, db=_db(), tenant_id="t1")
        assert result["invoice"] is None

    def test_lookup_by_customer_number(self):
        invoices = [{"DocumentNumber": "1001"}, {"DocumentNumber": "1002"}]
        mock_client = MagicMock()
        mock_client.find_recent_invoices_by_customer.return_value = invoices
        with patch("app.main._get_fortnox_client_or_raise", return_value=mock_client):
            result = fortnox_invoice_lookup({"customer_number": "42"}, db=_db(), tenant_id="t1")
        assert len(result["invoices"]) == 2

    def test_lookup_customer_default_limit_is_10(self):
        mock_client = MagicMock()
        mock_client.find_recent_invoices_by_customer.return_value = []
        with patch("app.main._get_fortnox_client_or_raise", return_value=mock_client):
            fortnox_invoice_lookup({"customer_number": "1"}, db=_db(), tenant_id="t1")
        call_kwargs = mock_client.find_recent_invoices_by_customer.call_args
        assert call_kwargs[1]["limit"] == 10

    def test_lookup_customer_limit_capped_at_50(self):
        mock_client = MagicMock()
        mock_client.find_recent_invoices_by_customer.return_value = []
        with patch("app.main._get_fortnox_client_or_raise", return_value=mock_client):
            fortnox_invoice_lookup({"customer_number": "1", "limit": 999}, db=_db(), tenant_id="t1")
        call_kwargs = mock_client.find_recent_invoices_by_customer.call_args
        assert call_kwargs[1]["limit"] == 50

    def test_document_number_takes_priority_over_customer_number(self):
        mock_client = MagicMock()
        mock_client.find_invoice_by_document_number.return_value = {"DocumentNumber": "5"}
        with patch("app.main._get_fortnox_client_or_raise", return_value=mock_client):
            result = fortnox_invoice_lookup(
                {"document_number": "5", "customer_number": "99"},
                db=_db(), tenant_id="t1",
            )
        mock_client.find_invoice_by_document_number.assert_called_once_with("5")
        mock_client.find_recent_invoices_by_customer.assert_not_called()
        assert result["invoice"]["DocumentNumber"] == "5"

    def test_missing_both_fields_raises_422(self):
        with patch("app.main._get_fortnox_client_or_raise", return_value=MagicMock()):
            with pytest.raises(HTTPException) as exc_info:
                fortnox_invoice_lookup({}, db=_db(), tenant_id="t1")
        assert exc_info.value.status_code == 422

    def test_missing_credentials_raises_503(self):
        with patch("app.main.get_settings", return_value=_make_settings(token="", secret="")):
            with pytest.raises(HTTPException) as exc_info:
                fortnox_invoice_lookup({"document_number": "1"}, db=_db(), tenant_id="t1")
        assert exc_info.value.status_code == 503

    def test_customer_lookup_returns_invoices_key(self):
        mock_client = MagicMock()
        mock_client.find_recent_invoices_by_customer.return_value = [{"DocumentNumber": "1"}]
        with patch("app.main._get_fortnox_client_or_raise", return_value=mock_client):
            result = fortnox_invoice_lookup({"customer_number": "3"}, db=_db(), tenant_id="t1")
        assert "invoices" in result
        assert "invoice" not in result

    def test_document_lookup_returns_invoice_key(self):
        mock_client = MagicMock()
        mock_client.find_invoice_by_document_number.return_value = {"DocumentNumber": "1"}
        with patch("app.main._get_fortnox_client_or_raise", return_value=mock_client):
            result = fortnox_invoice_lookup({"document_number": "1"}, db=_db(), tenant_id="t1")
        assert "invoice" in result
        assert "invoices" not in result
