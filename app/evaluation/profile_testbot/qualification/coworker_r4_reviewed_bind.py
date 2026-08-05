"""Bind human-reviewed R4 body onto pending approval (hash-locked)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.workflows.reply_quality.provenance import hash_body


@dataclass(frozen=True)
class R4ReviewedBindRequest:
    tenant_id: str
    job_id: str
    approval_id: str
    scenario_id: str
    reviewed_body: str
    expected_body_hash: str


class R4ReviewedBindError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def validate_r4_reviewed_bind_request(req: R4ReviewedBindRequest) -> None:
    actual = hash_body(req.reviewed_body)
    if actual != req.expected_body_hash:
        raise R4ReviewedBindError(
            f"reviewed_body_hash_mismatch:{actual}!={req.expected_body_hash}"
        )
    if not req.scenario_id:
        raise R4ReviewedBindError("missing_scenario_id")


def build_r4_reviewed_bind_audit(req: R4ReviewedBindRequest) -> dict[str, Any]:
    validate_r4_reviewed_bind_request(req)
    return {
        "scenario_id": req.scenario_id,
        "canonical_body_hash": req.expected_body_hash,
        "body_source": "r4_human_reviewed_candidate",
        "bound_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tenant_id": req.tenant_id,
        "approval_id": req.approval_id,
        "job_id": req.job_id,
        "r3_frozen_bind_reused": False,
    }
