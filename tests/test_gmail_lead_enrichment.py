"""
Tests for Gmail item naming and priority inference helpers.

Covers:
  - _make_monday_item_name: sender name, sender email only, subject only, long subject trim
  - _infer_priority: high from urgent keywords, medium from normal subject, low fallback
"""
from __future__ import annotations

import pytest

from app.main import (
    _infer_priority,
    _make_monday_item_name,
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


