"""Admin HTTP routes for live evaluation run registry."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.admin_auth import require_admin_api_key
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.readiness import run_gmail_readiness_checks
from app.evaluation.live.registry import (
    complete_live_eval_run,
    register_live_eval_run,
)
from app.evaluation.live.schemas import (
    GmailReadinessRequest,
    GmailReadinessResponse,
    LiveEvalRunRegisterRequest,
    LiveEvalRunResponse,
    LiveEvalRunStatusRequest,
)
from app.evaluation.live.safety import require_gmail_eval_enabled, require_live_eval_enabled

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


@router.post("/runs/{evaluation_run_id}/status", response_model=LiveEvalRunResponse)
def update_live_eval_run_status(
    evaluation_run_id: str,
    body: LiveEvalRunStatusRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_api_key),
):
    require_live_eval_enabled()
    try:
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
