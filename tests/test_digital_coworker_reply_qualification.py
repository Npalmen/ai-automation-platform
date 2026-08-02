"""Coworker reply quality qualification tests (Todos G-J)."""

from __future__ import annotations

from app.evaluation.profile_testbot.coworker_reply_dataset import (
    COWORKER_SCENARIO_TARGET,
    generate_coworker_reply_dataset,
    validate_coworker_dataset_gates,
)
from app.evaluation.profile_testbot.profile_contract import load_customer_profile
from app.evaluation.profile_testbot.qualification.hermetic_coworker_reply import (
    run_hermetic_coworker_reply_qualification,
)
from app.evaluation.profile_testbot.qualification.human_review_coworker import (
    evaluate_human_review_campaign,
    score_reply_for_review,
)
from app.evaluation.profile_testbot.qualification.hermetic_coworker_reply import (
    _render_scenario_reply,
)


class TestCoworkerDataset:
    def test_dataset_meets_plan_minimums(self):
        profile = load_customer_profile("niklas-demo-live-eval-v1")
        scenarios = generate_coworker_reply_dataset(profile)
        assert len(scenarios) == COWORKER_SCENARIO_TARGET
        assert validate_coworker_dataset_gates(scenarios) == []


class TestHermeticCoworkerQualification:
    def test_r1_hermetic_pass(self):
        result = run_hermetic_coworker_reply_qualification()
        assert result.overall_status == "PASS"
        assert result.scenario_count == COWORKER_SCENARIO_TARGET
        assert result.hard_safety_pass_rate == 1.0
        assert result.template_similarity <= 0.72
        assert result.fallback_rate <= 0.15


class TestHumanReviewRubric:
    def test_r2_proxy_review_passes_sample(self):
        profile = load_customer_profile("niklas-demo-live-eval-v1")
        scenarios = generate_coworker_reply_dataset(profile)[:40]
        scores = []
        for scenario in scenarios:
            body, _, _ = _render_scenario_reply(scenario)
            setup = scenario.customer_state_setup or {}
            scores.append(
                score_reply_for_review(
                    scenario_id=scenario.scenario_id,
                    family=scenario.family,
                    reply_body=body,
                    required_markers=list(setup.get("required_markers") or []),
                )
            )
        result = evaluate_human_review_campaign(scores)
        assert result.reviewed_count == 40
        assert result.overall_status == "PASS"
