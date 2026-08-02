"""Regression tests for the nine live-LLM fallback scenarios."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.evaluation.profile_testbot.coworker_reply_dataset import generate_coworker_reply_dataset
from app.evaluation.profile_testbot.profile_contract import load_customer_profile
from app.evaluation.profile_testbot.qualification.hermetic_coworker_reply import _render_scenario_reply
from app.workflows.reply_quality.llm_renderer import build_constrained_llm_prompt, render_constrained_llm_reply
from app.workflows.reply_quality.post_render_validator import validate_post_render_reply
from app.workflows.reply_quality.renderer import render_coworker_reply_with_validation

FALLBACK_SCENARIO_IDS = (
    "PTB-DCQ-0032",
    "PTB-DCQ-0098",
    "PTB-DCQ-0018",
    "PTB-DCQ-0037",
    "PTB-DCQ-0106",
    "PTB-DCQ-0056",
    "PTB-DCQ-0064",
    "PTB-DCQ-0060",
    "PTB-DCQ-0089",
)


def _scenario(scenario_id: str):
    profile = load_customer_profile("niklas-demo-live-eval-v1")
    scenarios = generate_coworker_reply_dataset(profile, seed=0)
    return next(s for s in scenarios if s.scenario_id == scenario_id)


def _plan_for(scenario_id: str):
    _body, plan_dict, _prov = _render_scenario_reply(_scenario(scenario_id))
    assert plan_dict is not None
    from app.workflows.reply_quality.thread_context import ThreadReplyContext

    thread_raw = plan_dict.get("thread_context") or {}
    from app.workflows.reply_quality.plan_v2 import CustomerReplyPlanV2

    return CustomerReplyPlanV2(
        response_objective=plan_dict["response_objective"],
        acknowledgement_mode=plan_dict["acknowledgement_mode"],
        service_family=plan_dict["service_family"],
        business_intent=plan_dict["business_intent"],
        verified_facts=tuple(plan_dict.get("verified_facts") or []),
        facts_not_allowed_to_repeat=tuple(plan_dict.get("facts_not_allowed_to_repeat") or []),
        selected_questions=tuple(plan_dict.get("selected_questions") or []),
        selected_question_labels=tuple(plan_dict.get("selected_question_labels") or []),
        next_step_statement=plan_dict["next_step_statement"],
        commitment_constraints=tuple(plan_dict.get("commitment_constraints") or []),
        tone_profile=plan_dict["tone_profile"],
        language=plan_dict["language"],
        greeting=plan_dict["greeting"],
        signature_name=plan_dict["signature_name"],
        salutation_strategy=plan_dict["salutation_strategy"],
        closing_strategy=plan_dict["closing_strategy"],
        thread_context=ThreadReplyContext(
            thread_state=thread_raw.get("thread_state", "new_thread"),
            is_first_contact=bool(thread_raw.get("is_first_contact", True)),
            is_continuation=bool(thread_raw.get("is_continuation", False)),
            prior_operator_reply=bool(thread_raw.get("prior_operator_reply", False)),
            prior_safe_ack=bool(thread_raw.get("prior_safe_ack", False)),
            supplied_facts=tuple(thread_raw.get("supplied_facts") or ()),
            summary=thread_raw.get("summary", ""),
            policy_version=thread_raw.get("policy_version", "thread_context_v1"),
        ),
        rendering_constraints=tuple(plan_dict.get("rendering_constraints") or ()),
        fallback_reason=plan_dict.get("fallback_reason"),
        evidence=tuple(plan_dict.get("evidence") or ()),
        playbook_id=plan_dict["playbook_id"],
        policy_version=plan_dict["policy_version"],
        acknowledgement_statement=str(plan_dict.get("acknowledgement_statement") or ""),
        question_surface_labels=tuple(plan_dict.get("question_surface_labels") or []),
        location_phrase=plan_dict.get("location_phrase"),
        case_reference_phrase=plan_dict.get("case_reference_phrase"),
    )


class TestFallbackPromptContract:
    @pytest.mark.parametrize("scenario_id", FALLBACK_SCENARIO_IDS)
    def test_prompt_forbids_key_value_and_states_register(self, scenario_id: str):
        plan = _plan_for(scenario_id)
        prompt = build_constrained_llm_prompt(plan)
        assert "key:value" in prompt.lower() or "key:value lines" in prompt
        assert plan.salutation_strategy in prompt or "pronoun" in prompt.lower()
        assert "approved_questions" in prompt


class TestHermeticBaselinePassesValidator:
    @pytest.mark.parametrize("scenario_id", FALLBACK_SCENARIO_IDS)
    def test_hermetic_output_passes_post_render(self, scenario_id: str):
        body, plan_dict, _ = _render_scenario_reply(_scenario(scenario_id))
        assert body
        plan = _plan_for(scenario_id)
        validation = validate_post_render_reply(plan=plan, body=body)
        assert validation["passed"], validation["issues"]


class TestMockedLiveOutputsPassValidator:
    """Simulated LLM outputs that follow the improved prompt contract."""

    def test_support_du_register_no_ni(self, monkeypatch):
        monkeypatch.setenv("DIGITAL_COWORKER_LLM_RENDER", "live")
        plan = _plan_for("PTB-DCQ-0056")
        body = (
            "Hej,\n\nTack för att du hör av dig om felet på den befintliga solcellsanläggningen. "
            "Kan du beskriva eventuell felkod på display eller app, om något känns osäkert "
            "el- eller brandsäkerhetsmässigt, samt bilder eller ritningar om du har?\n\n"
            "När vi har det går vi igenom uppgifterna och ser hur ärendet bör hanteras.\n\n"
            "Vänliga hälsningar\nNiklas"
        )
        with patch("app.ai.llm.client.get_llm_client") as mock_get:
            mock_get.return_value.generate_json_detailed.return_value = MagicMock(
                output={"reply_body": body},
                returned_model="gpt-4o-mini",
                usage={},
                finish_reason="stop",
            )
            result = render_coworker_reply_with_validation(plan)
        assert result.provenance.llm_used is True
        assert result.provenance.use_fallback is False

    def test_complaint_warranty_semantic_questions(self, monkeypatch):
        monkeypatch.setenv("DIGITAL_COWORKER_LLM_RENDER", "live")
        plan = _plan_for("PTB-DCQ-0089")
        body = (
            "Hej,\n\nTack för att du hör av dig om reklamationen. "
            "Kan du skicka orderreferens eller ursprungligt ärende, när problemet upptäcktes, "
            "bilder eller dokument som stödjer ärendet, samt om felet kan påverka säkerheten?\n\n"
            "När vi har underlaget går vi igenom ärendet.\n\nVänliga hälsningar\nNiklas"
        )
        with patch("app.ai.llm.client.get_llm_client") as mock_get:
            mock_get.return_value.generate_json_detailed.return_value = MagicMock(
                output={"reply_body": body},
                returned_model="gpt-4o-mini",
                usage={},
                finish_reason="stop",
            )
            result = render_coworker_reply_with_validation(plan)
        assert result.provenance.llm_used is True
        assert result.provenance.use_fallback is False

    def test_no_key_value_fragment_in_ev_charger_en(self, monkeypatch):
        monkeypatch.setenv("DIGITAL_COWORKER_LLM_RENDER", "live")
        plan = _plan_for("PTB-DCQ-0032")
        body = (
            "Hi,\n\nThank you for your enquiry about an EV charger in Uppsala. "
            "Could you please tell us the type of property, how many charging points you need "
            "and where they should be placed, and your main fuse rating or available capacity?\n\n"
            "Once we have that information we will review the details and get back to you.\n\n"
            "Kind regards\nNiklas"
        )
        with patch("app.ai.llm.client.get_llm_client") as mock_get:
            mock_get.return_value.generate_json_detailed.return_value = MagicMock(
                output={"reply_body": body},
                returned_model="gpt-4o-mini",
                usage={},
                finish_reason="stop",
            )
            result = render_coworker_reply_with_validation(plan)
        assert result.provenance.llm_used is True
        assert result.provenance.use_fallback is False
