"""R4 reviewed-live mutation contract (separate from R3 frozen)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.evaluation.live.constants import (
    REVIEWED_LIVE_LLM_BODY,
    RUN_STATUS_ABORTED,
    RUN_STATUS_ACTIVE,
    RUN_STATUS_REGISTERED,
    TERMINAL_RUN_STATUSES,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (
    R4_EXECUTE_AI_MODE,
    R4_EXECUTION_MODE,
    R4_LIVE_QUALITY_CAMPAIGN_TYPE,
    R4_LOCKED_MANIFEST_SEMANTIC_HASH,
    R4_NO_SEND_SCENARIO_IDS,
    R4_SEND_SCENARIO_IDS,
    R4_TENANT_ID,
)
from app.repositories.postgres.live_eval_models import LiveEvalRunRow

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
        and ai_mode == R4_EXECUTE_AI_MODE
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
    # Bare ai_mode without campaign/execution context must not authorize mutations.
    if ai_mode == REVIEWED_LIVE_LLM_BODY and (
        campaign_type != R4_LIVE_QUALITY_CAMPAIGN_TYPE
        or execution_mode != R4_EXECUTION_MODE
    ):
        if "not_r4_reviewed_live_context" not in blockers:
            blockers.append("generic_reviewed_live_llm_body_blocked")
    return R4MutationContractResult(allowed=not blockers, blockers=blockers)


def validate_r4_mutation_operation_for_row(
    row: LiveEvalRunRow,
    *,
    tenant_id: str,
    operation: str,
    recipient_message_id: str | None = None,
) -> R4MutationContractResult:
    blockers: list[str] = []
    ctx = getattr(row, "registration_context", None) or {}
    if not isinstance(ctx, dict):
        ctx = {}

    base = validate_r4_mutation_operation(
        operation=operation,
        tenant_id=row.tenant_id,
        campaign_type=getattr(row, "campaign_type", None),
        execution_mode=getattr(row, "execution_mode", None),
        ai_mode=row.ai_mode,
        automatic_gmail=bool(ctx.get("automatic_gmail")),
        production_activation=bool(ctx.get("production_activation")),
        drafts_allowed=False,
    )
    blockers.extend(base.blockers)

    if row.tenant_id != tenant_id:
        blockers.append("tenant_mismatch")
    if row.transport_mode != "live_gmail":
        blockers.append("transport_mode_mismatch")
    if getattr(row, "manifest_hash", None) != R4_LOCKED_MANIFEST_SEMANTIC_HASH:
        blockers.append("manifest_hash_mismatch")
    if row.scenario_id not in set(R4_SEND_SCENARIO_IDS) | set(R4_NO_SEND_SCENARIO_IDS):
        blockers.append("scenario_not_in_r4_registry")

    planned = ctx.get("planned_gmail_send")
    expected_send = row.scenario_id in R4_SEND_SCENARIO_IDS
    if planned is not None and bool(planned) != expected_send:
        blockers.append("planned_gmail_send_mismatch")
    if expected_send and not ctx.get("reviewed_body_hash"):
        blockers.append("send_missing_reviewed_body_hash")
    if not expected_send and ctx.get("reviewed_body_hash"):
        blockers.append("no_send_has_reviewed_body_hash")

    if row.status in TERMINAL_RUN_STATUSES and row.status != RUN_STATUS_ABORTED:
        blockers.append(f"run_terminal:{row.status}")
    if row.status not in {RUN_STATUS_REGISTERED, RUN_STATUS_ACTIVE, RUN_STATUS_ABORTED}:
        blockers.append(f"run_status_not_mutable:{row.status}")

    if recipient_message_id and row.root_gmail_message_id:
        if recipient_message_id != row.root_gmail_message_id:
            blockers.append("recipient_message_id_mismatch")

    blockers = list(dict.fromkeys(blockers))
    return R4MutationContractResult(allowed=not blockers, blockers=blockers)
