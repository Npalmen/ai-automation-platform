"""Structured, allowlisted live-eval safety rejection payloads."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.evaluation.live.errors import LiveEvalSafetyError

ALLOWED_SAFETY_REASONS = frozenset(
    {
        "recipient_identity_unverified",
        "recipient_identity_conflict",
        "recipient_not_allowlisted",
        "recipient_mismatch",
        "sender_mismatch",
        "run_tenant_mismatch",
        "run_scenario_mismatch",
        "run_attempt_mismatch",
        "run_status_invalid",
        "run_expired",
        "delivery_validation_failed",
        "intake_failed",
        "mutation_context_rejected",
        "safety_rejected_unknown",
        "missing_subject_token",
        "evaluation_run_id_mismatch",
        "scenario_id_mismatch",
        "attempt_id_mismatch",
        "missing_intake_label",
        "internal_date_out_of_window",
        "body_marker_mismatch",
    }
)

_DIAGNOSTIC_BY_REASON = {
    "recipient_identity_unverified": "RECIPIENT_IDENTITY_UNVERIFIED",
    "recipient_identity_conflict": "RECIPIENT_IDENTITY_CONFLICT",
    "recipient_not_allowlisted": "RECIPIENT_NOT_ALLOWLISTED",
    "recipient_mismatch": "RECIPIENT_MISMATCH",
    "sender_mismatch": "SENDER_MISMATCH",
    "run_tenant_mismatch": "RUN_TENANT_MISMATCH",
    "run_scenario_mismatch": "RUN_SCENARIO_MISMATCH",
    "run_attempt_mismatch": "RUN_ATTEMPT_MISMATCH",
    "run_status_invalid": "RUN_STATUS_INVALID",
    "run_expired": "RUN_EXPIRED",
    "delivery_validation_failed": "DELIVERY_VALIDATION_FAILED",
    "intake_failed": "INTAKE_FAILED",
    "mutation_context_rejected": "MUTATION_CONTEXT_REJECTED",
    "safety_rejected_unknown": "SAFETY_REJECTED_UNKNOWN",
    "missing_subject_token": "DELIVERY_MISSING_SUBJECT_TOKEN",
    "evaluation_run_id_mismatch": "DELIVERY_RUN_ID_MISMATCH",
    "scenario_id_mismatch": "DELIVERY_SCENARIO_MISMATCH",
    "attempt_id_mismatch": "DELIVERY_ATTEMPT_MISMATCH",
    "missing_intake_label": "DELIVERY_MISSING_INTAKE_LABEL",
    "internal_date_out_of_window": "DELIVERY_DATE_OUT_OF_WINDOW",
    "body_marker_mismatch": "DELIVERY_BODY_MARKER_MISMATCH",
}


class LiveEvalSafetyRejectedPayload(BaseModel):
    error_code: Literal["live_eval_safety"] = "live_eval_safety"
    safety_reason: str
    evaluation_run_id: str
    scenario_id: str
    attempt_id: int
    tenant_id: str
    failed_stage: str
    http_status: int = 400
    retry_allowed: bool = False
    root_job_created: bool = False
    diagnostic_code: str


def classify_safety_reason(message: str) -> str:
    text = (message or "").strip().lower()
    if text in ALLOWED_SAFETY_REASONS:
        return text
    if "recipient identity" in text or "verified recipient" in text:
        return "recipient_identity_unverified"
    if "recipient identity conflict" in text or text == "recipient_identity_conflict":
        return "recipient_identity_conflict"
    if "recipient not allowlisted" in text or text == "recipient_not_allowlisted":
        return "recipient_not_allowlisted"
    if "recipient does not match registered expected_recipient" in text:
        return "recipient_mismatch"
    if "sender does not match registered expected_sender" in text:
        return "sender_mismatch"
    if "run tenant mismatch" in text:
        return "run_tenant_mismatch"
    if "scenario_id mismatch" in text or "run scenario_id mismatch" in text:
        return "run_scenario_mismatch"
    if "attempt_id mismatch" in text or "run attempt_id mismatch" in text:
        return "run_attempt_mismatch"
    if "run status" in text or "terminal" in text:
        return "run_status_invalid"
    if "run has expired" in text:
        return "run_expired"
    if text.startswith("delivery validation failed:"):
        sub = text.split(":", 1)[1].strip()
        if sub in ALLOWED_SAFETY_REASONS:
            return sub
        return "delivery_validation_failed"
    if text.startswith("live_eval_safety:"):
        return classify_safety_reason(text.split(":", 1)[1])
    if text.startswith("intake failed"):
        return "intake_failed"
    return "safety_rejected_unknown"


def build_safety_rejected_payload(
    *,
    evaluation_run_id: str,
    scenario_id: str,
    attempt_id: int,
    tenant_id: str,
    safety_reason: str,
    failed_stage: str = "triggering_intake",
    root_job_created: bool = False,
) -> LiveEvalSafetyRejectedPayload:
    reason = safety_reason if safety_reason in ALLOWED_SAFETY_REASONS else classify_safety_reason(safety_reason)
    return LiveEvalSafetyRejectedPayload(
        safety_reason=reason,
        evaluation_run_id=evaluation_run_id,
        scenario_id=scenario_id,
        attempt_id=attempt_id,
        tenant_id=tenant_id,
        failed_stage=failed_stage,
        http_status=400,
        retry_allowed=False,
        root_job_created=root_job_created,
        diagnostic_code=_DIAGNOSTIC_BY_REASON.get(reason, "SAFETY_REJECTED_UNKNOWN"),
    )


def build_safety_rejected_payload_from_exc(
    exc: LiveEvalSafetyError | str,
    *,
    evaluation_run_id: str,
    scenario_id: str,
    attempt_id: int,
    tenant_id: str,
    failed_stage: str = "triggering_intake",
    root_job_created: bool = False,
) -> LiveEvalSafetyRejectedPayload:
    message = str(exc)
    return build_safety_rejected_payload(
        evaluation_run_id=evaluation_run_id,
        scenario_id=scenario_id,
        attempt_id=attempt_id,
        tenant_id=tenant_id,
        safety_reason=classify_safety_reason(message),
        failed_stage=failed_stage,
        root_job_created=root_job_created,
    )


def parse_safety_rejected_payload(data: object) -> LiveEvalSafetyRejectedPayload | None:
    if not isinstance(data, dict):
        return None
    detail = data.get("detail") if "detail" in data else data
    if not isinstance(detail, dict):
        return None
    if detail.get("error_code") != "live_eval_safety":
        return None
    try:
        return LiveEvalSafetyRejectedPayload.model_validate(detail)
    except Exception:
        return None
