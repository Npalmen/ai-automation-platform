"""Pure timeline, provenance, and idempotency helpers — no I/O."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.customer.enums import (
    FactState,
    ReferenceType,
    SourceType,
    TimelineEventType,
)
from app.domain.customer.schemas import CustomerSourceFact, CustomerTimelineEvent, SourceReference

# Higher rank = stronger authority. Not automatic overwrite logic.
SOURCE_PRECEDENCE_RANK: dict[SourceType, int] = {
    SourceType.ADMIN_CORRECTION: 7,
    SourceType.USER_INPUT: 6,
    SourceType.INTEGRATION: 5,
    SourceType.IMPORT: 4,
    SourceType.GMAIL_INBOUND: 3,
    SourceType.AI_EXTRACTION: 2,
    SourceType.SYSTEM_DERIVED: 1,
}

ALLOWED_FACT_TRANSITIONS: dict[FactState, frozenset[FactState]] = {
    FactState.KNOWN: frozenset(
        {FactState.PROPOSED, FactState.VERIFIED, FactState.CONFLICTING, FactState.HISTORICAL, FactState.REJECTED}
    ),
    FactState.PROPOSED: frozenset(
        {FactState.VERIFIED, FactState.CONFLICTING, FactState.HISTORICAL, FactState.REJECTED}
    ),
    FactState.VERIFIED: frozenset({FactState.HISTORICAL, FactState.CONFLICTING}),
    FactState.CONFLICTING: frozenset({FactState.VERIFIED, FactState.HISTORICAL, FactState.REJECTED}),
    FactState.HISTORICAL: frozenset(),
    FactState.REJECTED: frozenset({FactState.PROPOSED}),
}

FORBIDDEN_METADATA_KEYS: frozenset[str] = frozenset(
    {
        "payload",
        "request_payload",
        "delivery_payload",
        "result_payload",
        "input_data",
        "processor_history",
        "body_text",
        "message_text",
        "token",
        "access_token",
        "refresh_token",
        "credential",
        "credentials",
        "secret",
        "api_key",
        "password",
        "authorization",
    }
)

ALLOWED_METADATA_KEYS: frozenset[str] = frozenset(
    {
        "job_type",
        "job_status",
        "approval_state",
        "action_type",
        "action_status",
        "field_name",
        "fact_state",
        "previous_fact_state",
        "integration_type",
        "thread_id",
        "message_id",
        "duplicate_status",
        "confidence",
        "reason_code",
        "link_type",
        "event_family",
        "source_label",
        "count",
        "severity",
    }
)

FORBIDDEN_PAYLOAD_REFERENCE_TYPES: frozenset[ReferenceType] = frozenset(
    {ReferenceType.JOB, ReferenceType.APPROVAL, ReferenceType.ACTION_EXECUTION}
)


class TimelineReplayIdentity(BaseModel):
    """Stable identity for idempotent timeline registration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tenant_id: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    event_type: TimelineEventType
    source_reference_key: str = Field(min_length=1)

    def identity_key(self) -> str:
        return f"{self.tenant_id}:{self.customer_id}:{self.event_type.value}:{self.source_reference_key}"


class FactTransitionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool
    from_state: FactState
    to_state: FactState
    reason: str | None = None


def source_precedence_rank(source_type: SourceType) -> int:
    return SOURCE_PRECEDENCE_RANK.get(source_type, 0)


def can_transition_fact_state(from_state: FactState, to_state: FactState) -> bool:
    if from_state == to_state:
        return True
    return to_state in ALLOWED_FACT_TRANSITIONS.get(from_state, frozenset())


def evaluate_fact_transition(from_state: FactState, to_state: FactState) -> FactTransitionResult:
    allowed = can_transition_fact_state(from_state, to_state)
    reason = None if allowed else f"transition {from_state.value} -> {to_state.value} is forbidden"
    return FactTransitionResult(allowed=allowed, from_state=from_state, to_state=to_state, reason=reason)


