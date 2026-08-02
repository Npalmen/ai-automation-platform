"""Thread-aware context for coworker replies (Todo F)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

POLICY_VERSION = "thread_context_v1"


@dataclass(frozen=True)
class ThreadReplyContext:
    thread_state: str
    is_first_contact: bool
    is_continuation: bool
    prior_operator_reply: bool
    prior_safe_ack: bool
    supplied_facts: tuple[str, ...]
    summary: str
    policy_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "thread_state": self.thread_state,
            "is_first_contact": self.is_first_contact,
            "is_continuation": self.is_continuation,
            "prior_operator_reply": self.prior_operator_reply,
            "prior_safe_ack": self.prior_safe_ack,
            "supplied_facts": list(self.supplied_facts),
            "summary": self.summary,
            "policy_version": self.policy_version,
        }


def build_thread_reply_context(
    *,
    thread_state: str = "new_thread",
    prior_operator_reply: bool = False,
    prior_safe_ack: bool = False,
    supplied_facts: tuple[str, ...] = (),
) -> ThreadReplyContext:
    normalized = thread_state or "new_thread"
    is_continuation = normalized in {"continuation", "out_of_order"}
    is_first = normalized == "new_thread" and not prior_safe_ack and not prior_operator_reply
    if is_continuation:
        summary = "Kunden följer upp i befintlig tråd."
    elif prior_safe_ack:
        summary = "Tidigare säkert mottagningskvitto finns i tråden."
    else:
        summary = "Första kontakt i tråden."
    return ThreadReplyContext(
        thread_state=normalized,
        is_first_contact=is_first,
        is_continuation=is_continuation,
        prior_operator_reply=prior_operator_reply,
        prior_safe_ack=prior_safe_ack,
        supplied_facts=supplied_facts,
        summary=summary,
        policy_version=POLICY_VERSION,
    )


def acknowledgement_mode_for_thread(
    *,
    thread: ThreadReplyContext,
    service_family: str,
    next_step_id: str,
) -> str:
    if service_family == "job_status":
        return "status_acknowledgement"
    if service_family in {"existing_installation_support", "complaint_warranty"}:
        return "support_acknowledgement"
    if thread.is_continuation and not thread.is_first_contact:
        return "information_request"
    if next_step_id == "confirm_case_receipt_only":
        return "receipt_acknowledgement"
    return "information_request"
