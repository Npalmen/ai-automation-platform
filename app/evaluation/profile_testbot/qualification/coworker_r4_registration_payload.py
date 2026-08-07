"""Authoritative R4 live registration payload builder (execute + readiness)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from app.evaluation.live.config import LiveEvalConfig, get_live_eval_config
from app.evaluation.live.schemas import LiveEvalRunRegisterRequest
from app.evaluation.profile_testbot.qualification.coworker_r4_registration_contract import (
    R4RegistrationContext,
    R4RegistrationContractRequest,
    validate_r4_registration_contract,
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
    R4_SEND_SCENARIO_IDS,
    R4_TENANT_ID,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_reviewed_snapshot import (
    R4ReviewedBodySnapshot,
)


@dataclass(frozen=True)
class R4RegistrationCampaignBindings:
    campaign_id: str
    tenant_id: str
    candidate_runtime_sha: str
    executor_runtime_sha: str
    manifest_semantic_hash: str
    candidate_package_semantic_hash: str
    human_review_sha256: str
    expected_sender: str
    expected_recipient: str


@dataclass(frozen=True)
class R4SendRegistrationFields:
    plan_hash: str
    reviewed_body_hash: str
    review_status: str
    renderer_type: str
    model_id: str
    prompt_version: str


def r4_registration_campaign_bindings(
    *,
    campaign_id: str,
    candidate_runtime_sha: str,
    executor_runtime_sha: str,
    expected_sender: str,
    expected_recipient: str,
    manifest_semantic_hash: str = R4_LOCKED_MANIFEST_SEMANTIC_HASH,
    candidate_package_semantic_hash: str = R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH,
    human_review_sha256: str = R4_LOCKED_REVIEW_ARTIFACT_SHA256,
    tenant_id: str = R4_TENANT_ID,
) -> R4RegistrationCampaignBindings:
    return R4RegistrationCampaignBindings(
        campaign_id=campaign_id,
        tenant_id=tenant_id,
        candidate_runtime_sha=candidate_runtime_sha,
        executor_runtime_sha=executor_runtime_sha,
        manifest_semantic_hash=manifest_semantic_hash,
        candidate_package_semantic_hash=candidate_package_semantic_hash,
        human_review_sha256=human_review_sha256,
        expected_sender=expected_sender.strip().lower(),
        expected_recipient=expected_recipient.strip().lower(),
    )


def send_registration_fields_from_candidate(
    candidate: dict[str, Any],
    review_row: dict[str, Any],
) -> R4SendRegistrationFields:
    model_id = candidate.get("model_id") or candidate.get("returned_model_id")
    return R4SendRegistrationFields(
        plan_hash=str(candidate.get("plan_hash") or ""),
        reviewed_body_hash=str(candidate.get("body_hash") or ""),
        review_status=str(review_row.get("review_status") or ""),
        renderer_type=str(candidate.get("renderer_type") or ""),
        model_id=str(model_id or ""),
        prompt_version=str(candidate.get("prompt_version") or ""),
    )


def send_registration_fields_from_snapshot(
    snapshot: R4ReviewedBodySnapshot,
) -> R4SendRegistrationFields:
    return R4SendRegistrationFields(
        plan_hash=snapshot.plan_hash,
        reviewed_body_hash=snapshot.reviewed_body_hash,
        review_status=snapshot.review_status,
        renderer_type=snapshot.renderer_type,
        model_id=str(snapshot.model_id or ""),
        prompt_version=str(snapshot.prompt_version or ""),
    )


def build_r4_registration_context(
    bindings: R4RegistrationCampaignBindings,
    *,
    scenario_id: str,
    planned_gmail_send: bool,
    send_fields: R4SendRegistrationFields | None = None,
    probe: bool = False,
) -> R4RegistrationContext:
    if planned_gmail_send:
        if send_fields is None:
            raise ValueError("send_fields required when planned_gmail_send=true")
        return R4RegistrationContext(
            candidate_runtime_sha=bindings.candidate_runtime_sha,
            executor_runtime_sha=bindings.executor_runtime_sha,
            candidate_package_semantic_hash=bindings.candidate_package_semantic_hash,
            human_review_sha256=bindings.human_review_sha256,
            planned_gmail_send=True,
            plan_hash=send_fields.plan_hash,
            reviewed_body_hash=send_fields.reviewed_body_hash,
            review_status=send_fields.review_status,
            renderer_type=send_fields.renderer_type,
            model_id=send_fields.model_id,
            prompt_version=send_fields.prompt_version,
            automatic_gmail=False,
            production_activation=False,
            probe=probe,
        )
    if scenario_id not in R4_NO_SEND_SCENARIO_IDS:
        raise ValueError(f"scenario {scenario_id} is not a registered no-send scenario")
    if send_fields is not None:
        raise ValueError("send_fields forbidden for no-send registration")
    return R4RegistrationContext(
        candidate_runtime_sha=bindings.candidate_runtime_sha,
        executor_runtime_sha=bindings.executor_runtime_sha,
        candidate_package_semantic_hash=bindings.candidate_package_semantic_hash,
        human_review_sha256=bindings.human_review_sha256,
        planned_gmail_send=False,
        automatic_gmail=False,
        production_activation=False,
        probe=probe,
    )


def build_r4_live_eval_register_request(
    bindings: R4RegistrationCampaignBindings,
    *,
    scenario_id: str,
    evaluation_run_id: str,
    attempt_id: int = 1,
    planned_gmail_send: bool,
    send_fields: R4SendRegistrationFields | None = None,
    probe: bool = False,
) -> LiveEvalRunRegisterRequest:
    registration_context = build_r4_registration_context(
        bindings,
        scenario_id=scenario_id,
        planned_gmail_send=planned_gmail_send,
        send_fields=send_fields,
        probe=probe,
    )
    return LiveEvalRunRegisterRequest(
        evaluation_run_id=evaluation_run_id,
        tenant_id=bindings.tenant_id,
        scenario_id=scenario_id,
        attempt_id=attempt_id,
        transport_mode="live_gmail",
        ai_mode=R4_EXECUTE_AI_MODE,
        campaign_type=R4_LIVE_QUALITY_CAMPAIGN_TYPE,
        execution_mode=R4_EXECUTION_MODE,
        campaign_id=bindings.campaign_id,
        manifest_hash=bindings.manifest_semantic_hash,
        expected_sender=bindings.expected_sender,
        expected_recipient=bindings.expected_recipient,
        registration_context=registration_context,
    )


def validate_exact_r4_registration_payload(
    request: LiveEvalRunRegisterRequest,
    *,
    config: LiveEvalConfig | None = None,
) -> dict[str, Any]:
    config = config or get_live_eval_config()
    result = validate_r4_registration_contract(
        R4RegistrationContractRequest(
            tenant_id=request.tenant_id,
            scenario_id=request.scenario_id,
            transport_mode=request.transport_mode,
            ai_mode=request.ai_mode,
            campaign_type=request.campaign_type,
            execution_mode=request.execution_mode,
            expected_sender=request.expected_sender,
            expected_recipient=request.expected_recipient,
            manifest_hash=request.manifest_hash,
            campaign_id=request.campaign_id,
            evaluation_run_id=request.evaluation_run_id,
            registration_context=request.registration_context,
            sender_allowlist=config.sender_emails,
            recipient_allowlist=config.recipient_emails,
        )
    )
    ctx = request.registration_context
    return {
        "scenario_id": request.scenario_id,
        "evaluation_run_id": request.evaluation_run_id,
        "planned_gmail_send": ctx.planned_gmail_send if ctx else None,
        "registration_context_present": ctx is not None,
        "sender_allowlisted": (request.expected_sender or "").strip().lower()
        in {e.strip().lower() for e in config.sender_emails},
        "recipient_allowlisted": (request.expected_recipient or "").strip().lower()
        in {e.strip().lower() for e in config.recipient_emails},
        "schema_valid": True,
        "registration_contract_valid": result.registration_contract_valid,
        "registration_blockers": list(result.registration_blockers),
        "passed": result.registration_contract_valid,
    }


def evaluate_exact_r4_registration_payload_matrix(
    *,
    bindings: R4RegistrationCampaignBindings,
    candidates: dict[str, Any],
    human_review: dict[str, Any],
    config: LiveEvalConfig | None = None,
) -> dict[str, Any]:
    config = config or get_live_eval_config()
    blockers: list[str] = []
    send_ready = 0
    no_send_ready = 0
    sender_allowlist_ready = 0
    context_present = 0
    cand_by_id = {c.get("scenario_id"): c for c in (candidates.get("send_candidates") or [])}
    review_by_id = {r.get("scenario_id"): r for r in (human_review.get("reviews") or [])}

    for sid in R4_SEND_SCENARIO_IDS:
        candidate = cand_by_id.get(sid) or {}
        review_row = review_by_id.get(sid) or {}
        send_fields = send_registration_fields_from_candidate(candidate, review_row)
        request = build_r4_live_eval_register_request(
            bindings,
            scenario_id=sid,
            evaluation_run_id=str(uuid4()),
            planned_gmail_send=True,
            send_fields=send_fields,
        )
        row = validate_exact_r4_registration_payload(request, config=config)
        if row["passed"]:
            send_ready += 1
        else:
            blockers.extend([f"{sid}:{b}" for b in row["registration_blockers"][:3]])
        if row["sender_allowlisted"]:
            sender_allowlist_ready += 1
        if row["registration_context_present"]:
            context_present += 1

    for sid in R4_NO_SEND_SCENARIO_IDS:
        request = build_r4_live_eval_register_request(
            bindings,
            scenario_id=sid,
            evaluation_run_id=str(uuid4()),
            planned_gmail_send=False,
        )
        row = validate_exact_r4_registration_payload(request, config=config)
        if row["passed"]:
            no_send_ready += 1
        else:
            blockers.extend([f"{sid}:{b}" for b in row["registration_blockers"][:3]])
        if row["sender_allowlisted"]:
            sender_allowlist_ready += 1
        if row["registration_context_present"]:
            context_present += 1

    total = len(R4_SEND_SCENARIO_IDS) + len(R4_NO_SEND_SCENARIO_IDS)
    blockers = list(dict.fromkeys(blockers))
    return {
        "exact_send_registration_payload_ready": f"{send_ready}/20",
        "exact_no_send_registration_payload_ready": f"{no_send_ready}/16",
        "exact_registration_payload_ready": f"{send_ready + no_send_ready}/36",
        "sender_allowlist_ready": f"{sender_allowlist_ready}/{total}",
        "registration_context_present": f"{context_present}/{total}",
        "send_ready_count": send_ready,
        "no_send_ready_count": no_send_ready,
        "blockers": blockers,
        "passed": send_ready == 20 and no_send_ready == 16 and not blockers,
    }


def registration_context_semantic_hash(ctx: R4RegistrationContext) -> str:
    import hashlib
    import json

    from app.evaluation.profile_testbot.qualification.coworker_r4_registration_contract import (
        r4_registration_context_for_config_hash,
    )

    payload = r4_registration_context_for_config_hash(ctx)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
