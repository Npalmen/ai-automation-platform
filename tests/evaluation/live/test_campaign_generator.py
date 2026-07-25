"""Tests for campaign synthetic email generator."""

from __future__ import annotations

import pytest

from app.evaluation.live.campaign.generator import (
    build_campaign_message_body,
    build_campaign_send_payload,
    build_campaign_subject,
)
from app.evaluation.live.campaign.registry import clear_campaign_registry_cache, get_campaign_scenario
from app.evaluation.live.subject_parser import parse_body_marker, parse_subject_token


@pytest.fixture(autouse=True)
def _clear_registry_cache():
    clear_campaign_registry_cache()
    yield
    clear_campaign_registry_cache()


def test_build_campaign_subject_contains_token():
    scenario = get_campaign_scenario("TBS01_lead_observe")
    run_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    subject = build_campaign_subject(scenario=scenario, evaluation_run_id=run_id, attempt_id=1)
    parsed = parse_subject_token(subject)
    assert parsed is not None
    assert parsed.evaluation_run_id == run_id
    assert parsed.scenario_id == "TBS01_lead_observe"
    assert parsed.attempt_id == 1


def test_build_campaign_body_contains_markers():
    scenario = get_campaign_scenario("TBS02_support_observe")
    run_id = "12345678-1234-1234-1234-123456789abc"
    body = build_campaign_message_body(scenario=scenario, evaluation_run_id=run_id)
    assert parse_body_marker(body) == run_id
    assert "KROWOLF_CUSTOMER:family-support-001" in body
    assert "KROWOLF_THREAD:thread-support-001" in body
    assert "laddar inte" in body.lower() or "teknikern" in body.lower()


def test_build_campaign_send_payload_complete():
    scenario = get_campaign_scenario("TBS03_invoice_observe")
    payload = build_campaign_send_payload(
        scenario=scenario,
        evaluation_run_id="run-invoice-test-0001",
    )
    assert "subject" in payload
    assert "body" in payload
    assert payload["sender_email"] == "testbot-maria@eval.test"
