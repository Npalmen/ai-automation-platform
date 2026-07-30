"""Failure classification and regression promotion."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_FAILURE_CATEGORIES = (
    "generator_fixture",
    "oracle",
    "classification",
    "extraction",
    "routing",
    "decision",
    "policy_authorization",
    "reply_quality",
    "provider_transport",
    "idempotency",
    "customer_state",
    "observability",
)


@dataclass(frozen=True)
class ClassifiedFailure:
    scenario_id: str
    category: str
    evidence: dict[str, Any]


def classify_failure(*, scenario_id: str, blockers: list[str]) -> ClassifiedFailure:
    category = "observability"
    if any("classification" in b for b in blockers):
        category = "classification"
    elif any("route" in b or "send_behavior" in b for b in blockers):
        category = "routing"
    elif any("forbidden" in b or "reply" in b for b in blockers):
        category = "reply_quality"
    elif any("tenant" in b or "recipient" in b or "duplicate" in b for b in blockers):
        category = "policy_authorization"
    elif any("oracle" in b for b in blockers):
        category = "oracle"
    return ClassifiedFailure(
        scenario_id=scenario_id,
        category=category if category in _FAILURE_CATEGORIES else "observability",
        evidence={"blockers": blockers},
    )


def promote_failure_to_regression(
    *,
    failure: ClassifiedFailure,
    scenario_payload: dict[str, Any],
    corpus_path: str = "app/evaluation/profile_testbot/resources/regression_corpus.json",
) -> dict[str, Any]:
    path = Path(corpus_path)
    entries: list[dict[str, Any]] = []
    if path.is_file():
        entries = json.loads(path.read_text(encoding="utf-8"))
    record = {
        "scenario_id": failure.scenario_id,
        "category": failure.category,
        "evidence": failure.evidence,
        "scenario": scenario_payload,
    }
    entries.append(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    return record
