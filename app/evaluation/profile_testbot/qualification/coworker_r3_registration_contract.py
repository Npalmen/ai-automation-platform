"""Fail-closed R3 frozen live-canary registration contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.profile_testbot.constants import LIVE_EVAL_TENANT_ID
from app.evaluation.profile_testbot.qualification.constants import (
    PTB_SEM_0024_SCENARIO_ID,
    SEND_BEHAVIORS_COUNTING_AS_GMAIL_SEND,
)
from app.evaluation.profile_testbot.qualification.coworker_live_canary_manifest import (
    COWORKER_LIVE_CANARY_MANIFEST_HASH,
    COWORKER_LIVE_CANARY_SCENARIO_IDS,
    COWORKER_LIVE_CANARY_SEND_MAX,
    COWORKER_LIVE_CANARY_TARGET,
)
from app.evaluation.profile_testbot.qualification.coworker_r3_frozen_bodies import (
    r3_send_body_hash,
    validate_frozen_send_bodies,
)
from app.evaluation.profile_testbot.qualification.coworker_r3_readiness import (
    R3_APPROVED_SEND_BODY_HASHES,
)

R3_FROZEN_LIVE_CANARY_CAMPAIGN_TYPE = "coworker_r3_frozen_live_canary"
R3_FROZEN_EXECUTION_MODE = "r3_frozen_approved_body"
R3_FROZEN_AI_MODE = R3_FROZEN_EXECUTION_MODE

R3_SEND_SCENARIO_IDS: frozenset[str] = frozenset(
    {
        "PTB-DCQ-0000",
        "PTB-DCQ-0022",
        "PTB-DCQ-0033",
        "PTB-DCQ-0049",
        "PTB-DCQ-0056",
        "PTB-DCQ-0072",
        "PTB-DCQ-0080",
        "PTB-DCQ-0088",
    }
)
R3_NO_SEND_SCENARIO_IDS: frozenset[str] = frozenset(
    {
        "PTB-DCQ-0032",
        "PTB-DCQ-0048",
        "PTB-DCQ-0024",
        "PTB-DCQ-0037",
        "PTB-DCQ-0029",
        "PTB-DCQ-0053",
        PTB_SEM_0024_SCENARIO_ID,
    }
)
R3_ALL_SCENARIO_IDS: frozenset[str] = R3_SEND_SCENARIO_IDS | R3_NO_SEND_SCENARIO_IDS

R3_APPROVED_RECIPIENT_DOMAIN = "sol-f.se"
R3_APPROVED_RECIPIENT_LOCAL_PREFIX = "ni"


@dataclass(frozen=True)
class R3RegistrationContractRequest:
    tenant_id: str
    scenario_id: str
    transport_mode: str
    ai_mode: str
    campaign_type: str | None = None
    execution_mode: str | None = None
    expected_sender: str | None = None
    expected_recipient: str | None = None
    runtime_sha: str | None = None
    manifest_hash: str | None = None
    campaign_id: str | None = None
    scenario_ids: tuple[str, ...] | list[str] | None = None
    planned_gmail_send: bool | None = None
    frozen_body: str | None = None
    require_runtime_sha: bool = False


@dataclass
class R3RegistrationValidationResult:
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


def is_r3_frozen_live_canary_scenario(scenario_id: str) -> bool:
    return scenario_id in R3_ALL_SCENARIO_IDS


def is_r3_frozen_send_scenario(scenario_id: str) -> bool:
    return scenario_id in R3_SEND_SCENARIO_IDS


def is_r3_frozen_no_send_scenario(scenario_id: str) -> bool:
    return scenario_id in R3_NO_SEND_SCENARIO_IDS


def recipient_matches_r3_approval(recipient_email: str) -> bool:
    local, _, domain = recipient_email.lower().partition("@")
    return (
        domain == R3_APPROVED_RECIPIENT_DOMAIN
        and local.startswith(R3_APPROVED_RECIPIENT_LOCAL_PREFIX)
    )


def validate_r3_campaign_scenario_registry(
    scenario_ids: list[str] | tuple[str, ...] | None,
) -> list[str]:
    issues: list[str] = []
    if scenario_ids is None:
        return ["scenario_ids missing for R3 campaign registry validation"]
    normalized = list(scenario_ids)
    expected = list(COWORKER_LIVE_CANARY_SCENARIO_IDS)
    if normalized != expected:
        issues.append(f"scenario allowlist mismatch: expected {expected}, got {normalized}")
    if set(normalized) != R3_ALL_SCENARIO_IDS:
        issues.append("scenario set does not match locked R3 send/no-send union")
    if len([sid for sid in normalized if sid in R3_SEND_SCENARIO_IDS]) != COWORKER_LIVE_CANARY_SEND_MAX:
        issues.append(f"send scenario count != {COWORKER_LIVE_CANARY_SEND_MAX}")
    expected_no_send = COWORKER_LIVE_CANARY_TARGET - COWORKER_LIVE_CANARY_SEND_MAX
    if len([sid for sid in normalized if sid in R3_NO_SEND_SCENARIO_IDS]) != expected_no_send:
        issues.append(f"no-send scenario count != {expected_no_send}")
    return issues


def validate_r3_manifest_registration_contract(manifest: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if manifest.get("campaign_type") != R3_FROZEN_LIVE_CANARY_CAMPAIGN_TYPE:
        issues.append(
            f"campaign_type {manifest.get('campaign_type')!r} != {R3_FROZEN_LIVE_CANARY_CAMPAIGN_TYPE!r}"
        )
    if manifest.get("execution_mode") != R3_FROZEN_EXECUTION_MODE:
        issues.append(
            f"execution_mode {manifest.get('execution_mode')!r} != {R3_FROZEN_EXECUTION_MODE!r}"
        )
    if manifest.get("manifest_hash") != COWORKER_LIVE_CANARY_MANIFEST_HASH:
        issues.append("manifest hash drift")
    if manifest.get("tenant_id") != LIVE_EVAL_TENANT_ID:
        issues.append(f"manifest tenant {manifest.get('tenant_id')!r} != {LIVE_EVAL_TENANT_ID}")
    if manifest.get("send_budget") != COWORKER_LIVE_CANARY_SEND_MAX:
        issues.append(f"send_budget {manifest.get('send_budget')} != {COWORKER_LIVE_CANARY_SEND_MAX}")
    expected_no_send = COWORKER_LIVE_CANARY_TARGET - COWORKER_LIVE_CANARY_SEND_MAX
    if manifest.get("hold_reject_no_reply_count") != expected_no_send:
        issues.append(f"no-send count {manifest.get('hold_reject_no_reply_count')} != {expected_no_send}")
    issues.extend(validate_r3_campaign_scenario_registry(manifest.get("scenario_ids")))
    approved_hashes = manifest.get("approved_send_body_hashes") or {}
    if approved_hashes != R3_APPROVED_SEND_BODY_HASHES:
        issues.append("approved_send_body_hashes mismatch")
    issues.extend(validate_frozen_send_bodies(manifest=manifest))
    return issues


def validate_r3_registration_contract(
    request: R3RegistrationContractRequest,
) -> R3RegistrationValidationResult:
    blockers: list[str] = []
    campaign_type_valid = request.campaign_type == R3_FROZEN_LIVE_CANARY_CAMPAIGN_TYPE
    execution_mode_valid = (
        request.ai_mode == R3_FROZEN_AI_MODE
        and (request.execution_mode in (None, R3_FROZEN_EXECUTION_MODE))
    )
    scenario_registry_valid = request.scenario_id in R3_ALL_SCENARIO_IDS
    live_gmail_policy_valid = (
        request.transport_mode == "live_gmail"
        and request.ai_mode == R3_FROZEN_AI_MODE
        and request.ai_mode != "live_llm"
    )

    if request.tenant_id != LIVE_EVAL_TENANT_ID:
        blockers.append(f"tenant {request.tenant_id!r} != {LIVE_EVAL_TENANT_ID}")
    if not campaign_type_valid:
        blockers.append(
            f"campaign_type {request.campaign_type!r} != {R3_FROZEN_LIVE_CANARY_CAMPAIGN_TYPE!r}"
        )
    if not execution_mode_valid:
        blockers.append(
            f"execution_mode/ai_mode must be {R3_FROZEN_EXECUTION_MODE!r}, got ai_mode={request.ai_mode!r}"
        )
    if request.transport_mode != "live_gmail":
        blockers.append(f"transport_mode {request.transport_mode!r} != live_gmail")
    if request.ai_mode == "live_llm":
        blockers.append("live_gmail + live_llm is not allowed for R3 frozen execution")
    if not scenario_registry_valid:
        blockers.append(f"scenario_id {request.scenario_id!r} not in R3 frozen allowlist")
    if request.scenario_ids is not None:
        blockers.extend(validate_r3_campaign_scenario_registry(request.scenario_ids))
    if request.expected_recipient and not recipient_matches_r3_approval(request.expected_recipient):
        blockers.append("recipient does not match approved R3 eval recipient")
    if request.manifest_hash and request.manifest_hash != COWORKER_LIVE_CANARY_MANIFEST_HASH:
        blockers.append("manifest hash mismatch")
    if request.require_runtime_sha and not (request.runtime_sha or "").strip():
        blockers.append("runtime_sha missing")
    if request.planned_gmail_send is not None:
        expected_send = is_r3_frozen_send_scenario(request.scenario_id)
        if request.planned_gmail_send != expected_send:
            blockers.append(
                f"send/no-send mismatch for {request.scenario_id}: "
                f"planned={request.planned_gmail_send}, registry_send={expected_send}"
            )
    if request.frozen_body is not None and is_r3_frozen_send_scenario(request.scenario_id):
        canonical = R3_APPROVED_SEND_BODY_HASHES.get(request.scenario_id)
        digest = r3_send_body_hash(request.frozen_body)
        if canonical and digest != canonical:
            blockers.append(f"frozen body hash mismatch for {request.scenario_id}")

    if not live_gmail_policy_valid:
        blockers.append("R3 live Gmail policy invalid")

    valid = not blockers
    return R3RegistrationValidationResult(
        registration_contract_valid=valid,
        campaign_type_valid=campaign_type_valid,
        execution_mode_valid=execution_mode_valid,
        scenario_registry_valid=scenario_registry_valid,
        live_gmail_policy_valid=live_gmail_policy_valid,
        registration_blockers=blockers,
    )


def require_r3_registration_contract(request: R3RegistrationContractRequest) -> R3RegistrationValidationResult:
    result = validate_r3_registration_contract(request)
    if not result.registration_contract_valid:
        raise LiveEvalSafetyError("; ".join(result.registration_blockers))
    return result


def validate_r3_campaign_registration_contract(
    *,
    manifest: dict[str, Any],
    runtime_sha: str,
    recipient_email: str,
    render_rows: list[dict[str, Any]],
) -> R3RegistrationValidationResult:
    blockers = list(validate_r3_manifest_registration_contract(manifest))
    if manifest.get("runner_sha") and manifest.get("runner_sha") != runtime_sha:
        blockers.append("runtime_sha mismatch with manifest runner_sha")
    if not recipient_matches_r3_approval(recipient_email):
        blockers.append("recipient does not match approved R3 eval recipient")

    for row in render_rows:
        scenario_id = str(row.get("scenario_id") or "")
        row_result = validate_r3_registration_contract(
            R3RegistrationContractRequest(
                tenant_id=LIVE_EVAL_TENANT_ID,
                scenario_id=scenario_id,
                transport_mode="live_gmail",
                ai_mode=R3_FROZEN_AI_MODE,
                campaign_type=R3_FROZEN_LIVE_CANARY_CAMPAIGN_TYPE,
                execution_mode=R3_FROZEN_EXECUTION_MODE,
                expected_recipient=recipient_email,
                runtime_sha=runtime_sha,
                manifest_hash=str(manifest.get("manifest_hash") or ""),
                scenario_ids=list(manifest.get("scenario_ids") or []),
                planned_gmail_send=bool(row.get("planned_gmail_send")),
                frozen_body=str(row.get("frozen_customer_text") or row.get("final_customer_text") or ""),
                require_runtime_sha=True,
            )
        )
        blockers.extend(row_result.registration_blockers)

    blockers = list(dict.fromkeys(blockers))
    return R3RegistrationValidationResult(
        registration_contract_valid=not blockers,
        campaign_type_valid=manifest.get("campaign_type") == R3_FROZEN_LIVE_CANARY_CAMPAIGN_TYPE,
        execution_mode_valid=manifest.get("execution_mode") == R3_FROZEN_EXECUTION_MODE,
        scenario_registry_valid=not validate_r3_campaign_scenario_registry(manifest.get("scenario_ids")),
        live_gmail_policy_valid=True,
        registration_blockers=blockers,
    )


def scenario_expected_planned_send(scenario_id: str, *, expected_send_behavior: str) -> bool:
    if scenario_id == PTB_SEM_0024_SCENARIO_ID:
        return False
    return expected_send_behavior in SEND_BEHAVIORS_COUNTING_AS_GMAIL_SEND
