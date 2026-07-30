"""Decision oracle for profile-driven testbot."""

from __future__ import annotations

from app.evaluation.profile_testbot.oracles.hard_safety import OracleResult
from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario


def evaluate_decision_oracle(
    *,
    scenario: ProfileScenario,
    observed_classification: dict,
    observed_route: dict,
    observed_authorization: dict,
    observed_send_behavior: str,
) -> list[OracleResult]:
    results: list[OracleResult] = []
    expected_job_type = scenario.expected_classification.get("job_type")
    observed_job_type = observed_classification.get("job_type")
    results.append(
        OracleResult(
            name="classification_job_type",
            status="pass" if expected_job_type == observed_job_type else "fail",
            detail=f"expected={expected_job_type} observed={observed_job_type}",
            blocker=True,
        )
    )
    expected_queue = scenario.expected_route.get("queue")
    observed_queue = observed_route.get("queue")
    results.append(
        OracleResult(
            name="route_queue",
            status="pass" if expected_queue == observed_queue else "fail",
            detail=f"expected={expected_queue} observed={observed_queue}",
            blocker=True,
        )
    )
    expected_auth = scenario.expected_authorization.get("policy_authorization")
    observed_auth = observed_authorization.get("policy_authorization")
    results.append(
        OracleResult(
            name="policy_authorization",
            status="pass" if expected_auth == observed_auth else "fail",
            detail=f"expected={expected_auth} observed={observed_auth}",
            blocker=True,
        )
    )
    results.append(
        OracleResult(
            name="send_behavior",
            status="pass" if scenario.expected_send_behavior == observed_send_behavior else "fail",
            detail=f"expected={scenario.expected_send_behavior} observed={observed_send_behavior}",
            blocker=True,
        )
    )
    return results
