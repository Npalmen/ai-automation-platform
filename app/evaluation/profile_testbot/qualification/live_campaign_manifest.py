"""Locked 32-scenario live quality campaign manifest (Todo J step 3)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from app.evaluation.profile_testbot.profile_contract import CustomerProfileSnapshot, load_customer_profile
from app.evaluation.profile_testbot.qualification.constants import (
    LIVE_QUALITY_CAMPAIGN_TYPE,
    LIVE_QUALITY_CAMPAIGN_FAMILY_MIN,
    LIVE_QUALITY_CAMPAIGN_SEND_MAX,
    LIVE_QUALITY_CAMPAIGN_TARGET,
    NO_SEND_BEHAVIORS,
    SEND_BEHAVIORS_COUNTING_AS_GMAIL_SEND,
)
from app.evaluation.profile_testbot.quality_dataset import generate_quality_dataset
from app.evaluation.profile_testbot.quality_dataset.constants import QUALITY_FAMILIES
from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario

# Two deterministic scenarios per family (first send-capable + first no-send where possible).
LIVE_QUALITY_CAMPAIGN_SCENARIO_IDS: tuple[str, ...] = tuple(
    scenario_id
    for family_index, _family in enumerate(QUALITY_FAMILIES)
    for offset in (0, 3)
    for scenario_id in (f"PTB-Q96-{(family_index * 6) + offset:04d}",)
)

LIVE_QUALITY_CAMPAIGN_MANIFEST_HASH: str = hashlib.sha256(
    json.dumps(list(LIVE_QUALITY_CAMPAIGN_SCENARIO_IDS), separators=(",", ":")).encode("utf-8")
).hexdigest()


@dataclass
class LiveQualityCampaignManifest:
    campaign_type: str
    scenario_count: int
    scenario_ids: list[str]
    family_distribution: dict[str, int]
    send_budget: int
    hold_reject_no_reply_count: int
    manifest_hash: str
    scenarios: list[ProfileScenario] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "campaign_type": self.campaign_type,
            "scenario_count": self.scenario_count,
            "scenario_ids": self.scenario_ids,
            "family_distribution": self.family_distribution,
            "send_budget": self.send_budget,
            "hold_reject_no_reply_count": self.hold_reject_no_reply_count,
            "manifest_hash": self.manifest_hash,
        }


def validate_live_quality_campaign_budget(scenarios: list[ProfileScenario]) -> list[str]:
    issues: list[str] = []
    if len(scenarios) != LIVE_QUALITY_CAMPAIGN_TARGET:
        issues.append(
            f"scenario count {len(scenarios)} != {LIVE_QUALITY_CAMPAIGN_TARGET}"
        )

    send_count = sum(
        1 for s in scenarios if s.expected_send_behavior in SEND_BEHAVIORS_COUNTING_AS_GMAIL_SEND
    )
    if send_count > LIVE_QUALITY_CAMPAIGN_SEND_MAX:
        issues.append(f"send budget {send_count} > {LIVE_QUALITY_CAMPAIGN_SEND_MAX}")

    families = {s.family for s in scenarios}
    if len(families) < LIVE_QUALITY_CAMPAIGN_FAMILY_MIN:
        issues.append(f"family count {len(families)} < {LIVE_QUALITY_CAMPAIGN_FAMILY_MIN}")

    no_send_count = sum(
        1 for s in scenarios if s.expected_send_behavior in NO_SEND_BEHAVIORS
    )
    if no_send_count < LIVE_QUALITY_CAMPAIGN_TARGET - LIVE_QUALITY_CAMPAIGN_SEND_MAX:
        issues.append(
            f"insufficient no-send scenarios: {no_send_count} "
            f"< {LIVE_QUALITY_CAMPAIGN_TARGET - LIVE_QUALITY_CAMPAIGN_SEND_MAX}"
        )

    return issues


def build_live_quality_campaign_manifest(
    *,
    profile_id: str = "pilot-service-company-v1",
    seed: int = 0,
) -> LiveQualityCampaignManifest:
    profile = load_customer_profile(profile_id)
    quality_by_id = {s.scenario_id: s for s in generate_quality_dataset(profile, seed=seed)}
    scenarios: list[ProfileScenario] = []
    for scenario_id in LIVE_QUALITY_CAMPAIGN_SCENARIO_IDS:
        scenario = quality_by_id.get(scenario_id)
        if scenario is None:
            raise ValueError(f"campaign scenario {scenario_id!r} not found")
        scenarios.append(scenario)

    issues = validate_live_quality_campaign_budget(scenarios)
    if issues:
        raise ValueError("; ".join(issues))

    family_distribution: dict[str, int] = {}
    for scenario in scenarios:
        family_distribution[scenario.family] = family_distribution.get(scenario.family, 0) + 1

    send_budget = sum(
        1 for s in scenarios if s.expected_send_behavior in SEND_BEHAVIORS_COUNTING_AS_GMAIL_SEND
    )
    hold_count = sum(
        1 for s in scenarios if s.expected_send_behavior in NO_SEND_BEHAVIORS
    )

    return LiveQualityCampaignManifest(
        campaign_type=LIVE_QUALITY_CAMPAIGN_TYPE,
        scenario_count=len(scenarios),
        scenario_ids=[s.scenario_id for s in scenarios],
        family_distribution=family_distribution,
        send_budget=send_budget,
        hold_reject_no_reply_count=hold_count,
        manifest_hash=LIVE_QUALITY_CAMPAIGN_MANIFEST_HASH,
        scenarios=scenarios,
    )
