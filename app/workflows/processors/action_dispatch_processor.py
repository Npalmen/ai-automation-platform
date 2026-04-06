from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.domain.workflows.models import Job
from app.repositories.postgres.action_execution_repository import ActionExecutionRepository
from app.workflows.action_executor import execute_action
from app.workflows.processors.ai_processor_utils import (
    append_processor_result,
    get_latest_processor_payload,
)

PROCESSOR_NAME = "action_dispatch_processor"


def _build_actions_from_input(job: Job) -> list[dict[str, Any]]:
    input_data = job.input_data or {}
    actions = input_data.get("actions")
    if actions is None:
        return []

    if not isinstance(actions, list):
        raise ValueError("input_data.actions must be a list.")

    normalized: list[dict[str, Any]] = []
    for item in actions:
        if not isinstance(item, dict):
            raise ValueError("Each item in input_data.actions must be an object.")
        normalized.append(item)

    return normalized


def _build_actions_from_decisioning(job: Job) -> list[dict[str, Any]]:
    decisioning_payload = get_latest_processor_payload(job, "decisioning_processor")
    actions = decisioning_payload.get("actions")
    if actions is None:
        return []

    if not isinstance(actions, list):
        raise ValueError("decisioning_processor payload.actions must be a list.")

    normalized: list[dict[str, Any]] = []
    for item in actions:
        if not isinstance(item, dict):
            raise ValueError("Each decisioning action must be an object.")
        normalized.append(item)

    return normalized


def _build_fallback_actions(job: Job) -> list[dict[str, Any]]:
    input_data = job.input_data or {}
    classification_payload = get_latest_processor_payload(job, "classification_processor")

    detected_job_type = classification_payload.get("detected_job_type", job.job_type.value)
    subject = input_data.get("subject") or f"New {detected_job_type}"
    message_text = input_data.get("message_text") or ""

    owner_email = input_data.get("owner_email")
    slack_channel = input_data.get("slack_channel")
    teams_channel = input_data.get("teams_channel")

    actions: list[dict[str, Any]] = []

    if owner_email:
        actions.append(
            {
                "type": "send_email",
                "to": owner_email,
                "subject": f"[AI Automation] {subject}",
                "body": message_text or f"A new {detected_job_type} job was processed.",
            }
        )

    if slack_channel:
        actions.append(
            {
                "type": "notify_slack",
                "channel": slack_channel,
                "message": f"Processed job '{subject}' as {detected_job_type}.",
            }
        )

    if teams_channel:
        actions.append(
            {
                "type": "notify_teams",
                "channel": teams_channel,
                "message": f"Processed job '{subject}' as {detected_job_type}.",
            }
        )

    if not actions:
        actions.append(
            {
                "type": "create_internal_task",
                "title": f"Follow up: {subject}",
                "description": message_text or f"Review processed {detected_job_type} job.",
                "assignee": None,
                "metadata": {
                    "job_id": job.job_id,
                    "tenant_id": job.tenant_id,
                    "detected_job_type": detected_job_type,
                },
            }
        )

    return actions


def _resolve_actions(job: Job) -> list[dict[str, Any]]:
    input_actions = _build_actions_from_input(job)
    if input_actions:
        return input_actions

    decisioning_actions = _build_actions_from_decisioning(job)
    if decisioning_actions:
        return decisioning_actions

    return _build_fallback_actions(job)


def _persist_successful_action(
    db: Session | None,
    job: Job,
    request_action: dict[str, Any],
    executed_action: dict[str, Any],
    attempt_no: int,
) -> None:
    if db is None:
        return

    ActionExecutionRepository.create_from_executed_action(
        db=db,
        tenant_id=job.tenant_id,
        job_id=job.job_id,
        request_action=request_action,
        executed_action=executed_action,
        attempt_no=attempt_no,
    )


def _persist_failed_action(
    db: Session | None,
    job: Job,
    request_action: dict[str, Any],
    failure_payload: dict[str, Any],
    attempt_no: int,
) -> None:
    if db is None:
        return

    ActionExecutionRepository.create_from_failed_action(
        db=db,
        tenant_id=job.tenant_id,
        job_id=job.job_id,
        request_action=request_action,
        failure_payload=failure_payload,
        attempt_no=attempt_no,
    )


def process_action_dispatch_job(job: Job, db: Session | None = None) -> Job:
    actions = _resolve_actions(job)
    executed_actions: list[dict[str, Any]] = []
    failed_actions: list[dict[str, Any]] = []

    for index, action in enumerate(actions, start=1):
        try:
            executed = execute_action(action)
            executed_actions.append(executed)
            _persist_successful_action(
                db=db,
                job=job,
                request_action=action,
                executed_action=executed,
                attempt_no=index,
            )
        except Exception as exc:
            failure_payload = {
                "type": action.get("type"),
                "status": "failed",
                "error": str(exc),
                "payload": action,
            }
            failed_actions.append(failure_payload)
            _persist_failed_action(
                db=db,
                job=job,
                request_action=action,
                failure_payload=failure_payload,
                attempt_no=index,
            )

    requires_human_review = len(failed_actions) > 0

    result = {
        "status": "completed",
        "summary": (
            "Actions dispatched successfully."
            if not requires_human_review
            else "One or more actions failed during dispatch."
        ),
        "requires_human_review": requires_human_review,
        "payload": {
            "processor_name": PROCESSOR_NAME,
            "actions_requested": actions,
            "actions_executed": executed_actions,
            "actions_failed": failed_actions,
            "executed_count": len(executed_actions),
            "failed_count": len(failed_actions),
            "recommended_next_step": "manual_review" if requires_human_review else "completed",
        },
    }

    return append_processor_result(job, PROCESSOR_NAME, result)