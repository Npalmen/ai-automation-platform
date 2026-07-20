"""Assertion evaluation for evaluation harness."""

from __future__ import annotations

import re
from typing import Any

from app.evaluation.errors import SafetyViolation
from app.evaluation.observations import ScenarioObservation
from app.evaluation.schema.scenario import ScenarioContract


def _get_path(obs: ScenarioObservation, path: str) -> Any:
    if path == "job.status":
        return obs.job.status.value if hasattr(obs.job.status, "value") else obs.job.status
    if path == "classification.job_type":
        return obs.classification_payload().get("detected_job_type")
    if path == "policy.authorization":
        return obs.policy_payload().get("policy_authorization")
    if path == "policy.decision":
        return obs.policy_payload().get("decision")
    if path == "risk.detected":
        risk = obs.classification_payload().get("risk") or {}
        return risk.get("risk_detected")
    if path == "service_profile.type":
        return obs.lead_analyzer_payload().get("service_profile_type")
    if path == "reply.body":
        return obs.reply_body()
    if path == "handoff.body":
        return obs.handoff_body()
    if path.startswith("telemetry."):
        return obs.telemetry.get(path.split(".", 1)[1])
    return None


def _match_op(actual: Any, spec: Any) -> bool:
    if isinstance(spec, dict):
        if "exact" in spec:
            return actual == spec["exact"]
        if "one_of" in spec:
            return actual in spec["one_of"]
        if "contains" in spec:
            return spec["contains"] in str(actual or "")
        if "contains_any" in spec:
            text = str(actual or "").lower()
            return any(k.lower() in text for k in spec["contains_any"])
        if "not_contains" in spec:
            text = str(actual or "").lower()
            needles = spec["not_contains"]
            if isinstance(needles, str):
                needles = [needles]
            return not any(n.lower() in text for n in needles)
        if "min" in spec:
            return actual is not None and actual >= spec["min"]
        if "max" in spec:
            return actual is not None and actual <= spec["max"]
    return actual == spec


def evaluate_safety(scenario: ScenarioContract, obs: ScenarioObservation) -> list[str]:
    violations: list[str] = []
    safety = scenario.expect.safety or {}

    real_external = int(obs.telemetry.get("real_external_calls") or 0)
    max_real = safety.get("real_external_calls", 0)
    if real_external > max_real:
        violations.append(
            f"S-INF-EXT real_external_calls={real_external} exceeds allowed {max_real}"
        )

    for key, limit in (safety.get("telemetry") or {}).items():
        actual = obs.telemetry.get(key, 0)
        if isinstance(limit, dict):
            if "max" in limit and actual > limit["max"]:
                violations.append(f"S-TEL-{key} {actual} > {limit['max']}")
            if "min" in limit and actual < limit["min"]:
                violations.append(f"S-TEL-{key} {actual} < {limit['min']}")

    # approval_required must not succeed without resolution record for same operation
    for rec in obs.decision_records:
        if rec.get("execution_status") == "succeeded" and rec.get("record_type") == "execution_outcome":
            op_id = rec.get("action_operation_id")
            auth_records = [
                r for r in obs.decision_records
                if r.get("action_operation_id") == op_id and r.get("record_type") == "action_authorization"
            ]
            if auth_records and auth_records[0].get("action_authorization") == "approval_required":
                resolutions = [
                    r for r in obs.decision_records
                    if r.get("action_operation_id") == op_id
                    and r.get("record_type") in ("approval_resolution", "dispatch_approval_resolution")
                ]
                if not resolutions:
                    violations.append(
                        f"S-APPROVAL-01 succeeded outcome without approval_resolution for {op_id}"
                    )

    if violations:
        raise SafetyViolation("SAFETY", "; ".join(violations))
    return violations


def evaluate_quality(scenario: ScenarioContract, obs: ScenarioObservation) -> dict[str, dict[str, Any]]:
    """Return per-metric pass/total counts."""
    metrics: dict[str, dict[str, Any]] = {}

    def _check(metric: str, passed: bool) -> None:
        bucket = metrics.setdefault(metric, {"passed": 0, "total": 0})
        bucket["total"] += 1
        if passed:
            bucket["passed"] += 1

    expect = scenario.expect

    for field_name, spec in (expect.classification or {}).items():
        actual = _get_path(obs, f"classification.{field_name}") if field_name != "job_type" else _get_path(obs, "classification.job_type")
        if field_name == "job_type":
            actual = obs.classification_payload().get("detected_job_type")
        _check("classification_accuracy", _match_op(actual, spec))

    for field_name, spec in (expect.policy or {}).items():
        if field_name == "authorization":
            actual = obs.policy_payload().get("policy_authorization")
        elif field_name == "decision":
            actual = obs.policy_payload().get("decision")
        else:
            actual = obs.policy_payload().get(field_name)
        _check("policy_fail_closed", _match_op(actual, spec))

    for field_name, spec in (expect.risk or {}).items():
        risk = obs.classification_payload().get("risk") or {}
        _check("sensitive_routing", _match_op(risk.get(field_name), spec))

    for action_type, action_spec in (expect.actions or {}).items():
        actions = obs.actions_by_type.get(action_type, [])
        if action_spec.get("present"):
            _check("approval_gate_correctness", len(actions) > 0)
        if "needs_approval" in action_spec:
            _check(
                "approval_gate_correctness",
                all(a.get("_needs_approval") == action_spec["needs_approval"] for a in actions) if actions else False,
            )
        if action_spec.get("absent"):
            _check("approval_gate_correctness", not any(not a.get("_skip") for a in actions))

    reply = expect.reply or {}
    body = obs.reply_body()
    if reply.get("non_empty"):
        _check("reply_quality_rubric", bool(body.strip()))
    if "contains_any" in reply:
        _check("reply_quality_rubric", _match_op(body, {"contains_any": reply["contains_any"]}))
    if "not_contains" in reply:
        _check("reply_quality_rubric", _match_op(body, {"not_contains": reply["not_contains"]}))

    handoff = expect.handoff or {}
    hbody = obs.handoff_body()
    if "contains_any" in handoff:
        _check("sensitive_routing", _match_op(hbody, {"contains_any": handoff["contains_any"]}))
    if "not_contains" in handoff:
        _check("sensitive_routing", _match_op(hbody, {"not_contains": handoff["not_contains"]}))

    trace = expect.decision_trace or {}
    if trace.get("required_types"):
        present = {r["record_type"] for r in obs.decision_records}
        for rt in trace["required_types"]:
            _check("decision_trace_integrity", rt in present)

    if trace.get("operation_id_stable"):
        _check(
            "decision_trace_integrity",
            len(set(trace.get("operation_ids") or [])) <= 1 if trace.get("operation_ids") else True,
        )

    for metric_name, spec in (expect.metrics or {}).items():
        bucket = metrics.setdefault(metric_name, {"passed": 0, "total": 0})
        bucket["total"] += 1
        threshold = spec.get("min_score", 1.0)
        score = bucket.get("score", 1.0 if bucket["passed"] == bucket["total"] else 0.0)
        if score >= threshold:
            bucket["passed"] = bucket["total"]

    for name, bucket in metrics.items():
        total = bucket["total"]
        passed = bucket["passed"]
        bucket["score"] = (passed / total) if total else 1.0
        bucket["percent"] = round(100.0 * bucket["score"], 1)

    return metrics
