"""Locked 15-scenario digital coworker live canary manifest (Gate R3)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from app.evaluation.profile_testbot.coworker_reply_dataset import generate_coworker_reply_dataset
from app.evaluation.profile_testbot.generator.deduplication import semantic_fingerprint
from app.evaluation.profile_testbot.generator.profile_generator import generate_semi_auto_campaign
from app.evaluation.profile_testbot.profile_contract import CustomerProfileSnapshot, load_customer_profile
from app.evaluation.profile_testbot.qualification.constants import (
    NO_SEND_BEHAVIORS,
    PTB_SEM_0024_SCENARIO_ID,
    SEND_BEHAVIORS_COUNTING_AS_GMAIL_SEND,
)
from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario

COWORKER_LIVE_CANARY_CAMPAIGN_TYPE = "coworker-reply-live-canary"
COWORKER_LIVE_CANARY_TARGET = 15
COWORKER_LIVE_CANARY_SEND_MAX = 8
COWORKER_LIVE_CANARY_HOLD_MIN = 5
COWORKER_LIVE_CANARY_FAMILY_MIN = 10
COWORKER_LIVE_CANARY_MULTI_TURN_MIN = 4

# Deterministic selection — do not edit ad hoc without re-baselining manifest hash.
COWORKER_LIVE_CANARY_SCENARIO_IDS: tuple[str, ...] = (
    "PTB-DCQ-0000",  # solar_installation_new — send_after_approval
    "PTB-DCQ-0022",  # battery_installation_new — continuation send
    "PTB-DCQ-0033",  # ev_charger_new — continuation send
    "PTB-DCQ-0049",  # solar_battery_combined — send_after_approval
    "PTB-DCQ-0056",  # existing_support_symptom — send_after_approval
    "PTB-DCQ-0072",  # job_status_request — continuation send
    "PTB-DCQ-0080",  # job_status_no_contact — continuation send
    "PTB-DCQ-0088",  # complaint_warranty — send_after_approval
    "PTB-DCQ-0032",  # ev_charger_new — draft_for_approval
    "PTB-DCQ-0048",  # solar_battery_combined — draft_for_approval
    "PTB-DCQ-0024",  # battery_installation_known_facts — draft_for_approval
    "PTB-DCQ-0037",  # ev_charger_new — continuation draft
    "PTB-DCQ-0029",  # battery_installation_known_facts — continuation draft
    "PTB-DCQ-0053",  # solar_battery_combined — draft_for_approval
    "PTB-SEM-0024",  # adversarial spam reject — 0 send
)

COWORKER_LIVE_CANARY_MANIFEST_HASH: str = hashlib.sha256(
    json.dumps(list(COWORKER_LIVE_CANARY_SCENARIO_IDS), separators=(",", ":")).encode("utf-8")
).hexdigest()


@dataclass
class CoworkerLiveCanaryManifest:
    campaign_type: str
    scenario_count: int
    scenario_ids: list[str]
    family_distribution: dict[str, int]
    send_budget: int
    hold_reject_no_reply_count: int
    multi_turn_count: int
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
            "multi_turn_count": self.multi_turn_count,
            "manifest_hash": self.manifest_hash,
        }


def _is_multi_turn(scenario: ProfileScenario) -> bool:
    setup = scenario.customer_state_setup or {}
    thread = scenario.thread_setup or {}
    return setup.get("thread_state") == "continuation" or thread.get("thread_state") == "continuation"


def _resolve_scenarios(
    profile: CustomerProfileSnapshot,
    *,
    seed: int,
) -> list[ProfileScenario]:
    quality_by_id = {s.scenario_id: s for s in generate_coworker_reply_dataset(profile, seed=seed)}
    semi_by_id = {s.scenario_id: s for s in generate_semi_auto_campaign(profile, seed=seed)}
    resolved: list[ProfileScenario] = []
    for scenario_id in COWORKER_LIVE_CANARY_SCENARIO_IDS:
        if scenario_id == PTB_SEM_0024_SCENARIO_ID:
            scenario = semi_by_id.get(scenario_id)
        else:
            scenario = quality_by_id.get(scenario_id)
        if scenario is None:
            raise ValueError(f"canary scenario {scenario_id!r} not found in dataset")
        resolved.append(scenario)
    return resolved


def validate_coworker_live_canary_budget(scenarios: list[ProfileScenario]) -> list[str]:
    issues: list[str] = []
    if len(scenarios) != COWORKER_LIVE_CANARY_TARGET:
        issues.append(f"scenario count {len(scenarios)} != {COWORKER_LIVE_CANARY_TARGET}")

    send_count = sum(
        1 for s in scenarios if s.expected_send_behavior in SEND_BEHAVIORS_COUNTING_AS_GMAIL_SEND
    )
    if send_count > COWORKER_LIVE_CANARY_SEND_MAX:
        issues.append(f"send budget {send_count} > {COWORKER_LIVE_CANARY_SEND_MAX}")

    no_send_count = sum(
        1 for s in scenarios if s.expected_send_behavior in NO_SEND_BEHAVIORS
    )
    if no_send_count < COWORKER_LIVE_CANARY_HOLD_MIN:
        issues.append(
            f"hold/reject/no_reply count {no_send_count} < {COWORKER_LIVE_CANARY_HOLD_MIN}"
        )

    families = {s.family or "semi_auto_adversarial" for s in scenarios}
    if len(families) < COWORKER_LIVE_CANARY_FAMILY_MIN:
        issues.append(f"family count {len(families)} < {COWORKER_LIVE_CANARY_FAMILY_MIN}")

    multi_turn_count = sum(1 for s in scenarios if _is_multi_turn(s))
    if multi_turn_count < COWORKER_LIVE_CANARY_MULTI_TURN_MIN:
        issues.append(
            f"multi-turn count {multi_turn_count} < {COWORKER_LIVE_CANARY_MULTI_TURN_MIN}"
        )

    send_fingerprints = [
        semantic_fingerprint(s)
        for s in scenarios
        if s.expected_send_behavior in SEND_BEHAVIORS_COUNTING_AS_GMAIL_SEND
    ]
    if len(send_fingerprints) != len(set(send_fingerprints)):
        issues.append("two send scenarios are semantically identical")

    adversarial = [s for s in scenarios if s.scenario_id == PTB_SEM_0024_SCENARIO_ID]
    if not adversarial:
        issues.append(f"missing {PTB_SEM_0024_SCENARIO_ID}")
    elif adversarial[0].expected_send_behavior in SEND_BEHAVIORS_COUNTING_AS_GMAIL_SEND:
        issues.append(f"{PTB_SEM_0024_SCENARIO_ID} must be no-send")

    return issues


def build_coworker_live_canary_manifest(
    *,
    profile_id: str = "niklas-demo-live-eval-v1",
    seed: int = 0,
) -> CoworkerLiveCanaryManifest:
    profile = load_customer_profile(profile_id)
    scenarios = _resolve_scenarios(profile, seed=seed)
    issues = validate_coworker_live_canary_budget(scenarios)
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

    return CoworkerLiveCanaryManifest(
        campaign_type=COWORKER_LIVE_CANARY_CAMPAIGN_TYPE,
        scenario_count=len(scenarios),
        scenario_ids=[s.scenario_id for s in scenarios],
        family_distribution=family_distribution,
        send_budget=send_budget,
        hold_reject_no_reply_count=hold_count,
        multi_turn_count=sum(1 for s in scenarios if _is_multi_turn(s)),
        manifest_hash=COWORKER_LIVE_CANARY_MANIFEST_HASH,
        scenarios=scenarios,
    )
