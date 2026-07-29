"""TBF2 manifest contract tests."""

from __future__ import annotations

from app.evaluation.customer_domain.tbf2_registry import (
    EXPECTED_SCENARIO_IDS,
    load_tbf2_runners,
    validate_manifest,
)


def test_tbf2_manifest_has_exactly_ten_scenarios():
    failures = validate_manifest()
    assert failures == []
    runners = load_tbf2_runners()
    assert list(runners.keys()) == list(EXPECTED_SCENARIO_IDS)
