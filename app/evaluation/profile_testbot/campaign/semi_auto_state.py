"""Campaign state machine for profile semi-auto live execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CampaignState(str, Enum):
    CREATED = "created"
    READINESS_VERIFIED = "readiness_verified"
    SCENARIO_QUEUED = "scenario_queued"
    TEST_MESSAGE_SENT = "test_message_sent"
    INTAKE_OBSERVED = "intake_observed"
    PROCESSING_OBSERVED = "processing_observed"
    ORACLE_EVALUATED = "oracle_evaluated"
    AWAITING_HARNESS_DECISION = "awaiting_harness_decision"
    APPROVED_OR_REJECTED = "approved_or_rejected"
    REPLY_OBSERVED_OR_NO_SEND_VERIFIED = "reply_observed_or_no_send_verified"
    SCENARIO_VERIFIED = "scenario_verified"
    CAMPAIGN_COMPLETED = "campaign_completed"
    READINESS_FAILED = "readiness_failed"
    SEND_FAILED = "send_failed"
    INTAKE_TIMEOUT = "intake_timeout"
    PROCESSING_TIMEOUT = "processing_timeout"
    ORACLE_FAILED = "oracle_failed"
    UNEXPECTED_APPROVAL = "unexpected_approval"
    UNEXPECTED_SEND = "unexpected_send"
    PROVIDER_TIMEOUT = "provider_timeout"
    RECIPIENT_MISMATCH = "recipient_mismatch"
    DUPLICATE_SEND = "duplicate_send"
    CLEANUP_FAILED = "cleanup_failed"
    CAMPAIGN_ABORTED = "campaign_aborted"


TERMINAL_SCENARIO_STATES = frozenset(
    {
        CampaignState.SCENARIO_VERIFIED,
        CampaignState.SEND_FAILED,
        CampaignState.INTAKE_TIMEOUT,
        CampaignState.PROCESSING_TIMEOUT,
        CampaignState.ORACLE_FAILED,
        CampaignState.UNEXPECTED_APPROVAL,
        CampaignState.UNEXPECTED_SEND,
        CampaignState.PROVIDER_TIMEOUT,
        CampaignState.RECIPIENT_MISMATCH,
        CampaignState.DUPLICATE_SEND,
    }
)

FAILURE_CAMPAIGN_STATES = frozenset(
    {
        CampaignState.READINESS_FAILED,
        CampaignState.CLEANUP_FAILED,
        CampaignState.CAMPAIGN_ABORTED,
    }
)


@dataclass
class ScenarioExecutionState:
    scenario_id: str
    execution_id: str
    state: CampaignState = CampaignState.SCENARIO_QUEUED
    test_send_idempotency_key: str = ""
    approval_operation_id: str = ""
    reply_operation_id: str = ""
    sends: int = 0
    replies: int = 0
    approval_decision: str | None = None
    oracle_passed: bool | None = None
    failure_reason: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "execution_id": self.execution_id,
            "state": self.state.value,
            "test_send_idempotency_key": self.test_send_idempotency_key,
            "approval_operation_id": self.approval_operation_id,
            "reply_operation_id": self.reply_operation_id,
            "sends": self.sends,
            "replies": self.replies,
            "approval_decision": self.approval_decision,
            "oracle_passed": self.oracle_passed,
            "failure_reason": self.failure_reason,
            "evidence": dict(self.evidence),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ScenarioExecutionState:
        return cls(
            scenario_id=str(payload.get("scenario_id") or ""),
            execution_id=str(payload.get("execution_id") or ""),
            state=CampaignState(str(payload.get("state") or CampaignState.SCENARIO_QUEUED.value)),
            test_send_idempotency_key=str(payload.get("test_send_idempotency_key") or ""),
            approval_operation_id=str(payload.get("approval_operation_id") or ""),
            reply_operation_id=str(payload.get("reply_operation_id") or ""),
            sends=int(payload.get("sends") or 0),
            replies=int(payload.get("replies") or 0),
            approval_decision=payload.get("approval_decision"),
            oracle_passed=payload.get("oracle_passed"),
            failure_reason=payload.get("failure_reason"),
            evidence=dict(payload.get("evidence") or {}),
        )


@dataclass
class SemiAutoCampaignState:
    campaign_id: str
    runtime_sha: str
    profile_id: str
    profile_snapshot_hash: str
    manifest_hash: str
    oracle_version: str
    tenant_id: str
    contract_mode: bool = True
    state: CampaignState = CampaignState.CREATED
    scenario_states: dict[str, ScenarioExecutionState] = field(default_factory=dict)
    send_budget_used: int = 0
    failure_reason: str | None = None
    qualification_status: str = "PENDING"

    def to_dict(self) -> dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "runtime_sha": self.runtime_sha,
            "profile_id": self.profile_id,
            "profile_snapshot_hash": self.profile_snapshot_hash,
            "manifest_hash": self.manifest_hash,
            "oracle_version": self.oracle_version,
            "tenant_id": self.tenant_id,
            "contract_mode": self.contract_mode,
            "state": self.state.value,
            "scenario_states": {
                key: value.to_dict() for key, value in sorted(self.scenario_states.items())
            },
            "send_budget_used": self.send_budget_used,
            "failure_reason": self.failure_reason,
            "qualification_status": self.qualification_status,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SemiAutoCampaignState:
        scenarios = {
            key: ScenarioExecutionState.from_dict(value)
            for key, value in (payload.get("scenario_states") or {}).items()
        }
        return cls(
            campaign_id=str(payload.get("campaign_id") or ""),
            runtime_sha=str(payload.get("runtime_sha") or ""),
            profile_id=str(payload.get("profile_id") or ""),
            profile_snapshot_hash=str(payload.get("profile_snapshot_hash") or ""),
            manifest_hash=str(payload.get("manifest_hash") or ""),
            oracle_version=str(payload.get("oracle_version") or ""),
            tenant_id=str(payload.get("tenant_id") or ""),
            contract_mode=bool(payload.get("contract_mode", True)),
            state=CampaignState(str(payload.get("state") or CampaignState.CREATED.value)),
            scenario_states=scenarios,
            send_budget_used=int(payload.get("send_budget_used") or 0),
            failure_reason=payload.get("failure_reason"),
            qualification_status=str(payload.get("qualification_status") or "PENDING"),
        )
