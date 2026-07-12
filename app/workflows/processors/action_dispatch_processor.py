from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Any

from sqlalchemy.orm import Session

from app.core.audit_service import create_audit_event
from app.domain.workflows.models import Job
from app.repositories.postgres.action_execution_repository import ActionExecutionRepository
from app.workflows.action_executor import execute_action
from app.workflows.intelligence_safety import assess_content_risk
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

# Action types that represent outbound customer/internal emails requiring approval gate
_EMAIL_ACTION_TYPES = frozenset({
    "send_customer_auto_reply",
    "send_internal_handoff",
    "send_email",
})

_NO_REPLY_RE = re.compile(r"\b(?:no[-_. ]?reply|donotreply)\b", re.IGNORECASE)
_EMAIL_RE = re.compile(r"([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})", re.IGNORECASE)
_LEAD_SLA_TARGET_MINUTES = 15

# Short opening sentence per service profile type — replaces stiff "Tack för ditt meddelande."
_PROFILE_OPENERS: dict[str, str] = {
    "battery_storage":          "Absolut, ett batterilager till befintlig solcellsanläggning kan vi ordna.",
    "solar_installation":       "Kul att du är intresserad av solceller!",
    "ev_charger_installation":  "Vi installerar laddboxar — bra val med elbil!",
    "ev_charger_fault":         "Tråkigt att laddboxen strular — vi kollar upp det.",
    "electrical_fault":         "Vi hjälper till med elfelsökning.",
    "electrical_panel":         "Elcentralsbyte — det fixar vi.",
    "inverter_support":         "Vi tittar gärna på växelriktarproblemet.",
    "vvs_service":              "VVS är ingen fara — vi hjälper till.",
    "building_project":         "Kul projekt — vi tar gärna en titt!",
}

_ORG_PREFIX_WORDS = frozenset({"brf", "ab", "hb", "kb", "ab.", "ltd", "inc", "as", "oy"})


def _is_no_reply_email(value: str) -> bool:
    return bool(value and _NO_REPLY_RE.search(value))


def _first_name(full_name: str) -> str:
    """Return the first word of *full_name* as a greeting-safe first name.

    Returns empty string when:
    - name is empty or missing
    - first word looks like an org prefix (BRF, AB, Ltd, …)
    """
    if not full_name:
        return ""
    first = full_name.strip().split()[0] if full_name.strip() else ""
    if not first:
        return ""
    if first.lower() in _ORG_PREFIX_WORDS:
        return ""
    return first


def _profile_opener(profile_type: str) -> str:
    """Return a short, natural Swedish sentence for the profile type.

    Returns empty string for generic/unknown profiles so no opener is prepended.
    """
    return _PROFILE_OPENERS.get(profile_type, "")


def _extract_customer_email_candidates(text: str) -> list[str]:
    if not text:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for match in _EMAIL_RE.findall(text):
        email = match.strip().lower()
        if email in seen:
            continue
        seen.add(email)
        out.append(email)
    return out


def _resolve_customer_reply_target(
    input_data: dict[str, Any],
    sender_email: str,
    internal_recipient: str,
) -> tuple[str, bool]:
    """Return (recipient_email, use_thread_reply) for customer replies.

    For no-reply/form relays (e.g. Webflow), prefer a customer email from payload/body
    and send as a fresh message (not thread reply).
    """
    sender_email = (sender_email or "").strip().lower()
    if sender_email and not _is_no_reply_email(sender_email):
        return sender_email, True

    source = input_data.get("source") or {}
    if isinstance(source, dict):
        explicit = (
            source.get("customer_email")
            or source.get("reply_to")
            or source.get("from_email")
            or ""
        )
        explicit = str(explicit).strip().lower()
        if explicit and not _is_no_reply_email(explicit):
            return explicit, False

    for key in ("customer_contact_email", "customer_email", "reply_to_email", "email"):
        val = str(input_data.get(key) or "").strip().lower()
        if val and not _is_no_reply_email(val):
            return val, False

    body_text = str(input_data.get("message_text") or "")
    internal_recipient = (internal_recipient or "").strip().lower()
    for candidate in _extract_customer_email_candidates(body_text):
        if candidate == sender_email:
            continue
        if internal_recipient and candidate == internal_recipient:
            continue
        if _is_no_reply_email(candidate):
            continue
        return candidate, False

    return "", False


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


