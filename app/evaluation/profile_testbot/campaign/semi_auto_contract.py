"""Contract backend for profile semi-auto runner (no Gmail network I/O)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.profile_testbot.campaign.mailbox_readiness import mailbox_hash
from app.evaluation.profile_testbot.campaign.post_approval_execution import (
    ReplyExecutionEvidence,
    provider_accepted,
)
from app.evaluation.profile_testbot.constants import LIVE_EVAL_TENANT_ID
from app.evaluation.profile_testbot.profile_contract import load_customer_profile
from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario


def _contract_draft_text(scenario: ProfileScenario) -> str:
    if scenario.expected_send_behavior in {"hold", "reject", "no_reply", "observe_only"}:
        return ""
    profile = load_customer_profile(scenario.profile_id)
    for fact in scenario.required_reply_facts:
        if fact == "acknowledgement" and profile.safe_acknowledgements:
            return profile.safe_acknowledgements[0]
    return "Contract draft for approval"


@dataclass
class TestSendResult:
    accepted: bool
    provider_message_id: str
    idempotency_key: str
    recipient_hash: str
    inbound_provider_message_id: str = ""
    inbound_rfc_message_id: str | None = None

    def __post_init__(self) -> None:
        if not self.inbound_provider_message_id:
            self.inbound_provider_message_id = self.provider_message_id


@dataclass
class IntakeObservation:
    intake_event_id: str
    job_id: str
    tenant_id: str
    duplicate: bool = False


@dataclass
class ProcessingObservation:
    classification: dict[str, Any]
    route: dict[str, Any]
    authorization: dict[str, Any]
    approval_state: str
    draft_text: str


@dataclass
class ApprovalResult:
    operation_id: str
    decision: str
    already_resolved: bool = False
    reply_action_operation_id: str | None = None


@dataclass
class ReplyVerification:
    execution_intents: int
    adapter_invocations: int
    provider_accepted: bool
    recipient_verified: bool
    duplicate_send: bool
    reply_hash: str | None
    inbound_provider_message_id: str | None = None
    inbound_rfc_message_id: str | None = None
    reply_provider_message_id: str | None = None
    reply_rfc_message_id: str | None = None
    reply_action_operation_id: str | None = None
    reply_execution_status: str | None = None
    reply_provider_outcome: str | None = None


@dataclass
class ContractSemiAutoBackend:
    tenant_id: str = LIVE_EVAL_TENANT_ID
    sender_email: str = ""
    recipient_email: str = ""
    sent_keys: set[str] = field(default_factory=set)
    approval_operations: dict[str, str] = field(default_factory=dict)
    jobs: dict[str, dict[str, Any]] = field(default_factory=dict)
    intake_events: dict[str, IntakeObservation] = field(default_factory=dict)
    gmail_sends: int = 0
    external_writes: dict[str, int] = field(default_factory=lambda: {"sheets": 0, "monday": 0, "visma": 0})
    automatic_verify_link_merge: int = 0
    reply_execution: dict[str, ReplyExecutionEvidence] = field(default_factory=dict)
    simulate_execution_skipped: bool = False
    simulate_execution_failed: bool = False
    simulate_execution_outcome_unknown: bool = False

    def send_test_message(
        self,
        *,
        campaign_id: str,
        scenario: ProfileScenario,
        idempotency_key: str,
    ) -> TestSendResult:
        if self.tenant_id != LIVE_EVAL_TENANT_ID:
            raise LiveEvalSafetyError(f"cross-tenant send blocked: {self.tenant_id}")
        if idempotency_key in self.sent_keys:
            raise LiveEvalSafetyError(f"duplicate test send for idempotency_key={idempotency_key}")
        recipient = self.recipient_email.strip().lower()
        if not recipient:
            raise LiveEvalSafetyError("recipient mailbox missing")
        self.sent_keys.add(idempotency_key)
        message_id = hashlib.sha256(
            f"{campaign_id}:{scenario.scenario_id}:{idempotency_key}".encode("utf-8")
        ).hexdigest()[:16]
        job_id = f"job-{scenario.scenario_id.lower()}"
        self.jobs[job_id] = {
            "job_id": job_id,
            "tenant_id": self.tenant_id,
            "scenario_id": scenario.scenario_id,
            "campaign_id": campaign_id,
            "classification": dict(scenario.expected_classification),
            "route": dict(scenario.expected_route),
            "authorization": dict(scenario.expected_authorization),
            "approval_state": "pending"
            if scenario.expected_send_behavior == "send_after_approval"
            else "hold",
            "draft_text": _contract_draft_text(scenario),
        }
        intake = IntakeObservation(
            intake_event_id=f"intake-{scenario.scenario_id}",
            job_id=job_id,
            tenant_id=self.tenant_id,
        )
        self.intake_events[scenario.scenario_id] = intake
        return TestSendResult(
            accepted=True,
            provider_message_id=message_id,
            idempotency_key=idempotency_key,
            recipient_hash=mailbox_hash(recipient),
            inbound_provider_message_id=message_id,
        )

    def observe_intake(self, *, scenario_id: str, campaign_id: str) -> IntakeObservation:
        observation = self.intake_events.get(scenario_id)
        if observation is None:
            raise LiveEvalSafetyError(
                f"intake not found for campaign={campaign_id} scenario={scenario_id}"
            )
        if observation.tenant_id != self.tenant_id:
            raise LiveEvalSafetyError("cross-tenant intake observation")
        return observation

    def observe_processing(self, *, scenario_id: str) -> ProcessingObservation:
        job = self._job_for_scenario(scenario_id)
        return ProcessingObservation(
            classification=dict(job.get("classification") or {}),
            route=dict(job.get("route") or {}),
            authorization=dict(job.get("authorization") or {}),
            approval_state=str(job.get("approval_state") or "none"),
            draft_text=str(job.get("draft_text") or ""),
        )

    def approve_via_lifecycle(
        self,
        *,
        scenario_id: str,
        operation_id: str,
        decision: str,
    ) -> ApprovalResult:
        if operation_id in self.approval_operations:
            return ApprovalResult(
                operation_id=operation_id,
                decision=self.approval_operations[operation_id],
                already_resolved=True,
            )
        job = self._job_for_scenario(scenario_id)
        if decision == "approve":
            job["approval_state"] = "approved"
            reply_operation_id = f"reply-op-{scenario_id.lower()}"
            if self.simulate_execution_skipped:
                self.reply_execution[scenario_id] = ReplyExecutionEvidence(
                    reply_action_operation_id=reply_operation_id,
                    reply_execution_status="skipped",
                    reply_provider_outcome="skipped",
                )
            elif self.simulate_execution_failed:
                self.reply_execution[scenario_id] = ReplyExecutionEvidence(
                    reply_action_operation_id=reply_operation_id,
                    reply_execution_status="failed",
                    reply_provider_outcome="failed",
                )
            elif self.simulate_execution_outcome_unknown:
                self.reply_execution[scenario_id] = ReplyExecutionEvidence(
                    reply_action_operation_id=reply_operation_id,
                    reply_execution_status="outcome_unknown",
                    reply_provider_outcome="outcome_unknown",
                )
            else:
                reply_provider_id = hashlib.sha256(
                    f"reply:{scenario_id}:{operation_id}".encode("utf-8")
                ).hexdigest()[:16]
                self.reply_execution[scenario_id] = ReplyExecutionEvidence(
                    reply_action_operation_id=reply_operation_id,
                    reply_execution_status="succeeded",
                    reply_provider_outcome="executed",
                    reply_provider_message_id=reply_provider_id,
                )
            resolved = "approved"
        else:
            resolved = decision
        self.approval_operations[operation_id] = resolved
        return ApprovalResult(
            operation_id=operation_id,
            decision=resolved,
            reply_action_operation_id=self.reply_execution.get(scenario_id, ReplyExecutionEvidence()).reply_action_operation_id,
        )

    def verify_reply(
        self,
        *,
        scenario: ProfileScenario,
        approved: bool,
        inbound_provider_message_id: str | None = None,
        inbound_rfc_message_id: str | None = None,
    ) -> ReplyVerification:
        if scenario.expected_send_behavior == "send_after_approval":
            if not approved:
                return ReplyVerification(
                    execution_intents=0,
                    adapter_invocations=0,
                    provider_accepted=False,
                    recipient_verified=False,
                    duplicate_send=False,
                    reply_hash=None,
                )
            evidence = self.reply_execution.get(scenario.scenario_id)
            if evidence is None or not provider_accepted(evidence):
                status = evidence.reply_execution_status if evidence else "not_observed"
                return ReplyVerification(
                    execution_intents=1,
                    adapter_invocations=0,
                    provider_accepted=False,
                    recipient_verified=False,
                    duplicate_send=False,
                    reply_hash=None,
                    inbound_provider_message_id=inbound_provider_message_id,
                    inbound_rfc_message_id=inbound_rfc_message_id,
                    reply_action_operation_id=evidence.reply_action_operation_id if evidence else None,
                    reply_execution_status=status,
                    reply_provider_outcome=evidence.reply_provider_outcome if evidence else None,
                )
            if (
                inbound_provider_message_id
                and evidence.reply_provider_message_id == inbound_provider_message_id
            ):
                raise LiveEvalSafetyError(
                    "evidence invariant violated: inbound_provider_message_id equals reply_provider_message_id"
                )
            self.gmail_sends += 1
            reply_text = "Contract reply body"
            return ReplyVerification(
                execution_intents=1,
                adapter_invocations=1,
                provider_accepted=True,
                recipient_verified=True,
                duplicate_send=False,
                reply_hash=hashlib.sha256(reply_text.encode("utf-8")).hexdigest(),
                inbound_provider_message_id=inbound_provider_message_id,
                inbound_rfc_message_id=inbound_rfc_message_id,
                reply_provider_message_id=evidence.reply_provider_message_id,
                reply_action_operation_id=evidence.reply_action_operation_id,
                reply_execution_status=evidence.reply_execution_status,
                reply_provider_outcome=evidence.reply_provider_outcome,
            )
        return ReplyVerification(
            execution_intents=0,
            adapter_invocations=0,
            provider_accepted=False,
            recipient_verified=True,
            duplicate_send=False,
            reply_hash=None,
        )

    def _job_for_scenario(self, scenario_id: str) -> dict[str, Any]:
        for job in self.jobs.values():
            if job.get("scenario_id") == scenario_id:
                return job
        raise LiveEvalSafetyError(f"processing job missing for scenario={scenario_id}")
