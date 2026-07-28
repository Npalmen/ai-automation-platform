"""Provider execution outcome extraction and recipient verification helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProviderExecutionOutcome:
    provider_message_id: str
    adapter_recipient: str | None
    adapter_status: str | None
    provider_rfc_message_id: str | None = None


def extract_provider_execution_outcome(
    observation: dict[str, Any],
) -> ProviderExecutionOutcome | None:
    """Read provider Gmail metadata from execution outcome or telemetry events."""
    job = observation.get("job") or {}
    provider_message_id: str | None = None
    adapter_recipient: str | None = None
    adapter_status: str | None = None
    provider_rfc_message_id: str | None = None

    for row in job.get("decision_records") or []:
        if row.get("record_type") != "execution_outcome":
            continue
        if row.get("execution_status") != "succeeded":
            continue
        metadata = row.get("metadata") or {}
        provider_message_id = str(metadata.get("provider_message_id") or "") or provider_message_id
        adapter_recipient = str(metadata.get("adapter_recipient") or "") or adapter_recipient
        adapter_status = str(metadata.get("adapter_status") or "") or adapter_status
        provider_rfc_message_id = (
            str(metadata.get("provider_rfc_message_id") or "") or provider_rfc_message_id
        )

    trace = job.get("execution_trace") or {}
    outcome = trace.get("execution_outcome") or {}
    trace_metadata = outcome.get("metadata") or {}
    if not provider_message_id:
        provider_message_id = str(trace_metadata.get("provider_message_id") or "") or None
    if not adapter_recipient:
        adapter_recipient = str(trace_metadata.get("adapter_recipient") or "") or None
    if not adapter_status:
        adapter_status = str(trace_metadata.get("adapter_status") or "") or None
    if not provider_rfc_message_id:
        provider_rfc_message_id = (
            str(trace_metadata.get("provider_rfc_message_id") or "") or None
        )

    for event in observation.get("events") or []:
        event_metadata = event.get("metadata") or {}
        if not provider_message_id:
            provider_message_id = str(event_metadata.get("provider_message_id") or "") or None
        if not adapter_recipient:
            adapter_recipient = str(event_metadata.get("adapter_recipient") or "") or None
        if not adapter_status:
            adapter_status = str(event_metadata.get("adapter_status") or "") or None
        if not provider_rfc_message_id:
            provider_rfc_message_id = (
                str(event_metadata.get("provider_rfc_message_id") or "") or None
            )

    if not provider_message_id:
        return None
    return ProviderExecutionOutcome(
        provider_message_id=provider_message_id,
        adapter_recipient=adapter_recipient,
        adapter_status=adapter_status,
        provider_rfc_message_id=provider_rfc_message_id,
    )


def provider_execution_outcome_ready(observation: dict[str, Any]) -> bool:
    outcome = extract_provider_execution_outcome(observation)
    if outcome is None:
        return False
    if not (outcome.adapter_recipient or "").strip():
        return False
    status = (outcome.adapter_status or "").strip().lower()
    if status not in ("executed", "succeeded", "success"):
        return False

    job = observation.get("job") or {}
    for row in job.get("decision_records") or []:
        if row.get("record_type") != "execution_outcome":
            continue
        metadata = row.get("metadata") or {}
        provider = str(metadata.get("adapter_provider") or "").strip().lower()
        if provider in ("internal_stub", "internal", "none"):
            return False

    trace_metadata = (job.get("execution_trace") or {}).get("execution_outcome", {}).get("metadata") or {}
    provider = str(trace_metadata.get("adapter_provider") or "").strip().lower()
    if provider in ("internal_stub", "internal", "none"):
        return False
    return True
