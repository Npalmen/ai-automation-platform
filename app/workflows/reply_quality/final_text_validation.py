"""Final customer-text validation gate for coworker reply rendering."""

from __future__ import annotations

from typing import Any

from app.workflows.reply_quality.plan_v2 import CustomerReplyPlanV2
from app.workflows.reply_quality.post_render_validator import validate_post_render_reply
from app.workflows.reply_quality.provenance import hash_body

POLICY_VERSION = "final_customer_text_validation_v1"


def validate_stage(
    *,
    plan: CustomerReplyPlanV2,
    body: str,
    validation_stage: str,
) -> dict[str, Any]:
    validation = validate_post_render_reply(plan=plan, body=body)
    return {
        "validation_stage": validation_stage,
        "passed": bool(validation.get("passed")),
        "issues": list(validation.get("issues") or []),
        "validated_body_hash": hash_body(body),
        "validator_version": validation.get("policy_version"),
    }


def build_final_customer_text_validation(
  *,
    plan: CustomerReplyPlanV2,
    body: str,
    stage_results: list[dict[str, Any]],
) -> dict[str, Any]:
    final = validate_stage(plan=plan, body=body, validation_stage="final_customer_text")
    return {
        **final,
        "policy_version": POLICY_VERSION,
        "stage_results": stage_results,
    }
