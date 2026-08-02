"""R2 human-review closure v3: four blocking scenarios and oracle false-negatives."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.evaluation.profile_testbot.coworker_quality_oracles import (
    evaluate_semantic_human_review_oracles,
)
from app.evaluation.profile_testbot.profile_contract import load_customer_profile
from app.evaluation.profile_testbot.qualification.hermetic_coworker_reply import _render_scenario_reply
from app.evaluation.profile_testbot.coworker_reply_dataset import generate_coworker_reply_dataset
from app.workflows.reply_quality.customer_surface import contextual_question_surface
from app.workflows.reply_quality.pipeline_routing import resolve_reply_pipeline_context
from app.workflows.reply_quality.post_render_validator import _GRAMMATICAL_BAD_SV, validate_post_render_reply
from app.workflows.reply_quality.plan_v2 import CustomerReplyPlanV2
from app.workflows.reply_quality.thread_context import ThreadReplyContext
from tests.test_coworker_semantic_human_review_closure import _plan_from_dict

BLOCKER_SCENARIOS = (
    "PTB-DCQ-0040",
    "PTB-DCQ-0048",
    "PTB-DCQ-0099",
    "PTB-DCQ-0101",
)

ADVISORY_SCENARIOS = (
    "PTB-DCQ-0004",
    "PTB-DCQ-0007",
    "PTB-DCQ-0016",
    "PTB-DCQ-0024",
    "PTB-DCQ-0033",
    "PTB-DCQ-0051",
    "PTB-DCQ-0057",
    "PTB-DCQ-0113",
)

D76168C_METRICS = Path("storage/status/digital-coworker-human-review-metrics-d76168c.json")


def _scenario(scenario_id: str):
    profile = load_customer_profile("niklas-demo-live-eval-v1")
    scenarios = generate_coworker_reply_dataset(profile, seed=0)
    return next(s for s in scenarios if s.scenario_id == scenario_id)


def _render(scenario_id: str):
    return _render_scenario_reply(_scenario(scenario_id))


def _minimal_plan(overrides: dict) -> CustomerReplyPlanV2:
    base = {
        "response_objective": "collect_minimum_site_facts",
        "acknowledgement_mode": "information_request",
        "service_family": "general_consultation",
        "business_intent": "lead",
        "next_step_statement": "Vi går igenom underlaget och återkommer.",
        "tone_profile": "professional_concise",
        "language": "sv",
        "greeting": "Hej,",
        "signature_name": "Niklas",
        "salutation_strategy": "ni",
        "closing_strategy": "profile_signature",
        "playbook_id": "reply_general_consultation_v1",
        "policy_version": "customer_reply_plan_v3",
    }
    base.update(overrides)
    return _plan_from_dict(base)


@pytest.mark.parametrize("scenario_id", BLOCKER_SCENARIOS)
def test_blocker_scenario_semantic_oracles_pass(scenario_id: str):
    scenario = _scenario(scenario_id)
    body, plan_dict, _ = _render(scenario_id)
    plan_v2 = _plan_from_dict(plan_dict)
    results = evaluate_semantic_human_review_oracles(
        scenario=scenario, reply_body=body, plan_v2=plan_v2
    )
    failures = [r for r in results if r.blocker and r.status == "fail"]
    assert not failures, f"{scenario_id}: {[f.name for f in failures]}"


@pytest.mark.parametrize("scenario_id", ADVISORY_SCENARIOS)
def test_advisory_scenario_renders(scenario_id: str):
    body, plan_dict, _ = _render(scenario_id)
    assert body
    assert plan_dict is not None


def test_0040_load_balancing_surface_is_full_question():
    label = contextual_question_surface("load_balancing_need", language="sv")
    assert label.endswith("?")
    assert "om lastbalansering behövs" not in label.lower()


def test_0040_d76168c_fragment_blocked():
    bad = "Dessutom, om lastbalansering behövs till laddboxen?"
    assert _GRAMMATICAL_BAD_SV.search(bad)


def test_0048_combined_new_install_routing():
    scenario = _scenario("PTB-DCQ-0048")
    setup = scenario.customer_state_setup or {}
    ctx = resolve_reply_pipeline_context(
        base_service_type=str(setup.get("service_type") or "solar_installation"),
        business_intent=str(setup.get("business_intent") or "lead"),
        input_data={
            "subject": scenario.input.subject,
            "message_text": scenario.input.message_text,
        },
    )
    assert ctx.playbook.service_family == "solar_battery_combined"
    assert ctx.playbook.playbook_id == "reply_solar_battery_combined_v1"
    _, plan_dict, _ = _render("PTB-DCQ-0048")
    assert "existing_installation" not in (plan_dict.get("selected_questions") or [])


def test_0049_retrofit_still_battery():
    scenario = _scenario("PTB-DCQ-0049")
    setup = scenario.customer_state_setup or {}
    ctx = resolve_reply_pipeline_context(
        base_service_type=str(setup.get("service_type") or "solar_installation"),
        business_intent=str(setup.get("business_intent") or "lead"),
        input_data={
            "subject": scenario.input.subject,
            "message_text": scenario.input.message_text,
        },
    )
    assert ctx.playbook.service_family == "battery_installation"
    assert ctx.playbook.playbook_id == "reply_battery_installation_v1"


def test_0099_no_battery_domain_questions():
    _, plan_dict, _ = _render("PTB-DCQ-0099")
    selected = plan_dict.get("selected_questions") or []
    assert "intended_purpose" not in selected
    labels = " ".join(plan_dict.get("question_surface_labels") or []).lower()
    assert "batteriet" not in labels


def test_0101_booking_operationalized():
    _, plan_dict, _ = _render("PTB-DCQ-0101")
    selected = set(plan_dict.get("selected_questions") or [])
    assert selected.intersection({"preferred_call_times", "consultation_focus", "preferred_contact_method"})


def test_0016_conditional_battery_next_step():
    _, plan_dict, _ = _render("PTB-DCQ-0016")
    next_step = (plan_dict.get("next_step_statement") or "").lower()
    assert "om det finns ett befintligt system" in next_step or "any existing system" in next_step


def test_0024_conditional_battery_next_step_en():
    _, plan_dict, _ = _render("PTB-DCQ-0024")
    next_step = (plan_dict.get("next_step_statement") or "").lower()
    assert "any existing system" in next_step or "befintligt system" in next_step


@pytest.mark.skipif(not D76168C_METRICS.exists(), reason="d76168c metrics snapshot missing")
def test_d76168c_bad_plans_trigger_new_oracles():
    """Regression: d76168c false negatives must fail with v3 oracles."""
    fixtures = {
        "PTB-DCQ-0040": {
            "body": (
                "Hej,\n\nTack för er förfrågan om laddbox. För att vi ska kunna gå vidare, "
                "skulle ni kunna specificera antal laddpunkter och önskad placering? "
                "Dessutom, om lastbalansering behövs till laddboxen?\n\n"
                "När vi har underlaget går vi igenom installationsförutsättningar, "
                "elkapacitet och placering.\n\nMed vänliga hälsningar,\nNiklas"
            ),
            "plan": {
                "selected_questions": ["charging_points", "load_balancing_need"],
                "question_surface_labels": [
                    "antal laddpunkter och önskad placering",
                    "om lastbalansering behövs till laddboxen",
                ],
                "playbook_id": "reply_ev_charger_v1",
                "service_family": "ev_charger",
                "facts_not_allowed_to_repeat": [],
                "evidence": [],
            },
            "required_failures": {"malformed_natural_question"},
        },
        "PTB-DCQ-0048": {
            "body": "Hej, tack för er förfrågan om sol och batteri.",
            "plan": {
                "selected_questions": [
                    "address",
                    "roof_type",
                    "annual_consumption",
                    "existing_installation",
                ],
                "question_surface_labels": [],
                "playbook_id": "reply_solar_installation_v1",
                "service_family": "solar_installation",
                "facts_not_allowed_to_repeat": [],
                "evidence": [],
            },
            "required_failures": {"combined_new_install_question_alignment"},
        },
        "PTB-DCQ-0099": {
            "body": "Hej, tack för er fråga om laddbox eller solceller.",
            "plan": {
                "selected_questions": [
                    "annual_consumption",
                    "intended_purpose",
                    "charging_points",
                ],
                "question_surface_labels": [
                    "er ungefärliga årsförbrukning (kWh)",
                    "huvudsakligt syfte med batteriet",
                    "antal laddpunkter och önskad placering",
                ],
                "playbook_id": "reply_general_consultation_v1",
                "service_family": "general_consultation",
                "facts_not_allowed_to_repeat": [],
                "evidence": [],
            },
            "required_failures": {"consultation_question_domain_alignment"},
        },
        "PTB-DCQ-0101": {
            "body": "Hi, we'd be happy to arrange a call about solar, battery and charging.",
            "plan": {
                "selected_questions": [],
                "question_surface_labels": [],
                "playbook_id": "reply_general_consultation_v1",
                "service_family": "general_consultation",
                "facts_not_allowed_to_repeat": ["phone_or_email"],
                "evidence": [],
            },
            "required_failures": {"booking_request_operationalized"},
        },
    }
    for sid, fixture in fixtures.items():
        scenario = _scenario(sid)
        plan_v2 = _minimal_plan(fixture["plan"])
        semantic = evaluate_semantic_human_review_oracles(
            scenario=scenario,
            reply_body=fixture["body"],
            plan_v2=plan_v2,
        )
        blocking = {r.name for r in semantic if r.blocker and r.status == "fail"}
        assert fixture["required_failures"].issubset(blocking), f"{sid}: {blocking}"

        if "grammatical_question_composition" in fixture.get("required_failures", set()):
            validation = validate_post_render_reply(plan=plan_v2, body=fixture["body"])
            grammar_issues = [
                i for i in validation.get("issues", []) if i.startswith("grammatical_question_composition:")
            ]
            assert grammar_issues, f"{sid}: expected grammar issues"