def lower_source_cannot_supersede_verified(
    proposed: CustomerSourceFact,
    existing: CustomerSourceFact,
) -> bool:
    """Return True when a lower-precedence proposed fact must not replace verified data."""
    if existing.fact_state != FactState.VERIFIED:
        return False
    if proposed.fact_state in {FactState.VERIFIED, FactState.HISTORICAL}:
        return False
    if source_precedence_rank(proposed.source_type) <= source_precedence_rank(existing.source_type):
        return True
    return False


def validate_timeline_metadata(metadata: dict[str, object]) -> dict[str, str | int | float | bool | None]:
    cleaned: dict[str, str | int | float | bool | None] = {}
    for key, value in metadata.items():
        key_norm = str(key).strip().lower()
        if key_norm in FORBIDDEN_METADATA_KEYS:
            raise ValueError(f"forbidden metadata key: {key}")
        if key_norm not in ALLOWED_METADATA_KEYS:
            raise ValueError(f"metadata key not allowlisted: {key}")
        if value is None or isinstance(value, (str, int, float, bool)):
            cleaned[key_norm] = value
        else:
            raise ValueError(f"metadata value for {key} must be scalar")
    return cleaned


def build_source_reference_key(reference: SourceReference) -> str:
    source_suffix = reference.source_type.value if reference.source_type else "none"
    return f"{reference.reference_type.value}:{reference.reference_id}:{source_suffix}"


def build_timeline_replay_identity(
    tenant_id: str,
    customer_id: str,
    event_type: TimelineEventType,
    source_reference: SourceReference,
) -> TimelineReplayIdentity:
    return TimelineReplayIdentity(
        tenant_id=tenant_id,
        customer_id=customer_id,
        event_type=event_type,
        source_reference_key=build_source_reference_key(source_reference),
    )


def timeline_sort_key(event: CustomerTimelineEvent) -> tuple[datetime, datetime, str]:
    return (event.occurred_at, event.recorded_at, event.timeline_event_id)


def sort_timeline_events(events: Sequence[CustomerTimelineEvent]) -> list[CustomerTimelineEvent]:
    return sorted(events, key=timeline_sort_key)


def validate_same_tenant(*tenant_ids: str) -> None:
    normalized = [tenant_id.strip() for tenant_id in tenant_ids if tenant_id and tenant_id.strip()]
    if not normalized:
        raise ValueError("tenant_id required")
    first = normalized[0]
    if any(tenant_id != first for tenant_id in normalized):
        raise ValueError("cross-tenant reference forbidden")


def validate_reference_tenant_scope(
    record_tenant_id: str,
    reference_tenant_id: str | None,
) -> None:
    if reference_tenant_id is None:
        return
    validate_same_tenant(record_tenant_id, reference_tenant_id)


def timeline_event_uses_reference_only(event: CustomerTimelineEvent) -> bool:
    if event.reference_type is None:
        return True
    if event.reference_type in FORBIDDEN_PAYLOAD_REFERENCE_TYPES:
        return event.reference_id is not None and not event.metadata
    return True


def is_duplicate_replay(
    existing_identities: Iterable[str],
    replay_identity: TimelineReplayIdentity,
) -> bool:
    return replay_identity.identity_key() in set(existing_identities)


def supersession_fact(
    new_fact: CustomerSourceFact,
    prior_fact: CustomerSourceFact,
) -> CustomerSourceFact:
    """Return a copy-shaped fact linking supersession without mutating inputs."""
    if new_fact.tenant_id != prior_fact.tenant_id:
        raise ValueError("cross-tenant supersession forbidden")
    if new_fact.fact_id == prior_fact.fact_id:
        raise ValueError("cannot supersede self")
    return new_fact.model_copy(
        update={
            "supersedes_fact_id": prior_fact.fact_id,
            "fact_state": FactState.PROPOSED if new_fact.fact_state == FactState.KNOWN else new_fact.fact_state,
        }
    )


def conflict_fact(
    new_fact: CustomerSourceFact,
    conflicting_fact_ids: list[str],
) -> CustomerSourceFact:
    return new_fact.model_copy(
        update={
            "fact_state": FactState.CONFLICTING,
            "conflicts_with_fact_ids": sorted(set(conflicting_fact_ids)),
        }
    )


def historical_fact(prior_fact: CustomerSourceFact) -> CustomerSourceFact:
    return prior_fact.model_copy(update={"fact_state": FactState.HISTORICAL})
