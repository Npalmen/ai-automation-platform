"""Typed schemas for full-system testbot campaign scenarios."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CampaignBudget:
    gmail_sends: int = 1
    gmail_replies: int = 0
    external_writes: int = 0


@dataclass(frozen=True)
class CampaignEmailInput:
    subject: str
    message_text: str
    sender_name: str
    sender_email: str


@dataclass(frozen=True)
class CampaignScenario:
    scenario_id: str
    scenario_version: str
    mode: str
    campaign_type: str
    job_type: str
    service_profile: str | None
    synthetic_customer_id: str
    thread_id: str
    label: str
    email: CampaignEmailInput
    campaign_types: frozenset[str] = field(default_factory=frozenset)
    expected_classification: dict[str, Any] = field(default_factory=dict)
    expected_entities: dict[str, Any] = field(default_factory=dict)
    expected_routing: dict[str, Any] = field(default_factory=dict)
    expected_approval: dict[str, Any] = field(default_factory=dict)
    expected_customer_card: dict[str, Any] = field(default_factory=dict)
    expected_external_actions: list[dict[str, Any]] = field(default_factory=list)
    budgets: CampaignBudget = field(default_factory=CampaignBudget)
    content_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "scenario_version": self.scenario_version,
            "mode": self.mode,
            "campaign_type": self.campaign_type,
            "campaign_types": sorted(self.campaign_types),
            "job_type": self.job_type,
            "service_profile": self.service_profile,
            "synthetic_customer_id": self.synthetic_customer_id,
            "thread_id": self.thread_id,
            "label": self.label,
            "sender": {
                "name": self.email.sender_name,
                "email": self.email.sender_email,
            },
            "recipient": "allowlisted-app-mailbox",
            "expected_classification": self.expected_classification,
            "expected_entities": self.expected_entities,
            "expected_routing": self.expected_routing,
            "expected_approval": self.expected_approval,
            "expected_customer_card": self.expected_customer_card,
            "expected_external_actions": self.expected_external_actions,
            "budgets": {
                "gmail_sends": self.budgets.gmail_sends,
                "gmail_replies": self.budgets.gmail_replies,
                "external_writes": self.budgets.external_writes,
            },
            "content_hash": self.content_hash,
        }
