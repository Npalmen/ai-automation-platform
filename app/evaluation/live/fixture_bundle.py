"""Server-allowlisted fixture bundles for live eval fixture_ai mode."""

from __future__ import annotations

from typing import Any

from app.evaluation.live.errors import LiveEvalSafetyError

# scenario_id -> bundle_id (server resolved at registration; not client supplied)
SCENARIO_BUNDLE_MAP: dict[str, str] = {
    "S01_lead_laddbox_quality": "k2f_bundle_s01",
}

ALLOWLISTED_BUNDLE_IDS = frozenset(SCENARIO_BUNDLE_MAP.values())

# Minimal deterministic fixtures for foundation tests and future 2F.2 S01.
BUNDLE_FIXTURES: dict[str, dict[str, dict[str, Any]]] = {
    "k2f_bundle_s01": {
        "classification_v1": {
            "detected_job_type": "lead",
            "confidence": 0.9,
            "reasons": ["keyword_match"],
        },
        "entity_extraction_v1": {
            "entities": {"customer_name": "Anna Lindqvist", "email": "eval@example.com"},
            "confidence": 0.85,
        },
        "lead_scoring_v1": {
            "lead_score": 70,
            "priority": "medium",
            "routing": "crm_update",
            "reasons": [],
            "confidence": 0.85,
        },
        "decisioning_v1": {
            "decision": "auto_route",
            "target_queue": "sales_queue",
            "action_flags": {
                "create_crm_lead": False,
                "notify_human": False,
                "request_missing_data": True,
            },
            "reasons": [],
            "confidence": 0.85,
        },
    },
}


def resolve_fixture_bundle_id(*, scenario_id: str, ai_mode: str) -> str | None:
    if ai_mode != "fixture_ai":
        return None
    bundle_id = SCENARIO_BUNDLE_MAP.get(scenario_id)
    if bundle_id is None:
        raise LiveEvalSafetyError(f"No allowlisted fixture bundle for scenario {scenario_id!r}")
    if bundle_id not in ALLOWLISTED_BUNDLE_IDS:
        raise LiveEvalSafetyError(f"fixture bundle {bundle_id!r} is not allowlisted")
    return bundle_id


def load_bundle_fixtures(bundle_id: str) -> dict[str, dict[str, Any]]:
    if bundle_id not in ALLOWLISTED_BUNDLE_IDS:
        raise LiveEvalSafetyError(f"Unknown fixture bundle {bundle_id!r}")
    fixtures = BUNDLE_FIXTURES.get(bundle_id)
    if fixtures is None:
        raise LiveEvalSafetyError(f"Fixture bundle {bundle_id!r} has no content")
    return fixtures
