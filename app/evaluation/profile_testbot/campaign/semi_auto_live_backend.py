"""Live Gmail backend for profile semi-auto campaign runner."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from app.evaluation.live.campaign.test_operator import (
    PendingApproval,
    approve_approval,
    list_job_approvals,
)
from app.evaluation.live.config import LiveEvalConfig, get_live_eval_config
from app.evaluation.live.errors import LiveEvalIntakeSkippedError, LiveEvalPipelinePollError, LiveEvalSafetyError
from app.evaluation.live.gmail_transport import (
    SendOutcome,
    observe_expected_sender_reply,
    send_scenario_email,
)
from app.evaluation.live.observer import LiveEvalObserver
from app.evaluation.live.registry import new_evaluation_run_id
from app.evaluation.profile_testbot.campaign.mailbox_readiness import mailbox_hash
from app.evaluation.profile_testbot.campaign.post_approval_execution import (
    JobActionExecutionSnapshot,
    ReplyExecutionEvidence,
    poll_post_approval_reply_execution,
    provider_accepted,
)
from app.evaluation.profile_testbot.campaign.semi_auto_contract import (
    ApprovalResult,
    IntakeObservation,
    ProcessingObservation,
    ReplyVerification,
    TestSendResult,
)
from app.evaluation.profile_testbot.campaign.send_payload import build_profile_testbot_message_body
from app.evaluation.profile_testbot.constants import LIVE_EVAL_TENANT_ID
from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _derive_approval_state(job: dict[str, Any]) -> str:
    if job.get("has_pending_approvals"):
        return "pending"
    status = str(job.get("job_status") or job.get("status") or "").lower()
    if status in {"manual_review", "on_hold", "awaiting_approval"}:
        return "hold"
    return "none"


def _draft_text_from_job_and_approvals(
    *,
    base_url: str,
    admin_api_key: str,
    tenant_id: str,
    job_id: str,
    job: dict[str, Any],
) -> str:
    response = httpx.get(
        f"{base_url.rstrip('/')}/jobs/{job_id}/approvals",
        headers={
            "X-Admin-API-Key": admin_api_key,
            "X-Tenant-ID": tenant_id,
        },
        timeout=30.0,
    )
    response.raise_for_status()
    for row in response.json().get("items") or []:
        if str(row.get("state") or "") != "pending":
            continue
        delivery = row.get("delivery_payload") or {}
        body = delivery.get("body")
        if body:
            return str(body)
    policy = job.get("policy") or {}
    recommended = policy.get("recommended_next_step")
    if isinstance(recommended, dict):
        text = recommended.get("body") or recommended.get("draft_text")
        if text:
            return str(text)
    return ""


def _fetch_job_actions(
    *,
    base_url: str,
    admin_api_key: str,
    tenant_id: str,
    job_id: str,
) -> list[JobActionExecutionSnapshot]:
    response = httpx.get(
        f"{base_url.rstrip('/')}/jobs/{job_id}/actions",
        headers={
            "X-Admin-API-Key": admin_api_key,
            "X-Tenant-ID": tenant_id,
        },
        timeout=30.0,
    )
    response.raise_for_status()
    snapshots: list[JobActionExecutionSnapshot] = []
    for row in response.json().get("items") or []:
        snapshots.append(
            JobActionExecutionSnapshot(
                action_type=str(row.get("action_type") or ""),
                status=str(row.get("status") or ""),
                error_message=row.get("error_message"),
                external_id=row.get("external_id"),
            )
        )
    return snapshots


@dataclass
class _ScenarioRunContext:
    evaluation_run_id: str
    attempt_id: int = 1
    job_id: str | None = None
    intake_event_id: str | None = None
    send_outcome: SendOutcome | None = None
    send_window_start: datetime = field(default_factory=_utcnow)
    observation: dict[str, Any] = field(default_factory=dict)
    inbound_provider_message_id: str | None = None
    inbound_rfc_message_id: str | None = None
    reply_execution: ReplyExecutionEvidence | None = None


@dataclass
class LiveSemiAutoBackend:
    campaign_id: str
    tenant_id: str = LIVE_EVAL_TENANT_ID
    sender_email: str = ""
    recipient_email: str = ""
    base_url: str = ""
    admin_api_key: str = ""
    config: LiveEvalConfig | None = None
    registration_ai_mode: str = "live_llm"
    registration_campaign_type: str | None = None
    registration_execution_mode: str | None = None
    registration_manifest_hash: str | None = None
    sent_keys: set[str] = field(default_factory=set)
    approval_operations: dict[str, str] = field(default_factory=dict)
    runs: dict[str, _ScenarioRunContext] = field(default_factory=dict)
    gmail_sends: int = 0
    external_writes: dict[str, int] = field(
        default_factory=lambda: {"sheets": 0, "monday": 0, "visma": 0}
    )
    automatic_verify_link_merge: int = 0

    def __post_init__(self) -> None:
        self.config = self.config or get_live_eval_config()

    @property
    def observer(self) -> LiveEvalObserver:
        return LiveEvalObserver(
            base_url=self.base_url,
            admin_api_key=self.admin_api_key,
            tenant_id=self.tenant_id,
        )

    def _run_context(self, scenario_id: str) -> _ScenarioRunContext:
        ctx = self.runs.get(scenario_id)
        if ctx is None:
            raise LiveEvalSafetyError(f"missing live run context for scenario={scenario_id}")
        return ctx

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

        evaluation_run_id = new_evaluation_run_id()
        ctx = _ScenarioRunContext(evaluation_run_id=evaluation_run_id)
        self.runs[scenario.scenario_id] = ctx
        self.sent_keys.add(idempotency_key)

        self.observer.register_run(
            {
                "evaluation_run_id": evaluation_run_id,
                "tenant_id": self.tenant_id,
                "scenario_id": scenario.scenario_id,
                "attempt_id": ctx.attempt_id,
                "transport_mode": "live_gmail",
                "ai_mode": self.registration_ai_mode,
                "campaign_type": self.registration_campaign_type,
                "execution_mode": self.registration_execution_mode,
                "campaign_id": campaign_id,
                "manifest_hash": self.registration_manifest_hash,
                "expected_sender": self.sender_email,
                "expected_recipient": self.recipient_email,
                "llm_provider": (self.config.llm_provider if self.config else "") or None
                if self.registration_ai_mode == "live_llm"
                else None,
                "llm_requested_model": (self.config.llm_model if self.config else "") or None
                if self.registration_ai_mode == "live_llm"
                else None,
            }
        )

        body = build_profile_testbot_message_body(
            scenario=scenario,
            evaluation_run_id=evaluation_run_id,
            campaign_id=campaign_id,
        )
        outcome, _events = send_scenario_email(
            evaluation_run_id=evaluation_run_id,
            scenario_id=scenario.scenario_id,
            attempt_id=ctx.attempt_id,
            expected_sender=self.sender_email,
            expected_recipient=self.recipient_email,
            base_subject=scenario.input.subject,
            message_body=body,
            config=self.config,
        )
        ctx.send_outcome = outcome
        ctx.inbound_provider_message_id = outcome.sender_gmail_message_id
        ctx.inbound_rfc_message_id = outcome.rfc_message_id
        return TestSendResult(
            accepted=True,
            provider_message_id=outcome.sender_gmail_message_id,
            idempotency_key=idempotency_key,
            recipient_hash=mailbox_hash(recipient),
            inbound_provider_message_id=outcome.sender_gmail_message_id,
            inbound_rfc_message_id=outcome.rfc_message_id,
        )

    def observe_intake(self, *, scenario_id: str, campaign_id: str) -> IntakeObservation:
        ctx = self._run_context(scenario_id)

        def on_poll(payload: dict[str, Any]) -> None:
            if payload.get("duplicate_detected"):
                raise LiveEvalSafetyError("correlation_failure: duplicate delivery")

        try:
            delivery = self.observer.poll_delivery(
                ctx.evaluation_run_id,
                timeout_seconds=min(300, self.config.max_runtime_minutes * 60),
                on_poll=on_poll,
            )
        except LiveEvalPipelinePollError as exc:
            raise LiveEvalSafetyError(f"intake_timeout: {exc.timeout_reason}") from exc

        confirmed = delivery.get("confirmed") or {}
        recipient_id = str(confirmed.get("message_id") or "").strip()
        if not recipient_id:
            raise LiveEvalSafetyError("intake_timeout: missing recipient message id")

        try:
            processed = self.observer.process_delivery(ctx.evaluation_run_id, recipient_id)
        except LiveEvalIntakeSkippedError as exc:
            reason = str(exc.payload.get("reason") or exc.payload.get("intake_skip_reason") or "intake_skipped")
            raise LiveEvalSafetyError(f"intake_skipped: {reason}") from exc
        job_id = str(processed.get("job_id") or (processed.get("job") or {}).get("job_id") or "")
        ctx.job_id = job_id or None
        ctx.intake_event_id = recipient_id
        return IntakeObservation(
            intake_event_id=recipient_id,
            job_id=job_id,
            tenant_id=self.tenant_id,
        )

    def observe_processing(self, *, scenario_id: str) -> ProcessingObservation:
        ctx = self._run_context(scenario_id)
        try:
            observation = self.observer.poll_pipeline(
                ctx.evaluation_run_id,
                timeout_seconds=min(600, self.config.max_runtime_minutes * 60),
                success_statuses=frozenset(
                    {"awaiting_approval", "manual_review", "completed", "on_hold"}
                ),
            )
        except LiveEvalPipelinePollError as exc:
            raise LiveEvalSafetyError(f"processing_timeout: {exc.timeout_reason}") from exc

        ctx.observation = observation
        job = observation.get("job") or {}
        ctx.job_id = str(job.get("job_id") or ctx.job_id or "") or None
        draft_text = ""
        if ctx.job_id:
            draft_text = _draft_text_from_job_and_approvals(
                base_url=self.base_url,
                admin_api_key=self.admin_api_key,
                tenant_id=self.tenant_id,
                job_id=ctx.job_id,
                job=job,
            )
        classification = dict(job.get("classification") or {})
        policy = dict(job.get("policy") or {})
        return ProcessingObservation(
            classification=classification,
            route={"job_status": job.get("job_status")},
            authorization={
                "policy_authorization": policy.get("policy_authorization"),
            },
            approval_state=_derive_approval_state(job),
            draft_text=draft_text,
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
        ctx = self._run_context(scenario_id)
        if not ctx.job_id:
            raise LiveEvalSafetyError("approval blocked: missing job_id")
        pending = list_job_approvals(
            base_url=self.base_url,
            admin_api_key=self.admin_api_key,
            tenant_id=self.tenant_id,
            job_id=ctx.job_id,
        )
        target = next(
            (
                row
                for row in pending
                if row.state == "pending"
                and row.next_on_approve in ("action_execute", "email_send")
            ),
            None,
        )
        if target is None:
            raise LiveEvalSafetyError("approval blocked: no pending approval")
        reply_operation_id = target.action_operation_id
        if decision == "approve":
            result = approve_approval(
                base_url=self.base_url,
                admin_api_key=self.admin_api_key,
                tenant_id=self.tenant_id,
                approval=target,
                reason="profile testbot semi-auto harness approve",
            )
            if result.http_status >= 400 and not result.idempotent:
                raise LiveEvalSafetyError(
                    f"approval failed: http_status={result.http_status}"
                )
            ctx.reply_execution = poll_post_approval_reply_execution(
                lambda: self.observer.get_observation(ctx.evaluation_run_id),
                lambda: _fetch_job_actions(
                    base_url=self.base_url,
                    admin_api_key=self.admin_api_key,
                    tenant_id=self.tenant_id,
                    job_id=ctx.job_id or "",
                ),
                action_operation_id=reply_operation_id,
                inbound_provider_message_id=ctx.inbound_provider_message_id,
                inbound_rfc_message_id=ctx.inbound_rfc_message_id,
                timeout_seconds=120.0,
            )
            resolved = "approved"
        else:
            resolved = decision
        self.approval_operations[operation_id] = resolved
        return ApprovalResult(
            operation_id=operation_id,
            decision=resolved,
            reply_action_operation_id=reply_operation_id,
        )

    def bind_frozen_send_body(
        self,
        *,
        scenario_id: str,
        frozen_body: str,
        expected_body_hash: str,
    ) -> None:
        from app.evaluation.profile_testbot.qualification.coworker_r3_frozen_bodies import (
            r3_send_body_hash,
        )

        digest = r3_send_body_hash(frozen_body)
        if digest != expected_body_hash:
            raise LiveEvalSafetyError(
                f"frozen body hash mismatch for {scenario_id}: expected={expected_body_hash}"
            )
        ctx = self._run_context(scenario_id)
        if not ctx.job_id:
            raise LiveEvalSafetyError("frozen body bind blocked: missing job_id")
        pending = list_job_approvals(
            base_url=self.base_url,
            admin_api_key=self.admin_api_key,
            tenant_id=self.tenant_id,
            job_id=ctx.job_id,
        )
        target = next(
            (
                row
                for row in pending
                if row.state == "pending"
                and row.next_on_approve in ("action_execute", "email_send")
            ),
            None,
        )
        if target is None:
            raise LiveEvalSafetyError("frozen body bind blocked: no pending approval")
        response = httpx.post(
            f"{self.base_url.rstrip('/')}/admin/live-eval/r3/bind-frozen-approval-body",
            headers={
                "X-Admin-API-Key": self.admin_api_key,
                "X-Tenant-ID": self.tenant_id,
            },
            json={
                "tenant_id": self.tenant_id,
                "job_id": ctx.job_id,
                "approval_id": target.approval_id,
                "scenario_id": scenario_id,
                "frozen_body": frozen_body,
                "expected_body_hash": expected_body_hash,
            },
            timeout=30.0,
        )
        if response.status_code >= 400:
            raise LiveEvalSafetyError(
                f"frozen body bind failed: http_status={response.status_code}"
            )

    def verify_reply(
        self,
        *,
        scenario: ProfileScenario,
        approved: bool,
        inbound_provider_message_id: str | None = None,
        inbound_rfc_message_id: str | None = None,
    ) -> ReplyVerification:
        if scenario.expected_send_behavior != "send_after_approval" or not approved:
            return ReplyVerification(
                execution_intents=0,
                adapter_invocations=0,
                provider_accepted=False,
                recipient_verified=True,
                duplicate_send=False,
                reply_hash=None,
            )

        ctx = self._run_context(scenario.scenario_id)
        inbound_id = inbound_provider_message_id or ctx.inbound_provider_message_id
        inbound_rfc = inbound_rfc_message_id or ctx.inbound_rfc_message_id
        evidence = ctx.reply_execution

        if evidence is None or not provider_accepted(evidence):
            status = evidence.reply_execution_status if evidence else "not_observed"
            return ReplyVerification(
                execution_intents=1,
                adapter_invocations=0,
                provider_accepted=False,
                recipient_verified=False,
                duplicate_send=False,
                reply_hash=None,
                inbound_provider_message_id=inbound_id,
                inbound_rfc_message_id=inbound_rfc,
                reply_action_operation_id=evidence.reply_action_operation_id if evidence else None,
                reply_execution_status=status,
                reply_provider_outcome=evidence.reply_provider_outcome if evidence else None,
            )

        if (
            inbound_id
            and evidence.reply_provider_message_id
            and inbound_id == evidence.reply_provider_message_id
        ):
            raise LiveEvalSafetyError(
                "evidence invariant violated: inbound_provider_message_id equals reply_provider_message_id"
            )

        if evidence.reply_execution_status == "outcome_unknown":
            return ReplyVerification(
                execution_intents=1,
                adapter_invocations=0,
                provider_accepted=False,
                recipient_verified=False,
                duplicate_send=False,
                reply_hash=None,
                inbound_provider_message_id=inbound_id,
                inbound_rfc_message_id=inbound_rfc,
                reply_provider_message_id=evidence.reply_provider_message_id,
                reply_rfc_message_id=evidence.reply_rfc_message_id,
                reply_action_operation_id=evidence.reply_action_operation_id,
                reply_execution_status=evidence.reply_execution_status,
                reply_provider_outcome=evidence.reply_provider_outcome,
            )

        self.gmail_sends += 1
        reply_provider_id = evidence.reply_provider_message_id
        observed = observe_expected_sender_reply(
            evaluation_run_id=ctx.evaluation_run_id,
            scenario_id=scenario.scenario_id,
            attempt_id=ctx.attempt_id,
            expected_recipient=self.recipient_email,
            expected_sender=self.sender_email,
            send_window_start=ctx.send_window_start,
            timeout_seconds=180.0,
            campaign_run_id=self.campaign_id,
            provider_message_id=reply_provider_id,
            inbound_rfc_message_id=inbound_rfc,
        )
        if observed is None:
            return ReplyVerification(
                execution_intents=1,
                adapter_invocations=1,
                provider_accepted=True,
                recipient_verified=False,
                duplicate_send=False,
                reply_hash=None,
                inbound_provider_message_id=inbound_id,
                inbound_rfc_message_id=inbound_rfc,
                reply_provider_message_id=reply_provider_id,
                reply_rfc_message_id=evidence.reply_rfc_message_id,
                reply_action_operation_id=evidence.reply_action_operation_id,
                reply_execution_status=evidence.reply_execution_status,
                reply_provider_outcome=evidence.reply_provider_outcome,
            )
        reply_hash = hashlib.sha256(observed.message_id.encode("utf-8")).hexdigest()
        return ReplyVerification(
            execution_intents=1,
            adapter_invocations=1,
            provider_accepted=True,
            recipient_verified=True,
            duplicate_send=False,
            reply_hash=reply_hash,
            inbound_provider_message_id=inbound_id,
            inbound_rfc_message_id=inbound_rfc,
            reply_provider_message_id=reply_provider_id,
            reply_rfc_message_id=evidence.reply_rfc_message_id,
            reply_action_operation_id=evidence.reply_action_operation_id,
            reply_execution_status=evidence.reply_execution_status,
            reply_provider_outcome=evidence.reply_provider_outcome,
        )
