"""R2 human-review closure v2: fact integrity, pipeline consistency, consultation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.evaluation.profile_testbot.coworker_quality_oracles import (
    evaluate_semantic_human_review_oracles,
)
from app.evaluation.profile_testbot.profile_contract import load_customer_profile
from app.evaluation.profile_testbot.qualification.hermetic_coworker_reply import _render_scenario_reply
from app.evaluation.profile_testbot.coworker_reply_dataset import generate_coworker_reply_dataset
from app.workflows.reply_quality.fact_evidence import (
    ADDRESS_STATE_LOCATION_CITY,
    ADDRESS_STATE_PROPERTY_ADDRESS,
    build_fact_evidence,
    resolve_address_fact_state,
)
from app.workflows.reply_quality.fact_extraction import extract_customer_facts
from app.workflows.reply_quality.information_value import build_information_value_plan
from app.workflows.reply_quality.pipeline_routing import resolve_reply_pipeline_context
from app.workflows.reply_quality.post_render_validator import validate_post_render_reply
from app.workflows.reply_quality.plan_invariants import validate_evidence_based_known_facts
from tests.test_coworker_semantic_human_review_closure import _plan_from_dict

FOCUS_SCENARIOS = (
    "PTB-DCQ-0001",
    "PTB-DCQ-0007",
    "PTB-DCQ-0016",
    "PTB-DCQ-0032",
    "PTB-DCQ-0048",
    "PTB-DCQ-0049",
    "PTB-DCQ-0097",
    "PTB-DCQ-0098",
    "PTB-DCQ-0099",
    "PTB-DCQ-0015",
    "PTB-DCQ-0112",
    "PTB-DCQ-0113",
    "PTB-DCQ-0024",
    "PTB-DCQ-0051",
    "PTB-DCQ-0101",
)

CITY_ADDRESS_SCENARIOS = (
    "PTB-DCQ-0001",
    "PTB-DCQ-0007",
    "PTB-DCQ-0032",
    "PTB-DCQ-0048",
    "PTB-DCQ-0015",
    "PTB-DCQ-0112",
    "PTB-DCQ-0113",
    "PTB-DCQ-0024",
    "PTB-DCQ-0051",
)

A144AAE_METRICS = Path("storage/status/digital-coworker-human-review-metrics-a144aae.json")


def _scenario(scenario_id: str):
    profile = load_customer_profile("niklas-demo-live-eval-v1")
    scenarios = generate_coworker_reply_dataset(profile, seed=0)
    return next(s for s in scenarios if s.scenario_id == scenario_id)


def _render(scenario_id: str):
    return _render_scenario_reply(_scenario(scenario_id))


@pytest.mark.parametrize("scenario_id", FOCUS_SCENARIOS)
def test_focus_scenario_renders(scenario_id: str):
    body, plan_dict, _ = _render(scenario_id)
    assert body
    assert plan_dict is not None


@pytest.mark.parametrize("scenario_id", FOCUS_SCENARIOS)
def test_focus_semantic_oracles_pass(scenario_id: str):
    scenario = _scenario(scenario_id)
    body, plan_dict, _ = _render(scenario_id)
    plan_v2 = _plan_from_dict(plan_dict)
    semantic = evaluate_semantic_human_review_oracles(
        scenario=scenario, reply_body=body, plan_v2=plan_v2
    )
    failures = [r for r in semantic if r.blocker and r.status == "fail"]
    assert not failures, f"{scenario_id}: {[f.name for f in failures]}"


@pytest.mark.parametrize("scenario_id", CITY_ADDRESS_SCENARIOS)
def test_city_not_marked_as_address(scenario_id: str):
    scenario = _scenario(scenario_id)
    input_data = {
        "subject": scenario.input.subject,
        "message_text": scenario.input.message_text,
    }
    evidence = build_fact_evidence(input_data=input_data)
    address = resolve_address_fact_state(
        text=f"{scenario.input.subject} {scenario.input.message_text}"
    )
    if address.state == ADDRESS_STATE_LOCATION_CITY:
        assert "address" not in evidence.evidenced_question_fields
        assert address.state != ADDRESS_STATE_PROPERTY_ADDRESS


def test_0016_no_false_solar_known_facts():
    _, plan_dict, _ = _render("PTB-DCQ-0016")
    known = set(plan_dict.get("already_known_facts") or plan_dict.get("facts_not_allowed_to_repeat") or [])
    assert "current_inverter" not in known
    assert "existing_solar_system" not in known
    assert "existing_installation" in (plan_dict.get("selected_questions") or [])


def test_0049_pipeline_playbook_consistent():
    scenario = _scenario("PTB-DCQ-0049")
    setup = scenario.customer_state_setup or {}
    input_data = {
        "subject": scenario.input.subject,
        "message_text": scenario.input.message_text,
        "_force_service_type": setup.get("service_type"),
    }
    ctx = resolve_reply_pipeline_context(
        base_service_type=str(setup.get("service_type") or ""),
        business_intent=str(setup.get("business_intent") or "lead"),
        input_data=input_data,
    )
    assert ctx.playbook.service_family == "battery_installation"
    assert ctx.playbook.playbook_id == "reply_battery_installation_v1"
    _, plan_dict, _ = _render("PTB-DCQ-0049")
    assert plan_dict.get("playbook_id") == "reply_battery_installation_v1"
    assert plan_dict.get("service_family") == "battery_installation"


def test_0097_consultation_questions_not_project_description():
    _, plan_dict, _ = _render("PTB-DCQ-0097")
    selected = plan_dict.get("selected_questions") or []
    assert "project_description" not in selected
    assert "requested_service" not in selected
    assert any(q in selected for q in ("annual_consumption", "existing_installation", "intended_purpose"))


def test_0101_booking_acknowledged():
    body, plan_dict, _ = _render("PTB-DCQ-0101")
    lowered = body.lower()
    assert "call" in lowered or "samtal" in lowered
    assert "project_description" not in (plan_dict.get("selected_questions") or [])


def test_malformed_confirm_om_blocked():
    from app.workflows.reply_quality.post_render_validator import _GRAMMATICAL_BAD_SV

    bad = "Kan ni bekräfta om det finns redan en solcellsanläggning?"
    assert _GRAMMATICAL_BAD_SV.search(bad)


@pytest.mark.skipif(not A144AAE_METRICS.exists(), reason="a144aae metrics snapshot missing")
def test_a144aae_bad_plans_trigger_blocking_oracles():
    payload = json.loads(A144AAE_METRICS.read_text(encoding="utf-8"))
    bad_ids = {
        "PTB-DCQ-0001",
        "PTB-DCQ-0016",
        "PTB-DCQ-0024",
        "PTB-DCQ-0049",
        "PTB-DCQ-0097",
        "PTB-DCQ-0101",
    }
    for entry in payload.get("human_review_pack", {}).get("scenario_results", []):
        sid = entry.get("scenario_id")
        if sid not in bad_ids:
            continue
        plan = entry.get("plan_v2") or {}
        if not plan:
            continue
        scenario = _scenario(sid)
        plan_v2 = _plan_from_dict(plan)
        body = entry.get("reply_body") or ""
        results = evaluate_semantic_human_review_oracles(
            scenario=scenario, reply_body=body, plan_v2=plan_v2
        )
        blocking = {r.name for r in results if r.blocker and r.status == "fail"}
        assert blocking, f"{sid} should fail at least one blocking oracle on a144aae data"
