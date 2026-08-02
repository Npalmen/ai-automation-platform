"""Contract tests for constrained coworker LLM reply parsing."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.workflows.reply_quality.llm_reply_parser import LLMReplyParseError, parse_llm_reply_output
from app.workflows.reply_quality.llm_renderer import PROMPT_VERSION, render_constrained_llm_reply
from app.workflows.reply_quality.plan_v2 import CustomerReplyPlanV2
from app.workflows.reply_quality.renderer import render_coworker_reply_with_validation
from app.workflows.reply_quality.thread_context import ThreadReplyContext


def _minimal_plan(**overrides) -> CustomerReplyPlanV2:
    base = dict(
        response_objective="collect_facts",
        acknowledgement_mode="service_specific",
        service_family="solar_installation",
        business_intent="lead",
        verified_facts=(),
        facts_not_allowed_to_repeat=(),
        selected_questions=("roof_type",),
        selected_question_labels=("taktyp",),
        next_step_statement="När vi har underlaget återkommer vi.",
        commitment_constraints=(),
        tone_profile="professional",
        language="sv",
        greeting="Hej,",
        signature_name="Niklas",
        salutation_strategy="ni",
        closing_strategy="formal",
        thread_context=ThreadReplyContext(
            thread_state="new_thread",
            is_first_contact=True,
            is_continuation=False,
            prior_operator_reply=False,
            prior_safe_ack=False,
            supplied_facts=(),
            summary="",
            policy_version="thread_context_v1",
        ),
        rendering_constraints=(),
        fallback_reason=None,
        evidence=(),
        playbook_id="solar_v1",
        policy_version="customer_reply_plan_v3",
        acknowledgement_statement="Tack för er förfrågan om solceller.",
        question_surface_labels=("Vilken taktyp har huset?",),
    )
    base.update(overrides)
    return CustomerReplyPlanV2(**base)


class TestParseLLMReplyOutput:
    def test_dict_result(self):
        parsed = parse_llm_reply_output({"reply_body": "Hej,\n\nTack för ert meddelande."})
        assert parsed.reply_body.startswith("Hej")
        assert parsed.source_key == "reply_body"

    def test_json_string(self):
        raw = json.dumps({"reply_body": "Hello there"})
        parsed = parse_llm_reply_output(raw)
        assert parsed.reply_body == "Hello there"

    def test_empty_response_raises(self):
        with pytest.raises(LLMReplyParseError, match="empty"):
            parse_llm_reply_output("")

    def test_malformed_json_raises(self):
        with pytest.raises(LLMReplyParseError, match="malformed"):
            parse_llm_reply_output("{not-json")

    def test_missing_reply_body_raises(self):
        with pytest.raises(LLMReplyParseError, match="missing_reply_body"):
            parse_llm_reply_output({"other": "value"})


class TestRenderConstrainedLLMReply:
    def test_hermetic_when_live_disabled(self, monkeypatch):
        monkeypatch.delenv("DIGITAL_COWORKER_LLM_RENDER", raising=False)
        plan = _minimal_plan()
        body, meta = render_constrained_llm_reply(plan)
        assert body
        assert meta["provider_outcome"] == "skipped"
        assert meta["live_call"] is False

    def test_provider_exception_falls_back(self, monkeypatch):
        monkeypatch.setenv("DIGITAL_COWORKER_LLM_RENDER", "live")
        plan = _minimal_plan()
        with patch("app.ai.llm.client.get_llm_client") as mock_get:
            mock_get.return_value.generate_json_detailed.side_effect = RuntimeError("provider_down")
            body, meta = render_constrained_llm_reply(plan)
        assert body
        assert meta["provider_outcome"] == "failed"
        assert meta.get("live_call_failed")

    def test_parse_failure_outcome(self, monkeypatch):
        monkeypatch.setenv("DIGITAL_COWORKER_LLM_RENDER", "live")
        plan = _minimal_plan()
        with patch("app.ai.llm.client.get_llm_client") as mock_get:
            mock_get.return_value.generate_json_detailed.return_value = MagicMock(
                output={"wrong_key": "x"},
                returned_model="gpt-4o-mini",
                usage={},
                finish_reason="stop",
            )
            body, meta = render_constrained_llm_reply(plan)
        assert body
        assert meta["provider_outcome"] == "parse_failed"

    def test_successful_live_render(self, monkeypatch):
        monkeypatch.setenv("DIGITAL_COWORKER_LLM_RENDER", "live")
        plan = _minimal_plan()
        good_body = (
            "Hej,\n\nTack för er förfrågan om solceller. "
            "Kan ni berätta vilken taktyp huset har?\n\n"
            "När vi har underlaget återkommer vi.\n\nVänliga hälsningar\nNiklas"
        )
        with patch("app.ai.llm.client.get_llm_client") as mock_get:
            mock_get.return_value.generate_json_detailed.return_value = MagicMock(
                output={"reply_body": good_body},
                returned_model="gpt-4o-mini",
                usage={"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
                finish_reason="stop",
            )
            body, meta = render_constrained_llm_reply(plan)
        assert body == good_body
        assert meta["provider_outcome"] == "success"
        assert meta["live_call"] is True


class TestRendererProvenance:
    def test_validator_rejection_not_reported_as_llm_success(self, monkeypatch):
        monkeypatch.setenv("DIGITAL_COWORKER_LLM_RENDER", "live")
        plan = _minimal_plan(salutation_strategy="du", service_family="existing_installation_support")
        bad_body = (
            "Hej,\n\nTack för att ni hör av er. Kan ni skicka en bild?\n\n"
            "När vi har det går vi vidare.\n\nVänliga hälsningar\nNiklas"
        )
        with patch("app.ai.llm.client.get_llm_client") as mock_get:
            mock_get.return_value.generate_json_detailed.return_value = MagicMock(
                output={"reply_body": bad_body},
                returned_model="gpt-4o-mini",
                usage={},
                finish_reason="stop",
            )
            result = render_coworker_reply_with_validation(plan)
        assert result.provenance.llm_used is False
        assert result.provenance.use_fallback is True
        assert result.validation["llm_meta"]["live_validation_outcome"] == "fail"

    def test_successful_constrained_render(self, monkeypatch):
        monkeypatch.setenv("DIGITAL_COWORKER_LLM_RENDER", "live")
        plan = _minimal_plan()
        good_body = (
            "Hej,\n\nTack för er förfrågan om solceller. "
            "Kan ni berätta vilken taktyp huset har?\n\n"
            "När vi har underlaget återkommer vi.\n\nVänliga hälsningar\nNiklas"
        )
        with patch("app.ai.llm.client.get_llm_client") as mock_get:
            mock_get.return_value.generate_json_detailed.return_value = MagicMock(
                output={"reply_body": good_body},
                returned_model="gpt-4o-mini",
                usage={},
                finish_reason="stop",
            )
            result = render_coworker_reply_with_validation(plan)
        assert result.provenance.llm_used is True
        assert result.provenance.use_fallback is False
        assert result.provenance.prompt_version == PROMPT_VERSION
