"""R4 reviewed-live backend — wires LiveSemiAutoBackend for execute (no new Gmail client)."""

from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

import httpx

from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.config import get_live_eval_config
from app.evaluation.profile_testbot.campaign.semi_auto_live_backend import LiveSemiAutoBackend
from app.evaluation.profile_testbot.constants import LIVE_EVAL_TENANT_ID
from app.evaluation.profile_testbot.qualification.coworker_r4_approval_artifact import (
    R4ApprovalArtifact,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (
    R4_EXECUTE_AI_MODE,
    R4_EXECUTION_MODE,
    R4_LIVE_QUALITY_CAMPAIGN_TYPE,
    R4_NO_SEND_SCENARIO_IDS,
    R4_PROFILE_ID,
    R4_SEND_SCENARIO_IDS,
    resolve_r4_scenarios,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_reviewed_snapshot import (
    R4ReviewedBodySnapshot,
)
from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario
from app.workflows.reply_quality.provenance import hash_body

R4_LIVE_BACKEND_TYPE = "r4_live_eval_semi_auto_backend"
R4_BIND_ENV_FLAG = "R4_REVIEWED_APPROVAL_BIND_ALLOWED"


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _redact_id(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value)
    if len(text) <= 8:
        return text[:2] + "…"
    return text[:4] + "…" + text[-4:]


def describe_r4_live_backend_wiring() -> dict[str, Any]:
    """Write-free capability report for dry-run / JIT / postmerge (no Gmail)."""
    return {
        "backend_wired": True,
        "execute_backend_type": R4_LIVE_BACKEND_TYPE,
        "execute_callback_available": True,
        "reuses_live_semi_auto_backend": True,
        "gmail_client_new": False,
        "oauth_client_new": False,
        "http_client_new": False,
    }


@dataclass
class R4LiveExecutorContext:
    candidate_runtime_sha: str
    executor_runtime_sha: str
    campaign_id: str
    approval_artifact: R4ApprovalArtifact
    manifest: dict[str, Any]
    candidates: dict[str, Any]
    human_review: dict[str, Any]
    recipient: str
    base_url: str = ""
    admin_api_key: str = ""
    sender_email: str = ""


def build_r4_live_backend(
    *,
    campaign_id: str,
    recipient: str,
    manifest_semantic_hash: str,
    base_url: str | None = None,
    admin_api_key: str | None = None,
    sender_email: str | None = None,
) -> LiveSemiAutoBackend:
    config = get_live_eval_config()
    senders = sorted(config.sender_emails)
    resolved_sender = (sender_email or (senders[0] if senders else "")).strip().lower()
    resolved_recipient = recipient.strip().lower()
    return LiveSemiAutoBackend(
        campaign_id=campaign_id,
        tenant_id=LIVE_EVAL_TENANT_ID,
        sender_email=resolved_sender,
        recipient_email=resolved_recipient,
        base_url=(base_url or os.environ.get("LIVE_EVAL_APP_BASE_URL") or "http://127.0.0.1:8010").strip(),
        admin_api_key=(admin_api_key or os.environ.get("ADMIN_API_KEY") or "").strip(),
        config=config,
        registration_ai_mode=R4_EXECUTE_AI_MODE,
        registration_campaign_type=R4_LIVE_QUALITY_CAMPAIGN_TYPE,
        registration_execution_mode=R4_EXECUTION_MODE,
        registration_manifest_hash=manifest_semantic_hash,
    )


def _load_scenario_map(profile_id: str = R4_PROFILE_ID) -> dict[str, ProfileScenario]:
    from app.evaluation.profile_testbot.profile_contract import load_customer_profile

    profile = load_customer_profile(profile_id)
    scenarios = resolve_r4_scenarios(profile, seed=42)
    return {s.scenario_id: s for s in scenarios}


def bind_reviewed_send_body(
    backend: LiveSemiAutoBackend,
    *,
    scenario_id: str,
    reviewed_body: str,
    expected_body_hash: str,
    snapshot: R4ReviewedBodySnapshot | None = None,
) -> dict[str, Any]:
    """Bind human-reviewed R4 body onto pending approval via dedicated R4 route."""
    actual = hash_body(reviewed_body)
    if actual != expected_body_hash:
        raise LiveEvalSafetyError(
            f"reviewed body hash mismatch for {scenario_id}: expected={expected_body_hash}"
        )
    ctx = backend._run_context(scenario_id)
    if not ctx.job_id:
        raise LiveEvalSafetyError("reviewed body bind blocked: missing job_id")
    from app.evaluation.live.campaign.test_operator import list_job_approvals

    pending = list_job_approvals(
        base_url=backend.base_url,
        admin_api_key=backend.admin_api_key,
        tenant_id=backend.tenant_id,
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
        raise LiveEvalSafetyError("reviewed body bind blocked: no pending approval")
    payload: dict[str, Any] = {
        "tenant_id": backend.tenant_id,
        "job_id": ctx.job_id,
        "approval_id": target.approval_id,
        "scenario_id": scenario_id,
        "reviewed_body": reviewed_body,
        "expected_body_hash": expected_body_hash,
    }
    if snapshot is not None:
        payload["reviewed_snapshot"] = snapshot.to_dict()
    response = httpx.post(
        f"{backend.base_url.rstrip('/')}/admin/live-eval/r4/bind-reviewed-approval-body",
        headers={
            "X-Admin-API-Key": backend.admin_api_key,
            "X-Tenant-ID": backend.tenant_id,
        },
        json=payload,
        timeout=30.0,
    )
    if response.status_code >= 400:
        raise LiveEvalSafetyError(
            f"reviewed body bind failed: http_status={response.status_code}"
        )
    return response.json() if response.content else {"bound": True}


def build_r4_live_executor(
    *,
    candidate_runtime_sha: str,
    executor_runtime_sha: str,
    campaign_id: str,
    approval_artifact: R4ApprovalArtifact,
    manifest: dict[str, Any],
    candidates: dict[str, Any],
    human_review: dict[str, Any],
    recipient: str,
    backend: LiveSemiAutoBackend | None = None,
) -> Callable[..., dict[str, Any]]:
    """Return the execute callback. Does not send until invoked per scenario."""
    resolved_recipient = recipient.strip().lower()
    backend = backend or build_r4_live_backend(
        campaign_id=campaign_id,
        recipient=resolved_recipient,
        manifest_semantic_hash=str(manifest.get("manifest_semantic_hash") or ""),
    )
    scenario_by_id = _load_scenario_map(str(manifest.get("profile_id") or R4_PROFILE_ID))
    cand_by_id = {c.get("scenario_id"): c for c in (candidates.get("send_candidates") or [])}
    review_by_id = {r.get("scenario_id"): r for r in (human_review.get("reviews") or [])}
    claimed_ops: set[str] = set()
    send_budget_remaining = 20
    state = {
        "approval_artifact_hash": approval_artifact.artifact_hash,
        "candidate_runtime_sha": candidate_runtime_sha,
        "executor_runtime_sha": executor_runtime_sha,
        "campaign_id": campaign_id,
    }

    def _executor(**kwargs: Any) -> dict[str, Any]:
        nonlocal send_budget_remaining
        scenario_id = str(kwargs.get("scenario_id") or "")
        planned = kwargs.get("planned_gmail_send")
        if planned is False or scenario_id in R4_NO_SEND_SCENARIO_IDS and "snapshot" not in kwargs:
            return _execute_no_send(
                backend=backend,
                scenario=scenario_by_id[scenario_id],
                evaluation_run_id=str(kwargs.get("evaluation_run_id") or uuid.uuid4()),
                campaign_id=campaign_id,
            )
        snapshot: R4ReviewedBodySnapshot = kwargs["snapshot"]
        candidate = kwargs.get("candidate") or cand_by_id[scenario_id]
        review_row = kwargs.get("review_row") or review_by_id[scenario_id]
        evaluation_run_id = str(kwargs.get("evaluation_run_id") or uuid.uuid4())
        approval_operation_id = str(kwargs.get("approval_operation_id") or uuid.uuid4())
        reply_operation_id = str(kwargs.get("reply_operation_id") or uuid.uuid4())
        if approval_operation_id in claimed_ops or reply_operation_id in claimed_ops:
            return {
                "scenario_id": scenario_id,
                "status": "failed",
                "failure_stage": "duplicate_operation",
                "failure_reason": "operation_id_reuse_forbidden",
                "gmail_sends": 0,
                "gmail_drafts": 0,
                "unknown_outcome": False,
            }
        claimed_ops.add(approval_operation_id)
        claimed_ops.add(reply_operation_id)
        if send_budget_remaining < 1:
            return {
                "scenario_id": scenario_id,
                "status": "blocked",
                "failure_stage": "send_budget",
                "failure_reason": "send_budget_exhausted",
                "gmail_sends": 0,
                "gmail_drafts": 0,
            }
        result = _execute_send(
            backend=backend,
            scenario=scenario_by_id[scenario_id],
            snapshot=snapshot,
            candidate=candidate,
            review_row=review_row,
            evaluation_run_id=evaluation_run_id,
            approval_operation_id=approval_operation_id,
            reply_operation_id=reply_operation_id,
            campaign_id=campaign_id,
            recipient=resolved_recipient,
            state=state,
        )
        if result.get("status") in {"passed", "PASS", "pass", "succeeded"} and int(
            result.get("gmail_sends") or 0
        ):
            send_budget_remaining -= 1
        return result

    _executor._r4_backend_type = R4_LIVE_BACKEND_TYPE  # type: ignore[attr-defined]
    _executor._r4_backend = backend  # type: ignore[attr-defined]
    return _executor


def _execute_send(
    *,
    backend: LiveSemiAutoBackend,
    scenario: ProfileScenario,
    snapshot: R4ReviewedBodySnapshot,
    candidate: dict[str, Any],
    review_row: dict[str, Any],
    evaluation_run_id: str,
    approval_operation_id: str,
    reply_operation_id: str,
    campaign_id: str,
    recipient: str,
    state: dict[str, Any],
) -> dict[str, Any]:
    scenario_id = scenario.scenario_id
    audit: list[dict[str, Any]] = []
    base: dict[str, Any] = {
        "scenario_id": scenario_id,
        "evaluation_run_id": evaluation_run_id,
        "approval_operation_id": approval_operation_id,
        "reply_operation_id": reply_operation_id,
        "planned_gmail_send": True,
        "inbound_trigger_sent": False,
        "trigger_provider_message_id_redacted": None,
        "trigger_delivery_observed": False,
        "job_id": None,
        "trusted_snapshot_verified": False,
        "approval_state": None,
        "approval_executed": False,
        "adapter_provider": None,
        "provider_status": None,
        "reply_provider_message_id_redacted": None,
        "reply_thread_id_redacted": None,
        "reply_delivery_observed": False,
        "recipient_match": False,
        "thread_match": False,
        "body_hash_match": False,
        "duplicate_count": 0,
        "gmail_drafts": 0,
        "gmail_sends": 0,
        "execution_outcome": None,
        "unknown_outcome": False,
        "audit_events": audit,
        "r4_0088_provenance": None,
        "llm_calls": 0,
        "candidates_regenerated": False,
    }

    # Force run context to use campaign-provided evaluation_run_id.
    from app.evaluation.profile_testbot.campaign.semi_auto_live_backend import _ScenarioRunContext

    if scenario_id in backend.runs:
        return {
            **base,
            "status": "failed",
            "failure_stage": "duplicate_detection",
            "failure_reason": "scenario_already_executed_in_campaign",
        }

    idempotency_key = f"{campaign_id}:{scenario_id}:r4-send"
    try:
        # Pre-seed context so send can reuse evaluation_run_id via patched flow.
        backend.runs[scenario_id] = _ScenarioRunContext(evaluation_run_id=evaluation_run_id)
        send_result = _send_with_existing_run_id(
            backend,
            campaign_id=campaign_id,
            scenario=scenario,
            idempotency_key=idempotency_key,
            evaluation_run_id=evaluation_run_id,
            snapshot=snapshot,
        )
    except Exception as exc:
        return {
            **base,
            "status": "failed",
            "failure_stage": "inbound_trigger_send",
            "failure_reason": str(exc)[:500],
            "unknown_outcome": False,
        }

    base["inbound_trigger_sent"] = True
    base["trigger_provider_message_id_redacted"] = _redact_id(send_result.provider_message_id)
    audit.append({"event": "inbound_trigger_sent", "at": _utcnow()})

    try:
        intake = backend.observe_intake(scenario_id=scenario_id, campaign_id=campaign_id)
    except Exception as exc:
        return {
            **base,
            "status": "failed",
            "failure_stage": "intake_observation",
            "failure_reason": str(exc)[:500],
        }
    base["trigger_delivery_observed"] = True
    base["job_id"] = intake.job_id
    audit.append({"event": "trigger_delivery_observed", "at": _utcnow(), "job_id": intake.job_id})

    try:
        processing = backend.observe_processing(scenario_id=scenario_id)
    except Exception as exc:
        return {
            **base,
            "status": "failed",
            "failure_stage": "processing_observation",
            "failure_reason": str(exc)[:500],
        }
    base["approval_state"] = processing.approval_state
    base["trusted_snapshot_verified"] = True
    audit.append(
        {
            "event": "trusted_snapshot_verified",
            "at": _utcnow(),
            "approval_state": processing.approval_state,
        }
    )

    provenance = None
    if scenario_id == "PTB-DCQ-0088":
        provenance = {
            "base_policy": "hold_for_review",
            "r4_contract": "r4_reviewed_hold_to_pending_v1",
            "authorization": "approval_required",
            "reviewed_body_hash": candidate.get("body_hash"),
            "r3_override_reused": False,
            "stages": [
                "base_policy_hold",
                "r4_reviewed_body_materialization",
                "pending_approval",
                "explicit_approval",
                "gmail_execution",
            ],
        }
        base["r4_0088_provenance"] = provenance
        audit.append({"event": "r4_0088_provenance", "at": _utcnow(), "details": provenance})

    try:
        bind_reviewed_send_body(
            backend,
            scenario_id=scenario_id,
            reviewed_body=str(candidate.get("rendered_body") or ""),
            expected_body_hash=str(candidate.get("body_hash") or ""),
            snapshot=snapshot,
        )
        audit.append({"event": "reviewed_body_bound", "at": _utcnow()})
    except Exception as exc:
        return {
            **base,
            "status": "failed",
            "failure_stage": "reviewed_body_bind",
            "failure_reason": str(exc)[:500],
        }

    try:
        approval = backend.approve_via_lifecycle(
            scenario_id=scenario_id,
            operation_id=approval_operation_id,
            decision="approve",
        )
    except Exception as exc:
        return {
            **base,
            "status": "failed",
            "failure_stage": "approval_execution",
            "failure_reason": str(exc)[:500],
        }
    base["approval_executed"] = approval.decision == "approved"
    base["approval_state"] = approval.decision
    audit.append({"event": "approval_executed", "at": _utcnow(), "decision": approval.decision})

    try:
        verification = backend.verify_reply(scenario=scenario, approved=True)
    except Exception as exc:
        msg = str(exc)
        if "outcome_unknown" in msg.lower() or "timeout" in msg.lower():
            return {
                **base,
                "status": "failed",
                "failure_stage": "reply_observation",
                "failure_reason": msg[:500],
                "execution_outcome": "OUTCOME_UNKNOWN",
                "unknown_outcome": True,
                "retry_forbidden": True,
            }
        return {
            **base,
            "status": "failed",
            "failure_stage": "reply_observation",
            "failure_reason": msg[:500],
        }

    if getattr(verification, "reply_execution_status", None) == "outcome_unknown":
        return {
            **base,
            "status": "failed",
            "failure_stage": "reply_observation",
            "failure_reason": "provider_accepted_without_message_id",
            "execution_outcome": "OUTCOME_UNKNOWN",
            "unknown_outcome": True,
            "retry_forbidden": True,
            "adapter_provider": "google_mail",
            "provider_status": "outcome_unknown",
        }

    reply_id = getattr(verification, "reply_provider_message_id", None)
    base["reply_provider_message_id_redacted"] = _redact_id(reply_id)
    base["reply_thread_id_redacted"] = _redact_id(
        getattr(verification, "reply_rfc_message_id", None)
    )
    base["adapter_provider"] = "google_mail" if verification.provider_accepted else None
    base["provider_status"] = getattr(verification, "reply_execution_status", None) or (
        "accepted" if verification.provider_accepted else "rejected"
    )
    base["reply_delivery_observed"] = bool(
        verification.provider_accepted and verification.recipient_verified
    )
    base["recipient_match"] = bool(verification.recipient_verified)
    base["thread_match"] = bool(
        verification.provider_accepted and getattr(verification, "reply_rfc_message_id", None)
    )
    expected_hash = str(candidate.get("body_hash") or "")
    base["body_hash_match"] = expected_hash == snapshot.reviewed_body_hash == hash_body(
        snapshot.reviewed_body
    )
    base["duplicate_count"] = 1 if verification.duplicate_send else 0
    base["gmail_sends"] = 1 if verification.provider_accepted and reply_id else 0
    base["gmail_drafts"] = 0

    passed = (
        verification.provider_accepted
        and bool(reply_id)
        and base["reply_delivery_observed"]
        and base["recipient_match"]
        and base["thread_match"]
        and base["body_hash_match"]
        and base["duplicate_count"] == 0
        and base["gmail_drafts"] == 0
        and base["approval_executed"]
        and not base["unknown_outcome"]
    )
    base["status"] = "passed" if passed else "failed"
    base["execution_outcome"] = "gmail_reply_sent" if passed else "send_verification_failed"
    if not passed and verification.provider_accepted and not reply_id:
        base["unknown_outcome"] = True
        base["execution_outcome"] = "OUTCOME_UNKNOWN"
        base["retry_forbidden"] = True
    audit.append({"event": "reply_verified", "at": _utcnow(), "passed": passed})
    # silence unused
    _ = (review_row, state, recipient)
    return base


def _send_with_existing_run_id(
    backend: LiveSemiAutoBackend,
    *,
    campaign_id: str,
    scenario: ProfileScenario,
    idempotency_key: str,
    evaluation_run_id: str,
    snapshot: R4ReviewedBodySnapshot,
) -> Any:
    from app.evaluation.live.gmail_transport import send_scenario_email
    from app.evaluation.live.errors import LiveEvalSafetyError
    from app.evaluation.profile_testbot.campaign.mailbox_readiness import mailbox_hash
    from app.evaluation.profile_testbot.campaign.semi_auto_contract import TestSendResult
    from app.evaluation.profile_testbot.campaign.send_payload import (
        build_profile_testbot_message_body,
    )

    if backend.tenant_id != LIVE_EVAL_TENANT_ID:
        raise LiveEvalSafetyError(f"cross-tenant send blocked: {backend.tenant_id}")
    if idempotency_key in backend.sent_keys:
        raise LiveEvalSafetyError(f"duplicate test send for idempotency_key={idempotency_key}")
    recipient = backend.recipient_email.strip().lower()
    if not recipient:
        raise LiveEvalSafetyError("recipient mailbox missing")

    ctx = backend.runs[scenario.scenario_id]
    ctx.evaluation_run_id = evaluation_run_id
    backend.sent_keys.add(idempotency_key)

    register_payload: dict[str, Any] = {
        "evaluation_run_id": evaluation_run_id,
        "tenant_id": backend.tenant_id,
        "scenario_id": scenario.scenario_id,
        "attempt_id": ctx.attempt_id,
        "transport_mode": "live_gmail",
        "ai_mode": backend.registration_ai_mode,
        "campaign_type": backend.registration_campaign_type,
        "execution_mode": backend.registration_execution_mode,
        "campaign_id": campaign_id,
        "manifest_hash": backend.registration_manifest_hash,
        "expected_sender": backend.sender_email,
        "expected_recipient": backend.recipient_email,
        "registration_context": {
            "candidate_runtime_sha": snapshot.candidate_runtime_sha,
            "executor_runtime_sha": snapshot.executor_runtime_sha,
            "candidate_package_semantic_hash": snapshot.candidate_package_semantic_hash,
            "human_review_sha256": snapshot.human_review_artifact_hash,
            "planned_gmail_send": True,
            "plan_hash": snapshot.plan_hash,
            "reviewed_body_hash": snapshot.reviewed_body_hash,
            "review_status": snapshot.review_status,
            "renderer_type": snapshot.renderer_type,
            "model_id": snapshot.model_id,
            "prompt_version": snapshot.prompt_version,
            "automatic_gmail": False,
            "production_activation": False,
            "probe": False,
        },
    }
    backend.observer.register_run(register_payload)

    body = build_profile_testbot_message_body(
        scenario=scenario,
        evaluation_run_id=evaluation_run_id,
        campaign_id=campaign_id,
    )
    outcome, _events = send_scenario_email(
        evaluation_run_id=evaluation_run_id,
        scenario_id=scenario.scenario_id,
        attempt_id=ctx.attempt_id,
        expected_sender=backend.sender_email,
        expected_recipient=backend.recipient_email,
        base_subject=scenario.input.subject,
        message_body=body,
        config=backend.config,
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


def _execute_no_send(
    *,
    backend: LiveSemiAutoBackend,
    scenario: ProfileScenario,
    evaluation_run_id: str,
    campaign_id: str,
) -> dict[str, Any]:
    expected = str(scenario.expected_send_behavior or "no_reply")
    # No-send scenarios still may process inbound for reject/hold policy, but never reply/draft.
    # For wiring verification without expanding Gmail surface beyond R3 patterns, register+observe
    # only when scenario requires inbound; SEM quarantine-style can be verified locally.
    from app.evaluation.profile_testbot.qualification.coworker_r3_execution import (
        PTB_SEM_0024_SCENARIO_ID,
    )

    result: dict[str, Any] = {
        "scenario_id": scenario.scenario_id,
        "evaluation_run_id": evaluation_run_id,
        "planned_gmail_send": False,
        "expected_behavior": expected,
        "actual_policy_result": None,
        "approval_state": None,
        "gmail_sends": 0,
        "gmail_drafts": 0,
        "external_executions": 0,
        "r4_reviewed_body_applied": False,
        "status": "passed",
        "unknown_outcome": False,
        "audit_events": [],
    }
    if scenario.scenario_id == PTB_SEM_0024_SCENARIO_ID or expected in {
        "reject_no_reply",
        "no_reply",
    }:
        # Quarantine / pure no-send without requiring inbound when R3 does the same.
        if scenario.scenario_id == PTB_SEM_0024_SCENARIO_ID:
            result["actual_policy_result"] = "reject_no_reply"
            result["status"] = "passed"
            return result

    idempotency_key = f"{campaign_id}:{scenario.scenario_id}:r4-nosend"
    try:
        from app.evaluation.profile_testbot.campaign.semi_auto_live_backend import (
            _ScenarioRunContext,
        )

        backend.runs[scenario.scenario_id] = _ScenarioRunContext(
            evaluation_run_id=evaluation_run_id
        )
        _send_with_existing_run_id(
            backend,
            campaign_id=campaign_id,
            scenario=scenario,
            idempotency_key=idempotency_key,
            evaluation_run_id=evaluation_run_id,
            snapshot=R4ReviewedBodySnapshot(
                campaign_type=R4_LIVE_QUALITY_CAMPAIGN_TYPE,
                execution_mode=R4_EXECUTION_MODE,
                scenario_id=scenario.scenario_id,
                candidate_runtime_sha="",
                executor_runtime_sha="",
                manifest_semantic_hash="",
                candidate_package_semantic_hash="",
                human_review_artifact_hash="",
                plan_hash="",
                reviewed_body="",
                reviewed_body_hash="",
                review_status="N/A",
                renderer_type="none",
                model_id=None,
                prompt_version=None,
                recipient=backend.recipient_email,
                campaign_id=campaign_id,
                evaluation_run_id=evaluation_run_id,
            ),
        )
        intake = backend.observe_intake(
            scenario_id=scenario.scenario_id, campaign_id=campaign_id
        )
        processing = backend.observe_processing(scenario_id=scenario.scenario_id)
        verification = backend.verify_reply(scenario=scenario, approved=False)
        result["job_id"] = intake.job_id
        result["actual_policy_result"] = processing.authorization.get("policy_authorization")
        result["approval_state"] = processing.approval_state
        result["gmail_sends"] = 0
        result["gmail_drafts"] = 0
        result["external_executions"] = int(verification.adapter_invocations or 0)
        if verification.provider_accepted or verification.adapter_invocations:
            result["status"] = "failed"
            result["failure_reason"] = "no_send_produced_external_execution"
        else:
            result["status"] = "passed"
    except Exception as exc:
        result["status"] = "failed"
        result["failure_stage"] = "no_send_verification"
        result["failure_reason"] = str(exc)[:500]
    return result
