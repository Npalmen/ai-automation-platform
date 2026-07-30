"""Contract backend for profile semi-auto runner (no Gmail network I/O)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.profile_testbot.campaign.mailbox_readiness import mailbox_hash
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


@dataclass
class ReplyVerification:
    execution_intents: int
    adapter_invocations: int
    provider_accepted: bool
    recipient_verified: bool
    duplicate_send: bool
    reply_hash: str | None


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
            self.gmail_sends += 1
        else:
            job["approval_state"] = decision
        self.approval_operations[operation_id] = decision
        return ApprovalResult(operation_id=operation_id, decision=decision)

    def verify_reply(
        self,
        *,
        scenario: ProfileScenario,
        approved: bool,
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
            reply_text = "Contract reply body"
            return ReplyVerification(
                execution_intents=1,
                adapter_invocations=1,
                provider_accepted=True,
                recipient_verified=True,
                duplicate_send=False,
                reply_hash=hashlib.sha256(reply_text.encode("utf-8")).hexdigest(),
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
