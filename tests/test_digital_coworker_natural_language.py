"""Golden and regression tests for natural-language coworker replies."""

from __future__ import annotations

import os
import re

import pytest

from app.evaluation.profile_testbot.coworker_reply_dataset import generate_coworker_reply_dataset
from app.evaluation.profile_testbot.profile_contract import load_customer_profile
from app.evaluation.profile_testbot.qualification.hermetic_coworker_reply import _render_scenario_reply
from app.workflows.reply_quality.reply_language import decide_reply_language
from app.workflows.reply_quality.surface_contract import (
    detect_internal_metadata_leaks,
    detect_mixed_language,
    validate_customer_surface,
)


def _scenario(scenario_id: str):
    profile = load_customer_profile("niklas-demo-live-eval-v1")
    scenarios = generate_coworker_reply_dataset(profile, seed=0)
    return next(s for s in scenarios if s.scenario_id == scenario_id)


def _render(scenario_id: str) -> str:
    prev = os.environ.get("DIGITAL_COWORKER_REPLY_ENABLED")
    os.environ["DIGITAL_COWORKER_REPLY_ENABLED"] = "true"
    try:
        body, _, _ = _render_scenario_reply(_scenario(scenario_id))
    finally:
        if prev is None:
            os.environ.pop("DIGITAL_COWORKER_REPLY_ENABLED", None)
        else:
            os.environ["DIGITAL_COWORKER_REPLY_ENABLED"] = prev
    return body


def _assert_no_internal_metadata(body: str) -> None:
    assert detect_internal_metadata_leaks(body) == []


def _assert_single_language(body: str, language: str) -> None:
    assert detect_mixed_language(body, expected_language=language) == []


class TestReplyLanguageDecision:
    def test_swedish_email(self):
        decision = decide_reply_language(
            input_data={"message_text": "Hej, vi vill ha solceller i Uppsala.", "subject": "Offert"},
            profile_default_language="sv",
        )
        assert decision.language == "sv"

    def test_english_email(self):
        decision = decide_reply_language(
            input_data={
                "message_text": "Hi, we need a solar quote for our house in Uppsala.",
                "subject": "Solar quote",
            },
            profile_default_language="sv",
        )
        assert decision.language == "en"

    def test_english_with_swedish_place_name(self):
        decision = decide_reply_language(
            input_data={"message_text": "Hi from Uppsala, we need solar panels.", "subject": "Quote"},
            profile_default_language="sv",
        )
        assert decision.language == "en"


class TestGoldenReplies:
    def test_ptb_dcq_0000_solar_uppsala(self):
        body = _render("PTB-DCQ-0000")
        _assert_no_internal_metadata(body)
        _assert_single_language(body, "sv")
        assert "solcell" in body.lower()
        assert "uppsala" in body.lower()
        assert "service:" not in body.lower()
        assert "adressen till fastigheten" in body.lower() or "adress" in body.lower()

    def test_ptb_dcq_0007_follow_up_without_completion_claim(self):
        body = _render("PTB-DCQ-0007")
        _assert_no_internal_metadata(body)
        assert "kompletteringen" not in body.lower()
        assert "uppföljning" in body.lower() or "följer upp" in body.lower()

    def test_ptb_dcq_0072_status_case_reference(self):
        body = _render("PTB-DCQ-0072")
        _assert_no_internal_metadata(body)
        assert "1000" in body
        assert not re.search(r"ärendenummer", body, re.I)

    def test_ptb_dcq_0088_complaint_natural_language(self):
        body = _render("PTB-DCQ-0088")
        _assert_no_internal_metadata(body)
        assert "0 veckor sedan" not in body.lower()
        assert "reklamation" in body.lower()

    def test_ptb_dcq_0002_fully_english(self):
        body = _render("PTB-DCQ-0002")
        _assert_no_internal_metadata(body)
        _assert_single_language(body, "en")
        assert body.lower().startswith("hi,")
        assert "kind regards" in body.lower()
        assert "hej," not in body.lower()
        assert "vänliga hälsningar" not in body.lower()
        assert "för att vi ska" not in body.lower()

    def test_ptb_dcq_0032_english_charger(self):
        body = _render("PTB-DCQ-0032")
        _assert_no_internal_metadata(body)
        _assert_single_language(body, "en")
        assert body.lower().startswith("hi,")
        assert "charger" in body.lower() or "ev" in body.lower()

    def test_ptb_dcq_0048_solar_battery_uppsala(self):
        body = _render("PTB-DCQ-0048")
        _assert_no_internal_metadata(body)
        _assert_single_language(body, "sv")
        assert "sol" in body.lower()
        assert "batteri" in body.lower()
        assert "uppsala" in body.lower()
        assert "city" not in body.lower()

    def test_ptb_dcq_0024_english_battery(self):
        body = _render("PTB-DCQ-0024")
        _assert_no_internal_metadata(body)
        _assert_single_language(body, "en")
        assert body.lower().startswith("hi,")
        assert "battery" in body.lower()

    def test_ptb_dcq_0080_status_no_internal_labels(self):
        body = _render("PTB-DCQ-0080")
        _assert_no_internal_metadata(body)
        _assert_single_language(body, "sv")
        assert "case reference" not in body.lower()
        assert "customer identifier" not in body.lower()
        assert "status" in body.lower() or "ärende" in body.lower()


class TestSurfaceContract:
    def test_blocks_service_metadata(self):
        result = validate_customer_surface(
            "Hej,\n\nservice:solcellsinstallation\n\nVänliga hälsningar\nNiklas",
            expected_language="sv",
        )
        assert result["passed"] is False

    def test_allows_uppsala_in_english_reply(self):
        body = (
            "Hi,\n\nThank you for getting in touch about solar panels in Uppsala.\n\n"
            "Kind regards\nNiklas"
        )
        assert validate_customer_surface(body, expected_language="en")["passed"] is True
