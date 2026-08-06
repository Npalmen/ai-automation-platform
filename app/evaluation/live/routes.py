"""Admin HTTP routes for live evaluation run registry."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.admin_auth import require_admin_api_key
from app.core.settings import get_settings
from app.evaluation.live.cleanup import cleanup_recipient_message
from app.evaluation.live.config import get_live_eval_config
from app.evaluation.live.pipeline_runtime import (
    record_pipeline_execution_build_sha,
    resolve_api_build_git_sha,
    resolve_worker_build_git_sha,
)
from app.evaluation.live.constants import (
    RUN_STATUS_ACTIVE,
    RUN_STATUS_REGISTERED,
    TELEMETRY_APP_DELIVERY_OBSERVED,
)
from app.evaluation.live.delivery import (
    assert_delivery_observation_allowed,
    observe_delivery_candidates,
    validate_delivery_candidate,
    resolve_intake_label_id,
)
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.fixture_intake import process_fixture_input_for_run
from app.evaluation.live.gmail_intake import process_gmail_message_by_id
from app.evaluation.live.safety_errors import (
    build_safety_rejected_payload,
    build_safety_rejected_payload_from_exc,
    classify_safety_reason,
)
from app.evaluation.live.observation import (
    build_full_observation,
    get_run_summary,
    list_run_events,
)
from app.evaluation.live.readiness import run_gmail_readiness_checks
from app.evaluation.live.registry import (
    complete_live_eval_run,
    register_live_eval_run,
)
from app.evaluation.live.schemas import (
    DeliveryObservationResponse,
    GmailReadinessRequest,
    GmailReadinessResponse,
    LiveEvalRunRegisterRequest,
    LiveEvalRunResponse,
    LiveEvalRunStatusRequest,
    ProcessDeliveryRequest,
    ProcessDeliveryResponse,
    ProcessFixtureInputRequest,
    ProcessFixtureInputResponse,
    RecipientCleanupRequest,
    RuntimeReadinessResponse,
    R3BindFrozenApprovalBodyRequest,
    R3BindFrozenApprovalBodyResponse,
    R3FrozenBindAuditResponse,
    R4BindReviewedApprovalBodyRequest,
    R4BindReviewedApprovalBodyResponse,
    R4ReviewedBindAuditResponse,
)
from app.evaluation.live.safety import (
    require_gmail_eval_enabled,
    require_live_eval_enabled,
    require_live_eval_mutation_context,
    require_tenant_allowed,
    validate_live_gmail_run_for_mutation,
)
from app.evaluation.live.telemetry import build_operation_key, record_live_eval_external_event
from app.integrations.enums import IntegrationType
from app.integrations.factory import get_integration_adapter
from app.integrations.service import get_integration_connection_config
from app.repositories.postgres.live_eval_repository import LiveEvalRunRepository

router = APIRouter(prefix="/admin/live-eval", tags=["admin", "live-eval"])


def _safety_http_exception(
    exc: LiveEvalSafetyError | str,
    *,
    evaluation_run_id: str,
    scenario_id: str,
    attempt_id: int,
    tenant_id: str,
    failed_stage: str,
    root_job_created: bool = False,
) -> HTTPException:
    payload = build_safety_rejected_payload_from_exc(
        exc,
        evaluation_run_id=evaluation_run_id,
        scenario_id=scenario_id,
        attempt_id=attempt_id,
        tenant_id=tenant_id,
        failed_stage=failed_stage,
        root_job_created=root_job_created,
    )
    return HTTPException(status_code=400, detail=payload.model_dump())


def _intake_failed_http_exception(
    *,
    evaluation_run_id: str,
    scenario_id: str,
    attempt_id: int,
    tenant_id: str,
    reason: str,
    root_job_created: bool = False,
) -> HTTPException:
    payload = build_safety_rejected_payload(
        evaluation_run_id=evaluation_run_id,
        scenario_id=scenario_id,
        attempt_id=attempt_id,
        tenant_id=tenant_id,
        safety_reason=classify_safety_reason(reason),
        failed_stage="triggering_intake",
        root_job_created=root_job_created,
    )
    return HTTPException(status_code=400, detail=payload.model_dump())


@router.post("/runs", response_model=LiveEvalRunResponse)
def create_live_eval_run(
    body: LiveEvalRunRegisterRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_api_key),
):
    require_live_eval_enabled()
    try:
        return register_live_eval_run(db, body, created_by="admin_api")
    except LiveEvalSafetyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/runs/{evaluation_run_id}", response_model=dict)
def get_live_eval_run(
    evaluation_run_id: str,
    tenant_id: str = Query(...),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_api_key),
):
    require_live_eval_enabled()
    require_tenant_allowed(tenant_id)
    summary = get_run_summary(db, evaluation_run_id, tenant_id)
    if not summary:
        raise HTTPException(status_code=404, detail="run not found")
    return summary


@router.get("/runs/{evaluation_run_id}/events", response_model=list)
def get_live_eval_events(
    evaluation_run_id: str,
    tenant_id: str = Query(...),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_api_key),
):
    require_live_eval_enabled()
    require_tenant_allowed(tenant_id)
    if not get_run_summary(db, evaluation_run_id, tenant_id):
        raise HTTPException(status_code=404, detail="run not found")
    return list_run_events(db, evaluation_run_id, tenant_id, limit=limit)


@router.get("/runs/{evaluation_run_id}/delivery", response_model=DeliveryObservationResponse)
def get_live_eval_delivery(
    evaluation_run_id: str,
    tenant_id: str = Query(...),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_api_key),
):
    require_live_eval_enabled()
    require_gmail_eval_enabled()
    require_tenant_allowed(tenant_id)
    row = LiveEvalRunRepository.get_run(db, evaluation_run_id, tenant_id=tenant_id)
    if row is None:
        raise HTTPException(status_code=404, detail="run not found")
    try:
        assert_delivery_observation_allowed(row)
    except LiveEvalSafetyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    from app.evaluation.live.delivery_mailbox_reader import (
        CREDENTIAL_SOURCE_LIVE_EVAL_RECIPIENT_ENV,
        is_r3_frozen_live_eval_run,
        resolve_delivery_mailbox_reader,
    )
    from app.evaluation.live.recipient_gmail_readiness import run_recipient_gmail_readiness

    config = get_live_eval_config()
    recipient = sorted(config.recipient_emails)[0] if config.recipient_emails else ""
    reader_resolution = resolve_delivery_mailbox_reader(db=db, row=row, config=config)
    blockers: list[str] = []
    recipient_credential_source = None
    credential_source_match = None
    if is_r3_frozen_live_eval_run(row):
        recipient_readiness = run_recipient_gmail_readiness(
            expected_recipient=recipient,
            config=config,
            db=db,
            row=row,
        )
        recipient_credential_source = recipient_readiness.recipient_credential_source
        credential_source_match = recipient_readiness.credential_source_match
        blockers.extend(recipient_readiness.blockers)
        if not recipient_readiness.ready:
            pass
        elif reader_resolution.credential_source != CREDENTIAL_SOURCE_LIVE_EVAL_RECIPIENT_ENV:
            blockers.append("R3 delivery observation requires live_eval_recipient_env")
    if not reader_resolution.ready:
        blockers.extend(reader_resolution.blockers)
    if blockers:
        raise HTTPException(
            status_code=503,
            detail={
                "failure_stage": "delivery_observation",
                "recipient_delivery_observation_ready": False,
                "recipient_credential_source": recipient_credential_source,
                "delivery_observation_credential_source": reader_resolution.credential_source,
                "credential_source_match": credential_source_match,
                "blockers": list(dict.fromkeys(blockers)),
            },
        )

    bound_id = row.root_gmail_message_id if row.status == RUN_STATUS_ACTIVE else None
    try:
        result = observe_delivery_candidates(
            db,
            row,
            bound_message_id=bound_id,
            reader_resolution=reader_resolution,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "failure_stage": "delivery_observation",
                "recipient_delivery_observation_ready": False,
                "blockers": [f"delivery observation failed: {type(exc).__name__}"],
            },
        ) from exc
    if result.confirmed is not None:
        from app.evaluation.live.registry import trusted_snapshot_from_row

        snapshot = trusted_snapshot_from_row(row)
        record_live_eval_external_event(
            db,
            operation_key=build_operation_key(
                evaluation_run_id=evaluation_run_id,
                category=TELEMETRY_APP_DELIVERY_OBSERVED,
                operation=result.confirmed.message_id,
            ),
            outcome="succeeded",
            category=TELEMETRY_APP_DELIVERY_OBSERVED,
            operation=result.confirmed.message_id,
            integration_type=IntegrationType.GOOGLE_MAIL.value,
            snapshot=snapshot,
            metadata={
                "recipient_gmail_message_id": result.confirmed.message_id,
                "rfc_message_id": result.confirmed.rfc_message_id,
            },
        )
        db.commit()
    return DeliveryObservationResponse(
        candidate_count=result.candidate_count,
        valid_count=result.valid_count,
        duplicate_detected=result.duplicate_detected,
        confirmed=(
            {
                "message_id": result.confirmed.message_id,
                "thread_id": result.confirmed.thread_id,
                "rfc_message_id": result.confirmed.rfc_message_id,
            }
            if result.confirmed
            else None
        ),
        rejection_reasons=result.rejection_reasons,
    )


@router.get("/runs/{evaluation_run_id}/orphan-delivery-probe", response_model=dict)
def get_orphan_delivery_probe(
    evaluation_run_id: str,
    tenant_id: str = Query(...),
    classification: str = Query("orphaned_attempt_3_delivery_probe_verified"),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_api_key),
):
    """Read-only delivery observation probe — no run status change, no Gmail writes."""
    require_live_eval_enabled()
    require_gmail_eval_enabled()
    require_tenant_allowed(tenant_id)
    row = LiveEvalRunRepository.get_run(db, evaluation_run_id, tenant_id=tenant_id)
    if row is None:
        raise HTTPException(status_code=404, detail="run not found")
    from app.evaluation.live.delivery_mailbox_reader import probe_orphan_delivery_observation

    result = probe_orphan_delivery_observation(
        db,
        row=row,
        classification=classification,
    )
    return result.to_dict()


@router.get("/runs/{evaluation_run_id}/orphan-intake-probe", response_model=dict)
def get_orphan_intake_probe(
    evaluation_run_id: str,
    tenant_id: str = Query(...),
    classification: str = Query("orphaned_attempt_4_intake_probe_verified"),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_api_key),
):
    """Read-only exact-message intake probe — no job, no run mutation, no Gmail writes."""
    require_live_eval_enabled()
    require_gmail_eval_enabled()
    require_tenant_allowed(tenant_id)
    row = LiveEvalRunRepository.get_run(db, evaluation_run_id, tenant_id=tenant_id)
    if row is None:
        raise HTTPException(status_code=404, detail="run not found")
    from app.evaluation.live.delivery_mailbox_reader import probe_orphan_intake_observation

    result = probe_orphan_intake_observation(
        db,
        row=row,
        classification=classification,
    )
    return result.to_dict()


@router.get("/runs/{evaluation_run_id}/process-delivery-readiness", response_model=dict)
def get_process_delivery_readiness(
    evaluation_run_id: str,
    tenant_id: str = Query(...),
    recipient_gmail_message_id: str | None = Query(None),
    probe_exact_message: bool = Query(False),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_api_key),
):
    """Write-free R3 process-delivery readiness check."""
    require_live_eval_enabled()
    require_gmail_eval_enabled()
    require_tenant_allowed(tenant_id)
    row = LiveEvalRunRepository.get_run(db, evaluation_run_id, tenant_id=tenant_id)
    if row is None:
        raise HTTPException(status_code=404, detail="run not found")
    from app.evaluation.profile_testbot.qualification.coworker_r3_mutation_contract import (
        validate_r3_process_delivery_readiness,
    )
    from app.evaluation.live.tenant_intake_readiness import run_r3_tenant_intake_readiness

    result = validate_r3_process_delivery_readiness(
        db,
        row=row,
        tenant_id=tenant_id,
        recipient_message_id=recipient_gmail_message_id,
        probe_exact_message=probe_exact_message,
        allow_orphan_probe=evaluation_run_id in {
            "ccd9916f-c4b7-4b1c-aabc-fb2da09f89cf",
            "b5bbe7ab-7148-4366-8fba-bd92921481f4",
            "afaf7ec3-69d7-433a-9ba7-8338a0a508c0",
        },
    )
    payload = result.to_dict()
    tenant_intake = run_r3_tenant_intake_readiness(db, tenant_id=tenant_id)
    payload.update(
        {
            "tenant_intake_ready": tenant_intake.tenant_intake_ready,
            "tenant_config_exists": tenant_intake.tenant_config_exists,
            "intake_cutoff_at_redacted": tenant_intake.intake_cutoff_at_redacted,
            "intake_cutoff_age_seconds": tenant_intake.intake_cutoff_age_seconds,
            "intake_cutoff_fresh": tenant_intake.intake_cutoff_fresh,
            "tenant_intake_blockers": list(tenant_intake.blockers),
        }
    )
    return payload


@router.get("/runs/{evaluation_run_id}/observation", response_model=dict)
def get_live_eval_observation(
    evaluation_run_id: str,
    tenant_id: str = Query(...),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_api_key),
):
    require_live_eval_enabled()
    require_tenant_allowed(tenant_id)
    observation = build_full_observation(db, evaluation_run_id, tenant_id)
    if not observation.get("run"):
        raise HTTPException(status_code=404, detail="run not found")
    return observation


@router.post(
    "/runs/{evaluation_run_id}/process-fixture-input",
    response_model=ProcessFixtureInputResponse,
)
def process_live_eval_fixture_input(
    evaluation_run_id: str,
    body: ProcessFixtureInputRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_api_key),
):
    row = LiveEvalRunRepository.get_run(db, evaluation_run_id, tenant_id=body.tenant_id)
    if row is None:
        raise HTTPException(status_code=404, detail="run not found")

    try:
        require_live_eval_enabled()
        require_tenant_allowed(body.tenant_id)
        from app.evaluation.live.config import get_live_eval_config

        config = get_live_eval_config()
        if not config.llm_enabled:
            raise LiveEvalSafetyError("LIVE_LLM_EVAL_ALLOWED is required for fixture_input")
    except LiveEvalSafetyError as exc:
        raise _safety_http_exception(
            exc,
            evaluation_run_id=evaluation_run_id,
            scenario_id=row.scenario_id,
            attempt_id=row.attempt_id,
            tenant_id=body.tenant_id,
            failed_stage="triggering_fixture_intake",
            root_job_created=bool(row.root_job_id),
        ) from exc

    try:
        intake_result = process_fixture_input_for_run(
            db,
            evaluation_run_id=evaluation_run_id,
            tenant_id=body.tenant_id,
        )
    except LiveEvalSafetyError as exc:
        raise _safety_http_exception(
            exc,
            evaluation_run_id=evaluation_run_id,
            scenario_id=row.scenario_id,
            attempt_id=row.attempt_id,
            tenant_id=body.tenant_id,
            failed_stage="triggering_fixture_intake",
            root_job_created=bool(row.root_job_id),
        ) from exc
    except Exception as exc:
        raise _intake_failed_http_exception(
            evaluation_run_id=evaluation_run_id,
            scenario_id=row.scenario_id,
            attempt_id=row.attempt_id,
            tenant_id=body.tenant_id,
            reason=str(exc),
            root_job_created=bool(row.root_job_id),
        ) from exc

    refreshed = LiveEvalRunRepository.get_run(db, evaluation_run_id, tenant_id=body.tenant_id)
    return ProcessFixtureInputResponse(
        evaluation_run_id=evaluation_run_id,
        root_job_id=intake_result.get("job_id") or (refreshed.root_job_id if refreshed else None),
        job_status=intake_result.get("job_status"),
        pipeline_run_id=intake_result.get("pipeline_run_id"),
        intake_status=str(intake_result.get("status")),
        intake_detail={
            k: v
            for k, v in intake_result.items()
            if k not in ("message_text", "body_text")
        },
    )


@router.post("/runs/{evaluation_run_id}/process-delivery", response_model=ProcessDeliveryResponse)
def process_live_eval_delivery(
    evaluation_run_id: str,
    body: ProcessDeliveryRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_api_key),
):
    row = LiveEvalRunRepository.get_run(db, evaluation_run_id, tenant_id=body.tenant_id)
    if row is None:
        raise HTTPException(status_code=404, detail="run not found")

    try:
        require_live_eval_mutation_context(body.tenant_id)
    except LiveEvalSafetyError as exc:
        raise _safety_http_exception(
            exc,
            evaluation_run_id=evaluation_run_id,
            scenario_id=row.scenario_id,
            attempt_id=row.attempt_id,
            tenant_id=body.tenant_id,
            failed_stage="triggering_intake",
            root_job_created=bool(row.root_job_id),
        ) from exc

    if row.status == RUN_STATUS_ACTIVE and row.root_job_id and row.root_gmail_message_id:
        if body.recipient_gmail_message_id != row.root_gmail_message_id:
            raise _safety_http_exception(
                "recipient message id does not match registry root",
                evaluation_run_id=evaluation_run_id,
                scenario_id=row.scenario_id,
                attempt_id=row.attempt_id,
                tenant_id=body.tenant_id,
                failed_stage="triggering_intake",
                root_job_created=True,
            )
        return ProcessDeliveryResponse(
            evaluation_run_id=evaluation_run_id,
            recipient_gmail_message_id=body.recipient_gmail_message_id,
            root_job_id=row.root_job_id,
            job_status=None,
            pipeline_run_id=None,
            intake_status="skipped",
            intake_detail={"status": "skipped", "reason": "duplicate", "job_id": row.root_job_id},
        )

    from app.evaluation.live.delivery_mailbox_reader import (
        is_reviewed_live_eval_run,
        resolve_delivery_mailbox_reader,
        resolve_intake_label_id_from_reader,
    )
    from app.evaluation.profile_testbot.qualification.coworker_r3_mutation_contract import (
        R3_MUTATION_PROCESS_DELIVERY,
        ReaderMailboxAdapter,
    )

    try:
        validate_live_gmail_run_for_mutation(
            row,
            tenant_id=body.tenant_id,
            recipient_message_id=body.recipient_gmail_message_id,
            mutation_operation=R3_MUTATION_PROCESS_DELIVERY,
            db=db,
        )
    except LiveEvalSafetyError as exc:
        raise _safety_http_exception(
            exc,
            evaluation_run_id=evaluation_run_id,
            scenario_id=row.scenario_id,
            attempt_id=row.attempt_id,
            tenant_id=body.tenant_id,
            failed_stage="triggering_intake",
            root_job_created=bool(row.root_job_id),
        ) from exc

    config = get_live_eval_config()
    reviewed_run = is_reviewed_live_eval_run(row)
    mailbox_resolution = None
    if reviewed_run:
        mailbox_resolution = resolve_delivery_mailbox_reader(db=db, row=row, config=config)
        if not mailbox_resolution.ready or mailbox_resolution.reader is None:
            raise _safety_http_exception(
                "; ".join(mailbox_resolution.blockers or ["reviewed-live mailbox reader not ready"]),
                evaluation_run_id=evaluation_run_id,
                scenario_id=row.scenario_id,
                attempt_id=row.attempt_id,
                tenant_id=body.tenant_id,
                failed_stage="triggering_intake",
                root_job_created=bool(row.root_job_id),
            )
        adapter = ReaderMailboxAdapter(mailbox_resolution.reader)
        intake_label_id = resolve_intake_label_id_from_reader(
            mailbox_resolution.reader,
            config.intake_label,
        )
    else:
        connection_config = get_integration_connection_config(
            tenant_id=body.tenant_id,
            integration_type=IntegrationType.GOOGLE_MAIL,
            db=db,
        )
        adapter = get_integration_adapter(
            integration_type=IntegrationType.GOOGLE_MAIL,
            connection_config=connection_config,
        )
        intake_label_id = resolve_intake_label_id(adapter, config.intake_label)
    detail = adapter.execute_action(
        action="get_message",
        payload={"message_id": body.recipient_gmail_message_id},
    )
    msg = detail.get("message") or {}
    ok, reason = validate_delivery_candidate(
        msg, row=row, config=config, intake_label_id=intake_label_id
    )
    if not ok:
        raise _safety_http_exception(
            f"delivery validation failed: {reason}",
            evaluation_run_id=evaluation_run_id,
            scenario_id=row.scenario_id,
            attempt_id=row.attempt_id,
            tenant_id=body.tenant_id,
            failed_stage="triggering_intake",
            root_job_created=bool(row.root_job_id),
        )

    intake_query = f'label:{config.intake_label} subject:"KROWOLF-EVAL/{evaluation_run_id}"'
    intake_result = process_gmail_message_by_id(
        db,
        body.tenant_id,
        body.recipient_gmail_message_id,
        intake_query=intake_query,
        live_eval_run_id=evaluation_run_id,
        skip_slack_notify=True,
        mailbox_resolution=mailbox_resolution,
        skip_gmail_post_pipeline=reviewed_run,
    )
    record_pipeline_execution_build_sha()
    if intake_result.get("status") == "failed":
        reason = str(intake_result.get("reason") or "intake failed")
        raise _intake_failed_http_exception(
            evaluation_run_id=evaluation_run_id,
            scenario_id=row.scenario_id,
            attempt_id=row.attempt_id,
            tenant_id=body.tenant_id,
            reason=reason,
            root_job_created=bool(row.root_job_id),
        )
    if intake_result.get("status") == "skipped" and intake_result.get("reason") != "duplicate":
        from app.evaluation.live.intake_errors import build_intake_skipped_payload

        payload = build_intake_skipped_payload(
            evaluation_run_id=evaluation_run_id,
            raw_reason=intake_result.get("reason"),
            run_status=str(row.status),
            root_claimed=bool(row.root_job_id),
        )
        raise HTTPException(status_code=409, detail=payload.model_dump())

    refreshed = LiveEvalRunRepository.get_run(db, evaluation_run_id, tenant_id=body.tenant_id)
    return ProcessDeliveryResponse(
        evaluation_run_id=evaluation_run_id,
        recipient_gmail_message_id=body.recipient_gmail_message_id,
        root_job_id=intake_result.get("job_id") or (refreshed.root_job_id if refreshed else None),
        job_status=intake_result.get("job_status"),
        pipeline_run_id=intake_result.get("pipeline_run_id"),
        intake_status=str(intake_result.get("status")),
        intake_detail={
            k: v
            for k, v in intake_result.items()
            if k not in ("message_text", "body_text")
        },
    )


@router.post("/runs/{evaluation_run_id}/cleanup-recipient")
def cleanup_live_eval_recipient(
    evaluation_run_id: str,
    body: RecipientCleanupRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_api_key),
):
    row = LiveEvalRunRepository.get_run(db, evaluation_run_id, tenant_id=body.tenant_id)
    if row is None:
        raise HTTPException(status_code=404, detail="run not found")
    try:
        require_live_eval_mutation_context(body.tenant_id)
        return cleanup_recipient_message(
            db,
            evaluation_run_id=evaluation_run_id,
            tenant_id=body.tenant_id,
            recipient_gmail_message_id=body.recipient_gmail_message_id,
            phase=body.phase,
        )
    except LiveEvalSafetyError as exc:
        raise _safety_http_exception(
            exc,
            evaluation_run_id=evaluation_run_id,
            scenario_id=row.scenario_id,
            attempt_id=row.attempt_id,
            tenant_id=body.tenant_id,
            failed_stage="cleaning_up",
            root_job_created=bool(row.root_job_id),
        ) from exc


@router.get("/runtime-readiness", response_model=RuntimeReadinessResponse)
def runtime_readiness(
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_api_key),
):
    config = get_live_eval_config()
    settings = get_settings()
    database_ok = False
    try:
        db.execute(text("SELECT 1"))
        database_ok = True
    except Exception:
        database_ok = False
    api_sha = resolve_api_build_git_sha()
    worker_sha = resolve_worker_build_git_sha()
    return RuntimeReadinessResponse(
        env=settings.ENV,
        env_fingerprint=config.env_fingerprint,
        build_git_sha=api_sha,
        api_build_git_sha=api_sha,
        worker_build_git_sha=worker_sha,
        live_eval_enabled=config.enabled,
        gmail_eval_enabled=config.gmail_enabled,
        external_side_effects_enabled=config.external_side_effects_enabled,
        tenant_allowlist_ok=bool(config.tenant_ids),
        database_ok=database_ok,
    )


@router.get("/recipient-gmail-readiness")
def recipient_gmail_readiness(
    tenant_id: str = Query(...),
    _admin=Depends(require_admin_api_key),
):
    require_live_eval_enabled()
    require_gmail_eval_enabled()
    require_tenant_allowed(tenant_id)
    config = get_live_eval_config()
    recipient = sorted(config.recipient_emails)[0] if config.recipient_emails else ""
    from app.evaluation.live.recipient_gmail_readiness import run_recipient_gmail_readiness

    report = run_recipient_gmail_readiness(expected_recipient=recipient, config=config)
    payload = report.to_dict()
    payload["ready"] = report.ready
    payload["tenant_id"] = tenant_id
    return payload


@router.get("/r3-reply-provider-readiness")
def r3_reply_provider_readiness(
    tenant_id: str = Query(...),
    _admin=Depends(require_admin_api_key),
):
    """Write-free R3 reply provider resolution probe — no Gmail send."""
    require_live_eval_enabled()
    require_gmail_eval_enabled()
    require_tenant_allowed(tenant_id)
    from app.evaluation.profile_testbot.qualification.coworker_r3_reply_provider import (
        run_r3_live_reply_provider_readiness,
    )

    return run_r3_live_reply_provider_readiness(tenant_id=tenant_id)


@router.get("/r3-approval-materialization-readiness")
def r3_approval_materialization_readiness(
    tenant_id: str = Query(...),
    runtime_sha: str | None = Query(None),
    _admin=Depends(require_admin_api_key),
):
    """Write-free R3 approval materialization probe — no job/approval/Gmail writes."""
    require_live_eval_enabled()
    require_tenant_allowed(tenant_id)
    from app.core.settings import get_settings
    from app.evaluation.profile_testbot.qualification.coworker_live_canary_manifest import (
        COWORKER_LIVE_CANARY_MANIFEST_HASH,
        COWORKER_LIVE_CANARY_SCENARIO_IDS,
    )
    from app.evaluation.profile_testbot.qualification.coworker_r3_approval_materialization_contract import (
        run_r3_approval_materialization_readiness,
    )

    settings = get_settings()
    if str(getattr(settings, "ENV", "") or "").lower() != "test":
        raise HTTPException(status_code=403, detail="eval-only endpoint requires ENV=test")

    sha = (runtime_sha or "").strip() or str(
        getattr(settings, "BUILD_COMMIT_SHA", "") or ""
    ).strip()
    payload = run_r3_approval_materialization_readiness(
        manifest={
            "manifest_hash": COWORKER_LIVE_CANARY_MANIFEST_HASH,
            "scenarios": list(COWORKER_LIVE_CANARY_SCENARIO_IDS),
        },
        approval_artifact={
            "runtime_sha": sha,
            "manifest_hash": COWORKER_LIVE_CANARY_MANIFEST_HASH,
            "manual_execution_approved": True,
            "body_hashes_approved": True,
            "campaign_type": "coworker_r3_frozen_live_canary",
            "execution_mode": "r3_frozen_approved_body",
        },
        runtime_sha=sha,
    )
    payload["tenant_id"] = tenant_id
    payload["gmail_sent"] = False
    payload["gmail_drafts_created"] = False
    return payload


@router.get("/runs/{evaluation_run_id}/orphan-reply-probe", response_model=dict)
def get_orphan_reply_probe(
    evaluation_run_id: str,
    tenant_id: str = Query(...),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_api_key),
):
    """Read-only attempt-6 reply orphan probe — no resume, send, or process."""
    require_live_eval_enabled()
    require_tenant_allowed(tenant_id)
    from app.evaluation.profile_testbot.qualification.coworker_r3_reply_provider import (
        probe_orphaned_attempt_6_reply,
    )

    return probe_orphaned_attempt_6_reply(
        db,
        evaluation_run_id=evaluation_run_id,
        tenant_id=tenant_id,
    )


@router.get("/tenant-intake-readiness")
def tenant_intake_readiness(
    tenant_id: str = Query(...),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_api_key),
):
    require_live_eval_enabled()
    require_tenant_allowed(tenant_id)
    from app.evaluation.live.tenant_intake_readiness import run_r3_tenant_intake_readiness

    report = run_r3_tenant_intake_readiness(db, tenant_id=tenant_id)
    payload = report.to_dict()
    payload["tenant_id"] = tenant_id
    return payload


@router.get("/r4-registration-readiness")
def r4_registration_readiness(
    _admin=Depends(require_admin_api_key),
):
    """Write-free R4 registration readiness (no DB run, no Gmail)."""
    require_live_eval_enabled()
    from app.evaluation.live.pipeline_runtime import resolve_api_build_git_sha
    from app.evaluation.profile_testbot.qualification.coworker_r4_registration_readiness import (
        evaluate_r4_registration_readiness,
    )

    return evaluate_r4_registration_readiness(
        executor_runtime_sha=resolve_api_build_git_sha() or "unknown",
    )


@router.post("/r4-registration-probe")
def r4_registration_probe(
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_api_key),
):
    """DB-only registration round-trip probe; aborts immediately; zero Gmail writes."""
    require_live_eval_enabled()
    from app.evaluation.live.pipeline_runtime import resolve_api_build_git_sha
    from app.evaluation.profile_testbot.qualification.coworker_r4_registration_readiness import (
        run_r4_registration_db_probe,
    )

    return run_r4_registration_db_probe(
        db,
        executor_runtime_sha=resolve_api_build_git_sha() or "unknown",
    )


@router.post("/runs/{evaluation_run_id}/status", response_model=LiveEvalRunResponse)
def update_live_eval_run_status(
    evaluation_run_id: str,
    body: LiveEvalRunStatusRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_api_key),
):
    require_live_eval_enabled()
    try:
        require_tenant_allowed(body.tenant_id)
        return complete_live_eval_run(
            db,
            evaluation_run_id,
            tenant_id=body.tenant_id,
            status=body.status,
        )
    except LiveEvalSafetyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/gmail-readiness", response_model=GmailReadinessResponse)
def gmail_readiness(
    body: GmailReadinessRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_api_key),
):
    require_live_eval_enabled()
    require_gmail_eval_enabled()
    report = run_gmail_readiness_checks(db, body.tenant_id)
    return GmailReadinessResponse(
        ready=report.ready,
        issues=report.issues,
        checks=report.checks,
    )


@router.post("/r3/bind-frozen-approval-body", response_model=R3BindFrozenApprovalBodyResponse)
def bind_frozen_approval_body(
    body: R3BindFrozenApprovalBodyRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_api_key),
):
    import os

    from app.evaluation.profile_testbot.qualification.coworker_r3_frozen_bind import (
        R3FrozenBindError,
        R3FrozenBindRequest,
        bind_frozen_approval_body_record,
    )

    if os.environ.get("R3_FROZEN_APPROVAL_BIND_ALLOWED", "").strip().lower() not in (
        "yes",
        "true",
        "1",
    ):
        raise HTTPException(status_code=403, detail="R3 frozen approval bind not allowed")
    require_live_eval_enabled()
    require_gmail_eval_enabled()
    try:
        require_tenant_allowed(body.tenant_id)
    except LiveEvalSafetyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        result = bind_frozen_approval_body_record(
            db,
            R3FrozenBindRequest(
                tenant_id=body.tenant_id,
                job_id=body.job_id,
                approval_id=body.approval_id,
                scenario_id=body.scenario_id,
                frozen_body=body.frozen_body,
                expected_body_hash=body.expected_body_hash,
            ),
        )
    except R3FrozenBindError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return R3BindFrozenApprovalBodyResponse(
        approval_id=result.approval_id,
        job_id=result.job_id,
        scenario_id=result.scenario_id,
        body_hash=result.body_hash,
        bound=result.bound,
        audit=R3FrozenBindAuditResponse(**result.audit.to_dict()),
    )


@router.post("/r4/bind-reviewed-approval-body", response_model=R4BindReviewedApprovalBodyResponse)
def bind_reviewed_approval_body(
    body: R4BindReviewedApprovalBodyRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_api_key),
):
    import os

    from app.evaluation.profile_testbot.qualification.coworker_r4_reviewed_bind import (
        R4ReviewedBindError,
        R4ReviewedBindRequest,
        bind_reviewed_approval_body_record,
    )

    if os.environ.get("R4_REVIEWED_APPROVAL_BIND_ALLOWED", "").strip().lower() not in (
        "yes",
        "true",
        "1",
    ):
        raise HTTPException(status_code=403, detail="R4 reviewed approval bind not allowed")
    require_live_eval_enabled()
    require_gmail_eval_enabled()
    try:
        require_tenant_allowed(body.tenant_id)
    except LiveEvalSafetyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        result = bind_reviewed_approval_body_record(
            db,
            R4ReviewedBindRequest(
                tenant_id=body.tenant_id,
                job_id=body.job_id,
                approval_id=body.approval_id,
                scenario_id=body.scenario_id,
                reviewed_body=body.reviewed_body,
                expected_body_hash=body.expected_body_hash,
                reviewed_snapshot=body.reviewed_snapshot,
            ),
        )
    except R4ReviewedBindError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return R4BindReviewedApprovalBodyResponse(
        approval_id=result.approval_id,
        job_id=result.job_id,
        scenario_id=result.scenario_id,
        body_hash=result.body_hash,
        bound=result.bound,
        audit=R4ReviewedBindAuditResponse(**result.audit),
    )
