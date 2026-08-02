"""Golden pronoun-register regression tests for PTB-DCQ-0056/0060/0064."""

from __future__ import annotations

import re

import pytest

from app.evaluation.profile_testbot.qualification.hermetic_coworker_reply import _render_scenario_reply
from app.evaluation.profile_testbot.coworker_reply_dataset import generate_coworker_reply_dataset
from app.evaluation.profile_testbot.profile_contract import load_customer_profile
from app.workflows.reply_quality.customer_surface import pronoun_surface_contract
from app.workflows.reply_quality.llm_renderer import build_constrained_llm_prompt, build_constrained_llm_payload
from app.workflows.reply_quality.post_render_validator import validate_post_render_reply
from tests.test_coworker_fallback_regressions import _plan_for

PRONOUN_SCENARIOS = ("PTB-DCQ-0056", "PTB-DCQ-0060", "PTB-DCQ-0064")


def _scenario(scenario_id: str):
    profile = load_customer_profile("niklas-demo-live-eval-v1")
    scenarios = generate_coworker_reply_dataset(profile, seed=0)
    return next(s for s in scenarios if s.scenario_id == scenario_id)


@pytest.mark.parametrize("scenario_id", PRONOUN_SCENARIOS)
class TestPronounRegisterGolden:
    def test_plan_uses_du_register(self, scenario_id: str):
        plan = _plan_for(scenario_id)
        assert plan.salutation_strategy == "du"

    def test_acknowledgement_has_no_ni_forms(self, scenario_id: str):
        plan = _plan_for(scenario_id)
        ack = plan.acknowledgement_statement.lower()
        for forbidden in pronoun_surface_contract(register="du", language="sv")["forbidden"]:
            assert not re.search(rf"\b{forbidden}\b", ack), f"forbidden '{forbidden}' in ack"

    def test_hermetic_body_passes_validator(self, scenario_id: str):
        body, _, _ = _render_scenario_reply(_scenario(scenario_id))
        plan = _plan_for(scenario_id)
        result = validate_post_render_reply(plan=plan, body=body)
        assert result["passed"], result["issues"]

    def test_prompt_lists_allowed_and_forbidden_forms(self, scenario_id: str):
        plan = _plan_for(scenario_id)
        payload = build_constrained_llm_payload(plan)
        prompt = build_constrained_llm_prompt(plan)
        assert payload["pronoun_allowed_forms"]
        assert payload["pronoun_forbidden_forms"]
        assert "dig" in payload["pronoun_allowed_forms"]
        assert "er" in payload["pronoun_forbidden_forms"]
        assert "Allowed forms:" in prompt
        assert "Forbidden forms:" in prompt
