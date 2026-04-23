"""
Tests for deterministic classification fallback.

Covers:
  _classify_deterministic helper:
    A. Invoice keywords (faktura, invoice) — highest priority
    B. Lead keywords (offert, pris, köpa, intresserad, and English equivalents)
    C. Non-lead, non-invoice -> customer_inquiry
    D. Empty/unclear -> customer_inquiry
    E. Case-insensitivity
    F. Invoice beats lead when both keywords present

  process_classification_job (LLM unavailable = fallback path):
    - Invoice-like job classified as invoice
    - Lead-like job classified as lead
    - Non-lead, non-invoice job classified as customer_inquiry
    - Fallback confidence is 0.5, reasons include deterministic_fallback
    - Explicitly provided job_type on the Job object is NOT overridden by fallback
      (classification writes to payload; routing reads payload, not job.job_type)

  gmail_process_inbox path:
    - Lead-like email -> job created (inbox default)
    - Non-lead email -> job created (dedup/gating not broken)
    - Dedup / tenant-gating not broken
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.workflows.processors.classification_processor import (
    _classify_deterministic,
    process_classification_job,
)
from app.main import GmailProcessInboxRequest, gmail_process_inbox


# ── _classify_deterministic ───────────────────────────────────────────────────

class TestClassifyDeterministic:
    # Invoice keywords
    @pytest.mark.parametrize("subject,body", [
        ("Faktura #1234", ""),
        ("", "Please find the invoice attached"),
        ("Invoice for services rendered", ""),
        ("", "Hej, bifogad faktura avser mars"),
        ("Re: faktura", "Se bifogad fil"),
    ])
    def test_invoice_keywords(self, subject, body):
        assert _classify_deterministic(subject, body) == "invoice"

    def test_invoice_keyword_in_body_wins(self):
        assert _classify_deterministic("Hej", "din faktura är nu betald") == "invoice"

    def test_invoice_beats_lead_when_both_present(self):
        # "Faktura / pricing question" — invoice takes priority over lead
        assert _classify_deterministic("Faktura / pricing question", "") == "invoice"

    def test_invoice_beats_lead_keywords_in_body(self):
        assert _classify_deterministic("", "invoice for the demo you requested") == "invoice"

    def test_invoice_case_insensitive_upper(self):
        assert _classify_deterministic("FAKTURA ÄRENDE", "") == "invoice"

    def test_invoice_case_insensitive_mixed(self):
        assert _classify_deterministic("", "Bifogad Invoice från leverantör") == "invoice"

    # Lead keywords — Swedish
    @pytest.mark.parametrize("subject,body", [
        ("Vill ha offert", ""),
        ("", "vad är priset?"),
        ("Vi vill köpa er produkt", ""),
        ("", "Jag är intresserad av er tjänst"),
        ("Offert på solpaneler", "Hej, jag vill ha pris"),
    ])
    def test_swedish_lead_keywords(self, subject, body):
        assert _classify_deterministic(subject, body) == "lead"

    # Lead keywords — English equivalents
    @pytest.mark.parametrize("subject,body", [
        ("Request for quote", ""),
        ("", "What is the pricing?"),
        ("I want to buy", ""),
        ("", "Interested in your product"),
        ("Demo request", ""),
        ("trial signup", ""),
        ("I'd like to purchase your plan", ""),
    ])
    def test_english_lead_keywords(self, subject, body):
        assert _classify_deterministic(subject, body) == "lead"

    # Support / non-lead, non-invoice
    @pytest.mark.parametrize("subject,body", [
        ("Min produkt fungerar inte", "Kan ni hjälpa?"),
        ("Question about delivery", "When will my order arrive?"),
        ("Technical issue", "Getting error 500"),
    ])
    def test_non_lead_non_invoice_is_customer_inquiry(self, subject, body):
        assert _classify_deterministic(subject, body) == "customer_inquiry"

    def test_empty_subject_and_body_is_customer_inquiry(self):
        assert _classify_deterministic("", "") == "customer_inquiry"

    def test_whitespace_only_is_customer_inquiry(self):
        assert _classify_deterministic("   ", "   ") == "customer_inquiry"

    def test_case_insensitive_upper(self):
        assert _classify_deterministic("OFFERT ÖNSKAS", "") == "lead"

    def test_case_insensitive_mixed(self):
        assert _classify_deterministic("", "Jag är Intresserad av er lösning") == "lead"

    def test_lead_keyword_in_body_wins_over_neutral_subject(self):
        assert _classify_deterministic("Support fråga", "men vi vill också ha ett pris") == "lead"

    def test_no_false_positive_on_similar_word(self):
        # "priser" contains "pris" as substring — should still match
        assert _classify_deterministic("", "Vad är priser för support?") == "lead"


# ── process_classification_job — deterministic fallback ──────────────────────

def _make_job(subject: str, body: str, job_type: JobType = JobType.LEAD) -> Job:
    return Job(
        tenant_id="TENANT_1001",
        job_type=job_type,
        input_data={"subject": subject, "message_text": body},
    )


class TestClassificationFallback:
    def _run_with_llm_error(self, job: Job) -> Job:
        from app.ai.exceptions import LLMClientError

        class _FailingClient:
            def generate_json(self, prompt):
                raise LLMClientError("LLM unavailable")

        with patch(
            "app.workflows.processors.ai_processor_utils.get_llm_client",
            return_value=_FailingClient(),
        ):
            return process_classification_job(job)

    def test_invoice_job_classified_as_invoice_on_fallback(self):
        job = _make_job("Faktura #5678", "Se bifogad faktura för mars")
        result = self._run_with_llm_error(job)
        assert result.result["payload"]["detected_job_type"] == "invoice"

    def test_invoice_beats_lead_on_fallback(self):
        job = _make_job("Faktura / pricing question", "")
        result = self._run_with_llm_error(job)
        assert result.result["payload"]["detected_job_type"] == "invoice"

    def test_lead_job_classified_as_lead_on_fallback(self):
        job = _make_job("Vill ha offert", "Vi är intresserade av köp")
        result = self._run_with_llm_error(job)
        assert result.result["payload"]["detected_job_type"] == "lead"

    def test_inquiry_job_classified_as_customer_inquiry_on_fallback(self):
        job = _make_job("Min laddbox fungerar inte", "Fel kod visas.")
        result = self._run_with_llm_error(job)
        assert result.result["payload"]["detected_job_type"] == "customer_inquiry"

    def test_fallback_confidence_is_0_5(self):
        job = _make_job("Offert önskas", "")
        result = self._run_with_llm_error(job)
        assert result.result["payload"]["confidence"] == 0.5

    def test_fallback_reasons_include_deterministic_fallback(self):
        job = _make_job("Support fråga", "")
        result = self._run_with_llm_error(job)
        assert "deterministic_fallback" in result.result["payload"]["reasons"]

    def test_fallback_sets_requires_human_review_true(self):
        job = _make_job("Offert", "")
        result = self._run_with_llm_error(job)
        assert result.result["requires_human_review"] is True

    def test_explicit_job_type_not_overridden_by_classification_payload(self):
        # The classification processor writes to payload only.
        # The orchestrator resolves job_type from the payload, not the field on Job.
        # An explicitly set job_type on the Job object before classification
        # is the initial routing hint — classification output takes precedence
        # in the orchestrator, so a mismatch between job.job_type and
        # payload["detected_job_type"] is intentional design.
        # This test verifies the payload output, not the job.job_type field.
        job = _make_job(
            subject="Support problem",
            body="My product is broken.",
            job_type=JobType.LEAD,  # explicitly set
        )
        result = self._run_with_llm_error(job)
        # Content is support-like -> deterministic says customer_inquiry
        assert result.result["payload"]["detected_job_type"] == "customer_inquiry"
        # The job.job_type field itself is unchanged by this processor
        assert result.job_type == JobType.LEAD


# ── gmail_process_inbox path ──────────────────────────────────────────────────

def _make_processed_job(job_id: str = "job-1", status: str = "completed"):
    job = MagicMock()
    job.job_id = job_id
    job.status = MagicMock()
    job.status.value = status
    return job


def _detail_result(
    message_id: str = "msg1",
    from_header: str = "Erik <erik@example.com>",
    subject: str = "New inquiry",
    body_text: str = "Hello",
) -> dict:
    return {
        "status": "success",
        "message": {
            "message_id": message_id,
            "thread_id": f"t{message_id}",
            "from": from_header,
            "to": "me@example.com",
            "subject": subject,
            "received_at": "Mon, 21 Apr 2026 10:00:00 +0000",
            "snippet": "snippet",
            "label_ids": ["INBOX", "UNREAD"],
            "body_text": body_text,
        },
    }


def _run_inbox(detail: dict, tenant_config: dict | None = None) -> Job:
    captured: list[Job] = []

    mock_adapter = MagicMock()

    def fake_execute(action, payload):
        if action == "list_messages":
            return {"status": "success", "messages": [{"message_id": "msg1", "thread_id": "t1"}]}
        if action == "get_message":
            return detail
        return {"status": "success"}

    mock_adapter.execute_action.side_effect = fake_execute

    def fake_create(db, job):
        captured.append(job)
        return job

    cfg = tenant_config or {"enabled_job_types": ["lead", "customer_inquiry"]}

    with patch("app.main.get_integration_connection_config", return_value={}), \
         patch("app.main.get_integration_adapter", return_value=mock_adapter), \
         patch("app.main.get_tenant_config", return_value=cfg), \
         patch("app.main.JobRepository.get_by_gmail_message_id", return_value=None), \
         patch("app.main.JobRepository.create_job", side_effect=fake_create), \
         patch("app.main.run_pipeline", return_value=_make_processed_job()), \
         patch("app.main.dispatch_action"):
        gmail_process_inbox(
            request=GmailProcessInboxRequest(max_results=5),
            db=MagicMock(),
            tenant_id="TENANT_1001",
        )

    assert captured, "No job was created"
    return captured[0]


class TestGmailInboxClassificationRouting:
    def test_lead_like_email_creates_job_with_lead_type(self):
        job = _run_inbox(_detail_result(
            subject="Vill ha offert",
            body_text="Vi är intresserade av köp",
        ))
        # Job is initialised with LEAD (current inbox default)
        # Classification processor in the pipeline will route correctly
        assert job.job_type == JobType.LEAD

    def test_non_lead_email_still_creates_job(self):
        # The inbox creates the job; classification happens inside the pipeline.
        # This test checks the job is created (dedup/gating not broken).
        job = _run_inbox(_detail_result(
            subject="Support fråga",
            body_text="Min produkt fungerar inte.",
        ))
        assert job is not None

    def test_dedup_not_broken(self):
        mock_adapter = MagicMock()
        mock_adapter.execute_action.return_value = {
            "status": "success",
            "messages": [{"message_id": "msg1", "thread_id": "t1"}],
        }

        existing = MagicMock()
        existing.job_id = "old-job"

        with patch("app.main.get_integration_connection_config", return_value={}), \
             patch("app.main.get_integration_adapter", return_value=mock_adapter), \
             patch("app.main.get_tenant_config", return_value={"enabled_job_types": ["lead"]}), \
             patch("app.main.JobRepository.get_by_gmail_message_id", return_value=existing), \
             patch("app.main.JobRepository.create_job") as mock_create, \
             patch("app.main.dispatch_action"):
            result = gmail_process_inbox(
                request=GmailProcessInboxRequest(max_results=5),
                db=MagicMock(),
                tenant_id="TENANT_1001",
            )

        mock_create.assert_not_called()
        assert result["skipped"] == 1
        assert result["skipped_messages"][0]["reason"] == "duplicate"

    def test_lead_disabled_not_broken(self):
        # A lead-keyword email must be skipped with "lead_disabled" when lead is not in enabled_job_types.
        mock_adapter = MagicMock()

        def fake_execute(action, payload):
            if action == "list_messages":
                return {"status": "success", "messages": [{"message_id": "msg1", "thread_id": "t1"}]}
            if action == "get_message":
                return _detail_result(subject="Offert önskas")
            return {"status": "success"}

        mock_adapter.execute_action.side_effect = fake_execute

        with patch("app.main.get_integration_connection_config", return_value={}), \
             patch("app.main.get_integration_adapter", return_value=mock_adapter), \
             patch("app.main.get_tenant_config", return_value={"enabled_job_types": ["invoice"]}), \
             patch("app.main.JobRepository.get_by_gmail_message_id", return_value=None), \
             patch("app.main.JobRepository.create_job") as mock_create, \
             patch("app.main.dispatch_action"):
            result = gmail_process_inbox(
                request=GmailProcessInboxRequest(max_results=5),
                db=MagicMock(),
                tenant_id="TENANT_1001",
            )

        mock_create.assert_not_called()
        assert result["skipped_messages"][0]["reason"] == "lead_disabled"

    def test_input_data_subject_and_body_present_in_job(self):
        job = _run_inbox(_detail_result(
            subject="Offert önskas",
            body_text="Vi vill köpa 10 enheter",
        ))
        assert job.input_data["subject"] == "Offert önskas"
        assert job.input_data["message_text"] == "Vi vill köpa 10 enheter"
