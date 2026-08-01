"""Hermetic quality qualification runner (Gate Q5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.evaluation.profile_testbot.generator.profile_generator import generate_semi_auto_campaign
from app.evaluation.profile_testbot.profile_contract import load_customer_profile
from app.evaluation.profile_testbot.qualification.constants import PTB_SEM_0024_SCENARIO_ID
from app.evaluation.profile_testbot.quality_dataset import QUALITY_SCENARIO_TARGET
from app.evaluation.profile_testbot.quality_gates import (
    QUALITY_THRESHOLDS,
    THRESHOLD_VERSION,
    run_quality_campaign,
)

HERMETIC_QUALIFICATION_CONTRACT_VERSION = "inbox_quality_hermetic_v1"


@dataclass
class HermeticQualityQualificationResult:
    overall_status: str
    dataset_version: str
    threshold_version: str
    scenario_count: int
    manifest_hash: str
    hard_safety_pass_rate: float
    ptb_sem_0024_pass: bool
    gate_failures: list[str] = field(default_factory=list)
    ptb_sem_0024_detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_status": self.overall_status,
            "dataset_version": self.dataset_version,
            "threshold_version": self.threshold_version,
            "scenario_count": self.scenario_count,
            "manifest_hash": self.manifest_hash,
            "hard_safety_pass_rate": self.hard_safety_pass_rate,
            "ptb_sem_0024_pass": self.ptb_sem_0024_pass,
            "gate_failures": self.gate_failures,
            "ptb_sem_0024_detail": self.ptb_sem_0024_detail,
            "thresholds": QUALITY_THRESHOLDS,
            "contract_version": HERMETIC_QUALIFICATION_CONTRACT_VERSION,
        }


def _validate_ptb_sem_0024_blocking(*, profile_id: str, seed: int = 0) -> tuple[bool, str]:
    profile = load_customer_profile(profile_id)
    scenarios = generate_semi_auto_campaign(profile, seed=seed)
    phishing = [s for s in scenarios if s.scenario_id == PTB_SEM_0024_SCENARIO_ID]
    if not phishing:
        return False, f"{PTB_SEM_0024_SCENARIO_ID} missing from semi-auto campaign"
    scenario = phishing[0]
    if scenario.expected_send_behavior not in {"hold", "reject", "no_reply"}:
        return False, f"{PTB_SEM_0024_SCENARIO_ID} must be no-send, got {scenario.expected_send_behavior}"
    if scenario.intent != "spam_phishing":
        return False, f"{PTB_SEM_0024_SCENARIO_ID} intent must be spam_phishing"
    setup = scenario.customer_state_setup or {}
    if setup.get("customer_draft_allowed"):
        return False, f"{PTB_SEM_0024_SCENARIO_ID} customer draft must be forbidden"
    return True, "adversarial no-send contract satisfied"


def run_hermetic_quality_qualification(
    *,
    profile_id: str = "pilot-service-company-v1",
    seed: int = 0,
    tenant_id: str = "TENANT_LIVE_EVAL",
) -> HermeticQualityQualificationResult:
    campaign = run_quality_campaign(profile_id=profile_id, seed=seed, tenant_id=tenant_id)
    failures = list(campaign.gate_failures)

    if campaign.scenario_count != QUALITY_SCENARIO_TARGET:
        failures.append(
            f"scenario_count {campaign.scenario_count} != {QUALITY_SCENARIO_TARGET}"
        )
    if campaign.overall_status != "PASS":
        failures.append(f"quality campaign status {campaign.overall_status}")

    blocked = [r for r in campaign.scenario_results if not r.overall_pass]
    if blocked:
        failures.append(f"{len(blocked)} scenario(s) failed quality oracles")

    ptb_ok, ptb_detail = _validate_ptb_sem_0024_blocking(
        profile_id="niklas-demo-live-eval-v1",
        seed=seed,
    )
    if not ptb_ok:
        failures.append(ptb_detail)

    hard_safety_rate = 1.0 if campaign.overall_status == "PASS" and not blocked else 0.0
    overall = "PASS" if not failures else "FAIL"
    return HermeticQualityQualificationResult(
        overall_status=overall,
        dataset_version=campaign.dataset_version,
        threshold_version=THRESHOLD_VERSION,
        scenario_count=campaign.scenario_count,
        manifest_hash=campaign.manifest_hash,
        hard_safety_pass_rate=hard_safety_rate,
        ptb_sem_0024_pass=ptb_ok,
        gate_failures=failures,
        ptb_sem_0024_detail=ptb_detail,
    )
