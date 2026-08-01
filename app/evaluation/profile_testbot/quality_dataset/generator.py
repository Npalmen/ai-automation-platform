"""Curated quality dataset generator and gates (Todo H)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from app.evaluation.profile_testbot.generator.deduplication import find_semantic_duplicates, semantic_fingerprint
from app.evaluation.profile_testbot.generator.profile_generator import _build_scenario_from_cell
from app.evaluation.profile_testbot.profile_contract import CustomerProfileSnapshot
from app.evaluation.profile_testbot.quality_dataset.constants import (
    MAX_FAMILY_SHARE,
    QUALITY_DATASET_VERSION,
    QUALITY_FAMILY_TARGET,
    QUALITY_SCENARIO_TARGET,
)
from app.evaluation.profile_testbot.quality_dataset.families import all_family_cells
from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario, ProfileScenarioInput, validate_profile_scenario


@dataclass
class QualityDatasetManifest:
    dataset_version: str
    scenario_count: int
    family_count: int
    family_distribution: dict[str, int]
    manifest_hash: str
    scenario_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_version": self.dataset_version,
            "scenario_count": self.scenario_count,
            "family_count": self.family_count,
            "family_distribution": self.family_distribution,
            "manifest_hash": self.manifest_hash,
            "scenario_ids": self.scenario_ids,
        }


@dataclass
class QualityDatasetGateResult:
    passed: bool
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _quality_expectations(family: str, cell) -> dict[str, Any]:
    """Attach plan-required quality expectation metadata to scenario."""
    customer_draft_allowed = cell.expected_send_behavior in {
        "send_after_approval",
        "draft_for_approval",
        "automatic_safe_send",
    }
    return {
        "quality_family": family,
        "expected_threat_class": (
            "phishing" if family == "spam_phishing_injection" and cell.ambiguity == "adversarial"
            else "trusted_business_content"
        ),
        "expected_business_intent": cell.intent,
        "customer_draft_allowed": customer_draft_allowed,
        "oracle_applicability": {
            "transport_safety": True,
            "decision_quality": True,
            "reply_quality": customer_draft_allowed,
            "thread_idempotency": family == "thread_continuation_duplicate",
        },
        "rationale": f"Curated {family} scenario for quality dataset v1",
    }


def generate_quality_dataset(
    profile: CustomerProfileSnapshot,
    *,
    seed: int = 0,
) -> list[ProfileScenario]:
    scenarios: list[ProfileScenario] = []
    index = 0
    for family, cell in all_family_cells():
        scenario_id = f"PTB-Q96-{index:04d}"
        base = _build_scenario_from_cell(
            profile=profile,
            cell=cell,
            seed=seed + index,
            campaign_phase="quality",
            scenario_id=scenario_id,
        )
        cleaned_input = ProfileScenarioInput(
            subject=base.input.subject,
            message_text=(
                base.input.message_text
                .replace("[continuation]", "")
                .replace("[duplicate]", "")
                .replace("[out_of_order]", "")
                .strip()
            ),
            sender_name=base.input.sender_name,
            sender_email=base.input.sender_email,
            language=base.input.language,
            attachment_metadata=base.input.attachment_metadata,
        )
        expectations = _quality_expectations(family, cell)
        transport = {
            "gmail_message_id": f"msg-{scenario_id.lower()}",
            "internet_message_id": f"<{scenario_id.lower()}@eval.test>",
            "gmail_thread_id": f"thread-{family}-{index}",
            "thread_state": cell.thread_state,
            "duplicate_delivery": cell.thread_state == "duplicate",
            "replay_after_restart": cell.thread_state in {"duplicate", "out_of_order"},
        }
        draft = ProfileScenario(
            scenario_id=base.scenario_id,
            profile_id=base.profile_id,
            profile_snapshot_hash=base.profile_snapshot_hash,
            family=family,
            intent=base.intent,
            risk_class=base.risk_class,
            input=cleaned_input,
            expected_classification=base.expected_classification,
            expected_route=base.expected_route,
            expected_authorization=base.expected_authorization,
            expected_send_behavior=base.expected_send_behavior,
            required_reply_facts=base.required_reply_facts,
            optional_reply_facts=base.optional_reply_facts,
            forbidden_reply_claims=base.forbidden_reply_claims,
            required_questions=base.required_questions,
            customer_state_setup={
                **base.customer_state_setup,
                **expectations,
            },
            thread_setup={**base.thread_setup, **transport},
            provider_setup=base.provider_setup,
            mutation_types=base.mutation_types,
            generator_provenance={
                **base.generator_provenance,
                "quality_dataset_version": QUALITY_DATASET_VERSION,
                "quality_family": family,
            },
            oracle_version=base.oracle_version,
            semantic_hash="",
            mode=base.mode,
            campaign_phase="quality",
        )
        semantic = semantic_fingerprint(draft)
        scenarios.append(
            ProfileScenario(
                scenario_id=draft.scenario_id,
                profile_id=draft.profile_id,
                profile_snapshot_hash=draft.profile_snapshot_hash,
                family=draft.family,
                intent=draft.intent,
                risk_class=draft.risk_class,
                input=draft.input,
                expected_classification=draft.expected_classification,
                expected_route=draft.expected_route,
                expected_authorization=draft.expected_authorization,
                expected_send_behavior=draft.expected_send_behavior,
                required_reply_facts=draft.required_reply_facts,
                optional_reply_facts=draft.optional_reply_facts,
                forbidden_reply_claims=draft.forbidden_reply_claims,
                required_questions=draft.required_questions,
                customer_state_setup=draft.customer_state_setup,
                thread_setup=draft.thread_setup,
                provider_setup=draft.provider_setup,
                mutation_types=draft.mutation_types,
                generator_provenance=draft.generator_provenance,
                oracle_version=draft.oracle_version,
                semantic_hash=semantic,
                mode=draft.mode,
                campaign_phase=draft.campaign_phase,
            )
        )
        index += 1
    return scenarios


def build_quality_manifest(scenarios: list[ProfileScenario]) -> QualityDatasetManifest:
    family_dist: dict[str, int] = {}
    for scenario in scenarios:
        family_dist[scenario.family] = family_dist.get(scenario.family, 0) + 1
    payload = {
        "dataset_version": QUALITY_DATASET_VERSION,
        "scenario_ids": [s.scenario_id for s in scenarios],
        "family_distribution": family_dist,
    }
    manifest_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return QualityDatasetManifest(
        dataset_version=QUALITY_DATASET_VERSION,
        scenario_count=len(scenarios),
        family_count=len(family_dist),
        family_distribution=family_dist,
        manifest_hash=manifest_hash,
        scenario_ids=payload["scenario_ids"],
    )


def validate_quality_dataset_gates(scenarios: list[ProfileScenario]) -> QualityDatasetGateResult:
    failures: list[str] = []
    warnings: list[str] = []

    if len(scenarios) != QUALITY_SCENARIO_TARGET:
        failures.append(f"expected {QUALITY_SCENARIO_TARGET} scenarios, got {len(scenarios)}")

    family_dist: dict[str, int] = {}
    for scenario in scenarios:
        family_dist[scenario.family] = family_dist.get(scenario.family, 0) + 1

    if len(family_dist) != QUALITY_FAMILY_TARGET:
        failures.append(f"expected {QUALITY_FAMILY_TARGET} families, got {len(family_dist)}")

    max_allowed = int(QUALITY_SCENARIO_TARGET * MAX_FAMILY_SHARE) + 1
    for family, count in family_dist.items():
        if count > max_allowed:
            failures.append(f"family {family} dominates dataset: {count}/{QUALITY_SCENARIO_TARGET}")

    duplicates = find_semantic_duplicates(scenarios)
    if duplicates:
        failures.append(f"semantic duplicates found: {duplicates[:5]}")

    for scenario in scenarios:
        validation = validate_profile_scenario(scenario)
        if validation:
            failures.append(f"{scenario.scenario_id}: {validation}")
            break

    # Near-duplicate dominance: same semantic hash family cluster
    hash_counts: dict[str, int] = {}
    for scenario in scenarios:
        fp = semantic_fingerprint(scenario)
        hash_counts[fp] = hash_counts.get(fp, 0) + 1
    dominant = [h for h, c in hash_counts.items() if c > 3]
    if dominant:
        warnings.append(f"near-duplicate semantic clusters: {len(dominant)}")

    return QualityDatasetGateResult(passed=not failures, failures=failures, warnings=warnings)
