"""Tests for Classification v2 — expanded inbox taxonomy.

Covers:
  classify_email_type:
    - spam detection
    - newsletter detection
    - internal detection
    - invoice detection (unchanged)
    - supplier detection
    - partnership detection
    - lead detection (unchanged)
    - customer_inquiry fallback (unchanged)
    - priority ordering between types

  _build_fallback_actions:
    - visibility-only types produce only skipped sentinels
    - no customer auto-reply for newsletter/spam/internal/supplier/partnership
    - lead/invoice/inquiry fallbacks unchanged

  Regression:
    - quote request → lead
    - support issue → customer_inquiry
    - faktura → invoice
"""
from __future__ import annotations

from unittest.mock import patch

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.domain.workflows.statuses import JobStatus
from app.workflows.processors.action_dispatch_processor import (
    _build_fallback_actions,
    _VISIBILITY_ONLY_TYPES,
)
from app.workflows.processors.classification_processor import classify_email_type


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _job(detected_type: str, subject: str = "", body: str = "") -> Job:
    job = Job(
        job_id="job-cls-v2",
        tenant_id="TENANT_1001",
        job_type=JobType.LEAD,
        status=JobStatus.PROCESSING,
        input_data={"subject": subject, "message_text": body},
    )
    job.processor_history = [
        {
            "processor": "classification_processor",
            "result": {"payload": {"detected_job_type": detected_type}},
        }
    ]
    return job


# ---------------------------------------------------------------------------
# classify_email_type — new types
# ---------------------------------------------------------------------------

class TestSpamDetection:
    def test_you_won_is_spam(self):
        assert classify_email_type("You won a prize", "Click here to claim") == "spam"

    def test_lottery_in_body_is_spam(self):
        assert classify_email_type("Congratulations", "You have won the lottery") == "spam"

    def test_nigerian_prince_is_spam(self):
        assert classify_email_type("Request", "I am a nigerian prince") == "spam"

    def test_spam_beats_newsletter(self):
        # Even if newsletter keywords present, spam wins
        assert classify_email_type("You won a prize", "unsubscribe from our newsletter") == "spam"

    def test_spam_beats_lead(self):
        assert classify_email_type("You won a prize", "buy now at great pricing") == "spam"


class TestNewsletterDetection:
    def test_nyhetsbrev_in_subject(self):
        assert classify_email_type("Nyhetsbrev april", "Här kommer månadens kampanjer") == "newsletter"

    def test_unsubscribe_in_body(self):
        assert classify_email_type("April update", "Click to unsubscribe from our list") == "newsletter"

    def test_kampanjer_in_body(self):
        assert classify_email_type("Erbjudanden", "Denna månads kampanjer") == "newsletter"

    def test_newsletter_beats_invoice(self):
        # Newsletter signal in subject; invoice keyword only in body
        assert classify_email_type("Nyhetsbrev", "se bifogad faktura") == "newsletter"

    def test_newsletter_does_not_match_normal_message(self):
        result = classify_email_type("Fråga om produkten", "Hej, jag undrar om priset")
        assert result != "newsletter"


class TestInternalDetection:
    def test_intern_notering_is_internal(self):
        assert classify_email_type("Intern notering", "Vi behöver följa upp") == "internal"

    def test_internt_in_subject(self):
        assert classify_email_type("Internt meddelande", "Hej team") == "internal"

    def test_internal_note_english(self):
        assert classify_email_type("Internal note", "Please review this") == "internal"

    def test_internal_beats_lead(self):
        assert classify_email_type("Intern notering", "vi vill köpa produkten") == "internal"


class TestSupplierDetection:
    def test_orderbekraftelse_is_supplier(self):
        assert classify_email_type("Orderbekräftelse 12345", "Din beställning har skickats") == "supplier"

    def test_order_confirmation_english(self):
        assert classify_email_type("Order confirmation #999", "Your order has shipped") == "supplier"

    def test_kvitto_is_supplier(self):
        assert classify_email_type("Kvitto för din beställning", "") == "supplier"

    def test_din_bestallning_in_body(self):
        assert classify_email_type("Uppdatering", "Din beställning har levererats") == "supplier"

    def test_supplier_beats_lead(self):
        # "buy" is a lead keyword, but supplier signal wins
        assert classify_email_type("Order confirmation", "buy order has shipped") == "supplier"


class TestPartnershipDetection:
    def test_samarbete_is_partnership(self):
        assert classify_email_type(
            "Samarbete med ELit Gruppen",
            "Hej, vi vill diskutera ett potentiellt samarbete",
        ) == "partnership"

    def test_partnership_english(self):
        assert classify_email_type("Partnership opportunity", "We'd like to explore a business proposal") == "partnership"

    def test_b2b_cooperation(self):
        assert classify_email_type("B2B proposal", "Strategic alliance opportunity") == "partnership"

    def test_samarbetsforslag(self):
        assert classify_email_type("Samarbetsförslag", "Vi har ett intressant förslag") == "partnership"

    def test_partnership_beats_lead(self):
        # "intresserad" is lead keyword; partnership wins
        assert classify_email_type("Samarbete", "vi är intresserade av ett samarbete") == "partnership"


# ---------------------------------------------------------------------------
# classify_email_type — regression tests
# ---------------------------------------------------------------------------

