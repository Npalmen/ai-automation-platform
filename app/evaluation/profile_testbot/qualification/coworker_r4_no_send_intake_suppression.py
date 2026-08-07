"""R4-only authoritative no-send intake suppression contract.

Does NOT enable newsletter intake or generalize arbitrary intake skips.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (
    R4_NO_SEND_SCENARIO_IDS,
)

R4_NO_SEND_INTAKE_SUPPRESSION_SCENARIO_ID = "PTB-SEM-0023"
R4_NO_SEND_INTAKE_SUPPRESSION_REASON = "newsletter_disabled"
R4_NO_SEND_INTAKE_SUPPRESSION_EXPECTED_BEHAVIOR = "no_reply"

R4_AUTHORITATIVE_INTAKE_SUPPRESSION: dict[str, str] = {
    R4_NO_SEND_INTAKE_SUPPRESSION_SCENARIO_ID: R4_NO_SEND_INTAKE_SUPPRESSION_REASON,
}


@dataclass
class R4NoSendIntakeSuppressionResolution:
    eligible: bool
    blockers: list[str] = field(default_factory=list)
    scenario_id: str | None = None
    intake_suppression_reason: str | None = None
    expected_send_behavior: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "eligible": self.eligible,
            "blockers": list(self.blockers),
            "scenario_id": self.scenario_id,
            "intake_suppression_reason": self.intake_suppression_reason,
            "expected_send_behavior": self.expected_send_behavior,
        }


def parse_intake_skip_reason_from_error(exc: BaseException) -> str | None:
    msg = str(exc).strip()
    prefix = "intake_skipped:"
    if not msg.startswith(prefix):
        return None
    reason = msg[len(prefix) :].strip()
    return reason or None


def scenario_local_gmail_sends(
    *,
    campaign_gmail_sends_before: int,
    campaign_gmail_sends_after: int,
) -> int:
    """Scenario-local Gmail send delta from campaign cumulative counters."""
    return campaign_gmail_sends_after - campaign_gmail_sends_before


def resolve_r4_no_send_intake_suppression(
    *,
    scenario_id: str,
    expected_send_behavior: str,
    intake_skip_reason: str,
    inbound_delivery_observed: bool,
    job_id: str | None = None,
    approval_count: int = 0,
    gmail_sends: int = 0,
    gmail_drafts: int = 0,
    external_executions: int = 0,
    provider_accepted: bool = False,
    ambiguous_outcome: bool = False,
) -> R4NoSendIntakeSuppressionResolution:
    blockers: list[str] = []
    expected_reason = R4_AUTHORITATIVE_INTAKE_SUPPRESSION.get(scenario_id)
    if expected_reason is None:
        blockers.append("scenario_not_allowlisted_for_intake_suppression")
    elif intake_skip_reason != expected_reason:
        blockers.append(f"intake_skip_reason_mismatch:{intake_skip_reason}")
    if scenario_id not in R4_NO_SEND_SCENARIO_IDS:
        blockers.append("scenario_not_in_r4_no_send_registry")
    if expected_send_behavior != R4_NO_SEND_INTAKE_SUPPRESSION_EXPECTED_BEHAVIOR:
        blockers.append(f"expected_send_behavior_mismatch:{expected_send_behavior}")
    if not inbound_delivery_observed:
        blockers.append("inbound_delivery_not_observed")
    if ambiguous_outcome:
        blockers.append("ambiguous_outcome")
    if job_id:
        blockers.append("job_created_unexpectedly")
    if approval_count > 0:
        blockers.append("approval_created_unexpectedly")
    if gmail_sends > 0:
        blockers.append("gmail_send_observed")
    if gmail_drafts > 0:
        blockers.append("gmail_draft_observed")
    if external_executions > 0:
        blockers.append("external_execution_observed")
    if provider_accepted:
        blockers.append("provider_reply_observed")

    return R4NoSendIntakeSuppressionResolution(
        eligible=not blockers,
        blockers=blockers,
        scenario_id=scenario_id,
        intake_suppression_reason=intake_skip_reason,
        expected_send_behavior=expected_send_behavior,
    )


def apply_r4_expected_intake_suppression_result(
    result: dict[str, Any],
    *,
    resolution: R4NoSendIntakeSuppressionResolution,
    intake_skip_reason: str,
) -> dict[str, Any]:
    if not resolution.eligible:
        return result
    out = dict(result)
    out["status"] = "passed"
    out["execution_outcome"] = "expected_intake_suppression"
    out["intake_suppressed"] = True
    out["intake_suppression_reason"] = intake_skip_reason
    out["job_created"] = False
    out["job_id"] = ""
    out["approval_count"] = 0
    out["approval_state"] = None
    out["actual_policy_result"] = "intake_suppressed"
    out["gmail_sends"] = 0
    out["gmail_drafts"] = 0
    out["external_executions"] = 0
    out["trigger_delivery_observed"] = True
    out["inbound_trigger_sent"] = True
    out["unknown_outcome"] = False
    out.pop("failure_stage", None)
    out.pop("failure_reason", None)
    audit = list(out.get("audit_events") or [])
    audit.append(
        {
            "event": "expected_intake_suppression",
            "intake_suppression_reason": intake_skip_reason,
            "job_created": False,
        }
    )
    out["audit_events"] = audit
    out["_r4_no_send_intake_suppression"] = resolution.to_dict()
    return out
