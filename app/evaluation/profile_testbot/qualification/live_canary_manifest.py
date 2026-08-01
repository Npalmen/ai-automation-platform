"""Locked 12-scenario live quality canary manifest (Todo J step 2)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from app.evaluation.profile_testbot.generator.deduplication import semantic_fingerprint
from app.evaluation.profile_testbot.generator.profile_generator import generate_semi_auto_campaign
from app.evaluation.profile_testbot.profile_contract import CustomerProfileSnapshot, load_customer_profile
from app.evaluation.profile_testbot.qualification.constants import (
    LIVE_QUALITY_CANARY_CAMPAIGN_TYPE,
    LIVE_QUALITY_CANARY_FAMILY_MIN,
    LIVE_QUALITY_CANARY_HOLD_MIN,
    LIVE_QUALITY_CANARY_SEND_MAX,
    LIVE_QUALITY_CANARY_TARGET,
    NO_SEND_BEHAVIORS,
    PTB_SEM_0024_SCENARIO_ID,
    SEND_BEHAVIORS_COUNTING_AS_GMAIL_SEND,
)
from app.evaluation.profile_testbot.quality_dataset import generate_quality_dataset
from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario

# Deterministic selection — do not edit ad hoc without re-baselining manifest hash.
LIVE_QUALITY_CANARY_SCENARIO_IDS: tuple[str, ...] = (
    "PTB-Q96-0000",  # complete_new_lead — send_after_approval
    "PTB-Q96-0003",  # complete_new_lead — continuation send
    "PTB-Q96-0006",  # incomplete_new_lead — draft_for_approval
    "PTB-Q96-0012",  # existing_customer_support — send_after_approval
    "PTB-Q96-0018",  # status_request — send_after_approval
    "PTB-Q96-0021",  # status_request — out_of_order send
    "PTB-Q96-0024",  # pricing_request — hold
    "PTB-Q96-0036",  # urgent_safety — reject
    "PTB-Q96-0060",  # spam_phishing_injection — adversarial reject
    "PTB-Q96-0063",  # spam_phishing_injection — duplicate adversarial reject
    "PTB-Q96-0090",  # thread_continuation_duplicate — duplicate hold
    "PTB-SEM-0024",  # adversarial semi-auto regression — hold/reject, 0 send
)

LIVE_QUALITY_CANARY_MANIFEST_HASH: str = hashlib.sha256(
    json.dumps(list(LIVE_QUALITY_CANARY_SCENARIO_IDS), separators=(",", ":")).encode("utf-8")
).hexdigest()


@dataclass
class LiveQualityCanaryManifest:
    campaign_type: str
    scenario_count: int
    scenario_ids: list[str]
    family_distribution: dict[str, int]
    send_budget: int
    hold_reject_no_reply_count: int
    has_thread_fixture: bool
    has_duplicate_fixture: bool
    has_adversarial_no_send: bool
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
            "has_thread_fixture": self.has_thread_fixture,
            "has_duplicate_fixture": self.has_duplicate_fixture,
            "has_adversarial_no_send": self.has_adversarial_no_send,
            "manifest_hash": self.manifest_hash,
        }


def _resolve_scenarios(
    profile: CustomerProfileSnapshot,
    *,
    seed: int,
) -> list[ProfileScenario]:
    quality_by_id = {s.scenario_id: s for s in generate_quality_dataset(profile, seed=seed)}
    semi_by_id = {s.scenario_id: s for s in generate_semi_auto_campaign(profile, seed=seed)}
    resolved: list[ProfileScenario] = []
    for scenario_id in LIVE_QUALITY_CANARY_SCENARIO_IDS:
        if scenario_id == PTB_SEM_0024_SCENARIO_ID:
            scenario = semi_by_id.get(scenario_id)
        else:
            scenario = quality_by_id.get(scenario_id)
        if scenario is None:
            raise ValueError(f"canary scenario {scenario_id!r} not found in dataset")
        resolved.append(scenario)
    return resolved


def validate_live_quality_canary_budget(scenarios: list[ProfileScenario]) -> list[str]:
    issues: list[str] = []
    if len(scenarios) != LIVE_QUALITY_CANARY_TARGET:
        issues.append(
            f"scenario count {len(scenarios)} != {LIVE_QUALITY_CANARY_TARGET}"
        )

    send_count = sum(
        1 for s in scenarios if s.expected_send_behavior in SEND_BEHAVIORS_COUNTING_AS_GMAIL_SEND
    )
    if send_count > LIVE_QUALITY_CANARY_SEND_MAX:
        issues.append(f"send budget {send_count} > {LIVE_QUALITY_CANARY_SEND_MAX}")

    no_send_count = sum(
        1 for s in scenarios if s.expected_send_behavior in NO_SEND_BEHAVIORS
    )
    if no_send_count < LIVE_QUALITY_CANARY_HOLD_MIN:
        issues.append(
            f"hold/reject/no_reply count {no_send_count} < {LIVE_QUALITY_CANARY_HOLD_MIN}"
        )

    families = {s.family for s in scenarios if s.scenario_id != PTB_SEM_0024_SCENARIO_ID}
    families.add("spam_phishing_injection")
    if len(families) < LIVE_QUALITY_CANARY_FAMILY_MIN:
        issues.append(f"family count {len(families)} < {LIVE_QUALITY_CANARY_FAMILY_MIN}")

    send_fingerprints = [
        semantic_fingerprint(s)
        for s in scenarios
        if s.expected_send_behavior in SEND_BEHAVIORS_COUNTING_AS_GMAIL_SEND
    ]
    if len(send_fingerprints) != len(set(send_fingerprints)):
        issues.append("two send scenarios are semantically identical")

    has_thread = any(
        (s.thread_setup or {}).get("thread_state") in {"continuation", "duplicate"}
        or s.family == "thread_continuation_duplicate"
        for s in scenarios
    )
    if not has_thread:
        issues.append("missing thread fixture")

    has_duplicate = any(
        (s.thread_setup or {}).get("duplicate_delivery")
        or (s.thread_setup or {}).get("thread_state") == "duplicate"
        for s in scenarios
    )
    if not has_duplicate:
        issues.append("missing duplicate/replay fixture")

    adversarial = [
        s for s in scenarios if s.scenario_id == PTB_SEM_0024_SCENARIO_ID
    ]
    if not adversarial:
        issues.append(f"missing {PTB_SEM_0024_SCENARIO_ID}")
    elif adversarial[0].expected_send_behavior in SEND_BEHAVIORS_COUNTING_AS_GMAIL_SEND:
        issues.append(f"{PTB_SEM_0024_SCENARIO_ID} must be no-send")

    return issues


def build_live_quality_canary_manifest(
    *,
    profile_id: str = "pilot-service-company-v1",
    seed: int = 0,
) -> LiveQualityCanaryManifest:
    profile = load_customer_profile(profile_id)
    scenarios = _resolve_scenarios(profile, seed=seed)
    issues = validate_live_quality_canary_budget(scenarios)
    if issues:
        raise ValueError("; ".join(issues))

    family_distribution: dict[str, int] = {}
    for scenario in scenarios:
        family = scenario.family or "semi_auto_adversarial"
        family_distribution[family] = family_distribution.get(family, 0) + 1

    send_budget = sum(
        1 for s in scenarios if s.expected_send_behavior in SEND_BEHAVIORS_COUNTING_AS_GMAIL_SEND
    )
    hold_count = sum(
        1 for s in scenarios if s.expected_send_behavior in NO_SEND_BEHAVIORS
    )

    return LiveQualityCanaryManifest(
        campaign_type=LIVE_QUALITY_CANARY_CAMPAIGN_TYPE,
        scenario_count=len(scenarios),
        scenario_ids=[s.scenario_id for s in scenarios],
        family_distribution=family_distribution,
        send_budget=send_budget,
        hold_reject_no_reply_count=hold_count,
        has_thread_fixture=True,
        has_duplicate_fixture=True,
        has_adversarial_no_send=True,
        manifest_hash=LIVE_QUALITY_CANARY_MANIFEST_HASH,
        scenarios=scenarios,
    )
