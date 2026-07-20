"""Collect observations from a scenario run."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.repositories.postgres.decision_record_repository import DecisionRecordRepository
from app.workflows.processors.ai_processor_utils import get_latest_processor_payload


@dataclass
class ScenarioObservation:
    job: Any
    decision_records: list[dict[str, Any]] = field(default_factory=list)
    telemetry: dict[str, Any] = field(default_factory=dict)
    actions_by_type: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    operations_by_type: dict[str, list[str]] = field(default_factory=dict)

    def policy_payload(self) -> dict[str, Any]:
        return get_latest_processor_payload(self.job, "policy_processor") or {}

    def classification_payload(self) -> dict[str, Any]:
        return get_latest_processor_payload(self.job, "classification_processor") or {}

    def dispatch_payload(self) -> dict[str, Any]:
        return get_latest_processor_payload(self.job, "action_dispatch_processor") or {}

    def lead_analyzer_payload(self) -> dict[str, Any]:
        return get_latest_processor_payload(self.job, "lead_analyzer_processor") or {}

    def reply_body(self) -> str:
        for action in self.dispatch_payload().get("actions_requested") or []:
            if action.get("type") == "send_customer_auto_reply" and not action.get("_skip"):
                return str(action.get("body") or "")
        for action in self.dispatch_payload().get("actions_executed") or []:
            if action.get("type") == "send_customer_auto_reply":
                return str((action.get("payload") or {}).get("body") or "")
        return ""

    def handoff_body(self) -> str:
        for action in self.dispatch_payload().get("actions_requested") or []:
            if action.get("type") == "send_internal_handoff":
                return str(action.get("body") or "")
        return ""


def collect_observation(db: Session, job) -> ScenarioObservation:
    rows = DecisionRecordRepository.list_for_job(db, tenant_id=job.tenant_id, job_id=job.job_id)
    records = [
        {
            "record_type": r.record_type,
            "action_type": r.action_type,
            "action_operation_id": r.action_operation_id,
            "action_authorization": r.action_authorization,
            "execution_status": r.execution_status,
            "policy_authorization": r.policy_authorization,
            "policy_decision": r.policy_decision,
            "pipeline_run_id": r.pipeline_run_id,
            "parent_pipeline_run_id": r.parent_pipeline_run_id,
            "metadata": r.metadata_json or {},
            "event_sequence": r.event_sequence,
        }
        for r in rows
    ]
    by_type: dict[str, list[dict[str, Any]]] = {}
    dispatch = get_latest_processor_payload(job, "action_dispatch_processor") or {}
    for action in (dispatch.get("actions_requested") or []):
        t = str(action.get("type") or "")
        by_type.setdefault(t, []).append(action)

    ops_by_type: dict[str, list[str]] = {}
    for rec in records:
        op = rec.get("action_operation_id")
        at = rec.get("action_type")
        if op and at:
            ops_by_type.setdefault(at, [])
            if op not in ops_by_type[at]:
                ops_by_type[at].append(op)

    from app.evaluation.telemetry import get_telemetry

    return ScenarioObservation(
        job=job,
        decision_records=records,
        telemetry=get_telemetry().as_dict(),
        actions_by_type=by_type,
        operations_by_type=ops_by_type,
    )
