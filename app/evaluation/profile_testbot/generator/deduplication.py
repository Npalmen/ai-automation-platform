"""Semantic deduplication for generated profile scenarios."""

from __future__ import annotations

import hashlib
import json
from typing import Iterable

from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario


def semantic_fingerprint(scenario: ProfileScenario) -> str:
    payload = {
        "family": scenario.family,
        "intent": scenario.intent,
        "risk_class": scenario.risk_class,
        "expected_send_behavior": scenario.expected_send_behavior,
        "expected_classification": scenario.expected_classification,
        "expected_route": scenario.expected_route,
        "customer_state": scenario.customer_state_setup,
        "thread_state": scenario.thread_setup,
        "language": scenario.input.language,
        "mutation_types": sorted(scenario.mutation_types),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def find_semantic_duplicates(scenarios: Iterable[ProfileScenario]) -> list[str]:
    seen: dict[str, str] = {}
    duplicates: list[str] = []
    for scenario in scenarios:
        fp = semantic_fingerprint(scenario)
        if fp in seen:
            duplicates.append(f"{scenario.scenario_id} duplicates {seen[fp]}")
        else:
            seen[fp] = scenario.scenario_id
    return duplicates
