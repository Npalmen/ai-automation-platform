"""Locked R4 live coworker-quality scenario registry."""

from __future__ import annotations

from collections import Counter
from typing import Any

from app.evaluation.profile_testbot.coworker_reply_dataset import generate_coworker_reply_dataset
from app.evaluation.profile_testbot.generator.profile_generator import generate_semi_auto_campaign
from app.evaluation.profile_testbot.profile_contract import CustomerProfileSnapshot
from app.evaluation.profile_testbot.qualification.constants import (
    NO_SEND_BEHAVIORS,
    SEND_BEHAVIORS_COUNTING_AS_GMAIL_SEND,
)
from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario

R4_LIVE_QUALITY_CAMPAIGN_TYPE = "coworker_r4_live_quality_campaign"
R4_EXECUTION_MODE = "r4_reviewed_live_candidate"
R4_AI_MODE = "live_llm"
R4_PROFILE_ID = "niklas-demo-live-eval-v1"
R4_TENANT_ID = "TENANT_LIVE_EVAL"

R4_SCENARIO_TARGET = 36
R4_SEND_MAX = 20
R4_NO_SEND_MIN = 16
R4_FAMILY_MIN = 15
R4_MULTI_TURN_MIN = 10
R4_NO_NAME_PHONE_MIN = 10
R4_SERVICE_PREQUAL_MIN = 10

# Deterministic selection — do not edit without re-baselining manifest hash.
R4_SEND_SCENARIO_IDS: tuple[str, ...] = (
    "PTB-DCQ-0000",
    "PTB-DCQ-0002",
    "PTB-DCQ-0005",
    "PTB-DCQ-0007",
    "PTB-DCQ-0013",
    "PTB-DCQ-0016",
    "PTB-DCQ-0018",
    "PTB-DCQ-0022",
    "PTB-DCQ-0033",
    "PTB-DCQ-0040",
    "PTB-DCQ-0049",
    "PTB-DCQ-0056",
    "PTB-DCQ-0057",
    "PTB-DCQ-0065",
    "PTB-DCQ-0072",
    "PTB-DCQ-0080",
    "PTB-DCQ-0088",
    "PTB-DCQ-0098",
    "PTB-DCQ-0106",
    "PTB-DCQ-0112",
)

R4_NO_SEND_SCENARIO_IDS: tuple[str, ...] = (
    "PTB-DCQ-0024",
    "PTB-DCQ-0029",
    "PTB-DCQ-0032",
    "PTB-DCQ-0037",
    "PTB-DCQ-0048",
    "PTB-DCQ-0053",
    "PTB-SEM-0020",
    "PTB-SEM-0021",
    "PTB-SEM-0023",
    "PTB-SEM-0024",
    "PTB-SEM-0025",
    "PTB-SEM-0026",
    "PTB-SEM-0027",
    "PTB-SEM-0028",
    "PTB-SEM-0032",
    "PTB-SEM-0038",
)

R4_SCENARIO_IDS: tuple[str, ...] = R4_SEND_SCENARIO_IDS + R4_NO_SEND_SCENARIO_IDS

R4_SERVICE_PREQUAL_IDS: frozenset[str] = frozenset(
    {
        "PTB-DCQ-0000",
        "PTB-DCQ-0005",
        "PTB-DCQ-0016",
        "PTB-DCQ-0018",
        "PTB-DCQ-0033",
        "PTB-DCQ-0040",
        "PTB-DCQ-0049",
        "PTB-DCQ-0088",
        "PTB-DCQ-0098",
        "PTB-DCQ-0106",
    }
)

# R3-only override must never be applied to R4 complaint/risk scenarios.
R4_EXCLUDED_R3_HOLD_OVERRIDE_SCENARIOS: frozenset[str] = frozenset({"PTB-DCQ-0088"})

R3_QUALIFYING_SHA = "5e9b1839d9a4ac5ac6aef1795d88a2eff5f06517"
R3_QUALIFYING_CAMPAIGN_ID = "54f2f10b-4f09-4ae4-9950-39bd2efb1214"
R3_QUALIFYING_MANIFEST_HASH = (
    "dd87f9ce7676fb60b30e6a1651ae7db62aaafe04d7f2624ac80a5e1bcff16741"
)


def is_multi_turn(scenario: ProfileScenario) -> bool:
    setup = scenario.customer_state_setup or {}
    thread = scenario.thread_setup or {}
    return setup.get("thread_state") == "continuation" or thread.get("thread_state") == "continuation"


def is_no_name_phone(scenario: ProfileScenario) -> bool:
    setup = scenario.customer_state_setup or {}
    return bool(setup.get("forbid_name_request")) and bool(setup.get("forbid_phone_request"))


def is_service_prequalification(scenario: ProfileScenario) -> bool:
    return scenario.scenario_id in R4_SERVICE_PREQUAL_IDS


