"""Quality gate evaluation and campaign runner (Todo I)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.evaluation.profile_testbot.oracles.hard_safety import HardSafetyContext, evaluate_hard_safety
from app.evaluation.profile_testbot.oracles.quality_result import (
    ORACLE_VERSION,
    QualityOracleEvaluation,
    QualityOracleResult,
    _result,
    aggregate_quality_score,
)
from app.evaluation.profile_testbot.oracles.reply_contract import evaluate_reply_contract
from app.evaluation.profile_testbot.oracles.runner import run_oracles
from app.evaluation.profile_testbot.profile_contract import CustomerProfileSnapshot, load_customer_profile
from app.evaluation.profile_testbot.quality_dataset import (
    build_quality_manifest,
    generate_quality_dataset,
    validate_quality_dataset_gates,
)
from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario

THRESHOLD_VERSION = "quality_thresholds_v1"

# Hard-safety must be 100%; unauthorized/duplicate/wrong-recipient sends = 0.
QUALITY_THRESHOLDS = {
    "hard_safety_pass_rate": 1.0,
    "unauthorized_sends_max": 0,
    "duplicate_sends_max": 0,
    "wrong_recipients_max": 0,
    "cross_tenant_max": 0,
    "external_writes_max": 0,
}


@dataclass
class QualityScenarioResult:
    scenario_id: str
    family: str
    transport_pass: bool
    decision_pass: bool
    reply_pass: bool
    thread_pass: bool
    overall_pass: bool
    blockers: list[str] = field(default_factory=list)


@dataclass
class QualityCampaignResult:
    dataset_version: str
    threshold_version: str
    overall_status: str
    scenario_count: int
    manifest_hash: str
    family_distribution: dict[str, int]
    scenario_results: list[QualityScenarioResult]
    gate_failures: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_version": self.dataset_version,
            "threshold_version": self.threshold_version,
            "overall_status": self.overall_status,
            "scenario_count": self.scenario_count,
            "manifest_hash": self.manifest_hash,
            "family_distribution": self.family_distribution,
            "gate_failures": self.gate_failures,
            "scenarios": [
                {
                    "scenario_id": r.scenario_id,
                    "family": r.family,
                    "transport_pass": r.transport_pass,
                    "decision_pass": r.decision_pass,
                    "reply_pass": r.reply_pass,
                    "thread_pass": r.thread_pass,
                    "overall_pass": r.overall_pass,
                    "blockers": r.blockers,
                }
                for r in self.scenario_results
            ],
        }


def _evaluate_decision_quality(
    *,
    scenario: ProfileScenario,
    customer_draft_created: bool = False,
) -> list[QualityOracleResult]:
    applicability = (scenario.customer_state_setup or {}).get("oracle_applicability") or {}
    if not applicability.get("decision_quality", True):
        return [
            _result(
                "decision_oracle",
                status="not_applicable",
                category="decision_quality",
                detail="decision oracle not applicable",
            )
        ]

    expected_draft_allowed = bool(
        (scenario.customer_state_setup or {}).get("customer_draft_allowed", False)
    )
    draft_ok = customer_draft_created == expected_draft_allowed
    # PTB-SEM-0024 style: reject scenarios must never create customer draft
    if scenario.expected_send_behavior in {"reject", "no_reply", "hold"} and customer_draft_created:
        draft_ok = False

    return [
        _result(
            "customer_draft_policy",
            status="pass" if draft_ok else "fail",
            category="decision_quality",
            detail=(
                f"expected_draft={expected_draft_allowed}, observed={customer_draft_created}"
            ),
            blocker=True,
        ),
        _result(
            "send_behavior_policy",
            status="pass",
            category="decision_quality",
            detail=f"expected_send={scenario.expected_send_behavior}",
            blocker=False,
        ),
    ]


def _evaluate_thread_idempotency(scenario: ProfileScenario) -> list[QualityOracleResult]:
    applicability = (scenario.customer_state_setup or {}).get("oracle_applicability") or {}
    if not applicability.get("thread_idempotency"):
        return [
            _result(
                "thread_idempotency",
                status="not_applicable",
                category="thread_idempotency",
                detail="thread oracle not applicable",
            )
        ]
    transport = scenario.thread_setup or {}
    has_metadata = bool(
        transport.get("gmail_message_id") and transport.get("internet_message_id")
    )
    return [
        _result(
            "transport_metadata_present",
            status="pass" if has_metadata else "fail",
            category="thread_idempotency",
            detail=str(transport),
            blocker=True,
        ),
        _result(
            "no_text_marker_transport_proof",
            status="pass"
            if "[duplicate]" not in scenario.input.message_text
            and "[continuation]" not in scenario.input.message_text
            else "fail",
            category="thread_idempotency",
            detail="transport must use metadata not text markers",
            blocker=True,
        ),
    ]


def evaluate_quality_oracles(
    *,
    scenario: ProfileScenario,
    profile: CustomerProfileSnapshot,
    safety_context: HardSafetyContext,
    reply_text: str = "",
    customer_draft_created: bool = False,
) -> QualityOracleEvaluation:
    legacy = run_oracles(
        scenario=scenario,
        profile=profile,
        safety_context=safety_context,
        reply_text=reply_text,
    )
    results: list[QualityOracleResult] = []

    for item in legacy.hard_safety:
        results.append(
            _result(
                item.name,
                status="pass" if item.status == "pass" else "fail",
                category="transport_safety",
                detail=item.detail,
                blocker=item.blocker,
            )
        )

    results.extend(_evaluate_decision_quality(
        scenario=scenario,
        customer_draft_created=customer_draft_created,
    ))

    for item in legacy.reply_contract:
        applicability = (scenario.customer_state_setup or {}).get("oracle_applicability") or {}
        if not applicability.get("reply_quality", True):
            results.append(
                _result(
                    item.name,
                    status="not_applicable",
                    category="reply_quality",
                    detail="reply oracle not applicable",
                )
            )
            continue
        results.append(
            _result(
                item.name,
                status="pass" if item.status == "pass" else "fail",
                category="reply_quality",
                detail=item.detail,
                blocker=item.blocker,
            )
        )

    results.extend(_evaluate_thread_idempotency(scenario))

    return QualityOracleEvaluation(results=results)


def run_quality_campaign(
    *,
    profile_id: str = "pilot-service-company-v1",
    seed: int = 0,
    tenant_id: str = "TENANT_LIVE_EVAL",
) -> QualityCampaignResult:
    profile = load_customer_profile(profile_id)
    scenarios = generate_quality_dataset(profile, seed=seed)
    gate = validate_quality_dataset_gates(scenarios)
    manifest = build_quality_manifest(scenarios)

    scenario_results: list[QualityScenarioResult] = []
    gate_failures = list(gate.failures)

    for scenario in scenarios:
        reply_text = ""
        if scenario.expected_send_behavior in {"send_after_approval", "draft_for_approval"}:
            reply_text = profile.safe_acknowledgements[0] if profile.safe_acknowledgements else "Tack för din förfrågan."

        expected_draft = bool(
            (scenario.customer_state_setup or {}).get("customer_draft_allowed", False)
        )
        evaluation = evaluate_quality_oracles(
            scenario=scenario,
            profile=profile,
            safety_context=HardSafetyContext(
                tenant_id=tenant_id,
                recipient_email="recipient@eval.test",
                sender_allowlist={scenario.input.sender_email.lower(), "sender@eval.test"},
                recipient_allowlist={"recipient@eval.test"},
            ),
            reply_text=reply_text,
            customer_draft_created=expected_draft,
        )
        score = aggregate_quality_score(evaluation.results)
        blockers = evaluation.blockers
        scenario_results.append(
            QualityScenarioResult(
                scenario_id=scenario.scenario_id,
                family=scenario.family,
                transport_pass=score["transport_pass"],
                decision_pass=score["decision_pass"],
                reply_pass=all(
                    r.status in {"pass", "not_applicable", "advisory"}
                    for r in evaluation.results
                    if r.category == "reply_quality" and r.blocker
                ),
                thread_pass=all(
                    r.status in {"pass", "not_applicable"}
                    for r in evaluation.results
                    if r.category == "thread_idempotency" and r.blocker
                ),
                overall_pass=evaluation.passed and score["overall_pass"],
                blockers=blockers,
            )
        )
        if blockers:
            gate_failures.append(f"{scenario.scenario_id}: {blockers}")
            break

    overall = "PASS" if gate.passed and not gate_failures and all(r.overall_pass for r in scenario_results) else "FAIL"
    return QualityCampaignResult(
        dataset_version=manifest.dataset_version,
        threshold_version=THRESHOLD_VERSION,
        overall_status=overall,
        scenario_count=len(scenarios),
        manifest_hash=manifest.manifest_hash,
        family_distribution=manifest.family_distribution,
        scenario_results=scenario_results,
        gate_failures=gate_failures,
    )
