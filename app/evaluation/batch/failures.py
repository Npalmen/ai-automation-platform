"""Failure classification and fingerprinting for Kapitel 2G."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from app.evaluation.batch.runner import BatchRunResult
from app.evaluation.dataset_manifest import canonical_json_bytes

FAILURE_SCHEMA_VERSION = "2g.failures.v1"

_FAILURE_CLASS_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("approval_first_violation", re.compile(r"approval", re.I)),
    ("external_write_violation", re.compile(r"real_external_calls|forbidden action", re.I)),
    ("decision_policy_violation", re.compile(r"policy_authorization|policy_fail", re.I)),
    ("unsafe_response", re.compile(r"reply_claim|cross_tenant", re.I)),
    ("classification_mismatch", re.compile(r"classification", re.I)),
    ("routing_mismatch", re.compile(r"routing", re.I)),
    ("pipeline_exception", re.compile(r"unexpected:", re.I)),
    ("schema_failure", re.compile(r"Invalid scenario|schema", re.I)),
]


def _classify_failure(message: str, status: str) -> str:
    for failure_class, pattern in _FAILURE_CLASS_PATTERNS:
        if pattern.search(message):
            return failure_class
    if status == "fail_harness":
        return "pipeline_exception"
    if status == "fail_quality":
        return "classification_mismatch"
    if status == "fail_safety":
        return "decision_policy_violation"
    return "infrastructure_failure"


def _fingerprint(failure_class: str, scenario_id: str, message: str) -> str:
    normalized = re.sub(r"\s+", " ", message.strip())[:240]
    payload = {"failure_class": failure_class, "scenario_id": scenario_id, "message": normalized}
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def build_failure_corpus(batch: BatchRunResult) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for outcome in batch.outcomes:
        if outcome.result.status == "pass" and outcome.deterministic:
            continue
        messages = list(outcome.result.safety_violations)
        if outcome.result.status != "pass" and not messages:
            messages = [f"status={outcome.result.status}"]
        if not outcome.deterministic:
            messages.append("nondeterministic_result")
        for message in messages:
            failure_class = _classify_failure(message, outcome.result.status)
            if not outcome.deterministic and failure_class == "infrastructure_failure":
                failure_class = "nondeterministic_result"
            fp = _fingerprint(failure_class, outcome.record.scenario.scenario_id, message)
            if fp in seen:
                continue
            seen.add(fp)
            entries.append(
                {
                    "fingerprint": fp,
                    "failure_class": failure_class,
                    "blocking": True,
                    "scenario_id": outcome.record.scenario.scenario_id,
                    "parent_scenario_id": outcome.record.provenance.parent_scenario_id,
                    "category": outcome.record.scenario.category,
                    "mutation_types": list(outcome.record.provenance.mutation_types),
                    "message": message[:500],
                    "status": outcome.result.status,
                    "reproduction_command": (
                        "python scripts/run_2g_batch.py "
                        f"--mode {batch.mode} --scenario-id {outcome.record.scenario.scenario_id}"
                    ),
                }
            )
    entries.sort(key=lambda item: item["fingerprint"])
    payload = {
        "failures_schema_version": FAILURE_SCHEMA_VERSION,
        "mode": batch.mode,
        "failure_count": len(entries),
        "failures": entries,
    }
    payload["failures_payload_hash"] = hashlib.sha256(
        canonical_json_bytes({k: v for k, v in payload.items() if k != "failures_payload_hash"})
    ).hexdigest()
    return payload
