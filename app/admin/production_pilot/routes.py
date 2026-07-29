"""Admin routes for production pilot ground-truth reviews."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.admin.production_pilot.schemas import PilotMessageReviewRequest, PilotMessageReviewResponse
from app.api.dependencies import get_db
from app.core.admin_auth import require_operator_role
from app.core.admin_session import OperatorIdentity
from app.production_pilot.constants import PILOT_TENANT_ID
from app.production_pilot.observability.repository import ProductionPilotReviewRepository
from app.production_pilot.observability.review_service import submit_message_review

router = APIRouter(prefix="/admin/production-pilot", tags=["production-pilot"])
_WRITE_ROLES = frozenset({"operations", "admin", "super_admin"})
_READ_ROLES = frozenset({"read_only", "operations", "admin", "super_admin"})


@router.post(
    "/{tenant_id}/message-reviews",
    response_model=PilotMessageReviewResponse,
)
def create_pilot_message_review(
    tenant_id: str,
    body: PilotMessageReviewRequest,
    db: Session = Depends(get_db),
    operator: OperatorIdentity = Depends(require_operator_role(_WRITE_ROLES)),
) -> PilotMessageReviewResponse:
    if tenant_id != PILOT_TENANT_ID:
        raise HTTPException(status_code=403, detail="pilot tenant only")
    reviewed_by = str(operator.get("username") or "operator")
    try:
        result = submit_message_review(
            db,
            {
                **body.model_dump(),
                "tenant_id": tenant_id,
                "reviewed_by": reviewed_by,
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PilotMessageReviewResponse(**result)


@router.get(
    "/{tenant_id}/message-reviews",
    response_model=list[PilotMessageReviewResponse],
)
def list_pilot_message_reviews(
    tenant_id: str,
    db: Session = Depends(get_db),
    _: OperatorIdentity = Depends(require_operator_role(_READ_ROLES)),
) -> list[PilotMessageReviewResponse]:
    if tenant_id != PILOT_TENANT_ID:
        raise HTTPException(status_code=403, detail="pilot tenant only")
    rows = ProductionPilotReviewRepository.list_for_tenant(db, tenant_id=tenant_id)
    return [PilotMessageReviewResponse(**ProductionPilotReviewRepository.to_dict(row)) for row in rows]
