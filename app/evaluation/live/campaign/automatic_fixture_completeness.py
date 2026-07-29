"""Fail-closed fixture bundle completeness for automatic Gmail campaigns."""

from __future__ import annotations

from typing import Any

from app.evaluation.live.campaign.automatic_action_contract import (
    AUTOMATIC_GMAIL_CANARY_CAMPAIGN_TYPE,
    AUTOMATIC_GMAIL_CANARY_SCENARIO_IDS,
)
from app.evaluation.live.campaign.automatic_action_contract_core import (
    AUTOMATIC_GMAIL_CORE_CAMPAIGN_TYPE,
    AUTOMATIC_GMAIL_CORE_SCENARIO_IDS,
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
AUTOMATIC_CORE_FIXTURE_BUNDLE_MISSING = "automatic_core_fixture_bundle_missing"

_CAMPAIGN_SCENARIO_IDS: dict[str, tuple[str, ...]] = {
    AUTOMATIC_GMAIL_CANARY_CAMPAIGN_TYPE: AUTOMATIC_GMAIL_CANARY_SCENARIO_IDS,
    AUTOMATIC_GMAIL_CORE_CAMPAIGN_TYPE: AUTOMATIC_GMAIL_CORE_SCENARIO_IDS,
}

_CAMPAIGN_ERROR_CODES: dict[str, str] = {
    AUTOMATIC_GMAIL_CANARY_CAMPAIGN_TYPE: AUTOMATIC_CANARY_FIXTURE_BUNDLE_MISSING,
    AUTOMATIC_GMAIL_CORE_CAMPAIGN_TYPE: AUTOMATIC_CORE_FIXTURE_BUNDLE_MISSING,
}


def _expected_scenario_ids(
    *,
    campaign_type: str,
    selected_scenario_ids: tuple[str, ...] | None,
) -> tuple[str, ...]:
    default = _CAMPAIGN_SCENARIO_IDS.get(campaign_type)
    if default is None:
        raise LiveEvalSafetyError(f"unsupported automatic campaign_type={campaign_type!r}")
    if selected_scenario_ids is None:
        return default
    return tuple(selected_scenario_ids)


def validate_automatic_fixture_bundle_completeness(
    *,
    campaign_type: str = AUTOMATIC_GMAIL_CANARY_CAMPAIGN_TYPE,
    selected_scenario_ids: tuple[str, ...] | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """Ensure every automatic campaign scenario has a loadable allowlisted fixture bundle."""
    error_code = _CAMPAIGN_ERROR_CODES.get(
        campaign_type,
        AUTOMATIC_CANARY_FIXTURE_BUNDLE_MISSING,
    )
    expected_ids = _expected_scenario_ids(
        campaign_type=campaign_type,
        selected_scenario_ids=selected_scenario_ids,
    )
    scenario_ids = tuple(selected_scenario_ids or expected_ids)
    matrix: dict[str, Any] = {
        "campaign_type": campaign_type,
        "selected_scenario_ids": list(scenario_ids),
        "expected_scenario_ids": list(expected_ids),
        "mappings": {},
    }
    issues: list[str] = []

    if scenario_ids != expected_ids:
        issues.append(
            f"{error_code}: selected scenarios must be exactly "
            f"{list(expected_ids)}, got {list(scenario_ids)}"
        )

    if len(set(scenario_ids)) != len(scenario_ids):
        issues.append(
            f"{error_code}: duplicate scenario ids in selection"
        )

    for scenario_id in scenario_ids:
        entry: dict[str, Any] = {"scenario_id": scenario_id}
        try:
            scenario = get_campaign_scenario(scenario_id)
            entry["scenario_version"] = scenario.scenario_version
            entry["content_hash"] = scenario.content_hash
        except LiveEvalSafetyError as exc:
            issues.append(f"{error_code}: {scenario_id}: {exc}")
            matrix["mappings"][scenario_id] = entry
            continue

        bundle_id = SCENARIO_BUNDLE_MAP.get(scenario_id)
        entry["bundle_id"] = bundle_id
        if not bundle_id:
            issues.append(
                f"{error_code}: no SCENARIO_BUNDLE_MAP entry for {scenario_id!r}"
            )
            matrix["mappings"][scenario_id] = entry
            continue

        if bundle_id not in BUNDLE_FIXTURES:
            issues.append(
                f"{error_code}: bundle {bundle_id!r} missing from BUNDLE_FIXTURES"
            )
            matrix["mappings"][scenario_id] = entry
            continue

        try:
            resolve_fixture_bundle_id(scenario_id=scenario_id, ai_mode="fixture_ai")
            fixtures = load_bundle_fixtures(bundle_id)
            entry["fixture_stages"] = sorted(fixtures.keys())
        except LiveEvalSafetyError as exc:
            issues.append(f"{error_code}: {scenario_id}: {exc}")

        matrix["mappings"][scenario_id] = entry

    matrix["complete"] = not issues
    return issues, matrix
