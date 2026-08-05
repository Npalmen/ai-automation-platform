"""R4 reviewed-live mutation contract (separate from R3 frozen)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (
    R4_EXECUTE_AI_MODE,
    R4_EXECUTION_MODE,
    R4_LIVE_QUALITY_CAMPAIGN_TYPE,
    R4_TENANT_ID,
)

R4_MUTATION_PROCESS_DELIVERY = "process_delivery_exact_message"
R4_MUTATION_CLAIM_ROOT_JOB = "claim_root_job"
R4_MUTATION_BIND_REVIEWED_BODY = "bind_reviewed_approval_body"
R4_MUTATION_APPROVE_REVIEWED_REPLY = "approve_reviewed_reply"
R4_MUTATION_OBSERVE_APPROVED_REPLY = "observe_approved_reply"

R4_ALLOWED_MUTATIONS: frozenset[str] = frozenset(
    {
        R4_MUTATION_PROCESS_DELIVERY,
        R4_MUTATION_CLAIM_ROOT_JOB,
        R4_MUTATION_BIND_REVIEWED_BODY,
        R4_MUTATION_APPROVE_REVIEWED_REPLY,
        R4_MUTATION_OBSERVE_APPROVED_REPLY,
    }
)


@dataclass
class R4MutationContractResult:
    allowed: bool
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"allowed": self.allowed, "blockers": self.blockers}


def is_r4_reviewed_live_eval_context(
    *,
    tenant_id: str | None,
    campaign_type: str | None,
    execution_mode: str | None,
    ai_mode: str | None,
) -> bool:
    return (
        tenant_id == R4_TENANT_ID
        and campaign_type == R4_LIVE_QUALITY_CAMPAIGN_TYPE
        and execution_mode == R4_EXECUTION_MODE
        and ai_mode in {R4_EXECUTE_AI_MODE, "live_llm"}
    )


def validate_r4_mutation_operation(
    *,
    operation: str,
    tenant_id: str | None,
    campaign_type: str | None,
    execution_mode: str | None,
    ai_mode: str | None,
    automatic_gmail: bool = False,
    production_activation: bool = False,
    drafts_allowed: bool = False,
) -> R4MutationContractResult:
    blockers: list[str] = []
    if not is_r4_reviewed_live_eval_context(
        tenant_id=tenant_id,
        campaign_type=campaign_type,
        execution_mode=execution_mode,
        ai_mode=ai_mode,
    ):
        blockers.append("not_r4_reviewed_live_context")
    if operation not in R4_ALLOWED_MUTATIONS:
        blockers.append(f"operation_not_allowlisted:{operation}")
    if automatic_gmail:
        blockers.append("automatic_gmail_true")
    if production_activation:
        blockers.append("production_activation_true")
    if drafts_allowed:
        blockers.append("drafts_forbidden")
    return R4MutationContractResult(allowed=not blockers, blockers=blockers)