class TestRegressionExistingTypes:
    def test_offert_is_lead(self):
        assert classify_email_type("Offertförfrågan", "Vi vill ha offert") == "lead"

    def test_installation_is_lead(self):
        assert classify_email_type("Installation av solpaneler", "Boka installation") == "lead"

    def test_faktura_is_invoice(self):
        assert classify_email_type("Faktura 2024-001", "Belopp 5000 kr") == "invoice"

    def test_invoice_english(self):
        assert classify_email_type("Invoice #123", "Payment due") == "invoice"

    def test_normal_message_is_inquiry(self):
        assert classify_email_type("Fråga om leverans", "Hej, när kommer min order?") == "customer_inquiry"

    def test_empty_strings_is_inquiry(self):
        assert classify_email_type("", "") == "customer_inquiry"

    def test_problem_with_product_is_inquiry(self):
        assert classify_email_type("Problem med produkten", "Det fungerar inte") == "customer_inquiry"


# ---------------------------------------------------------------------------
# _build_fallback_actions — visibility-only types
# ---------------------------------------------------------------------------

class TestVisibilityOnlyTypes:
    def test_visibility_only_set_contains_expected_types(self):
        assert "partnership" in _VISIBILITY_ONLY_TYPES
        assert "supplier" in _VISIBILITY_ONLY_TYPES
        assert "newsletter" in _VISIBILITY_ONLY_TYPES
        assert "internal" in _VISIBILITY_ONLY_TYPES
        assert "spam" in _VISIBILITY_ONLY_TYPES

    def test_lead_not_in_visibility_only(self):
        assert "lead" not in _VISIBILITY_ONLY_TYPES

    def test_invoice_not_in_visibility_only(self):
        assert "invoice" not in _VISIBILITY_ONLY_TYPES

    def test_inquiry_not_in_visibility_only(self):
        assert "customer_inquiry" not in _VISIBILITY_ONLY_TYPES

    def _assert_no_customer_email(self, detected_type: str):
        job = _job(detected_type)
        actions = _build_fallback_actions(job)
        executing = [a for a in actions if not a.get("_skip")]
        customer_reply = [a for a in executing if a.get("type") == "send_customer_auto_reply"]
        assert len(customer_reply) == 0, f"{detected_type} should not send customer auto-reply"

    def test_newsletter_no_customer_auto_reply(self):
        self._assert_no_customer_email("newsletter")

    def test_spam_no_customer_auto_reply(self):
        self._assert_no_customer_email("spam")

    def test_internal_no_customer_auto_reply(self):
        self._assert_no_customer_email("internal")

    def test_supplier_no_customer_auto_reply(self):
        self._assert_no_customer_email("supplier")

    def test_partnership_no_customer_auto_reply(self):
        self._assert_no_customer_email("partnership")

    def _assert_all_skipped(self, detected_type: str):
        job = _job(detected_type)
        actions = _build_fallback_actions(job)
        assert len(actions) > 0
        assert all(a.get("_skip") for a in actions), f"All actions for {detected_type} should be skipped"

    def test_newsletter_all_actions_skipped(self):
        self._assert_all_skipped("newsletter")

    def test_spam_all_actions_skipped(self):
        self._assert_all_skipped("spam")

    def test_internal_all_actions_skipped(self):
        self._assert_all_skipped("internal")

    def test_supplier_all_actions_skipped(self):
        self._assert_all_skipped("supplier")

    def test_partnership_all_actions_skipped(self):
        self._assert_all_skipped("partnership")

    def test_skip_reason_mentions_type(self):
        job = _job("newsletter")
        actions = _build_fallback_actions(job)
        reasons = [a.get("_skip_reason", "") for a in actions]
        assert any("newsletter" in r for r in reasons)


# ---------------------------------------------------------------------------
# _build_fallback_actions — automation types unchanged
# ---------------------------------------------------------------------------

class TestFallbackAutomationTypesUnchanged:
    def test_lead_fallback_has_monday_item(self):
        job = _job("lead", subject="Offert", body="Vi vill ha offert")
        with patch(
            "app.workflows.processors.action_dispatch_processor._build_lead_default_actions",
            return_value=[{"type": "create_monday_item", "item_name": "test"}],
        ) as mock:
            _build_fallback_actions(job)
            mock.assert_called_once()

    def test_invoice_fallback_called(self):
        job = _job("invoice", subject="Faktura", body="5000 kr")
        with patch(
            "app.workflows.processors.action_dispatch_processor._build_invoice_default_actions",
            return_value=[{"type": "create_monday_item", "item_name": "test"}],
        ) as mock:
            _build_fallback_actions(job)
            mock.assert_called_once()

    def test_inquiry_fallback_called(self):
        job = _job("customer_inquiry", subject="Fråga", body="Hjälp")
        with patch(
            "app.workflows.processors.action_dispatch_processor._build_inquiry_default_actions",
            return_value=[{"type": "create_monday_item", "item_name": "test"}],
        ) as mock:
            _build_fallback_actions(job)
            mock.assert_called_once()


# ---------------------------------------------------------------------------
# AllowedJobType schema
# ---------------------------------------------------------------------------

class TestAllowedJobTypeSchema:
    def test_new_types_valid_in_schema(self):
        from app.ai.schemas import ClassificationResponse
        for job_type in ("partnership", "supplier", "newsletter", "internal", "spam"):
            resp = ClassificationResponse(
                detected_job_type=job_type,
                confidence=0.9,
                reasons=["test"],
            )
            assert resp.detected_job_type == job_type

    def test_unknown_still_valid(self):
        from app.ai.schemas import ClassificationResponse
        resp = ClassificationResponse(detected_job_type="unknown", confidence=0.3, reasons=[])
        assert resp.detected_job_type == "unknown"

    def test_invalid_type_rejected(self):
        from app.ai.schemas import ClassificationResponse
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ClassificationResponse(detected_job_type="garbage_type", confidence=0.5, reasons=[])


import pytest
