"""Structured, allowlisted intake skip error payloads for live-eval."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ALLOWED_INTAKE_SKIP_REASONS = frozenset(
    {
        "missing_intake_cutoff",
        "before_intake_cutoff",
        "lead_disabled",
        "customer_inquiry_disabled",
        "invoice_disabled",
        "duplicate",
        "intake_skipped_unknown",
    }
)

_DIAGNOSTIC_BY_REASON = {
    "missing_intake_cutoff": "INTAKE_GATE_MISSING_CUTOFF",
    "before_intake_cutoff": "INTAKE_GATE_BEFORE_CUTOFF",
    "lead_disabled": "INTAKE_JOB_TYPE_DISABLED",
    "customer_inquiry_disabled": "INTAKE_JOB_TYPE_DISABLED",
    "invoice_disabled": "INTAKE_JOB_TYPE_DISABLED",
    "duplicate": "INTAKE_DUPLICATE",
    "intake_skipped_unknown": "INTAKE_SKIPPED_UNKNOWN",
}


class IntakeSkippedErrorPayload(BaseModel):
    error_code: Literal["intake_skipped"] = "intake_skipped"
    intake_result: Literal["skipped"] = "skipped"
    intake_skip_reason: str
    evaluation_run_id: str
    failed_stage: str = "triggering_intake"
    http_status: int = 409
    run_status: str
    root_claimed: bool
    job_created: bool = False
    retry_allowed: bool = False
    diagnostic_code: str


def normalize_intake_skip_reason(raw: str | None) -> str:
    reason = (raw or "").strip()
    if reason in ALLOWED_INTAKE_SKIP_REASONS:
        return reason
    if reason.endswith("_disabled"):
        if reason in ALLOWED_INTAKE_SKIP_REASONS:
            return reason
    return "intake_skipped_unknown"


def build_intake_skipped_payload(
    *,
    evaluation_run_id: str,
    raw_reason: str | None,
    run_status: str,
    root_claimed: bool,
    failed_stage: str = "triggering_intake",
) -> IntakeSkippedErrorPayload:
    reason = normalize_intake_skip_reason(raw_reason)
    return IntakeSkippedErrorPayload(
        intake_skip_reason=reason,
        evaluation_run_id=evaluation_run_id,
        failed_stage=failed_stage,
        http_status=409,
        run_status=run_status,
        root_claimed=root_claimed,
        job_created=False,
        retry_allowed=False,
        diagnostic_code=_DIAGNOSTIC_BY_REASON.get(reason, "INTAKE_SKIPPED_UNKNOWN"),
    )


def parse_intake_skipped_payload(data: object) -> IntakeSkippedErrorPayload | None:
    if not isinstance(data, dict):
        return None
    detail = data.get("detail") if "detail" in data else data
    if not isinstance(detail, dict):
        return None
    if detail.get("error_code") != "intake_skipped":
        return None
    try:
        return IntakeSkippedErrorPayload.model_validate(detail)
    except Exception:
        return None
