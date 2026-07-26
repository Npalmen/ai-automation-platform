"""Physical Gmail reply metrics for semi-automatic campaign reporting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.evaluation.live.assertions import _count_unique_succeeded_operation_keys
from app.evaluation.live.constants import TELEMETRY_APP_GMAIL_REPLY


@dataclass(frozen=True)
class ScenarioReplyMetrics:
    expected_reply_count: int
    execution_intent_count: int
    adapter_invocation_count: int
    provider_accepted_count: int
    provider_rejected_count: int
    provider_outcome_unknown_count: int
    recipient_verified_reply_count: int
    unauthorized_reply_count: int

    @property
    def adapter_send_count(self) -> int:
        """Backward-compatible alias for adapter_invocation_count."""
        return self.adapter_invocation_count

    def to_dict(self) -> dict[str, int]:
        return {
            "expected_reply_count": self.expected_reply_count,
            "execution_intent_count": self.execution_intent_count,
            "adapter_invocation_count": self.adapter_invocation_count,
            "provider_accepted_count": self.provider_accepted_count,
            "provider_rejected_count": self.provider_rejected_count,
            "provider_outcome_unknown_count": self.provider_outcome_unknown_count,
            "recipient_verified_reply_count": self.recipient_verified_reply_count,
            "unauthorized_reply_count": self.unauthorized_reply_count,
            # Legacy key retained for downstream readers
            "adapter_send_count": self.adapter_invocation_count,
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

    execution_intent_count = _count_decision_records(records, "execution_intent")
    adapter_invocation_count = _count_unique_succeeded_operation_keys(
        events, TELEMETRY_APP_GMAIL_REPLY
    )
    if adapter_invocation_count == 0:
        adapter_invocation_count = execution_intent_count

    outcome_rows = [
        row
        for row in records
        if row.get("record_type") == "execution_outcome"
    ]
    provider_accepted_count = sum(
        1 for row in outcome_rows if row.get("execution_status") == "succeeded"
    )
    provider_rejected_count = sum(
        1 for row in outcome_rows if row.get("execution_status") == "failed"
    )
    provider_outcome_unknown_count = max(
        0,
        execution_intent_count
        - provider_accepted_count
        - provider_rejected_count,
    )

    expected_reply_count = 1 if expected_reply else 0
    recipient_verified_reply_count = 1 if recipient_verified else 0
    unauthorized_reply_count = 1 if unauthorized else 0

    return ScenarioReplyMetrics(
        expected_reply_count=expected_reply_count,
        execution_intent_count=execution_intent_count,
        adapter_invocation_count=adapter_invocation_count,
        provider_accepted_count=provider_accepted_count,
        provider_rejected_count=provider_rejected_count,
        provider_outcome_unknown_count=provider_outcome_unknown_count,
        recipient_verified_reply_count=recipient_verified_reply_count,
        unauthorized_reply_count=unauthorized_reply_count,
    )


@dataclass(frozen=True)
class CampaignReplyTotals:
    expected_reply_count: int
    execution_intent_count: int
    adapter_invocation_count: int
    provider_accepted_count: int
    provider_rejected_count: int
    provider_outcome_unknown_count: int
    recipient_verified_reply_count: int
    unauthorized_reply_count: int

    @property
    def adapter_send_count(self) -> int:
        return self.adapter_invocation_count

    def to_dict(self) -> dict[str, int]:
        return {
            "expected_reply_count": self.expected_reply_count,
            "execution_intent_count": self.execution_intent_count,
            "adapter_invocation_count": self.adapter_invocation_count,
            "provider_accepted_count": self.provider_accepted_count,
            "provider_rejected_count": self.provider_rejected_count,
            "provider_outcome_unknown_count": self.provider_outcome_unknown_count,
            "recipient_verified_reply_count": self.recipient_verified_reply_count,
            "unauthorized_reply_count": self.unauthorized_reply_count,
            "adapter_send_count": self.adapter_invocation_count,
        }

    @classmethod
    def from_scenarios(cls, metrics: list[ScenarioReplyMetrics]) -> CampaignReplyTotals:
        return cls(
            expected_reply_count=sum(m.expected_reply_count for m in metrics),
            execution_intent_count=sum(m.execution_intent_count for m in metrics),
            adapter_invocation_count=sum(m.adapter_invocation_count for m in metrics),
            provider_accepted_count=sum(m.provider_accepted_count for m in metrics),
            provider_rejected_count=sum(m.provider_rejected_count for m in metrics),
            provider_outcome_unknown_count=sum(
                m.provider_outcome_unknown_count for m in metrics
            ),
            recipient_verified_reply_count=sum(
                m.recipient_verified_reply_count for m in metrics
            ),
            unauthorized_reply_count=sum(m.unauthorized_reply_count for m in metrics),
        )
