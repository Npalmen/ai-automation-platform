"""
Tests for Gmail lead enrichment: item naming, priority, and Monday column_values.

Covers:
  - _make_monday_item_name: sender name, sender email only, subject only, long subject trim
  - _infer_priority: high from urgent keywords, medium from normal subject, low fallback
  - gmail_process_inbox: Monday action includes column_values
  - column_values contains email, source, priority, subject when present
  - column_values omits email when sender email is empty
  - column_values omits subject when subject is "(no subject)"
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.main import (
    GmailProcessInboxRequest,
    _infer_priority,
    _make_monday_item_name,
    gmail_process_inbox,
)


# ── _make_monday_item_name ────────────────────────────────────────────────────

class TestMakeMondayItemName:
    def test_sender_name_and_subject(self):
        assert _make_monday_item_name("Erik Lindqvist", "erik@example.com", "New inquiry") == \
            "Lead: Erik Lindqvist - New inquiry"

    def test_sender_email_only_when_no_name(self):
        assert _make_monday_item_name("", "erik@example.com", "New inquiry") == \
            "Lead: erik@example.com - New inquiry"

    def test_subject_only_when_no_sender(self):
        assert _make_monday_item_name("", "", "New inquiry") == "Lead: New inquiry"

    def test_long_subject_is_trimmed(self):
        long_subject = "A" * 100
        result = _make_monday_item_name("Erik", "erik@example.com", long_subject)
        # subject portion should be at most 60 chars
        suffix = result.split(" - ", 1)[1]
        assert len(suffix) <= 60

    def test_exactly_60_char_subject_is_not_trimmed(self):
        subject = "B" * 60
        result = _make_monday_item_name("Erik", "e@e.com", subject)
        assert result.endswith("B" * 60)

    def test_no_empty_separator_when_label_missing(self):
        result = _make_monday_item_name("", "", "Some subject")
        assert " -  " not in result
        assert result == "Lead: Some subject"

    def test_sender_name_preferred_over_email(self):
        result = _make_monday_item_name("Erik", "erik@example.com", "Hi")
        assert "Erik" in result
        assert "erik@example.com" not in result


# ── _infer_priority ───────────────────────────────────────────────────────────

class TestInferPriority:
    @pytest.mark.parametrize("keyword", [
        "urgent", "URGENT", "Urgent",
        "asap", "ASAP",
        "immediately",
        "akut",
        "omgående",
        "critical",
        "emergency",
        "prioritet",
    ])
    def test_high_priority_from_subject_keywords(self, keyword):
        assert _infer_priority(f"This is {keyword} request", "") == "high"

    def test_high_priority_from_body_keyword(self):
        assert _infer_priority("Normal subject", "Please handle this asap") == "high"

    def test_medium_priority_for_normal_subject(self):
        assert _infer_priority("Question about your product", "") == "medium"

    def test_low_priority_when_no_subject(self):
        assert _infer_priority("(no subject)", "") == "low"

    def test_low_priority_when_empty_subject(self):
        assert _infer_priority("", "") == "low"

    def test_high_takes_precedence_over_everything(self):
        assert _infer_priority("URGENT: Re: something", "long body text") == "high"

    def test_medium_when_subject_present_no_keywords(self):
        result = _infer_priority("Meeting follow-up", "Thanks for your time today.")
        assert result == "medium"


# ── Monday action column_values in gmail_process_inbox ───────────────────────

def _make_processed_job(job_id: str = "job-1", status: str = "completed"):
    job = MagicMock()
    job.job_id = job_id
    job.status = MagicMock()
    job.status.value = status
    return job


def _detail_result(
    message_id: str,
    from_header: str = "Erik Lindqvist <erik@example.com>",
    subject: str = "New sales inquiry",
    body_text: str = "Hi, I would like to learn more.",
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


def _run_inbox(detail: dict, tenant_id: str = "TENANT_1001"):
    """Call gmail_process_inbox and capture the job passed to create_job."""
    captured_jobs: list = []

    mock_adapter = MagicMock()

    def fake_execute(action, payload):
        if action == "list_messages":
            return {"status": "success", "messages": [{"message_id": "msg1", "thread_id": "t1"}]}
        if action == "get_message":
            return detail
        return {"status": "success"}

    mock_adapter.execute_action.side_effect = fake_execute

    def fake_create_job(db, job):
        captured_jobs.append(job)
        return job

    with patch("app.main.get_integration_connection_config", return_value={}), \
         patch("app.main.get_integration_adapter", return_value=mock_adapter), \
         patch("app.main.get_tenant_config", return_value={"enabled_job_types": ["lead"]}), \
         patch("app.main.JobRepository.get_by_gmail_message_id", return_value=None), \
         patch("app.main.JobRepository.create_job", side_effect=fake_create_job), \
         patch("app.main.run_pipeline", return_value=_make_processed_job()):
        gmail_process_inbox(
            request=GmailProcessInboxRequest(max_results=5),
            db=MagicMock(),
            tenant_id=tenant_id,
        )

    assert captured_jobs, "No job was created"
    return captured_jobs[0]


class TestMondayActionPayload:
    def test_action_type_is_create_monday_item(self):
        job = _run_inbox(_detail_result("msg1"))
        action = job.input_data["actions"][0]
        assert action["type"] == "create_monday_item"

    def test_column_values_present_in_action(self):
        job = _run_inbox(_detail_result("msg1"))
        action = job.input_data["actions"][0]
        assert "column_values" in action
        assert isinstance(action["column_values"], dict)

    def test_column_values_includes_email(self):
        job = _run_inbox(_detail_result("msg1", from_header="Erik <erik@example.com>"))
        cv = job.input_data["actions"][0]["column_values"]
        assert cv["email"] == "erik@example.com"

    def test_column_values_includes_source_gmail(self):
        job = _run_inbox(_detail_result("msg1"))
        cv = job.input_data["actions"][0]["column_values"]
        assert cv["source"] == "gmail"

    def test_column_values_includes_priority(self):
        job = _run_inbox(_detail_result("msg1", subject="URGENT: call me"))
        cv = job.input_data["actions"][0]["column_values"]
        assert cv["priority"] == "high"

    def test_column_values_includes_subject(self):
        job = _run_inbox(_detail_result("msg1", subject="New sales inquiry"))
        cv = job.input_data["actions"][0]["column_values"]
        assert cv["subject"] == "New sales inquiry"

    def test_column_values_omits_email_when_missing(self):
        job = _run_inbox(_detail_result("msg1", from_header=""))
        cv = job.input_data["actions"][0]["column_values"]
        assert "email" not in cv

    def test_column_values_omits_subject_for_no_subject(self):
        job = _run_inbox(_detail_result("msg1", subject="(no subject)"))
        cv = job.input_data["actions"][0]["column_values"]
        assert "subject" not in cv

    def test_item_name_uses_sender_name(self):
        job = _run_inbox(_detail_result("msg1", from_header="Erik Lindqvist <erik@example.com>", subject="New inquiry"))
        action = job.input_data["actions"][0]
        assert action["item_name"] == "Lead: Erik Lindqvist - New inquiry"

    def test_item_name_uses_email_when_no_name(self):
        job = _run_inbox(_detail_result("msg1", from_header="erik@example.com", subject="Question"))
        action = job.input_data["actions"][0]
        assert action["item_name"] == "Lead: erik@example.com - Question"

    def test_item_name_subject_only_when_no_sender(self):
        job = _run_inbox(_detail_result("msg1", from_header="", subject="Pricing request"))
        action = job.input_data["actions"][0]
        assert action["item_name"] == "Lead: Pricing request"

    def test_priority_stored_in_input_data(self):
        job = _run_inbox(_detail_result("msg1", subject="URGENT: help"))
        assert job.input_data["priority"] == "high"

    def test_medium_priority_for_normal_message(self):
        job = _run_inbox(_detail_result("msg1", subject="Question about pricing"))
        assert job.input_data["priority"] == "medium"
