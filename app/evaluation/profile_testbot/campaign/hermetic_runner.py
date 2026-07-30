"""Hermetic profile testbot campaign runner."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.evaluation.profile_testbot.generator.coverage_matrix import required_coverage_keys
from app.evaluation.profile_testbot.generator.deduplication import find_semantic_duplicates
from app.evaluation.profile_testbot.generator.profile_generator import generate_hermetic_campaign
from app.evaluation.profile_testbot.oracles.hard_safety import HardSafetyContext
from app.evaluation.profile_testbot.oracles.runner import run_oracles
from app.evaluation.profile_testbot.profile_contract import CustomerProfileSnapshot, load_customer_profile
from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario, validate_profile_scenario


@dataclass
class HermeticScenarioResult:
    scenario_id: str
    status: str
    blockers: list[str] = field(default_factory=list)


@dataclass
class HermeticCampaignResult:
    campaign_type: str
    overall_status: str
    scenario_count: int
    coverage_keys_present: int
    coverage_keys_required: int
    semantic_duplicates: list[str]
    scenario_results: list[HermeticScenarioResult]
    safety_violations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "campaign_type": self.campaign_type,
            "overall_status": self.overall_status,
            "scenario_count": self.scenario_count,
            "coverage_keys_present": self.coverage_keys_present,
            "coverage_keys_required": self.coverage_keys_required,
            "semantic_duplicates": self.semantic_duplicates,
            "safety_violations": self.safety_violations,
            "scenarios": [
                {
                    "scenario_id": r.scenario_id,
                    "status": r.status,
                    "blockers": r.blockers,
                }
                for r in self.scenario_results
            ],
        }


def _coverage_keys_present(scenarios: list[ProfileScenario]) -> set[str]:
    from app.evaluation.profile_testbot.generator.coverage_matrix import CoverageCell

    keys: set[str] = set()
    for scenario in scenarios:
        keys.add(
            CoverageCell(
                intent=scenario.intent,
                risk_class=scenario.risk_class,
                expected_send_behavior=scenario.expected_send_behavior,
                customer_state=str(scenario.customer_state_setup.get("state") or "new"),
                thread_state=str(scenario.thread_setup.get("state") or "new_thread"),
                language=scenario.input.language,
                ambiguity=str(scenario.customer_state_setup.get("ambiguity") or "clear"),
            ).key()
        )
    return keys


def run_hermetic_profile_campaign(
    *,
    profile_id: str = "pilot-service-company-v1",
    seed: int = 0,
    tenant_id: str = "TENANT_LIVE_EVAL",
    sender_allowlist: set[str] | None = None,
    recipient_allowlist: set[str] | None = None,
) -> HermeticCampaignResult:
    profile: CustomerProfileSnapshot = load_customer_profile(profile_id)
    scenarios = generate_hermetic_campaign(profile, seed=seed)
    senders = sender_allowlist or {"sender@eval.test"}
    recipients = recipient_allowlist or {"recipient@eval.test"}
    duplicates = find_semantic_duplicates(scenarios)
    required = required_coverage_keys()
    present = _coverage_keys_present(scenarios)
    results: list[HermeticScenarioResult] = []
    safety_violations: list[str] = []
    for scenario in scenarios:
        validation = validate_profile_scenario(scenario)
        if validation:
            results.append(HermeticScenarioResult(scenario.scenario_id, "FAIL", validation))
            safety_violations.extend(validation)
            break
        reply_text = ""
        if scenario.expected_send_behavior == "send_after_approval":
            reply_text = profile.safe_acknowledgements[0]
        evaluation = run_oracles(
            scenario=scenario,
            profile=profile,
            safety_context=HardSafetyContext(
                tenant_id=tenant_id,
                recipient_email=next(iter(recipients)),
                sender_allowlist=senders | {scenario.input.sender_email.lower()},
                recipient_allowlist=recipients,
                reply_text=reply_text,
            ),
            reply_text=reply_text,
        )
        if not evaluation.passed:
            results.append(HermeticScenarioResult(scenario.scenario_id, "FAIL", evaluation.blockers))
            safety_violations.extend(evaluation.blockers)
            break
        results.append(HermeticScenarioResult(scenario.scenario_id, "PASS", []))
    coverage_ok = required.issubset(present)
    status = "PASS"
    if duplicates or not coverage_ok or len(scenarios) < 120 or any(r.status != "PASS" for r in results):
        status = "FAIL"
    return HermeticCampaignResult(
        campaign_type="profile-hermetic",
        overall_status=status,
        scenario_count=len(scenarios),
        coverage_keys_present=len(present),
        coverage_keys_required=len(required),
        semantic_duplicates=duplicates,
        scenario_results=results,
        safety_violations=safety_violations,
    )
