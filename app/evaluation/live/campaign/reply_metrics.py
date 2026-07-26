"""Physical Gmail reply metrics for semi-automatic campaign reporting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.evaluation.live.assertions import _count_unique_succeeded_operation_keys
from app.evaluation.live.constants import TELEMETRY_APP_GMAIL_REPLY


@dataclass(frozen=True)
class ScenarioReplyMetrics:
    expected_reply_count: int
    adapter_send_count: int
    provider_accepted_count: int
    recipient_verified_reply_count: int
    unauthorized_reply_count: int

    def to_dict(self) -> dict[str, int]:
        return {
            "expected_reply_count": self.expected_reply_count,
            "adapter_send_count": self.adapter_send_count,
            "provider_accepted_count": self.provider_accepted_count,
            "recipient_verified_reply_count": self.recipient_verified_reply_count,
            "unauthorized_reply_count": self.unauthorized_reply_count,
        }


def _count_decision_records(records: list[dict[str, Any]], record_type: str) -> int:
    return sum(1 for row in records if row.get("record_type") == record_type)


def build_scenario_reply_metrics(
    *,
    expected_reply: bool,
    observation: dict[str, Any],
    recipient_verified: bool,
    unauthorized: bool,
) -> ScenarioReplyMetrics:
    events = observation.get("events") or []
    job = observation.get("job") or {}
    records = job.get("decision_records") or []

    adapter_send_count = _count_unique_succeeded_operation_keys(
        events, TELEMETRY_APP_GMAIL_REPLY
    )
    if adapter_send_count == 0:
        adapter_send_count = _count_decision_records(records, "execution_intent")

    provider_accepted_count = sum(
        1
        for row in records
        if row.get("record_type") == "execution_outcome"
        and row.get("execution_status") == "succeeded"
    )

    expected_reply_count = 1 if expected_reply else 0
    recipient_verified_reply_count = 1 if recipient_verified else 0
    unauthorized_reply_count = 1 if unauthorized else 0

    return ScenarioReplyMetrics(
        expected_reply_count=expected_reply_count,
        adapter_send_count=adapter_send_count,
        provider_accepted_count=provider_accepted_count,
        recipient_verified_reply_count=recipient_verified_reply_count,
        unauthorized_reply_count=unauthorized_reply_count,
    )


@dataclass(frozen=True)
class CampaignReplyTotals:
    expected_reply_count: int
    adapter_send_count: int
    provider_accepted_count: int
    recipient_verified_reply_count: int
    unauthorized_reply_count: int

    def to_dict(self) -> dict[str, int]:
        return {
            "expected_reply_count": self.expected_reply_count,
            "adapter_send_count": self.adapter_send_count,
            "provider_accepted_count": self.provider_accepted_count,
            "recipient_verified_reply_count": self.recipient_verified_reply_count,
            "unauthorized_reply_count": self.unauthorized_reply_count,
        }

    @classmethod
    def from_scenarios(cls, metrics: list[ScenarioReplyMetrics]) -> CampaignReplyTotals:
        return cls(
            expected_reply_count=sum(m.expected_reply_count for m in metrics),
            adapter_send_count=sum(m.adapter_send_count for m in metrics),
            provider_accepted_count=sum(m.provider_accepted_count for m in metrics),
            recipient_verified_reply_count=sum(
                m.recipient_verified_reply_count for m in metrics
            ),
            unauthorized_reply_count=sum(m.unauthorized_reply_count for m in metrics),
        )
