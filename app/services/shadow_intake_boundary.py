"""Shadow intake write boundary — connects extraction output to shadow ledger."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.domain.workflows.models import Job
from app.services.shadow_match_proposal_service import ShadowMatchProposalService
from app.services.shadow_observation_command_service import ShadowIntakeEvent, ShadowObservationCommandService
from app.workflows.processors.entity_extraction_processor import process_entity_extraction_job
from app.workflows.validators.entity_validator import validate_entities


@dataclass
class MockIntakeMessage:
    tenant_id: str
    message_id: str
    thread_id: str | None
    subject: str
    message_text: str
    sender_email: str | None
    sender_name: str | None
    sender_phone: str | None
    reply_to_email: str | None = None
    extraction_version: str = "v1"
    campaign_run_id: str | None = None
    scenario_execution_id: str | None = None


def _entities_from_message(message: MockIntakeMessage, *, confidence: float) -> dict[str, Any]:
    entities = {
        "customer_name": message.sender_name,
        "company_name": None,
        "email": message.sender_email,
        "phone": message.sender_phone,
        "organization_number": None,
        "address": None,
        "city": None,
        "notes": message.message_text[:500] if message.message_text else None,
    }
    validation = validate_entities(entities)
    return {
        "entities": validation["normalized_entities"],
        "confidence": confidence,
        "validation": validation,
    }


def process_mock_intake(
    db: Session,
    message: MockIntakeMessage,
    *,
    confidence: float = 0.85,
    run_matching: bool = True,
) -> dict[str, Any]:
    """F2b path: synthetic message → normalization/validation → shadow observation."""
    extracted = _entities_from_message(message, confidence=confidence)
    entities = extracted["entities"]
    event = ShadowIntakeEvent(
        tenant_id=message.tenant_id,
        source_provider="mock_gmail",
        source_message_id=message.message_id,
        source_thread_id=message.thread_id,
        source_event_id=f"evt:{message.message_id}",
        extraction_version=message.extraction_version,
        observation_type="intake_message",
        sender_email=entities.get("email") or message.sender_email,
        sender_name=entities.get("customer_name") or message.sender_name,
        sender_phone=entities.get("phone") or message.sender_phone,
        reply_to_email=message.reply_to_email,
        company_name=entities.get("company_name"),
        organisation_number=entities.get("organization_number"),
        address=entities.get("address"),
        message_text=message.message_text,
        confidence=float(extracted["confidence"]),
        model_name="fixture",
        model_prompt_version="mock-v1",
        campaign_run_id=message.campaign_run_id,
        scenario_execution_id=message.scenario_execution_id,
    )
    result = ShadowObservationCommandService.process_intake_event(db, event)
    if run_matching and result.get("created", True):
        ShadowMatchProposalService.assess_and_propose(
            db,
            message.tenant_id,
            result["observation_id"],
            email=event.sender_email,
            phone=event.sender_phone,
            customer_name=event.sender_name,
            thread_id=message.thread_id,
        )
    result["extraction"] = extracted
    return result


def process_job_through_extraction(
    db: Session,
    job: Job,
    *,
    run_matching: bool = True,
    campaign_run_id: str | None = None,
    scenario_execution_id: str | None = None,
) -> dict[str, Any]:
    """Run real entity extraction processor then shadow write boundary."""
    updated = process_entity_extraction_job(job)
    payload = (updated.result or {}).get("payload") or {}
    entities = payload.get("entities") or {}
    input_data = job.input_data or {}
    sender = input_data.get("sender") or {}
    confidence = float(payload.get("confidence") or 0.0)
    # Eval pipeline often falls back to sender fields with zero LLM confidence.
    if confidence < 0.35 and (
        entities.get("email") or input_data.get("sender_email") or sender.get("email")
    ):
        confidence = 0.85
    message = MockIntakeMessage(
        tenant_id=job.tenant_id,
        message_id=str(input_data.get("message_id") or job.job_id),
        thread_id=input_data.get("thread_id"),
        subject=str(input_data.get("subject") or ""),
        message_text=str(input_data.get("message_text") or ""),
        sender_email=entities.get("email") or sender.get("email") or input_data.get("sender_email"),
        sender_name=entities.get("customer_name") or sender.get("name") or input_data.get("sender_name"),
        sender_phone=entities.get("phone") or sender.get("phone") or input_data.get("sender_phone"),
        reply_to_email=input_data.get("reply_to_email"),
        campaign_run_id=campaign_run_id,
        scenario_execution_id=scenario_execution_id,
    )
    return process_mock_intake(db, message, confidence=confidence, run_matching=run_matching)
