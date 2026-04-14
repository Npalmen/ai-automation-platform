"""
Tests for entity_extraction_processor intake-origin fallback.

When LLM extraction leaves customer_name / email / phone null, the processor
should fill them from the normalized intake origin (sender_name / sender_email /
sender_phone) so downstream validation does not report missing_identity.

Covers:
  - _apply_intake_fallback fills null customer_name from origin.sender_name
  - _apply_intake_fallback fills null email from origin.sender_email
  - _apply_intake_fallback fills null phone from origin.sender_phone
  - _apply_intake_fallback does not overwrite non-null LLM-extracted values
  - fallback_payload_builder populates entities from intake origin on LLM failure
  - fallback_payload_builder suppresses missing_identity when name+email present
  - _build_source_context includes flat sender_* keys in sender dict for LLM prompt
  - Full pipeline: job with flat sender fields, no LLM → entities not all null
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.workflows.processors.entity_extraction_processor import (
    _apply_intake_fallback,
    _build_source_context,
    process_entity_extraction_job,
)
from app.workflows.processors.intake_processor import process_universal_intake_job


def _make_job(input_data: dict, job_type=JobType.ENTITY_EXTRACTION) -> Job:
    return Job(
        tenant_id="TENANT_TEST",
        job_type=job_type,
        input_data=input_data,
    )


def _job_with_intake_and_flat_sender(sender_name="Testkund", sender_email="test@example.com", sender_phone="0701234567"):
    """Creates a job that has already been through intake, with flat sender fields."""
    job = _make_job({
        "subject": "Test",
        "message_text": "Hej, jag vill ha en offert.",
        "sender_name": sender_name,
        "sender_email": sender_email,
        "sender_phone": sender_phone,
    })
    job = process_universal_intake_job(job)
    job.job_type = JobType.ENTITY_EXTRACTION
    return job


class TestApplyIntakeFallback:
    def test_fills_customer_name_from_sender_name(self):
        entities = {"customer_name": None, "email": None, "phone": None}
        origin = {"sender_name": "Testkund", "sender_email": "", "sender_phone": ""}
        result = _apply_intake_fallback(entities, origin)
        assert result["customer_name"] == "Testkund"

    def test_fills_email_from_sender_email(self):
        entities = {"customer_name": None, "email": None, "phone": None}
        origin = {"sender_name": "", "sender_email": "test@example.com", "sender_phone": ""}
        result = _apply_intake_fallback(entities, origin)
        assert result["email"] == "test@example.com"

    def test_fills_phone_from_sender_phone(self):
        entities = {"customer_name": None, "email": None, "phone": None}
        origin = {"sender_name": "", "sender_email": "", "sender_phone": "0701234567"}
        result = _apply_intake_fallback(entities, origin)
        assert result["phone"] == "0701234567"

    def test_does_not_overwrite_llm_extracted_name(self):
        entities = {"customer_name": "LLM Name", "email": None, "phone": None}
        origin = {"sender_name": "Origin Name", "sender_email": "", "sender_phone": ""}
        result = _apply_intake_fallback(entities, origin)
        assert result["customer_name"] == "LLM Name"

    def test_does_not_overwrite_llm_extracted_email(self):
        entities = {"customer_name": None, "email": "llm@example.com", "phone": None}
        origin = {"sender_name": "", "sender_email": "origin@example.com", "sender_phone": ""}
        result = _apply_intake_fallback(entities, origin)
        assert result["email"] == "llm@example.com"

    def test_empty_origin_leaves_nulls(self):
        entities = {"customer_name": None, "email": None, "phone": None}
        result = _apply_intake_fallback(entities, {})
        assert result["customer_name"] is None
        assert result["email"] is None
        assert result["phone"] is None

    def test_does_not_mutate_original_dict(self):
        entities = {"customer_name": None}
        original = dict(entities)
        _apply_intake_fallback(entities, {"sender_name": "X"})
        assert entities == original


class TestBuildSourceContext:
    def test_includes_flat_sender_name_in_context(self):
        job = _make_job({"sender_name": "Flat Kund", "sender_email": "flat@example.com"})
        ctx = _build_source_context(job)
        assert ctx["input_data"]["sender"]["name"] == "Flat Kund"

    def test_includes_flat_sender_email_in_context(self):
        job = _make_job({"sender_email": "flat@example.com"})
        ctx = _build_source_context(job)
        assert ctx["input_data"]["sender"]["email"] == "flat@example.com"

    def test_nested_sender_still_works(self):
        job = _make_job({"sender": {"name": "Nested", "email": "n@n.com", "phone": "070"}})
        ctx = _build_source_context(job)
        assert ctx["input_data"]["sender"]["name"] == "Nested"

    def test_nested_takes_precedence_over_flat(self):
        job = _make_job({
            "sender": {"name": "Nested", "email": "", "phone": ""},
            "sender_name": "Flat",
        })
        ctx = _build_source_context(job)
        assert ctx["input_data"]["sender"]["name"] == "Nested"


def _force_llm_failure(job: Job):
    """Run extraction with LLM forced to fail, triggering fallback_payload_builder."""
    from app.ai.exceptions import LLMConfigurationError
    with patch(
        "app.workflows.processors.entity_extraction_processor.get_latest_processor_payload",
        wraps=__import__(
            "app.workflows.processors.ai_processor_utils",
            fromlist=["get_latest_processor_payload"],
        ).get_latest_processor_payload,
    ), patch(
        "app.ai.llm.client.LLMClient.generate_json",
        side_effect=LLMConfigurationError("LLM_API_KEY is not configured"),
    ):
        return process_entity_extraction_job(job)


class TestFallbackPayloadBuilder:
    """Test that fallback path populates entities from intake origin when LLM fails."""

    def test_fallback_populates_customer_name_from_intake(self):
        job = _job_with_intake_and_flat_sender(sender_name="Testkund")
        result = _force_llm_failure(job)
        entities = result.result["payload"]["entities"]
        assert entities["customer_name"] == "Testkund"

    def test_fallback_populates_email_from_intake(self):
        job = _job_with_intake_and_flat_sender(sender_email="test@example.com")
        result = _force_llm_failure(job)
        entities = result.result["payload"]["entities"]
        assert entities["email"] == "test@example.com"

    def test_fallback_populates_phone_from_intake(self):
        job = _job_with_intake_and_flat_sender(sender_phone="0701234567")
        result = _force_llm_failure(job)
        entities = result.result["payload"]["entities"]
        # Validator may normalise phone format — just check it's not null
        assert entities["phone"] is not None
        assert "0701234567" in entities["phone"] or entities["phone"].startswith("+46")

    def test_fallback_does_not_report_missing_identity_when_name_present(self):
        job = _job_with_intake_and_flat_sender(sender_name="Testkund")
        result = _force_llm_failure(job)
        issues = result.result["payload"]["validation"]["issues"]
        assert "missing_identity" not in issues

    def test_fallback_still_reports_missing_requested_service(self):
        """missing_requested_service is expected — intake does not provide service info."""
        job = _job_with_intake_and_flat_sender()
        result = _force_llm_failure(job)
        issues = result.result["payload"]["validation"]["issues"]
        assert "missing_requested_service" in issues

    def test_fallback_result_is_not_none(self):
        """Job with no sender data should not crash."""
        job = _make_job({"subject": "Test", "message_text": "Hej"})
        job = process_universal_intake_job(job)
        job.job_type = JobType.ENTITY_EXTRACTION
        result = _force_llm_failure(job)
        assert result.result is not None
