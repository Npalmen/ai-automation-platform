"""Live inbox quality campaign runner (Gates Q6/Q7)."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from app.core.canonical_commit import resolve_canonical_commit
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.profile_testbot.campaign.readiness import build_profile_testbot_readiness
from app.evaluation.profile_testbot.campaign.scenario_gate import (
    require_live_quality_runner_execution,
)
from app.evaluation.profile_testbot.campaign.semi_auto_contract import (
    ContractSemiAutoBackend,
    ReplyVerification,
)
from app.evaluation.profile_testbot.campaign.semi_auto_evidence import (
    build_campaign_evidence,
    write_campaign_evidence_report,
)
from app.evaluation.profile_testbot.campaign.semi_auto_live_backend import LiveSemiAutoBackend
from app.evaluation.profile_testbot.campaign.semi_auto_safety import (
    assert_hold_scenario_no_send,
    assert_no_external_writes,
    assert_tenant_isolated,
)
from app.evaluation.profile_testbot.campaign.semi_auto_state import (
    CampaignState,
    ScenarioExecutionState,
    SemiAutoCampaignState,
)
from app.evaluation.profile_testbot.campaign.semi_auto_store import (
    count_campaign_rows,
    delete_campaign_state,
    load_campaign_state,
    save_campaign_state,
)
from app.evaluation.profile_testbot.constants import (
    LIVE_EVAL_TENANT_ID,
    ORACLE_VERSION,
    QUALITY_LIVE_PROFILE_ID,
)
from app.evaluation.profile_testbot.harness.quality_harness import evaluate_quality_harness_decision
from app.evaluation.profile_testbot.oracles.hard_safety import HardSafetyContext
from app.evaluation.profile_testbot.oracles.quality_result import aggregate_quality_score
from app.evaluation.profile_testbot.profile_contract import CustomerProfileSnapshot, load_customer_profile
from app.evaluation.profile_testbot.qualification.constants import (
    SEND_BEHAVIORS_COUNTING_AS_GMAIL_SEND,
)
from app.evaluation.profile_testbot.qualification.live_campaign_manifest import (
    build_live_quality_campaign_manifest,
)
from app.evaluation.profile_testbot.qualification.live_canary_manifest import (
    build_live_quality_canary_manifest,
)
from app.evaluation.profile_testbot.quality_gates import evaluate_quality_oracles
from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario

QualityCampaignKind = Literal["canary", "campaign"]


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("yes", "true", "1")


def _manifest_hash(scenario_ids: list[str]) -> str:
    payload = json.dumps(sorted(scenario_ids), separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _scenario_execution_id(campaign_id: str, scenario_id: str) -> str:
    return hashlib.sha256(f"{campaign_id}:{scenario_id}".encode("utf-8")).hexdigest()[:16]


def _load_manifest(
    *,
    kind: QualityCampaignKind,
    profile_id: str,
    seed: int,
) -> tuple[list[ProfileScenario], int, str]:
    if kind == "canary":
        manifest = build_live_quality_canary_manifest(profile_id=profile_id, seed=seed)
    else:
        manifest = build_live_quality_campaign_manifest(profile_id=profile_id, seed=seed)
    return manifest.scenarios, manifest.send_budget, manifest.campaign_type


@dataclass
class QualityRunnerConfig:
    campaign_id: str
    runtime_sha: str
    campaign_kind: QualityCampaignKind
    profile_id: str = QUALITY_LIVE_PROFILE_ID
    tenant_id: str = LIVE_EVAL_TENANT_ID
    seed: int = 0
    contract_mode: bool = False
    confirm_external: bool = False
    state_root: str | Path | None = None
    sender_email: str = ""
    recipient_email: str = ""
    base_url: str = ""
    admin_api_key: str = ""


@dataclass
class QualityRunnerResult:
    overall_status: str
    campaign_id: str
    campaign_kind: str
    runtime_sha: str
    scenario_count: int
    scenarios_passed: int
    send_budget_used: int
    send_budget_max: int
    qualification_status: str = "PENDING"
    failure_reason: str | None = None
    evidence_path: str | None = None
    scenario_results: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_status": self.overall_status,
            "campaign_id": self.campaign_id,
            "campaign_kind": self.campaign_kind,
            "runtime_sha": self.runtime_sha,
            "scenario_count": self.scenario_count,
            "scenarios_passed": self.scenarios_passed,
            "send_budget_used": self.send_budget_used,
            "send_budget_max": self.send_budget_max,
            "qualification_status": self.qualification_status,
            "failure_reason": self.failure_reason,
            "evidence_path": self.evidence_path,
            "scenario_results": self.scenario_results,
        }


def _resolve_runtime_sha(runtime_sha: str | None) -> str:
    return (runtime_sha or resolve_canonical_commit() or "unknown").strip()


def _customer_draft_created(*, scenario: ProfileScenario, approval_state: str, draft_text: str) -> bool:
    if bool(draft_text):
        return True
    if scenario.expected_send_behavior in {"hold", "observe_only"}:
        return False
    if scenario.expected_send_behavior in {"reject", "no_reply"}:
        return approval_state == "pending"
    if scenario.expected_send_behavior == "draft_for_approval":
        return approval_state == "pending"
    if scenario.expected_send_behavior in SEND_BEHAVIORS_COUNTING_AS_GMAIL_SEND:
        return approval_state == "pending"
    return False


def _prepare_campaign_state(
    config: QualityRunnerConfig,
    *,
    scenarios: list[ProfileScenario],
    manifest_hash: str,
) -> SemiAutoCampaignState:
    readiness = build_profile_testbot_readiness(
        profile_id=config.profile_id,
        tenant_id=config.tenant_id,
        seed=config.seed,
    )
    if not readiness.get("runner_ready_for_live_quality_execution"):
        blockers = readiness.get("live_quality_execution_blockers") or []
        raise LiveEvalSafetyError(
            "quality readiness failed: " + "; ".join(blockers or ["unknown"])
        )

    profile = load_customer_profile(config.profile_id)
    scenario_ids = [scenario.scenario_id for scenario in scenarios]
    if profile.profile_snapshot_hash != readiness.get("profile_snapshot_hash"):
        raise LiveEvalSafetyError("profile snapshot hash mismatch")

    existing = load_campaign_state(config.campaign_id, root=config.state_root)
    if existing is not None:
        if existing.runtime_sha != config.runtime_sha:
            raise LiveEvalSafetyError("runtime SHA mismatch for existing campaign")
        if existing.manifest_hash != manifest_hash:
            raise LiveEvalSafetyError("manifest hash mismatch for existing campaign")
        return existing

    state = SemiAutoCampaignState(
        campaign_id=config.campaign_id,
        runtime_sha=config.runtime_sha,
        profile_id=profile.profile_id,
        profile_snapshot_hash=profile.profile_snapshot_hash,
        manifest_hash=manifest_hash,
        oracle_version=ORACLE_VERSION,
        tenant_id=config.tenant_id,
        contract_mode=config.contract_mode,
        state=CampaignState.READINESS_VERIFIED,
    )
    for scenario in scenarios:
        state.scenario_states[scenario.scenario_id] = ScenarioExecutionState(
            scenario_id=scenario.scenario_id,
            execution_id=_scenario_execution_id(config.campaign_id, scenario.scenario_id),
        )
    save_campaign_state(state, root=config.state_root)
    return state


def run_profile_quality_live_campaign(
    config: QualityRunnerConfig,
    *,
    resume: bool = False,
) -> QualityRunnerResult:
    config.runtime_sha = _resolve_runtime_sha(config.runtime_sha)
    assert_tenant_isolated(config.tenant_id)

    if config.confirm_external and not config.contract_mode:
        blocked = require_live_quality_runner_execution(runtime_sha=config.runtime_sha)
        if blocked:
            raise LiveEvalSafetyError(blocked)
        if not _env_truthy("LIVE_GMAIL_EVAL_ALLOWED"):
            raise LiveEvalSafetyError("LIVE_GMAIL_EVAL_ALLOWED=yes required for live execution")
        if not _env_truthy("PROFILE_TESTBOT_LIVE_QUALITY_APPROVED"):
            raise LiveEvalSafetyError("PROFILE_TESTBOT_LIVE_QUALITY_APPROVED=yes required")
        if not config.base_url or not config.admin_api_key:
            raise LiveEvalSafetyError(
                "LIVE_EVAL_APP_BASE_URL and ADMIN_API_KEY required for live execution"
            )

    if not config.contract_mode and not config.confirm_external:
        raise LiveEvalSafetyError("live execution requires confirm_external")

    profile = load_customer_profile(config.profile_id)
    scenarios, send_budget_max, campaign_type = _load_manifest(
        kind=config.campaign_kind,
        profile_id=config.profile_id,
        seed=config.seed,
    )
    manifest_hash = _manifest_hash([s.scenario_id for s in scenarios])
    campaign_state = _prepare_campaign_state(
        config,
        scenarios=scenarios,
        manifest_hash=manifest_hash,
    )

    if config.contract_mode:
        backend: ContractSemiAutoBackend | LiveSemiAutoBackend = ContractSemiAutoBackend(
            tenant_id=config.tenant_id,
            sender_email=config.sender_email,
            recipient_email=config.recipient_email,
        )
    else:
        backend = LiveSemiAutoBackend(
            campaign_id=config.campaign_id,
            tenant_id=config.tenant_id,
            sender_email=config.sender_email,
            recipient_email=config.recipient_email,
            base_url=config.base_url,
            admin_api_key=config.admin_api_key,
        )

    scenario_results: list[dict[str, Any]] = []
    passed = 0
    failure_reason: str | None = None

    for scenario in scenarios:
        scenario_state = campaign_state.scenario_states[scenario.scenario_id]
        if resume and scenario_state.state == CampaignState.SCENARIO_VERIFIED:
            passed += 1
            scenario_results.append(scenario_state.to_dict())
            continue

        try:
            result = _execute_quality_scenario(
                config=config,
                campaign_state=campaign_state,
                scenario_state=scenario_state,
                scenario=scenario,
                backend=backend,
                profile=profile,
                send_budget_max=send_budget_max,
            )
            scenario_results.append(result)
            if result.get("state") == CampaignState.SCENARIO_VERIFIED.value:
                passed += 1
            else:
                failure_reason = result.get("failure_reason") or "scenario failed"
                campaign_state.state = CampaignState.CAMPAIGN_ABORTED
                campaign_state.failure_reason = failure_reason
                save_campaign_state(campaign_state, root=config.state_root)
                break
        except LiveEvalSafetyError as exc:
            scenario_state.state = CampaignState.CAMPAIGN_ABORTED
            scenario_state.failure_reason = str(exc)
            campaign_state.state = CampaignState.CAMPAIGN_ABORTED
            campaign_state.failure_reason = str(exc)
            save_campaign_state(campaign_state, root=config.state_root)
            scenario_results.append(scenario_state.to_dict())
            failure_reason = str(exc)
            break

        save_campaign_state(campaign_state, root=config.state_root)

    if failure_reason is None and passed == len(scenarios):
        campaign_state.state = CampaignState.CAMPAIGN_COMPLETED
        save_campaign_state(campaign_state, root=config.state_root)
        rows_before = count_campaign_rows(root=config.state_root)
        deleted = delete_campaign_state(config.campaign_id, root=config.state_root)
        rows_after = count_campaign_rows(root=config.state_root)
        cleanup = {
            "campaign_rows_before": rows_before,
            "campaign_rows_after": rows_after,
            "campaign_row_deleted": deleted,
        }
    else:
        cleanup = {
            "campaign_rows_before": count_campaign_rows(root=config.state_root),
            "campaign_rows_after": count_campaign_rows(root=config.state_root),
            "campaign_row_deleted": False,
        }

    overall = "PASS" if failure_reason is None and passed == len(scenarios) else "FAIL"
    evidence_payload = build_campaign_evidence(
        campaign_state={
            **campaign_state.to_dict(),
            "overall_status": overall,
            "campaign_kind": config.campaign_kind,
            "campaign_type": campaign_type,
        },
        scenario_results=scenario_results,
        external_writes=dict(backend.external_writes),
        tenant_isolation={
            "tenant_id": config.tenant_id,
            "blocked_tenants_respected": True,
        },
        cleanup=cleanup,
    )
    evidence_path = write_campaign_evidence_report(
        campaign_id=config.campaign_id,
        payload=evidence_payload,
    )

    return QualityRunnerResult(
        overall_status=overall,
        campaign_id=config.campaign_id,
        campaign_kind=config.campaign_kind,
        runtime_sha=config.runtime_sha,
        scenario_count=len(scenarios),
        scenarios_passed=passed,
        send_budget_used=campaign_state.send_budget_used,
        send_budget_max=send_budget_max,
        qualification_status="PENDING",
        failure_reason=failure_reason,
        evidence_path=str(evidence_path),
        scenario_results=scenario_results,
    )


def _apply_reply_evidence(scenario_state: ScenarioExecutionState, reply: ReplyVerification) -> None:
    for key in (
        "inbound_provider_message_id",
        "inbound_rfc_message_id",
        "reply_provider_message_id",
        "reply_rfc_message_id",
        "reply_thread_id",
        "reply_in_reply_to",
        "reply_references",
        "thread_match_basis",
        "reply_action_operation_id",
        "reply_execution_status",
        "reply_provider_outcome",
    ):
        value = getattr(reply, key, None)
        if value:
            scenario_state.evidence[key] = value
    scenario_state.evidence["thread_match"] = bool(getattr(reply, "thread_match", False))
    if reply.reply_hash:
        scenario_state.evidence["reply_hash"] = reply.reply_hash


def _execute_quality_scenario(
    *,
    config: QualityRunnerConfig,
    campaign_state: SemiAutoCampaignState,
    scenario_state: ScenarioExecutionState,
    scenario: ProfileScenario,
    backend: ContractSemiAutoBackend | LiveSemiAutoBackend,
    profile: CustomerProfileSnapshot,
    send_budget_max: int,
) -> dict[str, Any]:
    if scenario_state.state == CampaignState.SCENARIO_VERIFIED:
        return scenario_state.to_dict()

    if campaign_state.send_budget_used >= send_budget_max:
        if scenario.expected_send_behavior in SEND_BEHAVIORS_COUNTING_AS_GMAIL_SEND:
            raise LiveEvalSafetyError("send budget exhausted before send scenario")

    idempotency_key = scenario_state.test_send_idempotency_key or (
        f"{config.campaign_id}:{scenario.scenario_id}:send"
    )
    if scenario_state.state.value in {CampaignState.SCENARIO_QUEUED.value, CampaignState.CREATED.value}:
        if idempotency_key in backend.sent_keys:
            raise LiveEvalSafetyError("duplicate test send on resume")
        send_result = backend.send_test_message(
            campaign_id=config.campaign_id,
            scenario=scenario,
            idempotency_key=idempotency_key,
        )
        scenario_state.test_send_idempotency_key = send_result.idempotency_key
        scenario_state.state = CampaignState.TEST_MESSAGE_SENT
        scenario_state.evidence["inbound_provider_message_id"] = (
            send_result.inbound_provider_message_id or send_result.provider_message_id
        )
        if send_result.inbound_rfc_message_id:
            scenario_state.evidence["inbound_rfc_message_id"] = send_result.inbound_rfc_message_id

    intake = backend.observe_intake(scenario_id=scenario.scenario_id, campaign_id=config.campaign_id)
    if intake.tenant_id != config.tenant_id:
        raise LiveEvalSafetyError("cross-tenant intake")
    scenario_state.state = CampaignState.INTAKE_OBSERVED

    processing = backend.observe_processing(scenario_id=scenario.scenario_id)
    scenario_state.state = CampaignState.PROCESSING_OBSERVED

    draft_created = _customer_draft_created(
        scenario=scenario,
        approval_state=processing.approval_state,
        draft_text=processing.draft_text,
    )
    safety_context = HardSafetyContext(
        tenant_id=config.tenant_id,
        recipient_email=config.recipient_email or scenario.input.sender_email,
        sender_allowlist={
            scenario.input.sender_email.lower(),
            *({config.sender_email.lower()} if config.sender_email else set()),
        },
        recipient_allowlist={
            *({config.recipient_email.lower()} if config.recipient_email else set()),
        },
        gmail_sends=backend.gmail_sends,
        draft_text=processing.draft_text,
        reply_text=processing.draft_text,
    )
    evaluation = evaluate_quality_oracles(
        scenario=scenario,
        profile=profile,
        safety_context=safety_context,
        reply_text=processing.draft_text,
        customer_draft_created=draft_created,
    )
    score = aggregate_quality_score(evaluation.results)
    scenario_state.oracle_passed = evaluation.passed and score["overall_pass"]
    scenario_state.evidence["quality_oracles"] = evaluation.to_dict()
    scenario_state.evidence["quality_score"] = score
    scenario_state.state = CampaignState.ORACLE_EVALUATED

    if not evaluation.passed or not score["overall_pass"]:
        scenario_state.state = CampaignState.ORACLE_FAILED
        scenario_state.failure_reason = "; ".join(evaluation.blockers) or "quality oracle failed"
        return scenario_state.to_dict()

    harness = evaluate_quality_harness_decision(
        scenario=scenario,
        evaluation=evaluation,
        approval_state=processing.approval_state,
        send_budget_remaining=send_budget_max - campaign_state.send_budget_used,
        recipient_allowlisted=bool(config.recipient_email),
    )
    scenario_state.state = CampaignState.AWAITING_HARNESS_DECISION
    approved = False
    if harness.approved:
        operation_id = scenario_state.approval_operation_id or (
            f"{config.campaign_id}:{scenario.scenario_id}:approval"
        )
        approval = backend.approve_via_lifecycle(
            scenario_id=scenario.scenario_id,
            operation_id=operation_id,
            decision="approve",
        )
        if approval.already_resolved:
            raise LiveEvalSafetyError("duplicate harness approval")
        scenario_state.approval_operation_id = approval.operation_id
        scenario_state.approval_decision = approval.decision
        approved = True
        if approval.reply_action_operation_id:
            scenario_state.reply_operation_id = approval.reply_action_operation_id
    else:
        scenario_state.approval_decision = harness.decision
    scenario_state.state = CampaignState.APPROVED_OR_REJECTED

    inbound_provider_message_id = scenario_state.evidence.get("inbound_provider_message_id")
    inbound_rfc_message_id = scenario_state.evidence.get("inbound_rfc_message_id")
    reply = backend.verify_reply(
        scenario=scenario,
        approved=approved,
        inbound_provider_message_id=inbound_provider_message_id,
        inbound_rfc_message_id=inbound_rfc_message_id,
    )
    _apply_reply_evidence(scenario_state, reply)
    assert_hold_scenario_no_send(
        scenario=scenario,
        sends=scenario_state.sends,
        adapter_invocations=reply.adapter_invocations,
    )
    if reply.duplicate_send:
        raise LiveEvalSafetyError("duplicate send detected")

    if scenario.expected_send_behavior in SEND_BEHAVIORS_COUNTING_AS_GMAIL_SEND and approved:
        if reply.reply_execution_status in {"skipped", "failed", "outcome_unknown", "not_observed"}:
            scenario_state.state = CampaignState.SEND_FAILED
            scenario_state.failure_reason = (
                f"reply execution {reply.reply_execution_status or 'not_observed'}"
            )
            return scenario_state.to_dict()
        if reply.provider_accepted and not reply.recipient_verified:
            scenario_state.state = CampaignState.RECIPIENT_MISMATCH
            scenario_state.failure_reason = "recipient verification failed"
            return scenario_state.to_dict()
        if not reply.provider_accepted:
            scenario_state.state = CampaignState.SEND_FAILED
            scenario_state.failure_reason = "reply execution not provider accepted"
            return scenario_state.to_dict()
        scenario_state.sends = 1
        campaign_state.send_budget_used += 1

    scenario_state.replies = reply.adapter_invocations
    scenario_state.state = CampaignState.REPLY_OBSERVED_OR_NO_SEND_VERIFIED
    scenario_state.state = CampaignState.SCENARIO_VERIFIED
    assert_no_external_writes(backend)
    return scenario_state.to_dict()


def new_quality_campaign_id() -> str:
    return str(uuid.uuid4())
