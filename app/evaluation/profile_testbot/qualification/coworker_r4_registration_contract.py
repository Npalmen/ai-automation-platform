"""Fail-closed R4 reviewed-live registration contract (separate from R3)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.profile_testbot.qualification.coworker_r4_attempt1_orphan import (
    assert_r4_campaign_not_quarantined,
    assert_r4_evaluation_run_not_quarantined,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (
    R4_EXECUTE_AI_MODE,
    R4_EXECUTION_MODE,
    R4_LIVE_QUALITY_CAMPAIGN_TYPE,
    R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH,
    R4_LOCKED_CANDIDATE_RUNTIME_SHA,
    R4_LOCKED_MANIFEST_SEMANTIC_HASH,
    R4_LOCKED_REVIEW_ARTIFACT_SHA256,
    R4_NO_SEND_SCENARIO_IDS,
    R4_SCENARIO_IDS,
    R4_SEND_MAX,
    R4_SEND_SCENARIO_IDS,
    R4_TENANT_ID,
)

# Official shared AI-mode constant (also mirrored in live.constants.ALLOWED_AI_MODES).
REVIEWED_LIVE_LLM_BODY = R4_EXECUTE_AI_MODE

R4_REGISTRATION_TRANSPORT = "live_gmail"
R4_ALLOWED_REVIEW_STATUSES = frozenset({"PASS", "PASS_WITH_NOTE"})
R4_REQUIRED_RENDERER_TYPE = "constrained_llm_v1"


class R4RegistrationContext(BaseModel):
    """Authoritative R4 binding persisted on live_eval_runs.registration_context."""

    model_config = ConfigDict(extra="forbid")

    candidate_runtime_sha: str
    executor_runtime_sha: str
    candidate_package_semantic_hash: str
    human_review_sha256: str
    planned_gmail_send: bool
    plan_hash: str | None = None
    reviewed_body_hash: str | None = None
    review_status: str | None = None
    renderer_type: str | None = None
    model_id: str | None = None
    prompt_version: str | None = None
    automatic_gmail: bool = False
    production_activation: bool = False
    probe: bool = False


@dataclass(frozen=True)
class R4RegistrationContractRequest:
    tenant_id: str
    scenario_id: str
    transport_mode: str
    ai_mode: str
    campaign_type: str | None = None
    execution_mode: str | None = None
    expected_sender: str | None = None
    expected_recipient: str | None = None
    manifest_hash: str | None = None
    campaign_id: str | None = None
    evaluation_run_id: str | None = None
    registration_context: R4RegistrationContext | dict[str, Any] | None = None
    env_name: str | None = None
    sender_allowlist: frozenset[str] | set[str] | list[str] | None = None
    recipient_allowlist: frozenset[str] | set[str] | list[str] | None = None


@dataclass
class R4RegistrationValidationResult:
    registration_contract_valid: bool = False
    campaign_type_valid: bool = False
    execution_mode_valid: bool = False
    scenario_registry_valid: bool = False
    live_gmail_policy_valid: bool = False
    registration_blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "registration_contract_valid": self.registration_contract_valid,
            "campaign_type_valid": self.campaign_type_valid,
            "execution_mode_valid": self.execution_mode_valid,
            "scenario_registry_valid": self.scenario_registry_valid,
            "live_gmail_policy_valid": self.live_gmail_policy_valid,
            "registration_blockers": list(self.registration_blockers),
        }


def is_r4_reviewed_live_ai_mode(ai_mode: str | None) -> bool:
    return (ai_mode or "").strip() == REVIEWED_LIVE_LLM_BODY


def is_r4_registration_campaign(campaign_type: str | None) -> bool:
    return (campaign_type or "").strip() == R4_LIVE_QUALITY_CAMPAIGN_TYPE


def is_r4_registry_scenario(scenario_id: str) -> bool:
    return scenario_id in R4_SCENARIO_IDS


def is_r4_send_scenario(scenario_id: str) -> bool:
    return scenario_id in R4_SEND_SCENARIO_IDS


def is_r4_no_send_scenario(scenario_id: str) -> bool:
    return scenario_id in R4_NO_SEND_SCENARIO_IDS


def parse_r4_registration_context(
    raw: R4RegistrationContext | dict[str, Any] | None,
) -> R4RegistrationContext | None:
    if raw is None:
        return None
    if isinstance(raw, R4RegistrationContext):
        return raw
    return R4RegistrationContext.model_validate(raw)


def _normalize_email(value: str | None) -> str:
    return (value or "").strip().lower()


def validate_r4_registration_contract(
    request: R4RegistrationContractRequest,
) -> R4RegistrationValidationResult:
    blockers: list[str] = []
    env_name = (request.env_name if request.env_name is not None else os.environ.get("ENV", "")).strip()
    if env_name != "test":
        blockers.append(f"ENV {env_name!r} != test")

    campaign_type_valid = request.campaign_type == R4_LIVE_QUALITY_CAMPAIGN_TYPE
    execution_mode_valid = (
        request.ai_mode == REVIEWED_LIVE_LLM_BODY
        and request.execution_mode == R4_EXECUTION_MODE
    )
    scenario_registry_valid = request.scenario_id in R4_SCENARIO_IDS
    live_gmail_policy_valid = (
        request.transport_mode == R4_REGISTRATION_TRANSPORT
        and request.ai_mode == REVIEWED_LIVE_LLM_BODY
    )

    if request.tenant_id != R4_TENANT_ID:
        blockers.append(f"tenant {request.tenant_id!r} != {R4_TENANT_ID}")
    if not campaign_type_valid:
        blockers.append(
            f"campaign_type {request.campaign_type!r} != {R4_LIVE_QUALITY_CAMPAIGN_TYPE!r}"
        )
    if not execution_mode_valid:
        blockers.append(
            f"execution_mode/ai_mode must be {R4_EXECUTION_MODE!r}/{REVIEWED_LIVE_LLM_BODY!r}, "
            f"got execution_mode={request.execution_mode!r} ai_mode={request.ai_mode!r}"
        )
    if request.transport_mode != R4_REGISTRATION_TRANSPORT:
        blockers.append(f"transport_mode {request.transport_mode!r} != live_gmail")
    if not scenario_registry_valid:
        blockers.append(f"scenario_id {request.scenario_id!r} not in R4 registry")
    if request.manifest_hash != R4_LOCKED_MANIFEST_SEMANTIC_HASH:
        blockers.append("manifest_hash mismatch")

    try:
        assert_r4_campaign_not_quarantined(request.campaign_id)
        assert_r4_evaluation_run_not_quarantined(request.evaluation_run_id)
    except LiveEvalSafetyError as exc:
        blockers.append(str(exc))

    sender = _normalize_email(request.expected_sender)
    recipient = _normalize_email(request.expected_recipient)
    if request.sender_allowlist is not None:
        allow_s = {_normalize_email(x) for x in request.sender_allowlist}
        if not sender or sender not in allow_s:
            blockers.append("expected_sender not in sender allowlist")
    elif not sender:
        blockers.append("expected_sender missing")
    if request.recipient_allowlist is not None:
        allow_r = {_normalize_email(x) for x in request.recipient_allowlist}
        if not recipient or recipient not in allow_r:
            blockers.append("expected_recipient not in recipient allowlist")
    elif not recipient:
        blockers.append("expected_recipient missing")

    ctx: R4RegistrationContext | None = None
    try:
        ctx = parse_r4_registration_context(request.registration_context)
    except Exception as exc:
        blockers.append(f"registration_context_invalid:{type(exc).__name__}")

    if ctx is None:
        blockers.append("registration_context missing")
    else:
        if ctx.automatic_gmail:
            blockers.append("automatic_gmail must be false")
        if ctx.production_activation:
            blockers.append("production_activation must be false")
        if ctx.candidate_runtime_sha != R4_LOCKED_CANDIDATE_RUNTIME_SHA:
            blockers.append("candidate_runtime_sha mismatch")
        if not (ctx.executor_runtime_sha or "").strip():
            blockers.append("executor_runtime_sha missing")
        if ctx.candidate_package_semantic_hash != R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH:
            blockers.append("candidate_package_semantic_hash mismatch")
        if ctx.human_review_sha256 != R4_LOCKED_REVIEW_ARTIFACT_SHA256:
            blockers.append("human_review_sha256 mismatch")

        expected_send = is_r4_send_scenario(request.scenario_id)
        if ctx.planned_gmail_send != expected_send:
            blockers.append(
                f"planned_gmail_send mismatch for {request.scenario_id}: "
                f"planned={ctx.planned_gmail_send}, registry_send={expected_send}"
            )

        if expected_send:
            if not ctx.plan_hash:
                blockers.append("plan_hash required for send scenario")
            if not ctx.reviewed_body_hash:
                blockers.append("reviewed_body_hash required for send scenario")
            if ctx.review_status not in R4_ALLOWED_REVIEW_STATUSES:
                blockers.append(f"review_status not accepted: {ctx.review_status!r}")
            if ctx.renderer_type != R4_REQUIRED_RENDERER_TYPE:
                blockers.append("renderer_type must be constrained_llm_v1")
            if not (ctx.model_id or "").strip():
                blockers.append("model_id required for send scenario")
            if not (ctx.prompt_version or "").strip():
                blockers.append("prompt_version required for send scenario")
        else:
            if ctx.planned_gmail_send:
                blockers.append("no-send scenario cannot plan gmail send")
            if ctx.reviewed_body_hash:
                blockers.append("no-send scenario must not include reviewed_body_hash")
            if ctx.plan_hash:
                blockers.append("no-send scenario must not include plan_hash")
            if ctx.review_status:
                blockers.append("no-send scenario must not include review_status")
            if ctx.renderer_type:
                blockers.append("no-send scenario must not include renderer_type")

    if not live_gmail_policy_valid:
        blockers.append("R4 live Gmail policy invalid")

    # Locked send/no-send cardinality invariants (campaign-level).
    if len(R4_SEND_SCENARIO_IDS) != R4_SEND_MAX:
        blockers.append("R4 send registry cardinality drift")
    if len(R4_NO_SEND_SCENARIO_IDS) != 16:
        blockers.append("R4 no-send registry cardinality drift")

    valid = not blockers
    return R4RegistrationValidationResult(
        registration_contract_valid=valid,
        campaign_type_valid=campaign_type_valid,
        execution_mode_valid=execution_mode_valid,
        scenario_registry_valid=scenario_registry_valid,
        live_gmail_policy_valid=live_gmail_policy_valid,
        registration_blockers=blockers,
    )


def require_r4_registration_contract(
    request: R4RegistrationContractRequest,
) -> R4RegistrationValidationResult:
    result = validate_r4_registration_contract(request)
    if not result.registration_contract_valid:
        raise LiveEvalSafetyError("; ".join(result.registration_blockers))
    return result


def r4_registration_context_for_config_hash(ctx: R4RegistrationContext) -> dict[str, Any]:
    """Semantic binding for config_hash (excludes probe-only noise)."""
    payload = ctx.model_dump()
    payload.pop("probe", None)
    return payload
