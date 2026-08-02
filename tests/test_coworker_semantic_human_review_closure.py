"""Golden regressions for semantic human-review closure (14 FAIL scenarios)."""

from __future__ import annotations

import pytest

from app.evaluation.profile_testbot.coworker_quality_oracles import evaluate_semantic_human_review_oracles
from app.evaluation.profile_testbot.profile_contract import load_customer_profile
from app.evaluation.profile_testbot.qualification.hermetic_coworker_reply import _render_scenario_reply
from app.evaluation.profile_testbot.coworker_reply_dataset import generate_coworker_reply_dataset
from app.workflows.reply_quality.fact_extraction import extract_customer_facts
from app.workflows.reply_quality.plan_v2 import CustomerReplyPlanV2
from app.workflows.reply_quality.post_render_validator import validate_post_render_reply
from app.workflows.reply_quality.semantic_fact_predicates import detect_semantic_fact_ids
from app.workflows.reply_quality.thread_context import ThreadReplyContext

FAIL_SCENARIOS = (
    "PTB-DCQ-0016",
    "PTB-DCQ-0040",
    "PTB-DCQ-0049",
    "PTB-DCQ-0057",
    "PTB-DCQ-0064",
    "PTB-DCQ-0097",
    "PTB-DCQ-0098",
    "PTB-DCQ-0099",
    "PTB-DCQ-0013",
    "PTB-DCQ-0113",
    "PTB-DCQ-0024",
    "PTB-DCQ-0034",
    "PTB-DCQ-0101",
    "PTB-DCQ-0106",
)

CITY_ADDRESS_SCENARIOS = (
    "PTB-DCQ-0001",
    "PTB-DCQ-0007",
    "PTB-DCQ-0032",
    "PTB-DCQ-0048",
    "PTB-DCQ-0015",
    "PTB-DCQ-0112",
    "PTB-DCQ-0024",
    "PTB-DCQ-0051",
)


def _scenario(scenario_id: str):
    profile = load_customer_profile("niklas-demo-live-eval-v1")
    scenarios = generate_coworker_reply_dataset(profile, seed=0)
    return next(s for s in scenarios if s.scenario_id == scenario_id)


def _render(scenario_id: str):
    return _render_scenario_reply(_scenario(scenario_id))


@pytest.mark.parametrize("scenario_id", FAIL_SCENARIOS)
def test_semantic_closure_scenario_renders(scenario_id: str):
    body, plan_dict, _ = _render(scenario_id)
    assert body
    assert plan_dict is not None


def _plan_from_dict(plan_dict: dict) -> CustomerReplyPlanV2:
    thread_raw = plan_dict.get("thread_context") or {}
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
        language_decision_evidence=tuple(plan_dict.get("language_decision_evidence") or []),
        scenario_family=plan_dict.get("scenario_family"),
        attachment_state=plan_dict.get("attachment_state"),
    )


@pytest.mark.parametrize("scenario_id", FAIL_SCENARIOS)
def test_semantic_oracles_pass(scenario_id: str):
    scenario = _scenario(scenario_id)
    body, plan_dict, _ = _render(scenario_id)
    plan_v2 = _plan_from_dict(plan_dict)
    semantic = evaluate_semantic_human_review_oracles(
        scenario=scenario, reply_body=body, plan_v2=plan_v2
    )
    failures = [r for r in semantic if r.blocker and r.status == "fail"]
    assert not failures, f"{scenario_id}: {[f.name for f in failures]}"
    validation = validate_post_render_reply(plan=plan_v2, body=body)
    grammar = [i for i in validation.get("issues", []) if i.startswith("grammatical_question_composition:")]
    assert not grammar, f"{scenario_id}: {grammar}"


class TestSemanticPredicates:
    def test_villa_suppresses_housing_association_context(self):
        text = "Vi vill ha laddbox. Adress Storgatan 2 Uppsala, villa, huvudsäkring 25A."
        ids = detect_semantic_fact_ids(text)
        assert "property_type_villa" in ids
        facts = extract_customer_facts(
            input_data={"subject": "Laddbox", "message_text": text}
        )
        assert "housing_association_context" in facts.known_question_fields

    def test_load_balancing_stated(self):
        text = "Vi behöver offert på laddbox med lastbalansering i Uppsala."
        assert "load_balancing_stated" in detect_semantic_fact_ids(text)

    def test_requested_service_explicit_consultation(self):
        text = "Kan ni ge råd om solceller kontra batteri för vår förbrukning?"
        assert "requested_service_explicit" in detect_semantic_fact_ids(text)

    def test_battery_retrofit_intent(self):
        text = "Hej, vi har solceller och vill komplettera med batterilager i Enköping."
        assert "battery_retrofit" in detect_semantic_fact_ids(text)


class TestScenarioSpecificRegressions:
    def test_0016_asks_existing_installation_not_solar_description(self):
        _, plan_dict, _ = _render("PTB-DCQ-0016")
        selected = plan_dict.get("selected_questions") or []
        assert "existing_installation" in selected
        assert "existing_solar_system" not in selected
        assert "current_inverter" not in selected

    def test_0040_no_housing_association_reask(self):
        _, plan_dict, _ = _render("PTB-DCQ-0040")
        assert "housing_association_context" not in (plan_dict.get("selected_questions") or [])

    def test_0049_battery_retrofit_no_roof_questions(self):
        _, plan_dict, _ = _render("PTB-DCQ-0049")
        selected = set(plan_dict.get("selected_questions") or [])
        assert "roof_type" not in selected
        assert plan_dict.get("service_family") == "battery_installation"

    def test_0064_new_thread_no_followup_ack(self):
        body, plan_dict, _ = _render("PTB-DCQ-0064")
        ack = (plan_dict.get("acknowledgement_statement") or "").lower()
        assert "igen" not in ack
        assert "uppföljning" not in ack

    def test_0013_new_thread_no_quote_followup_ack(self):
        _, plan_dict, _ = _render("PTB-DCQ-0013")
        ack = (plan_dict.get("acknowledgement_statement") or "").lower()
        assert "återkomst" not in ack

    def test_0034_no_load_balancing_reask(self):
        _, plan_dict, _ = _render("PTB-DCQ-0034")
        assert "load_balancing_need" not in (plan_dict.get("selected_questions") or [])

    def test_0097_no_requested_service_reask(self):
        _, plan_dict, _ = _render("PTB-DCQ-0097")
        assert "requested_service" not in (plan_dict.get("selected_questions") or [])

    def test_0113_no_resend_when_kwh_attached(self):
        body, plan_dict, _ = _render("PTB-DCQ-0113")
        lowered = body.lower()
        assert "filen igen" not in lowered
        assert "skicka igen" not in lowered
        assert "attachment" not in (plan_dict.get("selected_questions") or [])

    def test_0106_attach_not_resend(self):
        body, _, _ = _render("PTB-DCQ-0106")
        assert "resend" not in body.lower()


@pytest.mark.parametrize("scenario_id", CITY_ADDRESS_SCENARIOS)
def test_city_not_full_address(scenario_id: str):
    scenario = _scenario(scenario_id)
    facts = extract_customer_facts(
        input_data={
            "subject": scenario.input.subject,
            "message_text": scenario.input.message_text,
        }
    )
    if facts.location_city and "property_address" not in facts.fact_ids:
        assert "address" not in facts.known_question_fields