def _build_sensitive_customer_ack(
    *,
    action_type: str,
    tenant_id: str,
    to: str,
    subject: str,
    sender_name: str,
    signature_name: str,
    source_thread_id: str | None = None,
    source_internet_message_id: str | None = None,
    use_thread_reply: bool = False,
) -> dict[str, Any]:
    closing = f"\n\nVänliga hälsningar\n{signature_name}" if signature_name else ""
    first = _first_name(sender_name)
    greeting = f"Hej {first}," if first else "Hej,"
    body = (
        f"{greeting}\n\n"
        "Vi har tagit emot ditt ärende och skickar det vidare "
        "till ansvarig handläggare för manuell bedömning.\n\n"
        "Vi återkommer när ärendet har granskats. Det här automatiska svaret innebär "
        "inte något juridiskt eller ekonomiskt ställningstagande."
        f"{closing}"
    )
    return {
        "type": action_type,
        "tenant_id": tenant_id,
        "to": to,
        "subject": subject,
        "body": body,
        "thread_id": source_thread_id if use_thread_reply else None,
        "in_reply_to": source_internet_message_id if use_thread_reply else None,
        "references": source_internet_message_id if use_thread_reply else None,
        "_needs_approval": True,
        "_approval_reason": "sensitive_case_requires_human_review",
    }


