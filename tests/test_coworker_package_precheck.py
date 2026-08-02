"""Package-level precheck aggregation tests."""

from __future__ import annotations

from app.evaluation.profile_testbot.qualification.coworker_package_precheck import (
    PACKAGE_THRESHOLDS,
    evaluate_package_precheck,
)


def _forty_scenario_baseline():
    """Reproduce 8b16728 diagnostic pack: 31 LLM success, 9 fallback, all scenario-pass."""
    n = 40
    return dict(
        scenario_pass=[True] * n,
        bodies=[f"unique body {i} with service context" for i in range(n)],
        families=[f"family_{i % 12}" for i in range(n)],
        thread_states=["new_thread"] * 20 + ["continuation"] * 20,
        use_fallback=[False] * 31 + [True] * 9,
        llm_used=[True] * 31 + [False] * 9,
        invocation_attempted=[True] * n,
        provider_outcomes=["success"] * n,
        live_validation_outcomes=(["pass"] * 31 + ["fail"] * 9),
        aggregation_consistent=[True] * n,
        renderer_distribution={
            "constrained_llm_success": 31,
            "deterministic_fallback": 9,
            "safe_fallback": 0,
            "no_reply": 0,
        },
    )


class TestPackagePrecheck:
    def test_fallback_threshold_fail_r2_precheck(self):
        kwargs = _forty_scenario_baseline()
        result = evaluate_package_precheck(**kwargs)
        assert result.scenario_oracles_pass is True
        assert result.fallback_rate == 9 / 40
        assert result.fallback_rate > float(PACKAGE_THRESHOLDS["fallback_rate_max"])
        assert result.fallback_rate_pass is False
        assert result.package_precheck_pass is False
        assert any("fallback_rate" in f for f in result.gate_failures)

    def test_zero_fallback_passes_fallback_gate(self):
        kwargs = _forty_scenario_baseline()
        kwargs["use_fallback"] = [False] * 40
        kwargs["llm_used"] = [True] * 40
        kwargs["live_validation_outcomes"] = ["pass"] * 40
        kwargs["renderer_distribution"]["constrained_llm_success"] = 40
        kwargs["renderer_distribution"]["deterministic_fallback"] = 0
        result = evaluate_package_precheck(**kwargs)
        assert result.fallback_rate_pass is True

    def test_llm_used_with_fallback_fails_integrity(self):
        kwargs = _forty_scenario_baseline()
        kwargs["llm_used"] = [True] * 40
        result = evaluate_package_precheck(**kwargs)
        assert result.provider_integrity_pass is False

    def test_cross_family_duplicate_fails(self):
        kwargs = _forty_scenario_baseline()
        kwargs["use_fallback"] = [False] * 40
        kwargs["llm_used"] = [True] * 40
        kwargs["live_validation_outcomes"] = ["pass"] * 40
        kwargs["bodies"][0] = "Identical reply text"
        kwargs["bodies"][1] = "Identical reply text"
        kwargs["families"][0] = "solar_installation_new"
        kwargs["families"][1] = "battery_installation_new"
        result = evaluate_package_precheck(**kwargs)
        assert result.duplication_gate_pass is False
