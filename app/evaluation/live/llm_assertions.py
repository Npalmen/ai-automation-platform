"""Semantic assertions for S01 live_llm fixture_input eval."""

from __future__ import annotations

from typing import Any

from app.evaluation.live.assertions import (
    FORBIDDEN_DECISION_TYPES,
    REQUIRED_DECISION_SUBSEQUENCE,
    _assert_decision_subsequence,
)

_LIVE_LLM_PROCESSORS = (
    "classification_processor",
    "entity_extraction_processor",
    "lead_processor",
    "decisioning_processor",
)


def _processor_payloads(job: dict[str, Any]) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for entry in job.get("processor_history") or []:
        name = entry.get("processor")
        if not name:
            continue
        result = entry.get("result") or {}
        payload = result.get("payload") or {}
        if isinstance(payload, dict):
            payloads[name] = payload
    return payloads


def assert_s01_live_llm_pipeline(observation: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    job = observation.get("job") or {}

    if job.get("job_type") != "lead":
        violations.append(f"expected job_type lead, got {job.get('job_type')!r}")
    if job.get("job_status") != "awaiting_approval":
        violations.append(f"expected awaiting_approval, got {job.get('job_status')!r}")

    pending = job.get("pending_approval_count")
    if pending is None:
        if not job.get("has_pending_approvals"):
            violations.append("expected pending approval")
    elif pending != 1:
        violations.append(f"expected pending_approval_count 1, got {pending!r}")

    classification = job.get("classification") or {}
    if classification.get("detected_job_type") != "lead":
        violations.append("classification lead mismatch")

    entities = job.get("entities") or job.get("entity_extraction") or {}
    entity_map = entities.get("entities") if isinstance(entities, dict) else {}
    if isinstance(entity_map, dict):
        if entity_map.get("customer_name") != "Anna Lindqvist":
            violations.append("expected customer_name Anna Lindqvist")
        if entity_map.get("email") != "anna@example.com":
            violations.append("expected email anna@example.com")

    service_profile = job.get("service_profile") or {}
    profile_name = (
        service_profile.get("profile")
        or service_profile.get("service_profile")
        or service_profile.get("name")
    )
    if profile_name and "laddbox" not in str(profile_name).lower():
        violations.append("service profile should reference laddbox context")

    policy = job.get("policy") or {}
    if policy.get("policy_authorization") != "approval_required":
        violations.append(
            f"expected policy_authorization approval_required, got {policy.get('policy_authorization')!r}"
        )
    if policy.get("decision") != "send_for_approval":
        violations.append(f"expected send_for_approval, got {policy.get('decision')!r}")

    records = job.get("decision_records") or []
    types = [
        r.get("record_type")
        for r in sorted(records, key=lambda x: int(x.get("event_sequence") or 0))
    ]
    violations.extend(_assert_decision_subsequence(types))
    for forbidden in FORBIDDEN_DECISION_TYPES:
        if forbidden in types:
            violations.append(f"forbidden decision record {forbidden}")

    payloads = _processor_payloads(job)
    for processor_name in _LIVE_LLM_PROCESSORS:
        payload = payloads.get(processor_name) or {}
        if payload.get("used_fallback") is True:
            violations.append(f"{processor_name} used_fallback must be false")

    return violations


def assert_live_llm_telemetry_budget(events: list[dict[str, Any]]) -> list[str]:
    violations: list[str] = []
    succeeded = {
        e.get("operation_key")
        for e in events
        if e.get("category") == "app_live_llm"
        and e.get("outcome") == "succeeded"
        and e.get("operation_key")
    }
    if len(succeeded) > 4:
        violations.append("app_live_llm succeeded must be <= 4")
    unknown = [
        e for e in events
        if e.get("category") == "app_live_llm"
        and e.get("outcome") == "outcome_unknown"
    ]
    if unknown:
        violations.append("app_live_llm outcome_unknown must be 0")
    return violations


def assert_s01_live_llm_semantics(observation: dict[str, Any]) -> list[str]:
    violations = assert_s01_live_llm_pipeline(observation)
    events = observation.get("events") or []
    violations.extend(assert_live_llm_telemetry_budget(events))
    run = observation.get("run") or {}
    if run.get("transport_mode") != "fixture_input":
        violations.append("fixture_input transport required")
    if run.get("ai_mode") != "live_llm":
        violations.append("live_llm ai_mode required")
    return violations
