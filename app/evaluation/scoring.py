"""Quality metric gating for evaluation harness."""

from __future__ import annotations

from app.evaluation.errors import QualityFailure

MANDATORY_METRIC_THRESHOLDS: dict[str, float] = {
    "approval_gate_correctness": 1.0,
    "sensitive_routing": 1.0,
    "policy_fail_closed": 1.0,
    "decision_trace_integrity": 1.0,
    "classification_accuracy": 0.95,
    "reply_quality_rubric": 0.90,
}


def gate_metrics(metrics: dict[str, dict]) -> list[str]:
    failures: list[str] = []
    for name, threshold in MANDATORY_METRIC_THRESHOLDS.items():
        if name not in metrics:
            continue
        score = metrics[name].get("score", 0.0)
        if score < threshold:
            failures.append(f"{name}: {score:.2%} < {threshold:.0%}")
    if failures:
        raise QualityFailure("quality_gate", "; ".join(failures))
    return failures


def diagnostic_weighted_score(metrics: dict[str, dict]) -> float:
    if not metrics:
        return 1.0
    scores = [m.get("score", 0.0) for m in metrics.values()]
    return sum(scores) / len(scores)
