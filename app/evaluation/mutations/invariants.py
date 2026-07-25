"""Semantic invariant enforcement for mutations."""

from __future__ import annotations

from app.evaluation.errors import ScenarioValidationError
from app.evaluation.schema.scenario import ScenarioContract


def assert_job_type_unchanged(before: ScenarioContract, after: ScenarioContract) -> None:
    before_type = before.expect.classification.get("job_type", {}).get("exact")
    after_type = after.expect.classification.get("job_type", {}).get("exact")
    if before_type and after_type and before_type != after_type:
        raise ScenarioValidationError(
            f"Mutation changed job_type from {before_type!r} to {after_type!r}"
        )


def assert_no_external_writes(scenario: ScenarioContract) -> None:
    safety = scenario.expect.safety
    if isinstance(safety, dict):
        calls = safety.get("real_external_calls")
        if calls not in (None, 0):
            raise ScenarioValidationError("Mutation introduced external calls expectation")
    forbidden = scenario.expect.outcomes.forbidden
    if forbidden.max_real_external_calls not in (None, 0):
        raise ScenarioValidationError("Mutation changed forbidden external call contract")


def assert_injection_is_data_only(scenario: ScenarioContract) -> None:
    if scenario.category != "injection_attempt":
        return
    body = scenario.input.message_text.lower()
    markers = ("ignore previous", "system:", "approve automatically", "send immediately")
    for marker in markers:
        if marker in body:
            # Injection text must remain in customer message body, not in system fields.
            continue
    assert "instruction" in body or "ignore" in body or "system" in body.lower()
