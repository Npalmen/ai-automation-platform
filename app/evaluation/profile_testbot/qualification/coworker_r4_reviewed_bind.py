"""Bind human-reviewed R4 body onto pending approval (hash-locked)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.evaluation.profile_testbot.constants import LIVE_EVAL_TENANT_ID
from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (
    R4_SEND_SCENARIO_IDS,
)
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.approval_repository import ApprovalRequestRepository
from app.repositories.postgres.job_repository import JobRepository
from app.workflows.reply_quality.provenance import hash_body

R4_REVIEWED_BODY_SOURCE = "r4_human_reviewed_candidate"
R4_ALLOWED_NEXT_ON_APPROVE = frozenset({"action_execute", "email_send"})


@dataclass(frozen=True)
class R4ReviewedBindRequest:
    tenant_id: str
    job_id: str
    approval_id: str
    scenario_id: str
    reviewed_body: str
    expected_body_hash: str
    reviewed_snapshot: dict[str, Any] | None = None


class R4ReviewedBindError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def validate_r4_reviewed_bind_request(
    req: R4ReviewedBindRequest,
    *,
    record: ApprovalRequestRecord | None = None,
) -> str:
    actual = hash_body(req.reviewed_body)
    if actual != req.expected_body_hash:
        raise R4ReviewedBindError(
            f"reviewed_body_hash_mismatch:{actual}!={req.expected_body_hash}"
        )
    if not req.scenario_id:
        raise R4ReviewedBindError("missing_scenario_id")
    if req.tenant_id != LIVE_EVAL_TENANT_ID:
        raise R4ReviewedBindError("tenant not allowed for R4 reviewed bind", status_code=403)
    if req.scenario_id not in R4_SEND_SCENARIO_IDS:
        raise R4ReviewedBindError("scenario not in R4 send allowlist", status_code=400)
    if record is not None:
        if record.job_id != req.job_id:
            raise R4ReviewedBindError("approval does not belong to job", status_code=404)
        if str(record.state or "") != "pending":
            raise R4ReviewedBindError("approval not pending", status_code=409)
        next_on_approve = str(record.next_on_approve or "")
        if next_on_approve not in R4_ALLOWED_NEXT_ON_APPROVE:
            raise R4ReviewedBindError("approval is not a send-type approval", status_code=400)
    return actual


def build_r4_reviewed_bind_audit(req: R4ReviewedBindRequest) -> dict[str, Any]:
    validate_r4_reviewed_bind_request(req)
    return {
        "scenario_id": req.scenario_id,
        "canonical_body_hash": req.expected_body_hash,
        "body_source": R4_REVIEWED_BODY_SOURCE,
        "bound_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tenant_id": req.tenant_id,
        "approval_id": req.approval_id,
        "job_id": req.job_id,
        "r3_frozen_bind_reused": False,
    }


@dataclass(frozen=True)
class R4ReviewedBindResult:
    approval_id: str
    job_id: str
    scenario_id: str
    body_hash: str
    bound: bool
    audit: dict[str, Any]


def bind_reviewed_approval_body_record(
    db: Session,
    request: R4ReviewedBindRequest,
) -> R4ReviewedBindResult:
    record = ApprovalRequestRepository.get_by_approval_id(
        db=db,
        tenant_id=request.tenant_id,
        approval_id=request.approval_id,
    )
    if record is None:
        raise R4ReviewedBindError("approval not found", status_code=404)
    body_hash = validate_r4_reviewed_bind_request(request, record=record)
    audit = build_r4_reviewed_bind_audit(request)
    delivery = dict(record.delivery_payload or {})
    delivery["body"] = request.reviewed_body
    delivery["r4_reviewed_bind"] = audit
    record.delivery_payload = delivery

    if request.reviewed_snapshot:
        job = JobRepository.get_job_by_id_record(db, request.tenant_id, request.job_id)
        if job is not None:
            input_data = dict(job.input_data or {})
            live = dict(input_data.get("live_eval") or {})
            if (
                "r4_reviewed_body_snapshot" in live
                and live["r4_reviewed_body_snapshot"] != request.reviewed_snapshot
            ):
                raise R4ReviewedBindError(
                    "r4_reviewed_body_snapshot_immutable_violation", status_code=409
                )
            live["r4_reviewed_body_snapshot"] = request.reviewed_snapshot
            input_data["live_eval"] = live
            job.input_data = input_data

    db.commit()
    db.refresh(record)
    return R4ReviewedBindResult(
        approval_id=request.approval_id,
        job_id=request.job_id,
        scenario_id=request.scenario_id,
        body_hash=body_hash,
        bound=True,
        audit=audit,
    )
