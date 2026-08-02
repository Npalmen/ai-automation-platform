"""Regression tests for coworker qualification aggregation consistency."""

from __future__ import annotations

from app.evaluation.profile_testbot.coworker_quality_oracles import (
    CoworkerOracleResult,
    aggregate_coworker_results,
    summarize_surface_quality_metrics,
)
from app.evaluation.profile_testbot.qualification.hermetic_coworker_reply import (
    run_hermetic_coworker_reply_qualification,
)
from app.evaluation.profile_testbot.qualification.human_review_coworker import (
    evaluate_human_review_campaign,
    score_reply_for_review,
)
from app.evaluation.profile_testbot.coworker_reply_dataset import generate_coworker_reply_dataset
from app.evaluation.profile_testbot.profile_contract import load_customer_profile
from app.evaluation.profile_testbot.qualification.hermetic_coworker_reply import _render_scenario_reply
from app.workflows.reply_quality.surface_contract import detect_mixed_language


class TestQualificationAggregation:
    def test_mixed_language_proxy_must_match_blocking_oracle(self):
        body = (
            "Hej,\n\nTack för din förfrågan om laddbox.\n\n"
            "For the charger project we need the property address.\n\n"
            "Kind regards\nNiklas"
        )
        mixed = detect_mixed_language(body, expected_language="en")
        assert mixed
        oracle_results = [
            CoworkerOracleResult(
                "single_reply_language",
                "fail" if mixed else "pass",
                "surface_quality",
                ";".join(mixed),
            )
        ]
        metrics = summarize_surface_quality_metrics(
            reply_body=body,
            expected_language="en",
            oracle_results=oracle_results,
        )
        agg = aggregate_coworker_results(oracle_results)
        assert metrics["mixed_language_violations"] >= 1
        assert metrics["blocking_oracle_failures"] >= 1
        assert metrics["aggregation_consistent"] is True
        assert agg["passed"] is False

    def test_r1_hermetic_pass_after_language_surface_fix(self):
        result = run_hermetic_coworker_reply_qualification()
        assert result.overall_status == "PASS"
        assert result.scenario_count == 120

    def test_human_review_40_pack_proxy_passes(self):
        profile = load_customer_profile("niklas-demo-live-eval-v1")
        scenarios = generate_coworker_reply_dataset(profile, seed=0)[:40]
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
        assert result.overall_status == "PASS"
