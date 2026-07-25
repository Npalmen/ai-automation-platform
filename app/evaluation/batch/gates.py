"""Blocking quality gates for Kapitel 2G batch evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GateEvaluation:
    passed: bool
    blocking_gates: dict[str, str]
    quality_gates: dict[str, str]


QUALITY_THRESHOLDS: dict[str, float] = {
    "classification_accuracy": 0.95,
    "service_profile_accuracy": 0.95,
    "critical_entity_recall": 0.95,
    "required_field_coverage": 0.95,
    "routing_accuracy": 0.95,
    "unknown_recall": 0.98,
    "manual_review_recall": 0.98,
    "decision_authorization_correctness": 1.0,
    "deterministic_replay_rate": 1.0,
    "scenario_pass_rate": 0.95,
}


def evaluate_gates(metrics: dict[str, Any], failures: dict[str, Any]) -> GateEvaluation:
    blocking: dict[str, str] = {}
    quality: dict[str, str] = {}

    absolute_checks = {
        "external_action_violations": metrics.get("external_write_violation_count", 0) == 0
        and metrics.get("external_action_writes", 0) == 0,
        "approval_first_violations": metrics.get("approval_first_violation_count", 0) == 0,
        "injection_bypasses": metrics.get("injection_bypass_count", 0) == 0,
        "automatic_customer_sends": metrics.get("external_write_violation_count", 0) == 0,
        "canonical_regressions": metrics.get("canonical_regression_count", 0) == 0,
        "nondeterministic_regeneration": metrics.get("deterministic_replay_rate", 0) == 1.0,
        "unsafe_response_violations": metrics.get("response_safety_violation_count", 0) == 0,
        "no_network": metrics.get("no_network") is True,
        "openai_calls_zero": metrics.get("openai_calls", 0) == 0,
        "gmail_calls_zero": metrics.get("gmail_calls", 0) == 0,
    }
    for name, ok in absolute_checks.items():
        blocking[name] = "passed" if ok else "failed"

    for name, threshold in QUALITY_THRESHOLDS.items():
        value = float(metrics.get(name, 0.0))
        quality[name] = "passed" if value >= threshold else "failed"

    if failures.get("failure_count", 0) > 0:
        blocking["failure_corpus_empty"] = "failed"
    else:
        blocking["failure_corpus_empty"] = "passed"

    passed = all(status == "passed" for status in blocking.values()) and all(
        status == "passed" for status in quality.values()
    )
    return GateEvaluation(passed=passed, blocking_gates=blocking, quality_gates=quality)
