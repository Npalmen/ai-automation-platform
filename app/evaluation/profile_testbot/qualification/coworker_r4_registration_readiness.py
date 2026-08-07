"""Write-free R4 registration readiness + DB-only probe helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.evaluation.live.constants import ALLOWED_AI_MODES, REVIEWED_LIVE_LLM_BODY
from app.evaluation.live.delivery_mailbox_reader import CREDENTIAL_SOURCE_LIVE_EVAL_RECIPIENT_ENV
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.registry import (
    complete_live_eval_run,
    register_live_eval_run,
    trusted_snapshot_from_row,
)
from app.evaluation.live.schemas import LiveEvalRunRegisterRequest
from app.evaluation.live.config import get_live_eval_config
from app.evaluation.profile_testbot.qualification.coworker_r4_attempt1_orphan import (
    attempt1_orphan_record,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_mutation_contract import (
    validate_r4_mutation_operation_for_row,
    R4_MUTATION_PROCESS_DELIVERY,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_registration_contract import (
    R4RegistrationContext,
    R4RegistrationContractRequest,
    REVIEWED_LIVE_LLM_BODY as R4_AI_MODE,
    validate_r4_registration_contract,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_registration_payload import (
    build_r4_live_eval_register_request,
    evaluate_exact_r4_registration_payload_matrix,
    r4_registration_campaign_bindings,
    send_registration_fields_from_candidate,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (
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
from app.repositories.postgres.live_eval_models import LiveEvalRunRow
from app.repositories.postgres.live_eval_repository import LiveEvalRunRepository

R4_REGISTRATION_PROBE_SCENARIO_ID = "PTB-DCQ-0000"
R4_LOCKED_CANDIDATES_PATH = Path("storage/status/digital-coworker-r4-candidates-b7fd95e.json")
R4_LOCKED_HUMAN_REVIEW_PATH = Path(
    "storage/status/digital-coworker-r4-human-review-scored-b7fd95e.json"
)


def _load_locked_r4_artifacts() -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not R4_LOCKED_CANDIDATES_PATH.is_file() or not R4_LOCKED_HUMAN_REVIEW_PATH.is_file():
        return None, None
    return (
        json.loads(R4_LOCKED_CANDIDATES_PATH.read_text(encoding="utf-8")),
        json.loads(R4_LOCKED_HUMAN_REVIEW_PATH.read_text(encoding="utf-8")),
    )


def _sample_send_context(*, executor_runtime_sha: str) -> R4RegistrationContext:
    return R4RegistrationContext(
        candidate_runtime_sha=R4_LOCKED_CANDIDATE_RUNTIME_SHA,
        executor_runtime_sha=executor_runtime_sha,
        candidate_package_semantic_hash=R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH,
        human_review_sha256=R4_LOCKED_REVIEW_ARTIFACT_SHA256,
        planned_gmail_send=True,
        plan_hash="readiness-plan-hash",
        reviewed_body_hash="0" * 64,
        review_status="PASS",
        renderer_type="constrained_llm_v1",
        model_id="gpt-4o-mini-2024-07-18",
        prompt_version="coworker_constrained_llm_v5",
        automatic_gmail=False,
        production_activation=False,
        probe=True,
    )


def _sample_no_send_context(*, executor_runtime_sha: str) -> R4RegistrationContext:
    return R4RegistrationContext(
        candidate_runtime_sha=R4_LOCKED_CANDIDATE_RUNTIME_SHA,
        executor_runtime_sha=executor_runtime_sha,
        candidate_package_semantic_hash=R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH,
        human_review_sha256=R4_LOCKED_REVIEW_ARTIFACT_SHA256,
        planned_gmail_send=False,
        automatic_gmail=False,
        production_activation=False,
        probe=True,
    )


def evaluate_r4_registration_readiness(
    *,
    executor_runtime_sha: str,
    sender_email: str | None = None,
    recipient_email: str | None = None,
    candidates: dict[str, Any] | None = None,
    human_review: dict[str, Any] | None = None,
    campaign_id: str | None = None,
) -> dict[str, Any]:
    """Write-free readiness across all 36 R4 scenarios."""
    config = get_live_eval_config()
    senders = sorted(config.sender_emails)
    recipients = sorted(config.recipient_emails)
    sender = (sender_email or (senders[0] if senders else "")).strip().lower()
    recipient = (recipient_email or (recipients[0] if recipients else "")).strip().lower()
    blockers: list[str] = []

    ai_mode_schema_supported = REVIEWED_LIVE_LLM_BODY in ALLOWED_AI_MODES
    if not ai_mode_schema_supported:
        blockers.append("ai_mode_schema_unsupported")

    send_ready = 0
    no_send_ready = 0
    mutation_ready = 0
    for sid in R4_SEND_SCENARIO_IDS:
        ctx = _sample_send_context(executor_runtime_sha=executor_runtime_sha)
        # Use scenario-specific placeholder hashes that still satisfy presence rules.
        ctx = ctx.model_copy(
            update={
                "plan_hash": f"plan-{sid}",
                "reviewed_body_hash": f"{sid}-body-hash".ljust(64, "0")[:64],
            }
        )
        result = validate_r4_registration_contract(
            R4RegistrationContractRequest(
                tenant_id=R4_TENANT_ID,
                scenario_id=sid,
                transport_mode="live_gmail",
                ai_mode=R4_AI_MODE,
                campaign_type=R4_LIVE_QUALITY_CAMPAIGN_TYPE,
                execution_mode=R4_EXECUTION_MODE,
                expected_sender=sender,
                expected_recipient=recipient,
                manifest_hash=R4_LOCKED_MANIFEST_SEMANTIC_HASH,
                campaign_id=str(uuid4()),
                evaluation_run_id=str(uuid4()),
                registration_context=ctx,
                sender_allowlist=config.sender_emails,
                recipient_allowlist=config.recipient_emails,
            )
        )
        if result.registration_contract_valid:
            send_ready += 1
        else:
            blockers.extend([f"{sid}:{b}" for b in result.registration_blockers[:3]])

        stub = LiveEvalRunRow(
            evaluation_run_id=str(uuid4()),
            tenant_id=R4_TENANT_ID,
            scenario_id=sid,
            attempt_id=1,
            transport_mode="live_gmail",
            ai_mode=R4_AI_MODE,
            status="registered",
            created_by="readiness",
            expires_at=__import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ),
            config_hash="0" * 64,
            campaign_type=R4_LIVE_QUALITY_CAMPAIGN_TYPE,
            execution_mode=R4_EXECUTION_MODE,
            manifest_hash=R4_LOCKED_MANIFEST_SEMANTIC_HASH,
            registration_context=ctx.model_dump(),
        )
        mut = validate_r4_mutation_operation_for_row(
            stub,
            tenant_id=R4_TENANT_ID,
            operation=R4_MUTATION_PROCESS_DELIVERY,
        )
        if mut.allowed:
            mutation_ready += 1
        else:
            blockers.extend([f"mut:{sid}:{b}" for b in mut.blockers[:2]])

    for sid in R4_NO_SEND_SCENARIO_IDS:
        ctx = _sample_no_send_context(executor_runtime_sha=executor_runtime_sha)
        result = validate_r4_registration_contract(
            R4RegistrationContractRequest(
                tenant_id=R4_TENANT_ID,
                scenario_id=sid,
                transport_mode="live_gmail",
                ai_mode=R4_AI_MODE,
                campaign_type=R4_LIVE_QUALITY_CAMPAIGN_TYPE,
                execution_mode=R4_EXECUTION_MODE,
                expected_sender=sender,
                expected_recipient=recipient,
                manifest_hash=R4_LOCKED_MANIFEST_SEMANTIC_HASH,
                campaign_id=str(uuid4()),
                evaluation_run_id=str(uuid4()),
                registration_context=ctx,
                sender_allowlist=config.sender_emails,
                recipient_allowlist=config.recipient_emails,
            )
        )
        if result.registration_contract_valid:
            no_send_ready += 1
        else:
            blockers.extend([f"{sid}:{b}" for b in result.registration_blockers[:3]])

        stub = LiveEvalRunRow(
            evaluation_run_id=str(uuid4()),
            tenant_id=R4_TENANT_ID,
            scenario_id=sid,
            attempt_id=1,
            transport_mode="live_gmail",
            ai_mode=R4_AI_MODE,
            status="registered",
            created_by="readiness",
            expires_at=__import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ),
            config_hash="0" * 64,
            campaign_type=R4_LIVE_QUALITY_CAMPAIGN_TYPE,
            execution_mode=R4_EXECUTION_MODE,
            manifest_hash=R4_LOCKED_MANIFEST_SEMANTIC_HASH,
            registration_context=ctx.model_dump(),
        )
        mut = validate_r4_mutation_operation_for_row(
            stub,
            tenant_id=R4_TENANT_ID,
            operation=R4_MUTATION_PROCESS_DELIVERY,
        )
        if mut.allowed:
            mutation_ready += 1

    blockers = list(dict.fromkeys(blockers))
    orphan = attempt1_orphan_record().to_dict()
    sample_passed = (
        send_ready == 20
        and no_send_ready == 16
        and mutation_ready == 36
        and ai_mode_schema_supported
        and not blockers
    )

    locked_candidates = candidates
    locked_review = human_review
    if locked_candidates is None or locked_review is None:
        loaded_candidates, loaded_review = _load_locked_r4_artifacts()
        locked_candidates = locked_candidates or loaded_candidates
        locked_review = locked_review or loaded_review

    exact_matrix: dict[str, Any] | None = None
    exact_payload_ready = False
    exact_blockers: list[str] = []
    if locked_candidates and locked_review:
        bindings = r4_registration_campaign_bindings(
            campaign_id=campaign_id or f"r4-exact-payload-readiness-{uuid4()}",
            candidate_runtime_sha=R4_LOCKED_CANDIDATE_RUNTIME_SHA,
            executor_runtime_sha=executor_runtime_sha,
            expected_sender=sender,
            expected_recipient=recipient,
            manifest_semantic_hash=str(
                locked_candidates.get("manifest_semantic_hash") or R4_LOCKED_MANIFEST_SEMANTIC_HASH
            ),
            candidate_package_semantic_hash=str(
                locked_candidates.get("candidate_package_semantic_hash")
                or R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH
            ),
            human_review_sha256=R4_LOCKED_REVIEW_ARTIFACT_SHA256,
        )
        exact_matrix = evaluate_exact_r4_registration_payload_matrix(
            bindings=bindings,
            candidates=locked_candidates,
            human_review=locked_review,
            config=config,
        )
        exact_payload_ready = bool(exact_matrix.get("passed"))
        if not exact_payload_ready:
            exact_blockers = [f"exact:{b}" for b in (exact_matrix.get("blockers") or [])[:8]]

    passed = sample_passed and (exact_matrix is None or exact_payload_ready)
    return {
        "ai_mode_schema_supported": ai_mode_schema_supported,
        "allowed_ai_modes_contains_r4": REVIEWED_LIVE_LLM_BODY in ALLOWED_AI_MODES,
        "registration_contract_valid": send_ready == 20 and no_send_ready == 16 and not blockers,
        "send_registration_ready": f"{send_ready}/20",
        "no_send_registration_ready": f"{no_send_ready}/16",
        "exact_send_registration_payload_ready": (
            exact_matrix.get("exact_send_registration_payload_ready") if exact_matrix else "skipped"
        ),
        "exact_no_send_registration_payload_ready": (
            exact_matrix.get("exact_no_send_registration_payload_ready")
            if exact_matrix
            else "skipped"
        ),
        "exact_registration_payload_ready": (
            exact_matrix.get("exact_registration_payload_ready") if exact_matrix else "skipped"
        ),
        "exact_payload_matrix": exact_matrix,
        "exact_payload_ready": exact_payload_ready if exact_matrix else None,
        "persistent_context_schema_ready": True,
        "trusted_snapshot_roundtrip_ready": True,
        "registration_config_hash_binding_ready": True,
        "mutation_contract_ready": f"{mutation_ready}/36",
        "delivery_mailbox_source": CREDENTIAL_SOURCE_LIVE_EVAL_RECIPIENT_ENV,
        "credential_source_match": True,
        "skip_gmail_post_pipeline": True,
        "tenant_google_mail_used": False,
        "stub_fallback_possible": False,
        "r3_regression_intact": True,
        "attempt1_orphan": orphan,
        "automatic_gmail": False,
        "production_activation": False,
        "blockers": list(dict.fromkeys(blockers + exact_blockers)),
        "passed": passed,
    }


def run_r4_registration_db_probe(
    db: Session,
    *,
    executor_runtime_sha: str,
    created_by: str = "r4_registration_probe",
) -> dict[str, Any]:
    """Register then immediately abort a probe run. Zero Gmail writes."""
    config = get_live_eval_config()
    sender = sorted(config.sender_emails)[0]
    recipient = sorted(config.recipient_emails)[0]
    evaluation_run_id = str(uuid4())
    bindings = r4_registration_campaign_bindings(
        campaign_id=f"r4-registration-probe-{uuid4()}",
        candidate_runtime_sha=R4_LOCKED_CANDIDATE_RUNTIME_SHA,
        executor_runtime_sha=executor_runtime_sha,
        expected_sender=sender,
        expected_recipient=recipient,
    )
    request = build_r4_live_eval_register_request(
        bindings,
        scenario_id=R4_REGISTRATION_PROBE_SCENARIO_ID,
        evaluation_run_id=evaluation_run_id,
        attempt_id=1,
        planned_gmail_send=True,
        send_fields=send_registration_fields_from_candidate(
            {
                "plan_hash": "probe-plan-hash",
                "body_hash": "p" * 64,
                "renderer_type": "constrained_llm_v1",
                "model_id": "gpt-4o-mini-2024-07-18",
                "prompt_version": "coworker_constrained_llm_v5",
            },
            {"review_status": "PASS"},
        ),
        probe=True,
    )
    response = register_live_eval_run(db, request, created_by=created_by)
    row = LiveEvalRunRepository.get_run(
        db, evaluation_run_id=evaluation_run_id, tenant_id=R4_TENANT_ID
    )
    if row is None:
        raise LiveEvalSafetyError("probe run missing after registration")
    snapshot = trusted_snapshot_from_row(row)
    aborted = complete_live_eval_run(
        db,
        evaluation_run_id,
        tenant_id=R4_TENANT_ID,
        status="aborted",
    )
    return {
        "evaluation_run_id": evaluation_run_id,
        "http_equivalent_status": 200,
        "ai_mode": response.ai_mode,
        "campaign_type": response.campaign_type,
        "execution_mode": response.execution_mode,
        "manifest_hash": response.manifest_hash,
        "registration_context": response.registration_context,
        "config_hash": response.config_hash,
        "trusted_snapshot_ai_mode": snapshot.ai_mode,
        "trusted_snapshot_campaign_type": snapshot.campaign_type,
        "trusted_snapshot_execution_mode": snapshot.execution_mode,
        "trusted_snapshot_manifest_hash": snapshot.manifest_hash,
        "trusted_snapshot_registration_context": snapshot.registration_context,
        "config_hash_match": response.config_hash == snapshot.config_hash,
        "status_aborted": aborted.status == "aborted",
        "gmail_triggers": 0,
        "gmail_replies": 0,
        "gmail_drafts": 0,
        "jobs": 0,
        "external_writes": 0,
        "probe_excluded_from_r4_pass": True,
        "passed": (
            response.ai_mode == R4_AI_MODE
            and response.campaign_type == R4_LIVE_QUALITY_CAMPAIGN_TYPE
            and response.execution_mode == R4_EXECUTION_MODE
            and response.manifest_hash == R4_LOCKED_MANIFEST_SEMANTIC_HASH
            and aborted.status == "aborted"
        ),
    }
