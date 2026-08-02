"""Tests for plan-driven next-step surface contracts."""

from __future__ import annotations

from app.evaluation.profile_testbot.qualification.hermetic_coworker_reply import _render_scenario_reply
from app.evaluation.profile_testbot.coworker_reply_dataset import generate_coworker_reply_dataset
from app.evaluation.profile_testbot.profile_contract import load_customer_profile
from app.evaluation.profile_testbot.qualification.coworker_package_precheck import (
    cross_family_exact_duplicate_pairs,
    dominant_next_step_phrase_rate,
)
from app.workflows.reply_quality.next_step_surface import build_next_step_surface
from scripts.build_digital_coworker_human_review_package import SELECTION

_GENERIC = "när vi har det underlaget går vi igenom förutsättningarna och återkommer"


def _scenario(scenario_id: str):
    profile = load_customer_profile("niklas-demo-live-eval-v1")
    scenarios = generate_coworker_reply_dataset(profile, seed=0)
    return next(s for s in scenarios if s.scenario_id == scenario_id)


class TestNextStepSurfaceContracts:
    def test_solar_new_thread_specific_next_step(self):
        surface = build_next_step_surface(
            step_id="collect_minimum_site_facts",
            service_family="solar_installation",
            business_intent="lead",
            thread_state="new_thread",
            is_continuation=False,
            has_questions=True,
            language="sv",
            scenario_family="solar_installation_new",
        )
        assert "takets förutsättningar" in surface.statement
        assert _GENERIC not in surface.statement.lower()

    def test_battery_specific_next_step(self):
        surface = build_next_step_surface(
            step_id="collect_minimum_site_facts",
            service_family="battery_installation",
            business_intent="lead",
            thread_state="new_thread",
            is_continuation=False,
            has_questions=True,
            language="sv",
        )
        assert "kompatibilitet" in surface.statement

    def test_ev_charger_specific_next_step(self):
        surface = build_next_step_surface(
            step_id="collect_minimum_site_facts",
            service_family="ev_charger",
            business_intent="lead",
            thread_state="new_thread",
            is_continuation=False,
            has_questions=True,
            language="sv",
        )
        assert "elkapacitet" in surface.statement

    def test_support_followup_differs_from_symptom(self):
        symptom = build_next_step_surface(
            step_id="collect_symptom_facts",
            service_family="existing_installation_support",
            business_intent="support_status",
            thread_state="new_thread",
            is_continuation=False,
            has_questions=True,
            language="sv",
            scenario_family="existing_support_symptom",
        )
        followup = build_next_step_surface(
            step_id="collect_symptom_facts",
            service_family="existing_installation_support",
            business_intent="support_status",
            thread_state="new_thread",
            is_continuation=False,
            has_questions=True,
            language="sv",
            scenario_family="existing_support_followup",
        )
        assert symptom.statement != followup.statement

    def test_job_status_no_contact_differs(self):
        standard = build_next_step_surface(
            step_id="provide_status_acknowledgement",
            service_family="job_status",
            business_intent="support_status",
            thread_state="continuation",
            is_continuation=True,
            has_questions=False,
            language="sv",
            scenario_family="job_status_request",
        )
        no_contact = build_next_step_surface(
            step_id="provide_status_acknowledgement",
            service_family="job_status",
            business_intent="support_status",
            thread_state="continuation",
            is_continuation=True,
            has_questions=False,
            language="sv",
            scenario_family="job_status_no_contact",
        )
        assert standard.statement != no_contact.statement


class TestCrossFamilyDuplicateRegression:
    """Four cross-family duplicate pairs from package 914b329 must not recur."""

    DUPLICATE_PAIRS = (
        ("PTB-DCQ-0007", "PTB-DCQ-0015"),
        ("PTB-DCQ-0056", "PTB-DCQ-0064"),
        ("PTB-DCQ-0057", "PTB-DCQ-0065"),
        ("PTB-DCQ-0005", "PTB-DCQ-0013"),
    )

    def test_pairs_no_longer_byte_identical(self):
        for a_id, b_id in self.DUPLICATE_PAIRS:
            body_a, _, _ = _render_scenario_reply(_scenario(a_id))
            body_b, _, _ = _render_scenario_reply(_scenario(b_id))
            assert body_a != body_b, f"{a_id} and {b_id} must differ"

    def test_forty_pack_zero_cross_family_duplicates(self):
        profile = load_customer_profile("niklas-demo-live-eval-v1")
        scenarios = {s.scenario_id: s for s in generate_coworker_reply_dataset(profile, seed=0)}
        ordered = [entry[0] for entry in SELECTION]
        bodies = []
        families = []
        for sid in ordered:
            body, _, _ = _render_scenario_reply(scenarios[sid])
            bodies.append(body)
            families.append(scenarios[sid].family)
        pairs = cross_family_exact_duplicate_pairs(bodies, families=families)
        assert pairs == []
        assert dominant_next_step_phrase_rate(bodies) <= 0.45
