"""
Tests for improved From-header parsing and phone extraction.

Covers:
  _parse_from_header:
    - name + email (angle-bracket)
    - quoted name
    - bare email only
    - empty / malformed
    - name == email -> name suppressed

  _extract_phone:
    - Swedish mobile in body (070-xxx xx xx)
    - Swedish mobile in subject (0701234567)
    - +46 international in body
    - landline-style (018-123456)
    - no phone -> None
    - first match wins (subject before body)

  gmail_process_inbox integration:
    - phone stored in input_data.sender.phone when present
    - no phone -> phone key absent from sender
    - sender name/email parsed correctly from From header
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.main import (
    GmailProcessInboxRequest,
    _extract_phone,
    _parse_from_header,
    gmail_process_inbox,
)


# ── _parse_from_header ────────────────────────────────────────────────────────

class TestParseFromHeader:
    def test_name_and_email(self):
        name, email = _parse_from_header("Erik Lindqvist <erik@example.com>")
        assert name == "Erik Lindqvist"
        assert email == "erik@example.com"

    def test_quoted_name(self):
        name, email = _parse_from_header('"Erik Lindqvist" <erik@example.com>')
        assert name == "Erik Lindqvist"
        assert email == "erik@example.com"

    def test_bare_email_no_name(self):
        name, email = _parse_from_header("erik@example.com")
        assert name == ""
        assert email == "erik@example.com"

    def test_empty_string(self):
        name, email = _parse_from_header("")
        assert name == ""
        assert email == ""

    def test_malformed_no_at_sign(self):
        name, email = _parse_from_header("not-an-email")
        # parseaddr treats this as display name with empty email
        # we don't crash; email may be empty
        assert isinstance(name, str)
        assert isinstance(email, str)

    def test_name_equals_email_is_suppressed(self):
        # Sender sets display name to their email address (quoted form that parseaddr handles)
        name, email = _parse_from_header('"erik@example.com" <erik@example.com>')
        assert email == "erik@example.com"
        assert name == ""  # redundant copy suppressed

    def test_email_normalised_to_lowercase(self):
        _, email = _parse_from_header("Erik <Erik@EXAMPLE.COM>")
        assert email == "erik@example.com"

    def test_extra_whitespace_trimmed(self):
        name, email = _parse_from_header("  Erik Lindqvist  <  erik@example.com  >")
        assert name == "Erik Lindqvist"
        assert email == "erik@example.com"


# ── _extract_phone ────────────────────────────────────────────────────────────

class TestExtractPhone:
    def test_swedish_mobile_with_dashes_in_body(self):
        result = _extract_phone("", "Ring mig på 070-123 45 67 tack")
        assert result is not None
        assert "070" in result
        assert "123" in result

    def test_swedish_mobile_digits_only_in_subject(self):
        result = _extract_phone("Ring 0701234567", "")
        assert result is not None
        assert "070" in result

    def test_plus46_in_body(self):
        result = _extract_phone("", "Nås på +46701234567")
        assert result is not None
        assert "46" in result

    def test_plus46_with_spaces_in_body(self):
        result = _extract_phone("", "Tel: +46 70 123 45 67")
        assert result is not None
        assert "46" in result

    def test_landline_style_in_body(self):
        result = _extract_phone("", "Kontoret: 018-123456")
        assert result is not None
        assert "018" in result

    def test_no_phone_returns_none(self):
        result = _extract_phone("Normal subject", "Hello, please get back to me.")
        assert result is None

    def test_subject_searched_before_body(self):
        # Subject has a phone, body has a different one — subject phone wins.
        result = _extract_phone("Call 070-111 11 11", "Or try 070-222 22 22")
        assert result is not None
        assert "111" in result

    def test_empty_inputs_returns_none(self):
        assert _extract_phone("", "") is None

    def test_result_is_string_or_none(self):
        result = _extract_phone("Call me at 070-123 45 67", "")
        assert result is None or isinstance(result, str)

    def test_0046_prefix_recognised(self):
        result = _extract_phone("", "Mobil: 0046701234567")
        assert result is not None
        assert "0046" in result or "46" in result


# ── integration: phone wired into payload ─────────────────────────────────────

def _make_processed_job(job_id: str = "job-1", status: str = "completed"):
    job = MagicMock()
    job.job_id = job_id
    job.status = MagicMock()
    job.status.value = status
    return job


def _detail_result(
    message_id: str = "msg1",
    from_header: str = "Erik Lindqvist <erik@example.com>",
    subject: str = "New inquiry",
    body_text: str = "Hi there.",
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
         patch("app.main.get_tenant_config", return_value={"enabled_job_types": ["lead", "invoice", "customer_inquiry"]}), \
         patch("app.main.JobRepository.get_by_gmail_message_id", return_value=None), \
         patch("app.main.JobRepository.create_job", side_effect=fake_create_job), \
         patch("app.main.run_pipeline", return_value=_make_processed_job()), \
         patch("app.main.dispatch_action", return_value={"status": "success"}):
        gmail_process_inbox(
            request=GmailProcessInboxRequest(max_results=5),
            db=MagicMock(),
            tenant_id=tenant_id,
        )

    assert captured_jobs, "No job was created"
    return captured_jobs[0]


class TestPhoneInPayload:
    def test_phone_stored_in_sender_when_present(self):
        job = _run_inbox(_detail_result(body_text="Ring mig på 070-123 45 67"))
        assert "phone" in job.input_data["sender"]
        assert "070" in job.input_data["sender"]["phone"]

    def test_no_phone_omitted_from_sender(self):
        job = _run_inbox(_detail_result(body_text="No number here."))
        assert "phone" not in job.input_data["sender"]

    def test_phone_from_subject_stored(self):
        job = _run_inbox(_detail_result(subject="Call 0701234567 please", body_text=""))
        assert "phone" in job.input_data["sender"]

    def test_sender_name_parsed_correctly(self):
        job = _run_inbox(_detail_result(from_header='"Erik Lindqvist" <erik@example.com>'))
        assert job.input_data["sender"]["name"] == "Erik Lindqvist"
        assert job.input_data["sender"]["email"] == "erik@example.com"

    def test_sender_email_lowercase(self):
        job = _run_inbox(_detail_result(from_header="Erik <Erik@EXAMPLE.COM>"))
        assert job.input_data["sender"]["email"] == "erik@example.com"

    def test_redundant_name_suppressed(self):
        job = _run_inbox(_detail_result(from_header='"erik@example.com" <erik@example.com>'))
        assert job.input_data["sender"]["name"] == ""
        assert job.input_data["sender"]["email"] == "erik@example.com"
