"""Regression tests for digital-coworker human-quality v4 closure."""

from __future__ import annotations

from app.evaluation.profile_testbot.coworker_reply_dataset import (
    COWORKER_REPLY_DATASET_VERSION,
    build_coworker_dataset_manifest,
    generate_coworker_reply_dataset,
)
from app.evaluation.profile_testbot.coworker_quality_oracles import (
    evaluate_coworker_reply_oracles,
    evaluate_input_realism_oracles,
)
from app.evaluation.profile_testbot.profile_contract import load_customer_profile
from app.evaluation.profile_testbot.qualification.hermetic_coworker_reply import _render_scenario_reply
from app.workflows.reply_quality.fact_extraction import extract_customer_facts
from app.workflows.reply_quality.plan_invariants import validate_selected_known_invariant
from app.workflows.reply_quality.surface_contract import detect_semantic_placeholders


def _scenario(scenario_id: str):
    profile = load_customer_profile("niklas-demo-live-eval-v1")
    scenarios = generate_coworker_reply_dataset(profile, seed=0)
    return next(s for s in scenarios if s.scenario_id == scenario_id)


def _render(scenario_id: str) -> str:
    body, _, _ = _render_scenario_reply(_scenario(scenario_id))
    return body


class TestDatasetV4:
    def test_dataset_version_bumped(self):
        assert COWORKER_REPLY_DATASET_VERSION == "coworker_reply_dataset_v4"

    def test_manifest_hash_present(self):
        profile = load_customer_profile("niklas-demo-live-eval-v1")
        scenarios = generate_coworker_reply_dataset(profile, seed=0)
        manifest = build_coworker_dataset_manifest(scenarios)
        assert manifest.manifest_hash
        assert manifest.dataset_version == "coworker_reply_dataset_v4"

    def test_no_transport_messages_in_dataset(self):
        profile = load_customer_profile("niklas-demo-live-eval-v1")
        scenarios = generate_coworker_reply_dataset(profile, seed=0)
        for scenario in scenarios:
            results = evaluate_input_realism_oracles(scenario=scenario)
            assert results[0].status == "pass", scenario.scenario_id


class TestFactExtraction:
    def test_support_message_extracts_core_facts(self):
        facts = extract_customer_facts(
            input_data={
                "subject": "Support",
                "message_text": "Hej, våra solceller fungerar dåligt sedan igår.",
            }
        )
        assert "system_type" in facts.known_question_fields
        assert "symptom" in facts.known_question_fields
        assert "when_started" in facts.known_question_fields

    def test_city_is_not_treated_as_full_address(self):
        facts = extract_customer_facts(
            input_data={
                "subject": "Offert",
                "message_text": "Hej, vi vill ha solceller i Enköping.",
            }
        )
        assert "address" not in facts.known_question_fields
        assert facts.location_city == "Enköping"


class TestLocationGoldenReplies:
    def test_no_city_placeholder_in_replies(self):
        for scenario_id in (
            "PTB-DCQ-0001",
            "PTB-DCQ-0007",
            "PTB-DCQ-0032",
            "PTB-DCQ-0048",
            "PTB-DCQ-0015",
            "PTB-DCQ-0024",
        ):
            body = _render(scenario_id)
            assert body
            assert detect_semantic_placeholders(body) == []
            assert " city" not in body.lower()


class TestSupportGoldenReplies:
    def test_support_does_not_reask_known_facts(self):
        for scenario_id in ("PTB-DCQ-0056", "PTB-DCQ-0057", "PTB-DCQ-0060", "PTB-DCQ-0064", "PTB-DCQ-0065"):
            scenario = _scenario(scenario_id)
            body = _render(scenario_id)
            assert body
            oracles = evaluate_coworker_reply_oracles(
                scenario=scenario,
                reply_body=body,
                plan_v2=None,
                provenance=None,
            )
            assert all(
                r.status == "pass"
                for r in oracles
                if r.name == "input_fact_reask"
            )


class TestPlanInvariant:
    def test_selected_known_conflict_blocks_plan_field(self):
        result = validate_selected_known_invariant(
            selected_questions=("symptom", "error_code"),
            already_known_facts=(),
            extracted_known_fields=("symptom", "system_type", "when_started"),
        )
        assert result.passed is False
        assert "selected_known_conflict:symptom" in result.violations