def scenario_tags(scenario: ProfileScenario) -> list[str]:
    tags: list[str] = []
    if scenario.scenario_id in R4_SEND_SCENARIO_IDS:
        tags.append("planned_send")
    if scenario.scenario_id in R4_NO_SEND_SCENARIO_IDS:
        tags.append("planned_no_send")
    if is_multi_turn(scenario):
        tags.append("multi_turn")
    if is_no_name_phone(scenario):
        tags.append("no_name_phone")
    if is_service_prequalification(scenario):
        tags.append("service_specific_prequalification")
    language = (scenario.input.language if scenario.input else "sv") or "sv"
    if str(language).lower().startswith("en"):
        tags.append("english")
    if scenario.expected_send_behavior == "draft_for_approval":
        tags.append("hold_draft")
    if scenario.expected_send_behavior in {"reject", "no_reply"}:
        tags.append("hard_no_send")
    if scenario.family in {"spam"} or "injection" in (scenario.family or ""):
        tags.append("threat")
    if scenario.family == "complaint_warranty":
        tags.append("complaint")
    if scenario.scenario_id in R4_EXCLUDED_R3_HOLD_OVERRIDE_SCENARIOS:
        tags.append("r3_hold_override_excluded")
    return tags


def resolve_r4_scenarios(
    profile: CustomerProfileSnapshot,
    *,
    seed: int = 42,
) -> list[ProfileScenario]:
    quality_by_id = {s.scenario_id: s for s in generate_coworker_reply_dataset(profile, seed=seed)}
    semi_by_id = {s.scenario_id: s for s in generate_semi_auto_campaign(profile, seed=seed)}
    resolved: list[ProfileScenario] = []
    for scenario_id in R4_SCENARIO_IDS:
        scenario = quality_by_id.get(scenario_id) or semi_by_id.get(scenario_id)
        if scenario is None:
            raise ValueError(f"R4 scenario {scenario_id!r} not found in dataset")
        resolved.append(scenario)
    return resolved


def validate_r4_scenario_coverage(scenarios: list[ProfileScenario]) -> list[str]:
    issues: list[str] = []
    if len(scenarios) != R4_SCENARIO_TARGET:
        issues.append(f"scenario count {len(scenarios)} != {R4_SCENARIO_TARGET}")
    if [s.scenario_id for s in scenarios] != list(R4_SCENARIO_IDS):
        issues.append("scenario order/ids do not match locked R4 registry")

    send_count = sum(
        1 for s in scenarios if s.expected_send_behavior in SEND_BEHAVIORS_COUNTING_AS_GMAIL_SEND
    )
    no_send_count = sum(1 for s in scenarios if s.expected_send_behavior in NO_SEND_BEHAVIORS)
    if send_count > R4_SEND_MAX:
        issues.append(f"send count {send_count} > {R4_SEND_MAX}")
    if send_count != len(R4_SEND_SCENARIO_IDS):
        issues.append(f"send count {send_count} != locked {len(R4_SEND_SCENARIO_IDS)}")
    if no_send_count < R4_NO_SEND_MIN:
        issues.append(f"no-send count {no_send_count} < {R4_NO_SEND_MIN}")

    families = Counter(s.family for s in scenarios)
    coworker_families = {
        f
        for f in families
        if f
        in {
            "solar_installation_new",
            "solar_installation_followup",
            "battery_installation_new",
            "battery_installation_known_facts",
            "ev_charger_new",
            "ev_charger_known_facts",
            "solar_battery_combined",
            "existing_support_symptom",
            "existing_support_followup",
            "job_status_request",
            "job_status_no_contact",
            "complaint_warranty",
            "general_consultation",
            "missing_attachment",
            "multi_turn_continuation",
        }
    }
    if len(coworker_families) < R4_FAMILY_MIN:
        issues.append(f"coworker family count {len(coworker_families)} < {R4_FAMILY_MIN}")

    multi_turn = sum(1 for s in scenarios if is_multi_turn(s))
    if multi_turn < R4_MULTI_TURN_MIN:
        issues.append(f"multi-turn count {multi_turn} < {R4_MULTI_TURN_MIN}")

    no_name_phone = sum(1 for s in scenarios if is_no_name_phone(s))
    if no_name_phone < R4_NO_NAME_PHONE_MIN:
        issues.append(f"no-name/phone count {no_name_phone} < {R4_NO_NAME_PHONE_MIN}")

    service_prequal = sum(1 for s in scenarios if is_service_prequalification(s))
    if service_prequal < R4_SERVICE_PREQUAL_MIN:
        issues.append(
            f"service-specific prequalification count {service_prequal} < {R4_SERVICE_PREQUAL_MIN}"
        )

    # No family may dominate (soft: >25% of 36 = 9).
    for family, count in families.items():
        if count > 9:
            issues.append(f"family {family} dominates with {count} scenarios")

    return issues


def coverage_summary(scenarios: list[ProfileScenario]) -> dict[str, Any]:
    return {
        "scenario_count": len(scenarios),
        "family_count": len({s.family for s in scenarios}),
        "coworker_family_count": len(
            {
                s.family
                for s in scenarios
                if s.scenario_id.startswith("PTB-DCQ-")
            }
        ),
        "planned_sends": sum(
            1
            for s in scenarios
            if s.expected_send_behavior in SEND_BEHAVIORS_COUNTING_AS_GMAIL_SEND
        ),
        "planned_no_send": sum(
            1 for s in scenarios if s.expected_send_behavior in NO_SEND_BEHAVIORS
        ),
        "multi_turn_count": sum(1 for s in scenarios if is_multi_turn(s)),
        "no_name_phone_count": sum(1 for s in scenarios if is_no_name_phone(s)),
        "service_prequalification_count": sum(
            1 for s in scenarios if is_service_prequalification(s)
        ),
        "family_distribution": dict(Counter(s.family for s in scenarios)),
    }
