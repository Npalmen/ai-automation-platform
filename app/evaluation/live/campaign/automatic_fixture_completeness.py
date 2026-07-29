"""Fail-closed fixture bundle completeness for automatic Gmail canary."""

from __future__ import annotations

from typing import Any

from app.evaluation.live.campaign.automatic_action_contract import (
    AUTOMATIC_GMAIL_CANARY_SCENARIO_IDS,
)
from app.evaluation.live.campaign.registry import get_campaign_scenario
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.fixture_bundle import (
    BUNDLE_FIXTURES,
    SCENARIO_BUNDLE_MAP,
    load_bundle_fixtures,
    resolve_fixture_bundle_id,
)

AUTOMATIC_CANARY_FIXTURE_BUNDLE_MISSING = "automatic_canary_fixture_bundle_missing"


def validate_automatic_fixture_bundle_completeness(
    *,
    selected_scenario_ids: tuple[str, ...] | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """Ensure every automatic-canary scenario has a loadable allowlisted fixture bundle."""
    scenario_ids = tuple(selected_scenario_ids or AUTOMATIC_GMAIL_CANARY_SCENARIO_IDS)
    matrix: dict[str, Any] = {
        "selected_scenario_ids": list(scenario_ids),
        "mappings": {},
    }
    issues: list[str] = []

    if scenario_ids != AUTOMATIC_GMAIL_CANARY_SCENARIO_IDS:
        issues.append(
            f"{AUTOMATIC_CANARY_FIXTURE_BUNDLE_MISSING}: selected scenarios must be exactly "
            f"{list(AUTOMATIC_GMAIL_CANARY_SCENARIO_IDS)}, got {list(scenario_ids)}"
        )

    if len(set(scenario_ids)) != len(scenario_ids):
        issues.append(
            f"{AUTOMATIC_CANARY_FIXTURE_BUNDLE_MISSING}: duplicate scenario ids in selection"
        )

    for scenario_id in scenario_ids:
        entry: dict[str, Any] = {"scenario_id": scenario_id}
        try:
            scenario = get_campaign_scenario(scenario_id)
            entry["scenario_version"] = scenario.scenario_version
            entry["content_hash"] = scenario.content_hash
        except LiveEvalSafetyError as exc:
            issues.append(
                f"{AUTOMATIC_CANARY_FIXTURE_BUNDLE_MISSING}: {scenario_id}: {exc}"
            )
            matrix["mappings"][scenario_id] = entry
            continue

        bundle_id = SCENARIO_BUNDLE_MAP.get(scenario_id)
        entry["bundle_id"] = bundle_id
        if not bundle_id:
            issues.append(
                f"{AUTOMATIC_CANARY_FIXTURE_BUNDLE_MISSING}: "
                f"no SCENARIO_BUNDLE_MAP entry for {scenario_id!r}"
            )
            matrix["mappings"][scenario_id] = entry
            continue

        if bundle_id not in BUNDLE_FIXTURES:
            issues.append(
                f"{AUTOMATIC_CANARY_FIXTURE_BUNDLE_MISSING}: "
                f"bundle {bundle_id!r} missing from BUNDLE_FIXTURES"
            )
            matrix["mappings"][scenario_id] = entry
            continue

        try:
            resolve_fixture_bundle_id(scenario_id=scenario_id, ai_mode="fixture_ai")
            fixtures = load_bundle_fixtures(bundle_id)
            entry["fixture_stages"] = sorted(fixtures.keys())
        except LiveEvalSafetyError as exc:
            issues.append(
                f"{AUTOMATIC_CANARY_FIXTURE_BUNDLE_MISSING}: {scenario_id}: {exc}"
            )

        matrix["mappings"][scenario_id] = entry

    matrix["complete"] = not issues
    return issues, matrix