def _build_lead_default_actions(
    job: Job,
    automation_settings: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    input_data = job.input_data or {}
    sender = normalize_sender(input_data)
    settings = automation_settings or {}

    followups_enabled = settings.get("followups_enabled", True)
    internal_recipient = settings.get("internal_notification_email") or ""
    signature_name = settings.get("email_signature_name") or ""

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
    source_meta = input_data.get("source") if isinstance(input_data.get("source"), dict) else {}
    source_thread_id = source_meta.get("thread_id") if isinstance(source_meta, dict) else None
    source_internet_message_id = source_meta.get("internet_message_id") if isinstance(source_meta, dict) else None
    customer_to, use_thread_reply = _resolve_customer_reply_target(
        input_data=input_data,
        sender_email=sender_email,
        internal_recipient=internal_recipient,
    )

    sender_label = sender_name or sender_email or "Okänd avsändare"
    item_name = f"Lead: {sender_label} - {subject}"[:80].rstrip()

    completeness = evaluate_information_completeness("lead", input_data)
    risk = assess_content_risk(input_data)

    lead_payload = get_latest_processor_payload(job, "lead_processor")
    priority = lead_payload.get("priority") or "normal"
    recommended_next_step = lead_payload.get("recommended_next_step") or ""

    # Use service-profile-specific question message from lead_analyzer when available
    lead_analyzer_payload = get_latest_processor_payload(job, "lead_analyzer_processor")
    profile_question_message = lead_analyzer_payload.get("generated_question_message") or ""

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
    if risk["risk_detected"]:
        column_values["risk"] = ", ".join(risk["categories"])

    actions: list[dict[str, Any]] = []

    # Customer auto-reply: conversational and information-seeking.
    if not followups_enabled:
        actions.append(_build_skipped_action("send_customer_auto_reply", "followups_enabled=false"))
    elif not customer_to:
        actions.append(_build_skipped_action("send_customer_auto_reply", "no_customer_email"))
    elif risk["risk_detected"]:
        reply_subject = f"Re: {subject}" if subject and subject != "Lead" else "Tack för ditt mejl"
        actions.append(_build_sensitive_customer_ack(
            action_type="send_customer_auto_reply",
            tenant_id=job.tenant_id,
            to=customer_to,
            subject=reply_subject,
            sender_name=sender_name,
            signature_name=signature_name,
            source_thread_id=source_thread_id,
            source_internet_message_id=source_internet_message_id,
            use_thread_reply=use_thread_reply,
        ))
    else:
        closing = f"\n\nVänliga hälsningar\n{signature_name}" if signature_name else ""
        reply_subject = f"Re: {subject}" if subject and subject != "Lead" else "Tack för ditt mejl"

        first = _first_name(sender_name)
        greeting = f"Hej {first}," if first else "Hej,"

        if profile_question_message:
            # Use service-profile-specific questions from lead_analyzer_processor.
            # Add a profile-specific natural opener before the question block.
            profile_type = lead_analyzer_payload.get("service_profile_type") or ""
            opener = _profile_opener(profile_type)
            opener_block = f"{opener}\n\n" if opener else ""
            auto_reply_body = (
                f"{greeting}\n\n"
                f"{opener_block}"
                f"{profile_question_message}"
                f"{closing}"
            )
        else:
            # Fallback: generic lead follow-up questions
            lead_questions = [
                "- Gäller det en specifik tjänst eller vill du att vi rekommenderar en lösning?",
                "- Vilken adress gäller ärendet?",
                "- När vill du helst komma igång?",
            ]
            if not sender_phone:
                lead_questions.append("- Vilket telefonnummer når vi dig bäst på?")
            if completeness["missing_fields"]:
                lead_questions.append(
                    "- Skicka gärna bilder eller annan info som hjälper oss bedöma snabbare."
                )
            auto_reply_body = (
                f"{greeting}\n\n"
                "Tack för att du hör av dig — kul att du kontaktar oss!\n\n"
                "Skicka gärna svar på:\n"
                f"{chr(10).join(lead_questions)}"
                f"{closing}"
            )
        actions.append({
            "type": "send_customer_auto_reply",
            "tenant_id": job.tenant_id,
            "to": customer_to,
            "subject": reply_subject,
            "body": auto_reply_body,
            "thread_id": source_thread_id if use_thread_reply else None,
            "in_reply_to": source_internet_message_id if use_thread_reply else None,
            "references": source_internet_message_id if use_thread_reply else None,
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
            f"Nytt lead inkom.\n\n"
            f"Prioritet:    {priority.upper()}\n"
            f"Namn:         {sender_label}\n"
            f"E-post:       {sender_email or '(okänd)'}\n"
            f"{phone_line}"
            f"{city_line}"
            f"Ämne:         {subject}\n\n"
            f"Meddelande:\n{message_text or '(inget meddelande)'}\n\n"
            f"Förslag nästa steg: {'Manuell granskning' if risk['risk_detected'] else (recommended_next_step or 'Kontakta kunden')}\n\n"
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

    # Gate outbound customer emails on auto_actions approval policy
    if risk["risk_detected"] or _email_needs_approval("lead", settings):
        actions = [
            _build_email_approval_action(a) if a.get("type") in _EMAIL_ACTION_TYPES and not a.get("_skip")
            else a
            for a in actions
        ]

    return actions


def _build_inquiry_default_actions(
    job: Job,
    automation_settings: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    input_data = job.input_data or {}
    sender = normalize_sender(input_data)
    settings = automation_settings or {}

    followups_enabled = settings.get("followups_enabled", True)
    internal_recipient = settings.get("internal_notification_email") or ""
    signature_name = settings.get("email_signature_name") or ""

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
    source_meta = input_data.get("source") if isinstance(input_data.get("source"), dict) else {}
    source_thread_id = source_meta.get("thread_id") if isinstance(source_meta, dict) else None
    source_internet_message_id = source_meta.get("internet_message_id") if isinstance(source_meta, dict) else None
    customer_to, use_thread_reply = _resolve_customer_reply_target(
        input_data=input_data,
        sender_email=sender_email,
        internal_recipient=internal_recipient,
    )

    priority = classify_inquiry_priority(subject, message_text)
    completeness = evaluate_information_completeness("customer_inquiry", input_data)
    risk = assess_content_risk(input_data)

    # Use service-profile-specific question message from support_analyzer when available
    support_analyzer_payload = get_latest_processor_payload(job, "support_analyzer_processor")
    support_profile_question = support_analyzer_payload.get("support_generated_question_message") or ""

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
    if risk["risk_detected"]:
        column_values["risk"] = ", ".join(risk["categories"])

    actions: list[dict[str, Any]] = []

    # Customer auto-reply: empathetic and action-oriented.
    if not followups_enabled:
        actions.append(_build_skipped_action("send_customer_auto_reply", "followups_enabled=false"))
    elif not customer_to:
        actions.append(_build_skipped_action("send_customer_auto_reply", "no_customer_email"))
    elif risk["risk_detected"]:
        reply_subject = f"Re: {subject}" if subject and subject != "Support" else "Re: ditt ärende"
        actions.append(_build_sensitive_customer_ack(
            action_type="send_customer_auto_reply",
            tenant_id=job.tenant_id,
            to=customer_to,
            subject=reply_subject,
            sender_name=sender_name,
            signature_name=signature_name,
            source_thread_id=source_thread_id,
            source_internet_message_id=source_internet_message_id,
            use_thread_reply=use_thread_reply,
        ))
    else:
        closing = f"\n\nVänliga hälsningar\n{signature_name}" if signature_name else ""
        urgency_line = (
            "Vi har tagit emot ärendet och prioriterar det.\n\n"
            if priority == "HIGH"
            else ""
        )
        reply_subject = f"Re: {subject}" if subject and subject != "Support" else "Re: ditt ärende"

        first = _first_name(sender_name)
        greeting = f"Hej {first}," if first else "Hej,"

        if support_profile_question:
            # Use service-profile-specific questions from support_analyzer_processor.
            support_profile_type = support_analyzer_payload.get("service_profile_type") or ""
            opener = _profile_opener(support_profile_type)
            opener_block = f"{opener}\n\n" if opener else ""
            auto_reply_body = (
                f"{greeting}\n\n"
                f"{opener_block}"
                f"{urgency_line}"
                f"{support_profile_question}"
                f"{closing}"
            )
        else:
            # Fallback: generic support follow-up questions
            support_questions = [
                "- Vilken adress/anläggning gäller det?",
                "- När började problemet och om något förändrades precis innan?",
                "- Ser du någon felkod eller lampa som blinkar? (fota gärna om möjligt)",
            ]
            if not sender_phone:
                support_questions.append("- Vilket telefonnummer når vi dig bäst på idag?")
            auto_reply_body = (
                f"{greeting}\n\n"
                f"{urgency_line}"
                "Skicka gärna:\n"
                f"{chr(10).join(support_questions)}\n\n"
                "Om det finns akut säkerhetsrisk, kontakta jour eller behörig hjälp direkt."
                f"{closing}"
            )
        actions.append({
            "type": "send_customer_auto_reply",
            "tenant_id": job.tenant_id,
            "to": customer_to,
            "subject": reply_subject,
            "body": auto_reply_body,
            "thread_id": source_thread_id if use_thread_reply else None,
            "in_reply_to": source_internet_message_id if use_thread_reply else None,
            "references": source_internet_message_id if use_thread_reply else None,
        })

    # Internal support handoff
    if not internal_recipient:
        actions.append(_build_skipped_action("send_internal_handoff", "no_internal_recipient"))
    else:
        phone_line = f"Telefon:   {sender_phone}\n" if sender_phone else ""
        email_subject = f"Ny kundfråga [{priority}]" if priority == "HIGH" else "Ny kundfråga"
        handoff_body = (
            f"Ny kundfråga inkom.\n\n"
            f"Prioritet: {priority}\n"
            f"Från:      {sender_label}\n"
            f"E-post:    {sender_email or '(okänd)'}\n"
            f"{phone_line}"
            f"Ämne:      {subject}\n"
            f"Källa:     {source}\n\n"
            f"Meddelande:\n{message_text or '(inget meddelande)'}\n\n"
            f"Förslag nästa steg: {'Manuell granskning' if risk['risk_detected'] else 'Kontakta kunden inom 24 h'}\n\n"
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

    # Gate outbound customer emails on auto_actions approval policy
    if risk["risk_detected"] or _email_needs_approval("customer_inquiry", settings):
        actions = [
            _build_email_approval_action(a) if a.get("type") in _EMAIL_ACTION_TYPES and not a.get("_skip")
            else a
            for a in actions
        ]

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


# Visibility-only types: no customer-facing emails, no Monday routing.
# Jobs are created and visible in cases/dashboard but no outbound actions fire.
_VISIBILITY_ONLY_TYPES = frozenset({"partnership", "supplier", "newsletter", "internal", "spam"})


def _build_visibility_only_actions(job: Job, detected_job_type: str) -> list[dict[str, Any]]:
    """Return skipped sentinels for types that are tracked but not acted on."""
    reason = f"No automation configured for classification type '{detected_job_type}'"
    return [
        _build_skipped_action("send_customer_auto_reply", reason),
        _build_skipped_action("send_internal_handoff", reason),
    ]


def _build_fallback_actions(
    job: Job,
    automation_settings: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    input_data = job.input_data or {}
    classification_payload = get_latest_processor_payload(job, "classification_processor")

    detected_job_type = classification_payload.get("detected_job_type", job.job_type.value)

    if detected_job_type in _VISIBILITY_ONLY_TYPES:
        return _build_visibility_only_actions(job, detected_job_type)

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
        branding = ctrl.get("branding") or {}
        # Also read the auto_actions column (separate from settings JSON blob)
        record = TenantConfigRepository.get(db, job.tenant_id)
        auto_actions = (record.auto_actions or {}) if record else {}
        tenant_name = (record.name or "") if record else ""
        company_display_name = branding.get("company_display_name") or tenant_name or ""
        email_signature_name = branding.get("email_signature_name") or company_display_name or ""
        internal_notification_email = (
            branding.get("internal_notification_email")
            or ctrl.get("support_email")
            or ""
        )
        return {
            "followups_enabled":           auto.get("followups_enabled", True),
            "leads_enabled":               auto.get("leads_enabled", True),
            "support_enabled":             auto.get("support_enabled", True),
            "support_email":               ctrl.get("support_email") or "",
            "auto_actions":                auto_actions,
            "company_display_name":        company_display_name,
            "email_signature_name":        email_signature_name,
            "internal_notification_email": internal_notification_email,
        }
    except Exception:
        return {}


def _email_needs_approval(job_type: str, automation_settings: dict[str, Any]) -> bool:
    """Return True when customer emails for this job type require manual approval.

    Approval is required when auto_actions[job_type] is falsy or explicitly 'manual'.
    auto_actions[job_type] == True / 'full_auto' / 'semi' → execute immediately.
    auto_actions[job_type] missing / False / 'manual' → approval required.
    """
    auto_actions = automation_settings.get("auto_actions") or {}
    value = auto_actions.get(job_type)
    if value is None or value is False or value == "manual":
        return True
    return False


def _build_email_approval_action(action: dict[str, Any]) -> dict[str, Any]:
    """Wrap an email action as an approval-pending sentinel."""
    return {
        **action,
        "_needs_approval": True,
    }


def _is_customer_email_action(action: dict[str, Any]) -> bool:
    action_type = str(action.get("type") or "")
    if action_type == "send_customer_auto_reply":
        return True
    if action_type == "send_email":
        recipient = str(action.get("to") or "").strip().lower()
        return bool(recipient)
    return False


def _build_ai_reply_suggestions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    for action in actions:
        if not _is_customer_email_action(action):
            continue
        if action.get("_skip"):
            continue
        suggestions.append({
            "type": action.get("type"),
            "to": action.get("to"),
            "subject": action.get("subject"),
            "body": action.get("body"),
            "approval_required": bool(action.get("_needs_approval")),
        })
    return suggestions


def _compute_lead_sla_payload(
    *,
    job: Job,
    actions_requested: list[dict[str, Any]],
    actions_executed: list[dict[str, Any]],
    actions_pending_approval: list[dict[str, Any]],
) -> dict[str, Any] | None:
    job_type = job.job_type.value if hasattr(job.job_type, "value") else str(job.job_type)
    if job_type != "lead":
        return None

    created_at = job.created_at or datetime.now(timezone.utc)
    due_at = created_at + timedelta(minutes=_LEAD_SLA_TARGET_MINUTES)
    now = datetime.now(timezone.utc)

    tracked_types = {"send_customer_auto_reply", "send_internal_handoff", "send_email"}
    has_executed = any((a.get("type") in tracked_types) for a in actions_executed)
    has_pending = any((a.get("action_type") in tracked_types) for a in actions_pending_approval)
    has_requested = any((a.get("type") in tracked_types and not a.get("_skip")) for a in actions_requested)

    if has_executed:
        follow_up_state = "executed"
    elif has_pending:
        follow_up_state = "pending_approval"
    elif has_requested:
        follow_up_state = "queued"
    else:
        follow_up_state = "missing"

    if follow_up_state in {"executed", "pending_approval", "queued"}:
        sla_status = "met" if now <= due_at else "breached"
    else:
        sla_status = "breached" if now > due_at else "pending"

    return {
        "enabled": True,
        "target_minutes": _LEAD_SLA_TARGET_MINUTES,
        "first_follow_up_due_at": due_at.isoformat(),
        "first_follow_up_state": follow_up_state,
        "status": sla_status,
    }


def _create_email_approval_record(
    db: Session,
    job: Job,
    action: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    """Persist a pending email approval and return a summary dict."""
    import uuid
    from app.repositories.postgres.approval_repository import ApprovalRequestRepository

    approval_id = f"eml_{uuid.uuid4().hex[:20]}"
    action_type = action.get("type", "send_email")
    recipient = action.get("to") or ""
    subject = action.get("subject") or ""

    approval_payload = {
        "approval_id": approval_id,
        "state": "pending",
        "channel": "dashboard",
        "title": f"E-post: {subject[:60]}",
        "summary": f"Väntande e-post till {recipient} ({action_type})",
        "next_on_approve": "email_send",
        "next_on_reject": "email_reject",
        "requested_by": "system",
    }
    # Store the full email payload so approve can execute it
    delivery = {
        "type": action_type,
        "to": recipient,
        "subject": subject,
        "body": action.get("body") or "",
    }
    if action.get("thread_id"):
        delivery["thread_id"] = action.get("thread_id")
    if action.get("in_reply_to"):
        delivery["in_reply_to"] = action.get("in_reply_to")
    if action.get("references"):
        delivery["references"] = action.get("references")

    ApprovalRequestRepository.upsert_from_payload(
        db=db,
        tenant_id=job.tenant_id,
        job_id=job.job_id,
        job_type=job.job_type.value if hasattr(job.job_type, "value") else str(job.job_type),
        approval_request=approval_payload,
        delivery_payload=delivery,
    )

    return {
        "approval_id": approval_id,
        "action_type": action_type,
        "to": recipient,
        "subject": subject,
        "status": "pending_approval",
        "approval_kind": "ai_reply_draft" if _is_customer_email_action(action) else "email_action",
    }


def process_action_dispatch_job(job: Job, db: Session | None = None) -> Job:
    automation_settings = _read_automation_settings(job, db)
    actions = _resolve_actions(job, automation_settings)
    executed_actions: list[dict[str, Any]] = []
    failed_actions: list[dict[str, Any]] = []
    skipped_actions: list[dict[str, Any]] = []
    pending_approvals: list[dict[str, Any]] = []

    for index, action in enumerate(actions, start=1):
        # Approval-pending sentinel — create approval record, do not execute
        if action.get("_needs_approval"):
            if db is not None:
                approval_summary = _create_email_approval_record(db, job, action, index)
                pending_approvals.append(approval_summary)
            else:
                pending_approvals.append({
                    "action_type": action.get("type"),
                    "to": action.get("to"),
                    "subject": action.get("subject"),
                    "status": "pending_approval",
                })
            continue

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
            "actions_pending_approval": pending_approvals,
            "ai_reply_suggestions": _build_ai_reply_suggestions(actions),
            "lead_sla": _compute_lead_sla_payload(
                job=job,
                actions_requested=actions,
                actions_executed=executed_actions,
                actions_pending_approval=pending_approvals,
            ),
            "executed_count": len(executed_actions),
            "failed_count": len(failed_actions),
            "skipped_count": len(skipped_actions),
            "pending_approval_count": len(pending_approvals),
            "recommended_next_step": "manual_review" if has_failures else "completed",
        },
    }

    return append_processor_result(job, PROCESSOR_NAME, result)