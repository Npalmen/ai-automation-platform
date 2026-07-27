"""Target-scoped approval observation helpers for semi-auto campaigns."""

from __future__ import annotations

from app.evaluation.live.campaign.semi_automatic_expected_outcomes import (
    SemiAutomaticExpectedOutcome,
)
from app.evaluation.live.campaign.test_operator import PendingApproval

_LEGACY_JOB_LEVEL_NEXT = frozenset({"action_dispatch"})
_PER_ACTION_NEXT = frozenset({"action_execute", "email_send"})
_EXTERNAL_WRITE_ACTIONS = frozenset({"send_customer_auto_reply", "send_email", "send_internal_handoff"})


def is_legacy_job_level_approval(row: PendingApproval) -> bool:
    """Job-level fallback row that per-action materialization supersedes."""
    if row.next_on_approve in _LEGACY_JOB_LEVEL_NEXT:
        return True
    if row.next_on_approve in _PER_ACTION_NEXT:
        return False
    return not row.action_operation_id


def count_contract_pending_external_write_approvals(
    approvals: list[PendingApproval],
    outcome: SemiAutomaticExpectedOutcome,
) -> int:
    """Count pending external-write rows that violate the semi-auto contract."""
    allowed_pending_types: set[str] = set()
    for secondary in outcome.secondary_approvals:
        if secondary.expected_final_state == "remain_pending":
            allowed_pending_types.add(secondary.action_type)

    count = 0
    for row in approvals:
        if row.state != "pending":
            continue
        if is_legacy_job_level_approval(row):
            continue
        action_type = row.action_type or row.delivery_type
        if action_type not in _EXTERNAL_WRITE_ACTIONS:
            continue
        if action_type in allowed_pending_types:
            continue
        count += 1
    return count


def has_unexpected_pending_approvals(
    approvals: list[PendingApproval],
    outcome: SemiAutomaticExpectedOutcome,
) -> bool:
    return count_contract_pending_external_write_approvals(approvals, outcome) > 0
