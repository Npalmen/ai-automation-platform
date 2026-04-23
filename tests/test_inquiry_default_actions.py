"""
Tests for customer_inquiry default action injection.

Covers:
  _build_inquiry_default_actions:
    - produces create_monday_item + send_email
    - item_name format: "Support: {sender} - {subject}"
    - missing sender/subject falls back cleanly
    - email body contains expected fields

  _resolve_actions (via process_action_dispatch_job):
    - inquiry without input_data.actions → default actions injected
    - inquiry WITH input_data.actions → defaults NOT added (override wins)
    - lead job → inquiry defaults NOT used (lead path unchanged)

  process_action_dispatch_job (mocked execute_action):
    - executes both default actions for inquiry
    - override actions executed as-is
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.workflows.processors.action_dispatch_processor import (
    _build_inquiry_default_actions,
    _build_fallback_actions,
    _resolve_actions,
    process_action_dispatch_job,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_job(
    job_type: JobType = JobType.CUSTOMER_INQUIRY,
    input_data: dict | None = None,
    classification_detected: str | None = None,
) -> Job:
    job = Job(
        tenant_id="TENANT_1001",
        job_type=job_type,
        input_data=input_data or {},
    )
    if classification_detected is not None:
        job.processor_history = [
            {
                "processor_name": "classification_processor",
                "result": {
                    "payload": {"detected_job_type": classification_detected},
                },
            }
        ]
    return job


def _inquiry_job(input_data: dict | None = None) -> Job:
    return _make_job(
        job_type=JobType.CUSTOMER_INQUIRY,
        input_data=input_data,
        classification_detected="customer_inquiry",
    )


def _lead_job(input_data: dict | None = None) -> Job:
    return _make_job(
        job_type=JobType.LEAD,
        input_data=input_data,
        classification_detected="lead",
    )


# ── _build_inquiry_default_actions ───────────────────────────────────────────

class TestBuildInquiryDefaultActions:
    def test_produces_two_actions(self):
        job = _inquiry_job({"subject": "Hjälp", "sender": {"name": "Anna", "email": "a@ex.com"}})
        actions = _build_inquiry_default_actions(job)
        assert len(actions) == 2

    def test_first_action_is_create_monday_item(self):
        job = _inquiry_job({"subject": "Hjälp", "sender": {"name": "Anna", "email": "a@ex.com"}})
        actions = _build_inquiry_default_actions(job)
        assert actions[0]["type"] == "create_monday_item"

    def test_second_action_is_send_email(self):
        job = _inquiry_job({"subject": "Hjälp", "sender": {"name": "Anna", "email": "a@ex.com"}})
        actions = _build_inquiry_default_actions(job)
        assert actions[1]["type"] == "send_email"

    def test_item_name_format(self):
        job = _inquiry_job({"subject": "Min produkt fungerar inte", "sender": {"name": "Erik", "email": "e@ex.com"}})
        actions = _build_inquiry_default_actions(job)
        assert actions[0]["item_name"] == "Support: Erik - Min produkt fungerar inte"

    def test_item_name_uses_email_when_no_name(self):
        job = _inquiry_job({"subject": "Fråga", "sender": {"name": "", "email": "anon@ex.com"}})
        actions = _build_inquiry_default_actions(job)
        assert "anon@ex.com" in actions[0]["item_name"]

    def test_item_name_missing_sender_fallback(self):
        job = _inquiry_job({"subject": "Fråga"})
        actions = _build_inquiry_default_actions(job)
        assert actions[0]["item_name"].startswith("Support:")
        assert "Okänd avsändare" in actions[0]["item_name"]

    def test_item_name_missing_subject_fallback(self):
        job = _inquiry_job({"sender": {"name": "Erik", "email": "e@ex.com"}})
        actions = _build_inquiry_default_actions(job)
        assert "Erik" in actions[0]["item_name"]
        assert actions[0]["item_name"].startswith("Support:")

    def test_item_name_truncated_at_80_chars(self):
        long_subject = "A" * 100
        job = _inquiry_job({"subject": long_subject, "sender": {"name": "X", "email": "x@x.com"}})
        actions = _build_inquiry_default_actions(job)
        assert len(actions[0]["item_name"]) <= 80

    def test_column_values_contains_email(self):
        job = _inquiry_job({"subject": "Test", "sender": {"name": "Bo", "email": "bo@ex.com"}})
        actions = _build_inquiry_default_actions(job)
        assert actions[0]["column_values"]["email"] == "bo@ex.com"

    def test_column_values_source_is_inquiry(self):
        job = _inquiry_job({"subject": "Test", "sender": {"email": "x@x.com"}})
        actions = _build_inquiry_default_actions(job)
        assert actions[0]["column_values"]["source"] == "inquiry"

    def test_email_to_is_support_address(self):
        job = _inquiry_job({"subject": "Test", "sender": {"email": "x@x.com"}})
        actions = _build_inquiry_default_actions(job)
        assert actions[1]["to"] == "support@company.com"

    def test_email_subject_is_ny_kundfraga(self):
        job = _inquiry_job({"subject": "Test"})
        actions = _build_inquiry_default_actions(job)
        assert actions[1]["subject"] == "Ny kundfråga"

    def test_email_body_contains_sender_name(self):
        job = _inquiry_job({"subject": "S", "sender": {"name": "Lena", "email": "l@ex.com"}, "message_text": "Help"})
        actions = _build_inquiry_default_actions(job)
        assert "Lena" in actions[1]["body"]

    def test_email_body_contains_sender_email(self):
        job = _inquiry_job({"subject": "S", "sender": {"name": "Lena", "email": "lena@ex.com"}, "message_text": "Help"})
        actions = _build_inquiry_default_actions(job)
        assert "lena@ex.com" in actions[1]["body"]

    def test_email_body_contains_subject(self):
        job = _inquiry_job({"subject": "Specialfråga", "sender": {"email": "x@x.com"}})
        actions = _build_inquiry_default_actions(job)
        assert "Specialfråga" in actions[1]["body"]

    def test_email_body_contains_message_text(self):
        job = _inquiry_job({"subject": "S", "sender": {"email": "x@x.com"}, "message_text": "Jag behöver hjälp"})
        actions = _build_inquiry_default_actions(job)
        assert "Jag behöver hjälp" in actions[1]["body"]

    def test_email_body_contains_job_id(self):
        job = _inquiry_job({"subject": "S"})
        job.job_id = "job-abc-123"
        actions = _build_inquiry_default_actions(job)
        assert "job-abc-123" in actions[1]["body"]

    def test_email_body_contains_tenant_id(self):
        job = _inquiry_job({"subject": "S"})
        actions = _build_inquiry_default_actions(job)
        assert "TENANT_1001" in actions[1]["body"]

    def test_flat_sender_keys_supported(self):
        job = _inquiry_job({"subject": "Test", "sender_name": "Flat", "sender_email": "flat@ex.com"})
        actions = _build_inquiry_default_actions(job)
        assert "Flat" in actions[0]["item_name"]

    def test_empty_input_data_produces_valid_actions(self):
        job = _inquiry_job({})
        actions = _build_inquiry_default_actions(job)
        assert len(actions) == 2
        assert actions[0]["type"] == "create_monday_item"
        assert actions[1]["type"] == "send_email"


# ── _build_fallback_actions routing ──────────────────────────────────────────

class TestFallbackActionRouting:
    def test_inquiry_job_gets_inquiry_defaults(self):
        job = _inquiry_job({"subject": "Test"})
        actions = _build_fallback_actions(job)
        types = [a["type"] for a in actions]
        assert "create_monday_item" in types
        assert "send_email" in types

    def test_lead_job_does_not_get_inquiry_defaults(self):
        job = _lead_job({"subject": "Offert"})
        actions = _build_fallback_actions(job)
        types = [a["type"] for a in actions]
        assert "create_monday_item" not in types
        assert "send_email" not in types

    def test_unknown_job_type_uses_generic_fallback(self):
        job = _make_job(job_type=JobType.UNKNOWN, classification_detected="unknown")
        actions = _build_fallback_actions(job)
        assert any(a["type"] == "create_internal_task" for a in actions)


# ── _resolve_actions override behaviour ──────────────────────────────────────

class TestResolveActions:
    def test_inquiry_without_input_actions_gets_defaults(self):
        job = _inquiry_job({"subject": "Min laddbox", "sender": {"email": "k@ex.com"}})
        actions = _resolve_actions(job)
        types = [a["type"] for a in actions]
        assert "create_monday_item" in types
        assert "send_email" in types

    def test_inquiry_with_input_actions_uses_override(self):
        override = [{"type": "notify_slack", "channel": "#support", "message": "msg"}]
        job = _inquiry_job({"subject": "Test", "actions": override})
        actions = _resolve_actions(job)
        assert len(actions) == 1
        assert actions[0]["type"] == "notify_slack"

    def test_lead_without_input_actions_does_not_get_inquiry_defaults(self):
        job = _lead_job({"subject": "Offert önskas"})
        actions = _resolve_actions(job)
        types = [a["type"] for a in actions]
        assert "create_monday_item" not in types


# ── process_action_dispatch_job (end-to-end with mocked execute_action) ──────

class TestProcessActionDispatch:
    def _run(self, job: Job) -> Job:
        with patch(
            "app.workflows.processors.action_dispatch_processor.execute_action",
            return_value={"status": "success", "type": "stub"},
        ):
            return process_action_dispatch_job(job, db=None)

    def test_inquiry_default_actions_both_executed(self):
        job = _inquiry_job({"subject": "Problem", "sender": {"name": "Ali", "email": "a@ex.com"}})
        result = self._run(job)
        executed_types = [
            a.get("type") for a in result.result["payload"]["actions_requested"]
        ]
        assert "create_monday_item" in executed_types
        assert "send_email" in executed_types

    def test_inquiry_with_override_executes_override_only(self):
        override = [{"type": "notify_slack", "channel": "#s", "message": "m"}]
        job = _inquiry_job({"subject": "Test", "actions": override})
        result = self._run(job)
        types = [a.get("type") for a in result.result["payload"]["actions_requested"]]
        assert types == ["notify_slack"]

    def test_lead_does_not_produce_inquiry_defaults(self):
        job = _lead_job({"subject": "Offert"})
        result = self._run(job)
        types = [a.get("type") for a in result.result["payload"]["actions_requested"]]
        assert "create_monday_item" not in types or result.result["payload"]["actions_requested"][0].get("column_values", {}).get("source") != "inquiry"

    def test_status_completed_when_all_succeed(self):
        job = _inquiry_job({"subject": "Test"})
        result = self._run(job)
        assert result.result["status"] == "completed"
