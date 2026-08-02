"""Generate 120-scenario coworker reply quality dataset."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from app.evaluation.profile_testbot.coworker_reply_dataset.constants import (
    COWORKER_FAMILY_TARGET,
    COWORKER_MAX_FAMILY_SHARE,
    COWORKER_REPLY_DATASET_VERSION,
    COWORKER_SCENARIO_TARGET,
)
from app.evaluation.profile_testbot.coworker_reply_dataset.families import all_coworker_family_cells
from app.workflows.reply_quality.customer_surface import extract_city_phrase
from app.evaluation.profile_testbot.profile_contract import CustomerProfileSnapshot
from app.evaluation.profile_testbot.scenarios.schema import (
    ProfileScenario,
    ProfileScenarioInput,
    validate_profile_scenario,
)


@dataclass
class CoworkerDatasetManifest:
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


def generate_coworker_reply_dataset(
    profile: CustomerProfileSnapshot,
    *,
    seed: int = 0,
) -> list[ProfileScenario]:
    scenarios: list[ProfileScenario] = []
    for index, (family, cell) in enumerate(all_coworker_family_cells()):
        scenario_id = f"PTB-DCQ-{index:04d}"
        entities = {}
        for key in cell.known_entities:
            if key == "city":
                entities[key] = extract_city_phrase(text=cell.message_text, entities={}) or "Uppsala"
            else:
                entities[key] = f"known-{key}"
        scenario = ProfileScenario(
            scenario_id=scenario_id,
            profile_id=profile.profile_id,
            profile_snapshot_hash=profile.profile_snapshot_hash,
            family=family,
            intent=cell.business_intent,
            risk_class="low",
            input=ProfileScenarioInput(
                subject=cell.subject,
                message_text=cell.message_text,
                sender_name="Test Kund" if "customer_name" not in cell.known_entities else "Anna Kund",
                sender_email="sender@eval.test",
                language=cell.language,
                attachment_metadata={},
            ),
            expected_classification={"job_type": "lead", "label": cell.business_intent},
            expected_route={"queue": "observe_manual_review", "final_job_status": "awaiting_approval"},
            expected_authorization={"policy_authorization": "send_for_approval"},
            expected_send_behavior=cell.expected_send,
            required_reply_facts=["acknowledgement"],
            optional_reply_facts=[],
            forbidden_reply_claims=["price", "booking", "warranty"],
            required_questions=[],
            customer_state_setup={
                "coworker_family": family,
                "service_type": cell.service_type,
                "business_intent": cell.business_intent,
                "thread_state": cell.thread_state,
                "known_entities": list(cell.known_entities),
                "forbid_name_request": cell.forbid_name,
                "forbid_phone_request": cell.forbid_phone,
                "required_markers": list(cell.required_markers),
                "forbidden_markers": list(cell.forbidden_markers),
                "customer_draft_allowed": cell.expected_send in {
                    "send_after_approval",
                    "draft_for_approval",
                },
                "oracle_applicability": {
                    "coworker_reply_quality": cell.expected_send
                    in {"send_after_approval", "draft_for_approval"},
                },
            },
            thread_setup={
                "thread_state": cell.thread_state,
                "gmail_thread_id": f"thread-{family}-{index}",
            },
            provider_setup={},
            mutation_types=[],
            generator_provenance={
                "seed": seed + index,
                "coworker_dataset_version": COWORKER_REPLY_DATASET_VERSION,
                "coworker_family": family,
            },
            oracle_version="coworker_reply_oracle_v1",
            semantic_hash=hashlib.sha256(
                f"{family}:{cell.subject}:{cell.message_text}".encode("utf-8")
            ).hexdigest(),
            mode="semi_automatic",
            campaign_phase="coworker_reply_quality",
        )
        failures = validate_profile_scenario(scenario)
        if failures:
            raise ValueError(f"{scenario_id}: {failures}")
        scenarios.append(scenario)
    return scenarios


def validate_coworker_dataset_gates(scenarios: list[ProfileScenario]) -> list[str]:
    failures: list[str] = []
    if len(scenarios) != COWORKER_SCENARIO_TARGET:
        failures.append(f"scenario_count {len(scenarios)} != {COWORKER_SCENARIO_TARGET}")
    families = {s.family for s in scenarios}
    if len(families) < COWORKER_FAMILY_TARGET:
        failures.append(f"family_count {len(families)} < {COWORKER_FAMILY_TARGET}")
    distribution: dict[str, int] = {}
    for scenario in scenarios:
        distribution[scenario.family] = distribution.get(scenario.family, 0) + 1
    max_share = max(distribution.values()) / max(len(scenarios), 1)
    if max_share > COWORKER_MAX_FAMILY_SHARE + 0.001:
        failures.append(f"family share {max_share:.2f} > {COWORKER_MAX_FAMILY_SHARE}")
    multi_turn = sum(
        1 for s in scenarios if (s.customer_state_setup or {}).get("thread_state") == "continuation"
    )
    if multi_turn < 30:
        failures.append(f"multi_turn {multi_turn} < 30")
    no_name = sum(1 for s in scenarios if (s.customer_state_setup or {}).get("forbid_name_request"))
    if no_name < 20:
        failures.append(f"no_name_cases {no_name} < 20")
    no_phone = sum(1 for s in scenarios if (s.customer_state_setup or {}).get("forbid_phone_request"))
    if no_phone < 20:
        failures.append(f"no_phone_cases {no_phone} < 20")
    return failures


def build_coworker_dataset_manifest(scenarios: list[ProfileScenario]) -> CoworkerDatasetManifest:
    distribution: dict[str, int] = {}
    for scenario in scenarios:
        distribution[scenario.family] = distribution.get(scenario.family, 0) + 1
    scenario_ids = [s.scenario_id for s in scenarios]
    manifest_hash = hashlib.sha256(
        json.dumps(scenario_ids, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return CoworkerDatasetManifest(
        dataset_version=COWORKER_REPLY_DATASET_VERSION,
        scenario_count=len(scenarios),
        family_count=len(distribution),
        family_distribution=distribution,
        manifest_hash=manifest_hash,
        scenario_ids=scenario_ids,
    )
