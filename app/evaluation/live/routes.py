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
from app.evaluation.live.gmail_intake import process_gmail_message_by_id
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
    RecipientCleanupRequest,
    RuntimeReadinessResponse,
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

    bound_id = row.root_gmail_message_id if row.status == RUN_STATUS_ACTIVE else None
    result = observe_delivery_candidates(db, row, bound_message_id=bound_id)
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


@router.post("/runs/{evaluation_run_id}/process-delivery", response_model=ProcessDeliveryResponse)
def process_live_eval_delivery(
    evaluation_run_id: str,
    body: ProcessDeliveryRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_api_key),
):
    try:
        require_live_eval_mutation_context(body.tenant_id)
    except LiveEvalSafetyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    row = LiveEvalRunRepository.get_run(db, evaluation_run_id, tenant_id=body.tenant_id)
    if row is None:
        raise HTTPException(status_code=404, detail="run not found")

    if row.status == RUN_STATUS_ACTIVE and row.root_job_id and row.root_gmail_message_id:
        if body.recipient_gmail_message_id != row.root_gmail_message_id:
            raise HTTPException(status_code=400, detail="recipient message id does not match registry root")
        return ProcessDeliveryResponse(
            evaluation_run_id=evaluation_run_id,
            recipient_gmail_message_id=body.recipient_gmail_message_id,
            root_job_id=row.root_job_id,
            job_status=None,
            pipeline_run_id=None,
            intake_status="skipped",
            intake_detail={"status": "skipped", "reason": "duplicate", "job_id": row.root_job_id},
        )

    try:
        if row.status == RUN_STATUS_REGISTERED:
            validate_live_gmail_run_for_mutation(
                row,
                tenant_id=body.tenant_id,
                recipient_message_id=body.recipient_gmail_message_id,
            )
        elif row.status == RUN_STATUS_ACTIVE:
            validate_live_gmail_run_for_mutation(
                row,
                tenant_id=body.tenant_id,
                recipient_message_id=body.recipient_gmail_message_id,
                allow_active_idempotent=False,
            )
        else:
            validate_live_gmail_run_for_mutation(
                row,
                tenant_id=body.tenant_id,
                recipient_message_id=body.recipient_gmail_message_id,
            )
    except LiveEvalSafetyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    connection_config = get_integration_connection_config(
        tenant_id=body.tenant_id,
        integration_type=IntegrationType.GOOGLE_MAIL,
        db=db,
    )
    adapter = get_integration_adapter(
        integration_type=IntegrationType.GOOGLE_MAIL,
        connection_config=connection_config,
    )
    intake_label_id = resolve_intake_label_id(adapter, get_live_eval_config().intake_label)
    detail = adapter.execute_action(
        action="get_message",
        payload={"message_id": body.recipient_gmail_message_id},
    )
    msg = detail.get("message") or {}
    ok, reason = validate_delivery_candidate(
        msg, row=row, config=None, intake_label_id=intake_label_id
    )
    if not ok:
        raise HTTPException(status_code=400, detail=f"delivery validation failed: {reason}")

    intake_query = f'label:{get_live_eval_config().intake_label} subject:"KROWOLF-EVAL/{evaluation_run_id}"'
    intake_result = process_gmail_message_by_id(
        db,
        body.tenant_id,
        body.recipient_gmail_message_id,
        intake_query=intake_query,
        live_eval_run_id=evaluation_run_id,
        skip_slack_notify=True,
    )
    if intake_result.get("status") == "failed":
        raise HTTPException(status_code=400, detail=intake_result.get("reason", "intake failed"))
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
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
    return RuntimeReadinessResponse(
        env=settings.ENV,
        env_fingerprint=config.env_fingerprint,
        build_git_sha=os.environ.get("BUILD_GIT_SHA") or None,
        live_eval_enabled=config.enabled,
        gmail_eval_enabled=config.gmail_enabled,
        external_side_effects_enabled=config.external_side_effects_enabled,
        tenant_allowlist_ok=bool(config.tenant_ids),
        database_ok=database_ok,
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
