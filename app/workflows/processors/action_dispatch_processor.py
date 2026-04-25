from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.audit_service import create_audit_event
from app.domain.workflows.models import Job
from app.repositories.postgres.action_execution_repository import ActionExecutionRepository
from app.workflows.action_executor import execute_action
from app.workflows.processors.ai_processor_utils import (
    append_processor_result,
    classify_inquiry_priority,
    evaluate_information_completeness,
    extract_invoice_data,
    extract_phone,
    get_latest_processor_payload,
    normalize_sender,
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


_DEFAULT_SUPPORT_EMAIL = "support@company.com"
_COMPANY_NAME = "AI Automation"

_FOLLOW_UP_SUBJECT = "Vi behöver lite mer information"
_FOLLOW_UP_GREETING = (
    "Hej!\n\n"
    "Tack för ditt meddelande. För att kunna hjälpa dig behöver vi komplettera med:\n\n"
)
_FOLLOW_UP_CLOSING = "\nSvara gärna direkt på detta mejl.\n\nVänliga hälsningar"


def _build_follow_up_email(
    sender_email: str,
    questions: list[str],
) -> dict[str, Any]:
    bullet_lines = "\n".join(f"* {q}" for q in questions)
    body = _FOLLOW_UP_GREETING + bullet_lines + _FOLLOW_UP_CLOSING
    return {
        "type": "send_email",
        "to": sender_email,
        "subject": _FOLLOW_UP_SUBJECT,
        "body": body,
    }


def _build_skipped_action(action_type: str, reason: str) -> dict[str, Any]:
    """Return a sentinel action that will be persisted as 'skipped' without being dispatched."""
    return {
        "type": action_type,
        "_skip": True,
        "_skip_reason": reason,
    }


def _build_lead_default_actions(
    job: Job,
    automation_settings: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    input_data = job.input_data or {}
    sender = normalize_sender(input_data)
    settings = automation_settings or {}

    followups_enabled = settings.get("followups_enabled", True)
    internal_recipient = settings.get("support_email") or _DEFAULT_SUPPORT_EMAIL

    sender_name = sender.get("name", "")
    sender_email = sender.get("email", "")
    sender_phone = sender.get("phone") or extract_phone(
        input_data.get("subject") or "",
        input_data.get("message_text") or "",
    ) or ""

    subject = input_data.get("subject") or "Lead"
    message_text = input_data.get("message_text") or ""
    source = input_data.get("source") or "lead"
    if isinstance(source, dict):
        source = source.get("system") or "lead"

    sender_label = sender_name or sender_email or "Okänd avsändare"
    item_name = f"Lead: {sender_label} - {subject}"[:80].rstrip()

    completeness = evaluate_information_completeness("lead", input_data)

    lead_payload = get_latest_processor_payload(job, "lead_processor")
    priority = lead_payload.get("priority") or "normal"
    recommended_next_step = lead_payload.get("recommended_next_step") or ""

    column_values: dict[str, Any] = {
        "source": source if isinstance(source, str) else "lead",
        "completeness_status": completeness["recommended_status"],
    }
    if sender_email:
        column_values["email"] = sender_email
    if sender_phone:
        column_values["phone"] = sender_phone
    if subject and subject != "Lead":
        column_values["subject"] = subject[:60].rstrip()
    if message_text:
        column_values["message"] = message_text[:200].rstrip()
    if completeness["missing_fields"]:
        column_values["missing_fields"] = ", ".join(completeness["missing_fields"])

    actions: list[dict[str, Any]] = []

    # Customer auto-reply
    if not followups_enabled:
        actions.append(_build_skipped_action("send_customer_auto_reply", "followups_enabled=false"))
    elif not sender_email:
        actions.append(_build_skipped_action("send_customer_auto_reply", "no_customer_email"))
    else:
        short_summary = subject if subject != "Lead" else message_text[:120]
        auto_reply_body = (
            f"Hej {sender_name or 'där'},\n\n"
            f"Tack för din förfrågan. Vi har tagit emot ditt meddelande och återkommer så snart som möjligt.\n\n"
            f"För att kunna hjälpa dig snabbare får du gärna komplettera med:\n"
            f"- adress/ort\n"
            f"- bilder på nuvarande installation\n"
            f"- telefonnummer om det saknas\n"
            f"- när du önskar få arbetet utfört\n\n"
            f"Sammanfattning:\n{short_summary}\n\n"
            f"Vänliga hälsningar\n{_COMPANY_NAME}"
        )
        actions.append({
            "type": "send_customer_auto_reply",
            "tenant_id": job.tenant_id,
            "to": sender_email,
            "subject": "Tack för din förfrågan",
            "body": auto_reply_body,
        })

    # Internal sales handoff
    if not internal_recipient:
        actions.append(_build_skipped_action("send_internal_handoff", "no_internal_recipient"))
    else:
        phone_line = f"Telefon:      {sender_phone}\n" if sender_phone else ""
        city = ""
        entities = get_latest_processor_payload(job, "entity_extraction_processor")
        if entities:
            city = (entities.get("entities") or {}).get("city") or ""
        city_line = f"Ort:          {city}\n" if city else ""
        handoff_body = (
            f"Nytt lead inkom via AI Automation Platform.\n\n"
            f"Prioritet:    {priority.upper()}\n"
            f"Namn:         {sender_label}\n"
            f"E-post:       {sender_email or '(okänd)'}\n"
            f"{phone_line}"
            f"{city_line}"
            f"Ämne:         {subject}\n\n"
            f"Meddelande:\n{message_text or '(inget meddelande)'}\n\n"
            f"Förslag nästa steg: {recommended_next_step or 'Kontakta kunden'}\n\n"
            f"Job ID:       {job.job_id}\n"
            f"Tenant:       {job.tenant_id}"
        )
        actions.append({
            "type": "send_internal_handoff",
            "tenant_id": job.tenant_id,
            "to": internal_recipient,
            "subject": f"Nytt lead [{priority.upper()}]: {sender_label}",
            "body": handoff_body,
        })

    # Monday item
    actions.append({
        "type": "create_monday_item",
        "item_name": item_name,
        "tenant_id": job.tenant_id,
        "column_values": column_values,
    })

    if not completeness["is_complete"] and sender_email and completeness["follow_up_questions"]:
        actions.append(_build_follow_up_email(sender_email, completeness["follow_up_questions"]))

    return actions


def _build_inquiry_default_actions(
    job: Job,
    automation_settings: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    input_data = job.input_data or {}
    sender = normalize_sender(input_data)
    settings = automation_settings or {}

    followups_enabled = settings.get("followups_enabled", True)
    internal_recipient = settings.get("support_email") or _DEFAULT_SUPPORT_EMAIL

    sender_name = sender.get("name", "")
    sender_email = sender.get("email", "")
    sender_phone = sender.get("phone") or extract_phone(
        input_data.get("subject") or "",
        input_data.get("message_text") or "",
    ) or ""

    subject = input_data.get("subject") or "Support"
    message_text = input_data.get("message_text") or ""
    source = input_data.get("source") or "inquiry"
    if isinstance(source, dict):
        source = source.get("system") or "inquiry"

    priority = classify_inquiry_priority(subject, message_text)
    completeness = evaluate_information_completeness("customer_inquiry", input_data)

    sender_label = sender_name or sender_email or "Okänd avsändare"
    base_name = f"Support: {sender_label} - {subject}"
    if priority == "HIGH":
        base_name = f"[HIGH] {base_name}"
    item_name = base_name[:80].rstrip()

    column_values: dict[str, Any] = {
        "source": "inquiry",
        "priority": priority,
        "completeness_status": completeness["recommended_status"],
    }
    if sender_email:
        column_values["email"] = sender_email
    if sender_phone:
        column_values["phone"] = sender_phone
    if subject and subject != "Support":
        column_values["subject"] = subject[:60].rstrip()
    if message_text:
        column_values["message"] = message_text[:200].rstrip()
    if completeness["missing_fields"]:
        column_values["missing_fields"] = ", ".join(completeness["missing_fields"])

    actions: list[dict[str, Any]] = []

    # Customer auto-reply
    if not followups_enabled:
        actions.append(_build_skipped_action("send_customer_auto_reply", "followups_enabled=false"))
    elif not sender_email:
        actions.append(_build_skipped_action("send_customer_auto_reply", "no_customer_email"))
    else:
        short_summary = subject if subject != "Support" else message_text[:120]
        auto_reply_body = (
            f"Hej {sender_name or 'där'},\n\n"
            f"Tack för ditt meddelande. Vi har tagit emot ärendet och återkommer så snart som möjligt.\n\n"
            f"Sammanfattning:\n{short_summary}\n\n"
            f"Om ärendet är akut, ring oss direkt.\n\n"
            f"Vänliga hälsningar\n{_COMPANY_NAME}"
        )
        actions.append({
            "type": "send_customer_auto_reply",
            "tenant_id": job.tenant_id,
            "to": sender_email,
            "subject": "Vi har tagit emot ditt ärende",
            "body": auto_reply_body,
        })

    # Internal support handoff
    if not internal_recipient:
        actions.append(_build_skipped_action("send_internal_handoff", "no_internal_recipient"))
    else:
        phone_line = f"Telefon:   {sender_phone}\n" if sender_phone else ""
        email_subject = f"Ny kundfråga [{priority}]" if priority == "HIGH" else "Ny kundfråga"
        handoff_body = (
            f"Ny kundfråga inkom via AI Automation Platform.\n\n"
            f"Prioritet: {priority}\n"
            f"Från:      {sender_label}\n"
            f"E-post:    {sender_email or '(okänd)'}\n"
            f"{phone_line}"
            f"Ämne:      {subject}\n"
            f"Källa:     {source}\n\n"
            f"Meddelande:\n{message_text or '(inget meddelande)'}\n\n"
            f"Förslag nästa steg: Kontakta kunden inom 24 h\n\n"
            f"Job ID:    {job.job_id}\n"
            f"Tenant:    {job.tenant_id}"
        )
        actions.append({
            "type": "send_internal_handoff",
            "tenant_id": job.tenant_id,
            "to": internal_recipient,
            "subject": email_subject,
            "body": handoff_body,
        })

    # Monday item
    actions.append({
        "type": "create_monday_item",
        "item_name": item_name,
        "tenant_id": job.tenant_id,
        "column_values": column_values,
    })

    if not completeness["is_complete"] and sender_email and completeness["follow_up_questions"]:
        actions.append(_build_follow_up_email(sender_email, completeness["follow_up_questions"]))

    return actions


def _build_invoice_default_actions(job: Job) -> list[dict[str, Any]]:
    input_data = job.input_data or {}
    invoice = extract_invoice_data(input_data)

    sender = normalize_sender(input_data)
    sender_name = sender.get("name", "")
    sender_email = sender.get("email", "")
    sender_label = sender_name or sender_email or "Okänd avsändare"

    completeness = evaluate_information_completeness("invoice", input_data)

    item_name = f"Faktura: {sender_label}"

    column_values: dict[str, Any] = {
        "source": "invoice",
        "completeness_status": completeness["recommended_status"],
    }
    if sender_email:
        column_values["email"] = sender_email
    subject = input_data.get("subject") or ""
    if subject:
        column_values["subject"] = subject[:60].rstrip()
    if invoice.get("amount"):
        column_values["amount"] = invoice["amount"]
    if invoice.get("invoice_number"):
        column_values["invoice_number"] = invoice["invoice_number"]
    if invoice.get("due_date"):
        column_values["due_date"] = invoice["due_date"]
    if invoice.get("supplier_name"):
        column_values["supplier_name"] = invoice["supplier_name"]
    if completeness["missing_fields"]:
        column_values["missing_fields"] = ", ".join(completeness["missing_fields"])

    desc_parts = [f"Inkommande faktura från {sender_label}."]
    if subject:
        desc_parts.append(f"Ämne: {subject}.")
    if invoice.get("amount"):
        desc_parts.append(f"Belopp: {invoice['amount']}.")
    if invoice.get("invoice_number"):
        desc_parts.append(f"Fakturanummer: {invoice['invoice_number']}.")
    if invoice.get("due_date"):
        desc_parts.append(f"Förfallodatum: {invoice['due_date']}.")
    if not completeness["is_complete"]:
        missing_str = ", ".join(completeness["missing_fields"])
        desc_parts.append(f"SAKNAD INFORMATION: {missing_str}. Kräver manuell granskning.")
    description = " ".join(desc_parts)

    return [
        {
            "type": "create_monday_item",
            "item_name": item_name,
            "tenant_id": job.tenant_id,
            "column_values": column_values,
        },
        {
            "type": "create_internal_task",
            "title": f"Granska faktura: {sender_label}",
            "description": description,
            "assignee": None,
            "metadata": {
                "job_id": job.job_id,
                "tenant_id": job.tenant_id,
                "detected_job_type": "invoice",
                "invoice": invoice,
                "completeness": completeness,
            },
        },
    ]


def _build_fallback_actions(
    job: Job,
    automation_settings: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    input_data = job.input_data or {}
    classification_payload = get_latest_processor_payload(job, "classification_processor")

    detected_job_type = classification_payload.get("detected_job_type", job.job_type.value)

    if detected_job_type == "invoice":
        return _build_invoice_default_actions(job)

    if detected_job_type == "customer_inquiry":
        return _build_inquiry_default_actions(job, automation_settings)

    if detected_job_type == "lead":
        return _build_lead_default_actions(job, automation_settings)

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


def _resolve_actions(
    job: Job,
    automation_settings: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    input_actions = _build_actions_from_input(job)
    if input_actions:
        return input_actions

    decisioning_actions = _build_actions_from_decisioning(job)
    if decisioning_actions:
        return decisioning_actions

    return _build_fallback_actions(job, automation_settings)


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


def _read_automation_settings(job: Job, db: Session | None) -> dict[str, Any]:
    """Read tenant automation settings; returns empty dict when unavailable."""
    if db is None:
        return {}
    try:
        from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
        ctrl = TenantConfigRepository.get_settings(db, job.tenant_id)
        auto = ctrl.get("automation") or {}
        return {
            "followups_enabled": auto.get("followups_enabled", True),
            "leads_enabled":     auto.get("leads_enabled", True),
            "support_enabled":   auto.get("support_enabled", True),
            "support_email":     ctrl.get("support_email") or "",
        }
    except Exception:
        return {}


def process_action_dispatch_job(job: Job, db: Session | None = None) -> Job:
    automation_settings = _read_automation_settings(job, db)
    actions = _resolve_actions(job, automation_settings)
    executed_actions: list[dict[str, Any]] = []
    failed_actions: list[dict[str, Any]] = []
    skipped_actions: list[dict[str, Any]] = []

    for index, action in enumerate(actions, start=1):
        # Skipped sentinel — log to action_executions but do not dispatch
        if action.get("_skip"):
            skip_record = {
                "type":         action["type"],
                "status":       "skipped",
                "skip_reason":  action.get("_skip_reason", ""),
                "executed_at":  None,
                "target":       None,
                "provider":     "none",
                "payload":      {},
            }
            skipped_actions.append(skip_record)
            if db is not None:
                ActionExecutionRepository.create_from_executed_action(
                    db=db,
                    tenant_id=job.tenant_id,
                    job_id=job.job_id,
                    request_action=action,
                    executed_action={
                        **skip_record,
                        "executed_at": __import__("datetime").datetime.now(
                            __import__("datetime").timezone.utc
                        ).isoformat(),
                        "integration_result": {"skipped": True, "reason": action.get("_skip_reason", "")},
                    },
                    attempt_no=index,
                )
            continue

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

    has_failures = len(failed_actions) > 0

    if has_failures and db is not None:
        create_audit_event(
            db=db,
            tenant_id=job.tenant_id,
            category="workflow",
            action="action_dispatch_failed",
            status="failed",
            details={
                "job_id": job.job_id,
                "failed_count": len(failed_actions),
                "executed_count": len(executed_actions),
                "failed_actions": [f.get("type") for f in failed_actions],
                "errors": [f.get("error") for f in failed_actions],
            },
        )

    result = {
        "status": "failed" if has_failures else "completed",
        "summary": (
            "Actions dispatched successfully."
            if not has_failures
            else "One or more actions failed during dispatch."
        ),
        "requires_human_review": has_failures,
        "payload": {
            "processor_name": PROCESSOR_NAME,
            "actions_requested": actions,
            "actions_executed": executed_actions,
            "actions_failed": failed_actions,
            "actions_skipped": skipped_actions,
            "executed_count": len(executed_actions),
            "failed_count": len(failed_actions),
            "skipped_count": len(skipped_actions),
            "recommended_next_step": "manual_review" if has_failures else "completed",
        },
    }

    return append_processor_result(job, PROCESSOR_NAME, result)