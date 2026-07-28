"""Phase-separated observation contracts for semi-automatic live-eval."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from app.evaluation.live.campaign.operator_contract import OperatorPlanStep
from app.evaluation.live.campaign.semi_automatic_expected_outcomes import (
    SemiAutomaticExpectedOutcome,
)
from app.evaluation.live.campaign.test_operator import PendingApproval, match_target_approval
from app.evaluation.live.errors import LiveEvalPipelinePollError, LiveEvalSafetyError
from app.evaluation.live.pipeline_poll import (
    PipelinePollResult,
    build_redacted_job_snapshot,
    poll_pipeline_observation,
)

_TERMINAL_JOB_STATUSES = frozenset({"completed", "manual_review", "cancelled", "rejected"})
_PRE_OPERATOR_TERMINAL_WITHOUT_OPERATOR = frozenset(
    {"approval_bypass_or_phase_order_violation"}
)


@dataclass
class SemiAutoPhaseProvenance:
    evaluation_run_id: str
    job_id: str | None = None
    target_approval_id: str | None = None
    target_action_operation_id: str | None = None
    pre_operator_gate_started_at: str | None = None
    pre_operator_gate_passed_at: str | None = None
    operator_started_at: str | None = None
    operator_completed_at: str | None = None
    post_operator_poll_started_at: str | None = None
    post_operator_completed_at: str | None = None
    pre_operator_status: str | None = None
    post_operator_status: str | None = None
    pre_operator_pending_count: int | None = None
    post_operator_pending_count: int | None = None
    pre_operator_resolution_count: int = 0
    pre_operator_intent_count: int = 0
    pre_operator_outcome_count: int = 0
    post_operator_resolution_count: int = 0
    post_operator_intent_count: int = 0
    post_operator_outcome_count: int = 0
    phase_violations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "evaluation_run_id": self.evaluation_run_id,
            "job_id": self.job_id,
            "target_approval_id": self.target_approval_id,
            "target_action_operation_id": self.target_action_operation_id,
            "pre_operator_gate_started_at": self.pre_operator_gate_started_at,
            "pre_operator_gate_passed_at": self.pre_operator_gate_passed_at,
            "operator_started_at": self.operator_started_at,
            "operator_completed_at": self.operator_completed_at,
            "post_operator_poll_started_at": self.post_operator_poll_started_at,
            "post_operator_completed_at": self.post_operator_completed_at,
            "pre_operator_status": self.pre_operator_status,
            "post_operator_status": self.post_operator_status,
            "pre_operator_pending_count": self.pre_operator_pending_count,
            "post_operator_pending_count": self.post_operator_pending_count,
            "pre_operator_resolution_count": self.pre_operator_resolution_count,
            "pre_operator_intent_count": self.pre_operator_intent_count,
            "pre_operator_outcome_count": self.pre_operator_outcome_count,
            "post_operator_resolution_count": self.post_operator_resolution_count,
            "post_operator_intent_count": self.post_operator_intent_count,
            "post_operator_outcome_count": self.post_operator_outcome_count,
            "phase_violations": list(self.phase_violations),
        }


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _count_records(observation: dict[str, Any], record_type: str) -> int:
    records = (observation.get("job") or {}).get("decision_records") or []
    return sum(1 for row in records if str(row.get("record_type") or "") == record_type)


def _target_step(outcome: SemiAutomaticExpectedOutcome) -> OperatorPlanStep:
    if not outcome.operator_plan:
        raise LiveEvalSafetyError("semi-auto phase contract requires operator_plan")
    return outcome.operator_plan[0]


def resolve_post_operator_success_statuses(
    outcome: SemiAutomaticExpectedOutcome,
) -> frozenset[str]:
    """Terminal statuses allowed after explicit operator execution."""
    statuses = set(outcome.final_success_statuses)
    if outcome.operator_plan:
        first = outcome.operator_plan[0]
        if first.decision == "approve":
            statuses.add("completed")
        elif first.decision == "reject":
            statuses.add("manual_review")
    return frozenset(statuses)


def _snapshot_phase_counts(observation: dict[str, Any]) -> dict[str, int]:
    job = observation.get("job") or {}
    return {
        "pending": int(job.get("pending_approval_count") or 0),
        "resolution": _count_records(observation, "action_approval_resolution"),
        "intent": _count_records(observation, "execution_intent"),
        "outcome": _count_records(observation, "execution_outcome"),
        "status": str(job.get("job_status") or ""),
    }


def _assert_evaluation_run_unchanged(
    observation: dict[str, Any],
    *,
    evaluation_run_id: str,
) -> None:
    run = observation.get("run") or {}
    observed_run_id = str(run.get("evaluation_run_id") or "")
    if observed_run_id and observed_run_id != evaluation_run_id:
        raise LiveEvalSafetyError(
            "approval_bypass_or_phase_order_violation: evaluation_run_id changed between phases"
        )


def _raise_bypass(*, reason: str) -> None:
    raise LiveEvalSafetyError(f"approval_bypass_or_phase_order_violation: {reason}")


def classify_pre_operator_readiness(
    observation: dict[str, Any],
    *,
    outcome: SemiAutomaticExpectedOutcome,
    pending_approvals: list[PendingApproval],
    operator_started: bool,
) -> str | None:
    """Return None when ready to proceed, or a typed failure/bypass reason."""
    run = observation.get("run") or {}
    job = observation.get("job") or {}
    if not run.get("root_job_id") and not job.get("job_id"):
        return None

    counts = _snapshot_phase_counts(observation)
    status = counts["status"]
    step = _target_step(outcome)

    if not operator_started:
        if counts["resolution"] > 0 or counts["intent"] > 0 or counts["outcome"] > 0:
            return "resolution_or_execution_before_operator_request"
        if status in _TERMINAL_JOB_STATUSES and counts["pending"] == 0:
            return "terminal_status_before_operator_request"

    pending_rows = [row for row in pending_approvals if row.state == "pending"]
    if counts["pending"] != 1:
        if operator_started:
            return f"expected_pending_count_1_got_{counts['pending']}"
        if counts["pending"] == 0 and status in _TERMINAL_JOB_STATUSES:
            return "terminal_status_before_operator_request"
        if counts["pending"] != 1:
            return None

    try:
        target = match_target_approval(pending_rows, step)
    except LiveEvalSafetyError:
        if operator_started:
            return "target_approval_not_pending"
        return None

    if target.state != "pending":
        return "target_approval_not_pending"

    contract_pending = [
        row
        for row in pending_rows
        if row.next_on_approve in ("action_execute", "email_send")
    ]
    if len(contract_pending) != 1:
        return None

    if counts["resolution"] > 0 or counts["intent"] > 0 or counts["outcome"] > 0:
        return "resolution_or_execution_before_operator_request"

    return "ready"


def poll_pre_operator_readiness(
    fetch_observation: Callable[[], dict[str, Any]],
    fetch_pending_approvals: Callable[[str], list[PendingApproval]],
    *,
    outcome: SemiAutomaticExpectedOutcome,
    evaluation_run_id: str,
    timeout_seconds: float,
    provenance: SemiAutoPhaseProvenance,
) -> tuple[dict[str, Any], PendingApproval]:
    """Poll until target approval is pending and pre-operator gate preconditions hold."""
    started = time.monotonic()
    deadline = started + timeout_seconds
    delay = 0.0
    poll_attempts = 0
    last: dict[str, Any] = {}
    step = _target_step(outcome)

    provenance.pre_operator_gate_started_at = provenance.pre_operator_gate_started_at or _utcnow_iso()

    while time.monotonic() < deadline:
        poll_attempts += 1
        last = fetch_observation()
        _assert_evaluation_run_unchanged(last, evaluation_run_id=evaluation_run_id)

        job = last.get("job") or {}
        run = last.get("run") or {}
        job_id = str(job.get("job_id") or run.get("root_job_id") or "")
        if not job_id:
            time.sleep(max(delay, 0.05))
            delay = min(max(delay, 0.05) * 1.5, 2.0)
            continue

        provenance.job_id = job_id
        counts = _snapshot_phase_counts(last)
        provenance.pre_operator_status = counts["status"]
        provenance.pre_operator_pending_count = counts["pending"]
        provenance.pre_operator_resolution_count = counts["resolution"]
        provenance.pre_operator_intent_count = counts["intent"]
        provenance.pre_operator_outcome_count = counts["outcome"]

        pending_approvals = fetch_pending_approvals(job_id)
        readiness = classify_pre_operator_readiness(
            last,
            outcome=outcome,
            pending_approvals=pending_approvals,
            operator_started=False,
        )

        if readiness in _PRE_OPERATOR_TERMINAL_WITHOUT_OPERATOR or (
            readiness
            and readiness not in (None, "ready")
            and readiness.endswith("before_operator_request")
        ):
            _raise_bypass(reason=readiness)

        if readiness == "ready":
            target = match_target_approval(
                [row for row in pending_approvals if row.state == "pending"],
                step,
            )
            provenance.target_approval_id = target.approval_id
            provenance.target_action_operation_id = target.action_operation_id
            provenance.pre_operator_gate_passed_at = _utcnow_iso()
            return last, target

        time.sleep(max(delay, 0.05))
        delay = min(max(delay, 0.05) * 1.5, 2.0)

    raise LiveEvalPipelinePollError(
        timeout_reason="pre_operator_gate_timeout",
        job_snapshot=build_redacted_job_snapshot(last),
        poll_attempts=poll_attempts,
        poll_duration_seconds=time.monotonic() - started,
    )


def poll_post_operator_observation(
    fetch_observation: Callable[[], dict[str, Any]],
    *,
    outcome: SemiAutomaticExpectedOutcome,
    evaluation_run_id: str,
    timeout_seconds: float,
    provenance: SemiAutoPhaseProvenance,
) -> PipelinePollResult:
    """Poll job status using post-operator terminal contract only."""
    provenance.post_operator_poll_started_at = provenance.post_operator_poll_started_at or _utcnow_iso()
    if not provenance.operator_completed_at:
        raise LiveEvalSafetyError(
            "approval_bypass_or_phase_order_violation: post_operator_poll_before_operator_completion"
        )

    success_statuses = resolve_post_operator_success_statuses(outcome)

    def _on_poll(observation: dict[str, Any]) -> None:
        _assert_evaluation_run_unchanged(observation, evaluation_run_id=evaluation_run_id)
        counts = _snapshot_phase_counts(observation)
        provenance.post_operator_status = counts["status"]
        provenance.post_operator_pending_count = counts["pending"]
        provenance.post_operator_resolution_count = counts["resolution"]
        provenance.post_operator_intent_count = counts["intent"]
        provenance.post_operator_outcome_count = counts["outcome"]

    result = poll_pipeline_observation(
        fetch_observation,
        timeout_seconds=timeout_seconds,
        on_poll=_on_poll,
        success_statuses=success_statuses,
    )
    provenance.post_operator_completed_at = _utcnow_iso()
    return result


def assert_phase_monotonicity(provenance: SemiAutoPhaseProvenance) -> list[str]:
    """Validate timestamp and phase ordering invariants."""
    violations: list[str] = []

    def _parse(value: str | None) -> datetime | None:
        if not value:
            return None
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    ordered = [
        ("pre_operator_gate_started_at", provenance.pre_operator_gate_started_at),
        ("pre_operator_gate_passed_at", provenance.pre_operator_gate_passed_at),
        ("operator_started_at", provenance.operator_started_at),
        ("operator_completed_at", provenance.operator_completed_at),
        ("post_operator_poll_started_at", provenance.post_operator_poll_started_at),
        ("post_operator_completed_at", provenance.post_operator_completed_at),
    ]
    previous: datetime | None = None
    for label, raw in ordered:
        current = _parse(raw)
        if current is None:
            continue
        if previous is not None and current < previous:
            violations.append(f"phase_timestamp_not_monotonic:{label}")
        previous = current

    if provenance.operator_started_at and not provenance.pre_operator_gate_passed_at:
        violations.append("operator_started_before_pre_operator_gate_pass")
    if provenance.post_operator_poll_started_at and not provenance.operator_completed_at:
        violations.append("post_operator_poll_before_operator_completion")
    if provenance.pre_operator_resolution_count > 0 and not provenance.operator_started_at:
        violations.append("resolution_before_operator_request")

    provenance.phase_violations = violations
    return violations
