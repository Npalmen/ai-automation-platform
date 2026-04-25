"""
Tests for deterministic invoice extraction helpers.

Covers:
  extract_invoice_amount:
    - "12 500 kr"
    - "12500 kr"
    - "SEK 12500"
    - decimal "1 250,50 kr"
    - "12,500.00" without kr -> not matched (requires kr or SEK marker)
    - subject checked before body
    - no amount -> None

  extract_invoice_number:
    - "Faktura #1234"
    - "Fakturanummer: INV-2026-001"
    - "Invoice No: INV-2026-001"
    - "Invoice 5678"
    - subject checked before body
    - no number -> None

  extract_due_date:
    - "2026-05-01" (ISO)
    - "2026/05/01"
    - "2026.05.01"
    - normalised separator is always '-'
    - subject checked before body
    - no date -> None

  extract_invoice_data:
    - supplier_name from sender.name
    - fallback supplier_name from sender.email
    - omitted when neither available
    - all fields present when found
    - raw_text present
    - fields omitted when not found

  _build_invoice_default_actions (extraction wired in):
    - column_values includes amount, invoice_number, due_date, supplier_name
    - column_values omits fields not found
    - internal task description includes extracted fields
    - internal task metadata["invoice"] contains structured payload
    - lead flow unchanged
    - inquiry flow unchanged
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.workflows.processors.ai_processor_utils import (
    extract_due_date,
    extract_invoice_amount,
    extract_invoice_data,
    extract_invoice_number,
)
from app.workflows.processors.action_dispatch_processor import (
    _build_invoice_default_actions,
)
from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job


# ── helpers ───────────────────────────────────────────────────────────────────

def _invoice_job(input_data: dict | None = None) -> Job:
    job = Job(
        tenant_id="TENANT_1001",
        job_type=JobType.INVOICE,
        input_data=input_data or {},
    )
    job.processor_history = [
        {
            "processor": "classification_processor",
            "result": {"payload": {"detected_job_type": "invoice"}},
        }
    ]
    return job


# ── extract_invoice_amount ────────────────────────────────────────────────────

class TestExtractInvoiceAmount:
    def test_spaced_thousands_with_kr(self):
        result = extract_invoice_amount("", "Totalt 12 500 kr exkl moms")
        assert result is not None
        assert "12" in result and "500" in result

    def test_plain_integer_with_kr(self):
        result = extract_invoice_amount("", "Belopp: 12500 kr")
        assert result is not None
        assert "12500" in result

    def test_sek_prefix(self):
        result = extract_invoice_amount("", "SEK 12500")
        assert result is not None
        assert "12500" in result

    def test_decimal_amount_with_kr(self):
        result = extract_invoice_amount("", "1 250,50 kr att betala")
        assert result is not None
        assert "1" in result

    def test_subject_checked_before_body(self):
        result = extract_invoice_amount("500 kr", "SEK 9999")
        assert result is not None
        assert "500" in result

    def test_no_amount_returns_none(self):
        assert extract_invoice_amount("Hej", "Inga siffror här") is None

    def test_standalone_number_without_marker_not_matched(self):
        # plain number with no kr/SEK marker should not match
        assert extract_invoice_amount("", "Referens 12345") is None


# ── extract_invoice_number ────────────────────────────────────────────────────

class TestExtractInvoiceNumber:
    def test_faktura_hash(self):
        result = extract_invoice_number("Faktura #1234", "")
        assert result == "1234"

    def test_fakturanummer_colon(self):
        result = extract_invoice_number("", "Fakturanummer: INV-2026-001")
        assert result == "INV-2026-001"

    def test_invoice_no_colon(self):
        result = extract_invoice_number("", "Invoice No: INV-2026-001")
        assert result == "INV-2026-001"

    def test_invoice_plain_number(self):
        result = extract_invoice_number("", "Invoice 5678")
        assert result == "5678"

    def test_inv_prefix(self):
        result = extract_invoice_number("", "INV #ABC-99")
        assert result is not None

    def test_subject_checked_before_body(self):
        result = extract_invoice_number("Faktura #100", "Invoice 999")
        assert result == "100"

    def test_no_invoice_number_returns_none(self):
        assert extract_invoice_number("Hej", "Inga fakturanummer här") is None


# ── extract_due_date ──────────────────────────────────────────────────────────

class TestExtractDueDate:
    def test_iso_dash(self):
        assert extract_due_date("", "Förfaller 2026-05-01") == "2026-05-01"

    def test_slash_separator(self):
        assert extract_due_date("", "Due date 2026/05/01") == "2026-05-01"

    def test_dot_separator(self):
        assert extract_due_date("", "Betalas senast 2026.05.01") == "2026-05-01"

    def test_subject_checked_before_body(self):
        result = extract_due_date("2026-01-15", "2026-12-31")
        assert result == "2026-01-15"

    def test_no_date_returns_none(self):
        assert extract_due_date("Hej", "Ingen datum här") is None

    def test_normalized_separator_is_dash(self):
        result = extract_due_date("", "2026/12/31")
        assert result == "2026-12-31"
        assert "/" not in result


# ── extract_invoice_data ──────────────────────────────────────────────────────

class TestExtractInvoiceData:
    def test_supplier_name_from_sender_name(self):
        data = extract_invoice_data({"sender": {"name": "Leverantör AB", "email": "lev@ex.com"}})
        assert data["supplier_name"] == "Leverantör AB"

    def test_supplier_name_falls_back_to_email(self):
        data = extract_invoice_data({"sender": {"email": "lev@ex.com"}})
        assert data["supplier_name"] == "lev@ex.com"

    def test_supplier_name_omitted_when_no_sender(self):
        data = extract_invoice_data({})
        assert "supplier_name" not in data

    def test_amount_extracted_when_present(self):
        data = extract_invoice_data({"message_text": "Totalt 5 000 kr"})
        assert data.get("amount") is not None
        assert "5" in data["amount"]

    def test_amount_omitted_when_absent(self):
        data = extract_invoice_data({"message_text": "Ingen summa"})
        assert "amount" not in data

    def test_invoice_number_extracted(self):
        data = extract_invoice_data({"subject": "Faktura #XYZ-99"})
        assert data.get("invoice_number") == "XYZ-99"

    def test_invoice_number_omitted_when_absent(self):
        data = extract_invoice_data({"subject": "Betalning"})
        assert "invoice_number" not in data

    def test_due_date_extracted(self):
        data = extract_invoice_data({"message_text": "Förfaller 2026-07-31"})
        assert data.get("due_date") == "2026-07-31"

    def test_due_date_omitted_when_absent(self):
        data = extract_invoice_data({"message_text": "Ingen förfallodag"})
        assert "due_date" not in data

    def test_raw_text_is_subject_plus_body(self):
        data = extract_invoice_data({"subject": "Ämne", "message_text": "Text"})
        assert "Ämne" in data["raw_text"]
        assert "Text" in data["raw_text"]

    def test_raw_text_omitted_when_both_empty(self):
        data = extract_invoice_data({})
        assert "raw_text" not in data

    def test_all_fields_present_in_rich_email(self):
        data = extract_invoice_data({
            "sender": {"name": "AB Bygg", "email": "bygg@ex.com"},
            "subject": "Faktura #2026-001",
            "message_text": "Belopp 12 500 kr. Förfaller 2026-06-30.",
        })
        assert data["supplier_name"] == "AB Bygg"
        assert data["invoice_number"] == "2026-001"
        assert data["amount"] is not None
        assert data["due_date"] == "2026-06-30"
        assert data["raw_text"]

    def test_flat_sender_keys_supported(self):
        data = extract_invoice_data({"sender_name": "Flat AB", "sender_email": "flat@ex.com"})
        assert data["supplier_name"] == "Flat AB"


# ── _build_invoice_default_actions — extraction wired in ─────────────────────

class TestInvoiceActionsWithExtraction:
    def test_column_values_includes_amount(self):
        job = _invoice_job({
            "sender": {"name": "AB Bygg", "email": "bygg@ex.com"},
            "subject": "Faktura #1",
            "message_text": "Belopp 3 500 kr",
        })
        cv = _build_invoice_default_actions(job)[0]["column_values"]
        assert "amount" in cv
        assert "3" in cv["amount"]

    def test_column_values_includes_invoice_number(self):
        job = _invoice_job({
            "subject": "Faktura #INV-99",
            "sender": {"email": "x@x.com"},
        })
        cv = _build_invoice_default_actions(job)[0]["column_values"]
        assert cv.get("invoice_number") == "INV-99"

    def test_column_values_includes_due_date(self):
        job = _invoice_job({
            "message_text": "Förfaller 2026-08-15",
            "sender": {"email": "x@x.com"},
        })
        cv = _build_invoice_default_actions(job)[0]["column_values"]
        assert cv.get("due_date") == "2026-08-15"

    def test_column_values_includes_supplier_name(self):
        job = _invoice_job({"sender": {"name": "Leverantör AB"}})
        cv = _build_invoice_default_actions(job)[0]["column_values"]
        assert cv.get("supplier_name") == "Leverantör AB"

    def test_column_values_omits_amount_when_absent(self):
        job = _invoice_job({"sender": {"email": "x@x.com"}, "message_text": "Ingen summa"})
        cv = _build_invoice_default_actions(job)[0]["column_values"]
        assert "amount" not in cv

    def test_column_values_omits_invoice_number_when_absent(self):
        job = _invoice_job({"subject": "Betalning", "sender": {"email": "x@x.com"}})
        cv = _build_invoice_default_actions(job)[0]["column_values"]
        assert "invoice_number" not in cv

    def test_column_values_omits_due_date_when_absent(self):
        job = _invoice_job({"message_text": "Ingen datum"})
        cv = _build_invoice_default_actions(job)[0]["column_values"]
        assert "due_date" not in cv

    def test_task_description_includes_amount(self):
        job = _invoice_job({"message_text": "Totalt 7 000 kr", "sender": {"email": "x@x.com"}})
        desc = _build_invoice_default_actions(job)[1]["description"]
        assert "7" in desc

    def test_task_description_includes_invoice_number(self):
        job = _invoice_job({"subject": "Faktura #ABC-1", "sender": {"email": "x@x.com"}})
        desc = _build_invoice_default_actions(job)[1]["description"]
        assert "ABC-1" in desc

    def test_task_description_includes_due_date(self):
        job = _invoice_job({"message_text": "Förfaller 2026-09-01"})
        desc = _build_invoice_default_actions(job)[1]["description"]
        assert "2026-09-01" in desc

    def test_task_metadata_contains_invoice_payload(self):
        job = _invoice_job({
            "sender": {"name": "AB Bygg"},
            "message_text": "Belopp 1 000 kr. Förfaller 2026-10-01.",
        })
        metadata = _build_invoice_default_actions(job)[1]["metadata"]
        assert "invoice" in metadata
        assert metadata["invoice"].get("supplier_name") == "AB Bygg"

    def test_source_is_invoice(self):
        job = _invoice_job({})
        cv = _build_invoice_default_actions(job)[0]["column_values"]
        assert cv["source"] == "invoice"

    def test_lead_flow_unchanged(self):
        from app.workflows.processors.action_dispatch_processor import _build_fallback_actions
        job = Job(tenant_id="TENANT_1001", job_type=JobType.LEAD, input_data={"subject": "Offert"})
        job.processor_history = [
            {
                "processor": "classification_processor",
                "result": {"payload": {"detected_job_type": "lead"}},
            }
        ]
        actions = _build_fallback_actions(job)
        for a in actions:
            assert a.get("column_values", {}).get("source") != "invoice"

    def test_inquiry_flow_unchanged(self):
        from app.workflows.processors.action_dispatch_processor import _build_fallback_actions
        job = Job(
            tenant_id="TENANT_1001",
            job_type=JobType.CUSTOMER_INQUIRY,
            input_data={"subject": "Support fråga"},
        )
        job.processor_history = [
            {
                "processor": "classification_processor",
                "result": {"payload": {"detected_job_type": "customer_inquiry"}},
            }
        ]
        actions = _build_fallback_actions(job)
        types = [a["type"] for a in actions]
        assert "send_internal_handoff" in types
        monday = next((a for a in actions if a["type"] == "create_monday_item"), None)
        if monday:
            assert monday["column_values"]["source"] == "inquiry"
