"""
Tests for universal_intake_processor sender field normalization.

Covers:
  - Flat sender_* keys at input_data root are preserved in origin
  - Nested sender dict is still supported (existing behaviour)
  - Nested sender dict takes precedence over flat keys when both present
  - Missing sender fields produce empty strings (not None or missing keys)
"""
from __future__ import annotations

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.workflows.processors.intake_processor import process_universal_intake_job


def _make_job(input_data: dict) -> Job:
    return Job(
        tenant_id="TENANT_TEST",
        job_type=JobType.INTAKE,
        input_data=input_data,
    )


def _origin(job: Job) -> dict:
    payload = job.result["payload"]
    return payload["origin"]


class TestFlatSenderFields:
    def test_sender_name_from_flat_key(self):
        job = _make_job({"sender_name": "Testkund", "sender_email": "", "sender_phone": ""})
        result = process_universal_intake_job(job)
        assert _origin(result)["sender_name"] == "Testkund"

    def test_sender_email_from_flat_key(self):
        job = _make_job({"sender_email": "test@example.com"})
        result = process_universal_intake_job(job)
        assert _origin(result)["sender_email"] == "test@example.com"

    def test_sender_phone_from_flat_key(self):
        job = _make_job({"sender_phone": "0701234567"})
        result = process_universal_intake_job(job)
        assert _origin(result)["sender_phone"] == "0701234567"

    def test_all_flat_fields_preserved(self):
        job = _make_job({
            "subject": "Fråga om offert",
            "message_text": "Hej, jag vill ha en offert.",
            "sender_name": "Testkund",
            "sender_email": "test@example.com",
            "sender_phone": "0701234567",
        })
        result = process_universal_intake_job(job)
        origin = _origin(result)
        assert origin["sender_name"] == "Testkund"
        assert origin["sender_email"] == "test@example.com"
        assert origin["sender_phone"] == "0701234567"


class TestNestedSenderDict:
    def test_nested_sender_name_preserved(self):
        job = _make_job({"sender": {"name": "Nested Kund", "email": "nested@example.com", "phone": "070999"}})
        result = process_universal_intake_job(job)
        assert _origin(result)["sender_name"] == "Nested Kund"

    def test_nested_sender_email_preserved(self):
        job = _make_job({"sender": {"name": "", "email": "nested@example.com", "phone": ""}})
        result = process_universal_intake_job(job)
        assert _origin(result)["sender_email"] == "nested@example.com"

    def test_nested_sender_takes_precedence_over_flat(self):
        """Nested sender dict value wins when both nested and flat keys are present."""
        job = _make_job({
            "sender": {"name": "Nested Name", "email": "", "phone": ""},
            "sender_name": "Flat Name",
        })
        result = process_universal_intake_job(job)
        assert _origin(result)["sender_name"] == "Nested Name"


class TestMissingSenderFields:
    def test_missing_sender_fields_produce_empty_strings(self):
        job = _make_job({"subject": "Testar"})
        result = process_universal_intake_job(job)
        origin = _origin(result)
        assert origin["sender_name"] == ""
        assert origin["sender_email"] == ""
        assert origin["sender_phone"] == ""

    def test_origin_keys_always_present(self):
        job = _make_job({})
        result = process_universal_intake_job(job)
        origin = _origin(result)
        assert "sender_name" in origin
        assert "sender_email" in origin
        assert "sender_phone" in origin
