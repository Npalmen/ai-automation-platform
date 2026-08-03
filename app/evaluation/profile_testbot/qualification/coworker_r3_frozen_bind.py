"""Server-side canonical validation for R3 frozen approval body binding."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.evaluation.profile_testbot.constants import LIVE_EVAL_TENANT_ID
from app.evaluation.profile_testbot.qualification.coworker_r3_execution import (
    R3_SEND_SCENARIO_IDS,
)
from app.evaluation.profile_testbot.qualification.coworker_r3_frozen_bodies import (
    load_r3_approved_send_body_texts,
    r3_send_body_hash,
)
from app.evaluation.profile_testbot.qualification.coworker_r3_readiness import (
    R3_APPROVED_SEND_BODY_HASHES,
)
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.approval_repository import ApprovalRequestRepository

R3_FROZEN_BODY_SOURCE = "frozen_approved_body"
R3_ALLOWED_NEXT_ON_APPROVE = frozenset({"action_execute", "email_send"})


@dataclass(frozen=True)
class R3FrozenBindRequest:
    tenant_id: str
    job_id: str
    approval_id: str
    scenario_id: str
    frozen_body: str
    expected_body_hash: str


@dataclass(frozen=True)
class R3FrozenBindAudit:
    scenario_id: str
    canonical_body_hash: str
    body_source: str
    bound_at: str
    tenant_id: str
    approval_id: str
    job_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "canonical_body_hash": self.canonical_body_hash,
            "body_source": self.body_source,
            "bound_at": self.bound_at,
            "tenant_id": self.tenant_id,
            "approval_id": self.approval_id,
            "job_id": self.job_id,
        }


@dataclass(frozen=True)
class R3FrozenBindResult:
    approval_id: str
    job_id: str
    scenario_id: str
    body_hash: str
    bound: bool
    audit: R3FrozenBindAudit


class R3FrozenBindError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def validate_r3_frozen_bind_request(
    request: R3FrozenBindRequest,
    *,
    record: ApprovalRequestRecord | None,
) -> str:
    """Validate bind request against canonical allowlist. Returns canonical hash."""
    if request.tenant_id != LIVE_EVAL_TENANT_ID:
        raise R3FrozenBindError("tenant not allowed for R3 frozen bind", status_code=403)
    if request.scenario_id not in R3_APPROVED_SEND_BODY_HASHES:
        raise R3FrozenBindError("scenario not in canonical approved body hashes", status_code=400)
    if request.scenario_id not in R3_SEND_SCENARIO_IDS:
        raise R3FrozenBindError("scenario not in R3 send allowlist", status_code=400)
    canonical_hash = R3_APPROVED_SEND_BODY_HASHES[request.scenario_id]
    if request.expected_body_hash != canonical_hash:
        raise R3FrozenBindError(
            "request expected_body_hash does not match canonical approved hash",
            status_code=400,
        )
    body_hash = r3_send_body_hash(request.frozen_body)
    if body_hash != canonical_hash:
        raise R3FrozenBindError(
            "frozen body hash does not match canonical approved hash",
            status_code=400,
        )
    canonical_text = load_r3_approved_send_body_texts().get(request.scenario_id, "")
    if canonical_text.strip() and request.frozen_body != canonical_text:
        raise R3FrozenBindError(
            "frozen body text does not match canonical approved body",
            status_code=400,
        )
    if record is None:
        raise R3FrozenBindError("approval not found", status_code=404)
    if record.job_id != request.job_id:
        raise R3FrozenBindError("approval does not belong to job", status_code=404)
    if str(record.state or "") != "pending":
        raise R3FrozenBindError("approval not pending", status_code=409)
    next_on_approve = str(record.next_on_approve or "")
    if next_on_approve not in R3_ALLOWED_NEXT_ON_APPROVE:
        raise R3FrozenBindError("approval is not a send-type approval", status_code=400)
    return canonical_hash


def bind_frozen_approval_body_record(
    db: Session,
    request: R3FrozenBindRequest,
) -> R3FrozenBindResult:
    record = ApprovalRequestRepository.get_by_approval_id(
        db=db,
        tenant_id=request.tenant_id,
        approval_id=request.approval_id,
    )
    canonical_hash = validate_r3_frozen_bind_request(request, record=record)
    bound_at = _utc_now()
    audit = R3FrozenBindAudit(
        scenario_id=request.scenario_id,
        canonical_body_hash=canonical_hash,
        body_source=R3_FROZEN_BODY_SOURCE,
        bound_at=bound_at,
        tenant_id=request.tenant_id,
        approval_id=request.approval_id,
        job_id=request.job_id,
    )
    delivery = dict(record.delivery_payload or {})
    delivery["body"] = request.frozen_body
    delivery["r3_frozen_bind"] = audit.to_dict()
    record.delivery_payload = delivery
    db.commit()
    db.refresh(record)
    return R3FrozenBindResult(
        approval_id=request.approval_id,
        job_id=request.job_id,
        scenario_id=request.scenario_id,
        body_hash=canonical_hash,
        bound=True,
        audit=audit,
    )
