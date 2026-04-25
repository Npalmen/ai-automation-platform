"""
Tests for customer_inquiry default action injection, structured data, and priority.

Covers:
  classify_inquiry_priority:
    - subject keywords → HIGH
    - body keywords → HIGH
    - normal message → NORMAL
    - case-insensitive
    - empty strings → NORMAL

  normalize_sender / extract_phone (shared helpers):
    - nested sender dict
    - flat sender_* keys
    - mixed / missing fields
    - phone extracted from message_text

  _build_inquiry_default_actions:
    - produces create_monday_item + send_email
    - HIGH priority: item_name prefixed with [HIGH], email subject includes [HIGH]
    - NORMAL priority: no prefix, standard email subject
    - column_values includes priority, email, phone, source, subject, message
    - phone omitted from column_values when absent
    - email body includes priority and all structured fields
    - flat sender_name / sender_email backward-compatible
    - empty input still produces valid actions

  _resolve_actions:
    - inquiry without input_data.actions → defaults injected
    - inquiry WITH input_data.actions → override wins
    - lead job → inquiry defaults not used

  process_action_dispatch_job (mocked execute_action):
    - executes both default actions for inquiry
    - override actions executed as-is
    - status completed when all succeed
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.workflows.processors.action_dispatch_processor import (
    _build_fallback_actions,
    _build_inquiry_default_actions,
    _resolve_actions,
    process_action_dispatch_job,
)
from app.workflows.processors.ai_processor_utils import (
    classify_inquiry_priority,
    extract_phone,
    normalize_sender,
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
        # key is "processor", not "processor_name" — matches append_processor_result
        job.processor_history = [
            {
                "processor": "classification_processor",
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


# ── classify_inquiry_priority ────────────────────────────────────────────────

class TestClassifyInquiryPriority:
    def test_subject_akut_is_high(self):
        assert classify_inquiry_priority("akut problem", "") == "HIGH"

    def test_subject_snabbt_is_high(self):
        assert classify_inquiry_priority("Behöver hjälp snabbt", "") == "HIGH"

    def test_subject_problem_is_high(self):
        assert classify_inquiry_priority("problem med produkten", "") == "HIGH"

    def test_body_akut_is_high(self):
        assert classify_inquiry_priority("", "Det är akut") == "HIGH"

    def test_body_snabbt_is_high(self):
        assert classify_inquiry_priority("Fråga", "Behöver svar snabbt") == "HIGH"

    def test_body_problem_is_high(self):
        assert classify_inquiry_priority("Support", "Har ett problem med faktura") == "HIGH"

    def test_normal_message_is_normal(self):
        assert classify_inquiry_priority("Fråga om leverans", "När kommer min order?") == "NORMAL"

    def test_empty_subject_and_body_is_normal(self):
        assert classify_inquiry_priority("", "") == "NORMAL"

    def test_case_insensitive_upper(self):
        assert classify_inquiry_priority("AKUT ÄRENDE", "") == "HIGH"

    def test_case_insensitive_mixed(self):
        assert classify_inquiry_priority("", "Det är ett Problem") == "HIGH"

    def test_keyword_in_body_wins(self):
        assert classify_inquiry_priority("Vanlig fråga", "men det är akut") == "HIGH"

    def test_no_false_positive_on_unrelated_word(self):
        assert classify_inquiry_priority("Fråga om öppettider", "Hej, när öppnar ni?") == "NORMAL"


# ── normalize_sender ──────────────────────────────────────────────────────────

class TestNormalizeSender:
    def test_nested_sender_dict(self):
        s = normalize_sender({"sender": {"name": "Anna", "email": "a@ex.com", "phone": "070-123"}})
        assert s == {"name": "Anna", "email": "a@ex.com", "phone": "070-123"}

    def test_flat_keys(self):
        s = normalize_sender({"sender_name": "Bo", "sender_email": "bo@ex.com"})
        assert s["name"] == "Bo"
        assert s["email"] == "bo@ex.com"

    def test_nested_takes_priority_over_flat(self):
        s = normalize_sender({
            "sender": {"name": "Nested"},
            "sender_name": "Flat",
        })
        assert s["name"] == "Nested"

    def test_missing_name_omitted(self):
        s = normalize_sender({"sender": {"email": "x@x.com"}})
        assert "name" not in s

    def test_missing_email_omitted(self):
        s = normalize_sender({"sender": {"name": "X"}})
        assert "email" not in s

    def test_missing_phone_omitted(self):
        s = normalize_sender({"sender": {"name": "X", "email": "x@x.com"}})
        assert "phone" not in s

    def test_email_lowercased(self):
        s = normalize_sender({"sender": {"email": "USER@EXAMPLE.COM"}})
        assert s["email"] == "user@example.com"

    def test_empty_input_data(self):
        s = normalize_sender({})
        assert s == {}

    def test_whitespace_stripped(self):
        s = normalize_sender({"sender": {"name": "  Anna  ", "email": "  a@ex.com  "}})
        assert s["name"] == "Anna"
        assert s["email"] == "a@ex.com"


# ── extract_phone ─────────────────────────────────────────────────────────────

class TestExtractPhone:
    def test_phone_in_body(self):
        result = extract_phone("Fråga", "Ring mig på 070-123 45 67")
        assert result is not None
        assert "070" in result

    def test_phone_in_subject(self):
        result = extract_phone("Ring 070-999 88 77", "")
        assert result is not None

    def test_no_phone_returns_none(self):
        assert extract_phone("Hej", "Jag har en fråga") is None

    def test_subject_checked_before_body(self):
        result = extract_phone("0701234567", "Call 0709876543")
        assert "070" in result and "1234" in result


# ── _build_inquiry_default_actions ───────────────────────────────────────────

def _get_monday(actions):
    return next(a for a in actions if a["type"] == "create_monday_item")


def _get_handoff(actions):
    return next(a for a in actions if a["type"] == "send_internal_handoff")


class TestBuildInquiryDefaultActions:
    def test_produces_three_actions(self):
        job = _inquiry_job({
            "subject": "Hjälp",
            "sender": {"name": "Anna", "email": "a@ex.com"},
            "message_text": "Jag behöver hjälp med mitt abonnemang snarast.",
        })
        actions = _build_inquiry_default_actions(job)
        assert len(actions) == 3

    def test_first_action_is_create_monday_item(self):
        actions = _build_inquiry_default_actions(
            _inquiry_job({"subject": "S", "sender": {"email": "x@x.com"}})
        )
        monday = _get_monday(actions)
        assert monday["type"] == "create_monday_item"

    def test_second_action_is_send_internal_handoff(self):
        actions = _build_inquiry_default_actions(
            _inquiry_job({"subject": "S", "sender": {"email": "x@x.com"}})
        )
        handoff = _get_handoff(actions)
        assert handoff["type"] == "send_internal_handoff"

    # item_name ---

    def test_item_name_format_name_and_subject(self):
        job = _inquiry_job({"subject": "Min produkt fungerar inte", "sender": {"name": "Erik", "email": "e@ex.com"}})
        assert _get_monday(_build_inquiry_default_actions(job))["item_name"] == "Support: Erik - Min produkt fungerar inte"

    def test_item_name_uses_email_when_no_name(self):
        job = _inquiry_job({"subject": "Fråga", "sender": {"email": "anon@ex.com"}})
        assert "anon@ex.com" in _get_monday(_build_inquiry_default_actions(job))["item_name"]

    def test_item_name_missing_sender_fallback(self):
        job = _inquiry_job({"subject": "Fråga"})
        name = _get_monday(_build_inquiry_default_actions(job))["item_name"]
        assert name.startswith("Support:")
        assert "Okänd avsändare" in name

    def test_item_name_truncated_at_80_chars(self):
        job = _inquiry_job({"subject": "A" * 100, "sender": {"name": "X"}})
        assert len(_get_monday(_build_inquiry_default_actions(job))["item_name"]) <= 80

    def test_item_name_flat_sender_keys(self):
        job = _inquiry_job({"subject": "Test", "sender_name": "Flat", "sender_email": "flat@ex.com"})
        assert "Flat" in _get_monday(_build_inquiry_default_actions(job))["item_name"]

    # priority ---

    def test_high_priority_prefixes_item_name(self):
        job = _inquiry_job({"subject": "Akut problem med enheten", "sender": {"name": "Anna"}})
        item_name = _get_monday(_build_inquiry_default_actions(job))["item_name"]
        assert item_name.startswith("[HIGH]")

    def test_normal_priority_no_prefix(self):
        job = _inquiry_job({"subject": "Fråga om leverans", "sender": {"name": "Bo"}})
        item_name = _get_monday(_build_inquiry_default_actions(job))["item_name"]
        assert not item_name.startswith("[HIGH]")

    def test_high_priority_email_subject_includes_high(self):
        job = _inquiry_job({"subject": "Akut", "message_text": ""})
        email_subject = _get_handoff(_build_inquiry_default_actions(job))["subject"]
        assert "[HIGH]" in email_subject or "HIGH" in email_subject

    def test_normal_priority_email_subject_no_high(self):
        job = _inquiry_job({"subject": "Fråga"})
        email_subject = _get_handoff(_build_inquiry_default_actions(job))["subject"]
        assert "[HIGH]" not in email_subject

    def test_email_body_contains_priority_high(self):
        job = _inquiry_job({"subject": "Akut ärende"})
        body = _get_handoff(_build_inquiry_default_actions(job))["body"]
        assert "HIGH" in body

    def test_email_body_contains_priority_normal(self):
        job = _inquiry_job({"subject": "Vanlig fråga"})
        body = _get_handoff(_build_inquiry_default_actions(job))["body"]
        assert "NORMAL" in body

    def test_column_values_contains_priority(self):
        job = _inquiry_job({"subject": "Test"})
        cv = _get_monday(_build_inquiry_default_actions(job))["column_values"]
        assert cv["priority"] in ("HIGH", "NORMAL")

    def test_column_values_priority_high_for_urgent(self):
        job = _inquiry_job({"subject": "Akut"})
        cv = _get_monday(_build_inquiry_default_actions(job))["column_values"]
        assert cv["priority"] == "HIGH"

    def test_column_values_priority_normal_for_standard(self):
        job = _inquiry_job({"subject": "Fråga"})
        cv = _get_monday(_build_inquiry_default_actions(job))["column_values"]
        assert cv["priority"] == "NORMAL"

    # column_values ---

    def test_column_values_source_is_inquiry(self):
        job = _inquiry_job({"subject": "T"})
        cv = _get_monday(_build_inquiry_default_actions(job))["column_values"]
        assert cv["source"] == "inquiry"

    def test_column_values_contains_email(self):
        job = _inquiry_job({"subject": "T", "sender": {"email": "bo@ex.com"}})
        cv = _get_monday(_build_inquiry_default_actions(job))["column_values"]
        assert cv["email"] == "bo@ex.com"

    def test_column_values_contains_phone_when_present(self):
        job = _inquiry_job({
            "subject": "T",
            "sender": {"email": "x@x.com"},
            "message_text": "Nå mig på 070-111 22 33",
        })
        cv = _get_monday(_build_inquiry_default_actions(job))["column_values"]
        assert "phone" in cv
        assert "070" in cv["phone"]

    def test_column_values_omits_phone_when_absent(self):
        job = _inquiry_job({"subject": "T", "sender": {"email": "x@x.com"}, "message_text": "Ingen telefon"})
        cv = _get_monday(_build_inquiry_default_actions(job))["column_values"]
        assert "phone" not in cv

    def test_column_values_contains_subject(self):
        job = _inquiry_job({"subject": "Specialfråga", "sender": {"email": "x@x.com"}})
        cv = _get_monday(_build_inquiry_default_actions(job))["column_values"]
        assert cv["subject"] == "Specialfråga"

    def test_column_values_contains_message(self):
        job = _inquiry_job({"subject": "T", "sender": {"email": "x@x.com"}, "message_text": "Detaljerat problem"})
        cv = _get_monday(_build_inquiry_default_actions(job))["column_values"]
        assert cv["message"] == "Detaljerat problem"

    def test_column_values_message_truncated_at_200(self):
        job = _inquiry_job({"subject": "T", "message_text": "X" * 300})
        cv = _get_monday(_build_inquiry_default_actions(job))["column_values"]
        assert len(cv["message"]) <= 200

    def test_column_values_omits_email_when_missing(self):
        job = _inquiry_job({"subject": "T", "message_text": "Hej"})
        cv = _get_monday(_build_inquiry_default_actions(job))["column_values"]
        assert "email" not in cv

    def test_column_values_omits_message_when_missing(self):
        job = _inquiry_job({"subject": "T"})
        cv = _get_monday(_build_inquiry_default_actions(job))["column_values"]
        assert "message" not in cv

    # internal handoff action ---

    def test_email_to_is_support_address(self):
        job = _inquiry_job({"subject": "T"})
        assert _get_handoff(_build_inquiry_default_actions(job))["to"] == "support@company.com"

    def test_email_subject_is_ny_kundfraga(self):
        job = _inquiry_job({"subject": "T"})
        assert "kundfråga" in _get_handoff(_build_inquiry_default_actions(job))["subject"].lower()

    def test_email_body_contains_sender_name(self):
        job = _inquiry_job({"subject": "S", "sender": {"name": "Lena", "email": "l@ex.com"}})
        assert "Lena" in _get_handoff(_build_inquiry_default_actions(job))["body"]

    def test_email_body_contains_sender_email(self):
        job = _inquiry_job({"subject": "S", "sender": {"email": "lena@ex.com"}})
        assert "lena@ex.com" in _get_handoff(_build_inquiry_default_actions(job))["body"]

    def test_email_body_contains_phone_when_present(self):
        job = _inquiry_job({
            "subject": "S",
            "message_text": "Ring 070-555 44 33",
            "sender": {"email": "x@x.com"},
        })
        body = _get_handoff(_build_inquiry_default_actions(job))["body"]
        assert "070" in body

    def test_email_body_omits_phone_line_when_absent(self):
        job = _inquiry_job({"subject": "S", "sender": {"email": "x@x.com"}, "message_text": "Ingen tel"})
        body = _get_handoff(_build_inquiry_default_actions(job))["body"]
        assert "Telefon" not in body

    def test_email_body_contains_subject(self):
        job = _inquiry_job({"subject": "Specialfråga"})
        assert "Specialfråga" in _get_handoff(_build_inquiry_default_actions(job))["body"]

    def test_email_body_contains_message_text(self):
        job = _inquiry_job({"subject": "S", "message_text": "Jag behöver hjälp"})
        assert "Jag behöver hjälp" in _get_handoff(_build_inquiry_default_actions(job))["body"]

    def test_email_body_contains_job_id(self):
        job = _inquiry_job({"subject": "S"})
        job.job_id = "job-abc-123"
        assert "job-abc-123" in _get_handoff(_build_inquiry_default_actions(job))["body"]

    def test_email_body_contains_tenant_id(self):
        job = _inquiry_job({"subject": "S"})
        assert "TENANT_1001" in _get_handoff(_build_inquiry_default_actions(job))["body"]

    def test_email_body_contains_source(self):
        job = _inquiry_job({"subject": "S"})
        assert "inquiry" in _get_handoff(_build_inquiry_default_actions(job))["body"]

    def test_source_from_nested_source_dict(self):
        job = _inquiry_job({"subject": "S", "source": {"system": "gmail"}})
        body = _get_handoff(_build_inquiry_default_actions(job))["body"]
        assert "gmail" in body

    def test_empty_input_data_produces_valid_actions(self):
        job = _inquiry_job({})
        actions = _build_inquiry_default_actions(job)
        assert len(actions) == 3
        types = {a["type"] for a in actions}
        assert "create_monday_item" in types
        assert "send_internal_handoff" in types


# ── _build_fallback_actions routing ──────────────────────────────────────────

class TestFallbackActionRouting:
    def test_inquiry_gets_inquiry_defaults(self):
        job = _inquiry_job({"subject": "Test"})
        types = [a["type"] for a in _build_fallback_actions(job)]
        assert "create_monday_item" in types
        assert "send_internal_handoff" in types

    def test_lead_does_not_get_inquiry_defaults(self):
        job = _lead_job({"subject": "Offert"})
        types = [a["type"] for a in _build_fallback_actions(job)]
        # lead fallback produces create_internal_task (no actions provided)
        assert not any(
            a.get("column_values", {}).get("source") == "inquiry"
            for a in _build_fallback_actions(job)
        )

    def test_unknown_type_uses_generic_fallback(self):
        job = _make_job(job_type=JobType.UNKNOWN, classification_detected="unknown")
        types = [a["type"] for a in _build_fallback_actions(job)]
        assert "create_internal_task" in types

    def test_lead_fallback_has_no_inquiry_priority_field(self):
        job = _lead_job({"subject": "Offert"})
        for action in _build_fallback_actions(job):
            cv = action.get("column_values", {})
            assert cv.get("source") != "inquiry"


# ── _resolve_actions override behaviour ──────────────────────────────────────

class TestResolveActions:
    def test_inquiry_without_input_actions_gets_defaults(self):
        job = _inquiry_job({"subject": "Min laddbox", "sender": {"email": "k@ex.com"}})
        types = [a["type"] for a in _resolve_actions(job)]
        assert "create_monday_item" in types
        assert "send_internal_handoff" in types

    def test_inquiry_with_input_actions_uses_override(self):
        override = [{"type": "notify_slack", "channel": "#support", "message": "msg"}]
        job = _inquiry_job({"subject": "Test", "actions": override})
        actions = _resolve_actions(job)
        assert len(actions) == 1
        assert actions[0]["type"] == "notify_slack"

    def test_lead_without_input_actions_does_not_get_inquiry_defaults(self):
        job = _lead_job({"subject": "Offert önskas"})
        types = [a["type"] for a in _resolve_actions(job)]
        inquiry_monday = [
            a for a in _resolve_actions(job)
            if a.get("column_values", {}).get("source") == "inquiry"
        ]
        assert not inquiry_monday


# ── process_action_dispatch_job (end-to-end with mocked execute_action) ──────

class TestProcessActionDispatch:
    def _run(self, job: Job) -> Job:
        with patch(
            "app.workflows.processors.action_dispatch_processor.execute_action",
            return_value={"status": "success", "type": "stub"},
        ):
            return process_action_dispatch_job(job, db=None)

    def test_inquiry_default_actions_both_in_requested(self):
        job = _inquiry_job({"subject": "Problem", "sender": {"name": "Ali", "email": "a@ex.com"}})
        result = self._run(job)
        types = [a.get("type") for a in result.result["payload"]["actions_requested"]]
        assert "create_monday_item" in types
        assert "send_internal_handoff" in types

    def test_inquiry_with_override_executes_override_only(self):
        override = [{"type": "notify_slack", "channel": "#s", "message": "m"}]
        job = _inquiry_job({"subject": "Test", "actions": override})
        result = self._run(job)
        types = [a.get("type") for a in result.result["payload"]["actions_requested"]]
        assert types == ["notify_slack"]

    def test_status_completed_when_all_succeed(self):
        job = _inquiry_job({"subject": "Test"})
        result = self._run(job)
        assert result.result["status"] == "completed"

    def test_column_values_source_in_monday_action(self):
        job = _inquiry_job({"subject": "Fråga", "sender": {"email": "x@x.com"}})
        result = self._run(job)
        monday = next(
            a for a in result.result["payload"]["actions_requested"]
            if a.get("type") == "create_monday_item"
        )
        assert monday["column_values"]["source"] == "inquiry"

    def test_email_body_contains_job_id_after_save(self):
        job = _inquiry_job({"subject": "Fråga"})
        job.job_id = "saved-job-id"
        result = self._run(job)
        handoff_action = next(
            a for a in result.result["payload"]["actions_requested"]
            if a.get("type") == "send_internal_handoff"
        )
        assert "saved-job-id" in handoff_action["body"]
