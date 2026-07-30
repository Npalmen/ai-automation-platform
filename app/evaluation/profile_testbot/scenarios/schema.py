"""Profile scenario contract for profile-driven testbot."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.evaluation.profile_testbot.constants import SEND_BEHAVIORS


@dataclass(frozen=True)
class ProfileScenarioInput:
    subject: str
    message_text: str
    sender_name: str
    sender_email: str
    language: str = "sv"
    attachment_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProfileScenario:
    scenario_id: str
    profile_id: str
    profile_snapshot_hash: str
    family: str
    intent: str
    risk_class: str
    input: ProfileScenarioInput
    expected_classification: dict[str, Any]
    expected_route: dict[str, Any]
    expected_authorization: dict[str, Any]
    expected_send_behavior: str
    required_reply_facts: list[str] = field(default_factory=list)
    optional_reply_facts: list[str] = field(default_factory=list)
    forbidden_reply_claims: list[str] = field(default_factory=list)
    required_questions: list[str] = field(default_factory=list)
    customer_state_setup: dict[str, Any] = field(default_factory=dict)
    thread_setup: dict[str, Any] = field(default_factory=dict)
    provider_setup: dict[str, Any] = field(default_factory=dict)
    mutation_types: list[str] = field(default_factory=list)
    generator_provenance: dict[str, Any] = field(default_factory=dict)
    oracle_version: str = ""
    semantic_hash: str = ""
    mode: str = "observe"
    campaign_phase: str = "hermetic"

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "profile_id": self.profile_id,
            "profile_snapshot_hash": self.profile_snapshot_hash,
            "family": self.family,
            "intent": self.intent,
            "risk_class": self.risk_class,
            "input": {
                "subject": self.input.subject,
                "message_text": self.input.message_text,
                "sender_name": self.input.sender_name,
                "sender_email": self.input.sender_email,
                "language": self.input.language,
                "attachment_metadata": self.input.attachment_metadata,
            },
            "expected_classification": self.expected_classification,
            "expected_route": self.expected_route,
            "expected_authorization": self.expected_authorization,
            "expected_send_behavior": self.expected_send_behavior,
            "required_reply_facts": list(self.required_reply_facts),
            "optional_reply_facts": list(self.optional_reply_facts),
            "forbidden_reply_claims": list(self.forbidden_reply_claims),
            "required_questions": list(self.required_questions),
            "customer_state_setup": dict(self.customer_state_setup),
            "thread_setup": dict(self.thread_setup),
            "provider_setup": dict(self.provider_setup),
            "mutation_types": list(self.mutation_types),
            "generator_provenance": dict(self.generator_provenance),
            "oracle_version": self.oracle_version,
            "semantic_hash": self.semantic_hash,
            "mode": self.mode,
            "campaign_phase": self.campaign_phase,
        }


def validate_profile_scenario(scenario: ProfileScenario) -> list[str]:
    failures: list[str] = []
    if not scenario.scenario_id:
        failures.append("scenario_id required")
    if scenario.expected_send_behavior not in SEND_BEHAVIORS:
        failures.append(f"invalid expected_send_behavior: {scenario.expected_send_behavior}")
    if not scenario.profile_snapshot_hash:
        failures.append("profile_snapshot_hash required")
    if not scenario.semantic_hash:
        failures.append("semantic_hash required")
    return failures
