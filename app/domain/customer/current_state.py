"""Pure deterministic current-state projection for end-customer reads."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Iterable, Mapping, Sequence

from app.domain.customer.enums import (
    EntityOwnerType,
    FactState,
    IdentityType,
    SourceType,
    VerificationStatus,
)
from app.domain.customer.provenance import source_precedence_rank
from app.domain.customer.schemas import CustomerIdentity, CustomerSourceFact

# Address and structured fields resolved from source facts (no address table).
ADDRESS_FIELD_ALLOWLIST: frozenset[str] = frozenset(
    {
        "street",
        "postal_code",
        "city",
        "region",
        "country_code",
        "address",
    }
)

FACT_FIELD_ALLOWLIST: frozenset[str] = frozenset(
    {
        "email",
        "phone",
        "organization_number",
        "customer_number",
        "legal_name",
        "display_name",
    }
) | ADDRESS_FIELD_ALLOWLIST

CANONICAL_FIELD_CATEGORY: dict[str, str] = {
    "address": "street",
}

SAFE_CONTACT_IDENTITY_TYPES: frozenset[IdentityType] = frozenset(
    {
        IdentityType.EMAIL,
        IdentityType.PHONE,
        IdentityType.ORGANIZATION_NUMBER,
        IdentityType.CUSTOMER_NUMBER,
    }
)

VERIFICATION_STATUS_RANK: dict[VerificationStatus, int] = {
    VerificationStatus.VERIFIED: 0,
    VerificationStatus.PROPOSED: 1,
    VerificationStatus.UNVERIFIED: 2,
    VerificationStatus.REJECTED: 3,
}

FACT_STATE_RANK: dict[FactState, int] = {
    FactState.VERIFIED: 0,
    FactState.PROPOSED: 1,
    FactState.CONFLICTING: 2,
    FactState.KNOWN: 3,
    FactState.HISTORICAL: 4,
    FactState.REJECTED: 5,
}

HISTORICAL_SUMMARY_CAP = 20


class CurrentStateResolutionIssueCode(str, Enum):
    SUPERSESSION_CYCLE = "supersession_cycle"
    ORPHAN_SUPERSESSION = "orphan_supersession"
    MULTIPLE_VERIFIED_HEADS = "multiple_verified_heads"
    UNSUPPORTED_FACT_STATE = "unsupported_fact_state"


@dataclass(frozen=True)
class SubjectRef:
    subject_type: EntityOwnerType
    subject_id: str
    is_primary: bool = False


@dataclass(frozen=True)
class ResolvedFactValue:
    fact_id: str
    field_name: str
    display_value: str | None
    normalized_value: str | None
    state: FactState
    subject_type: EntityOwnerType
    subject_id: str
    source_type: SourceType
    observed_at: datetime | None
    verified_at: datetime | None
    confidence: float
    canonical_field_category: str | None = None
    is_current: bool = False


@dataclass(frozen=True)
class CustomerValueConflict:
    fact_id: str
    field_name: str
    display_value: str | None
    state: FactState
    subject_type: EntityOwnerType
    subject_id: str
    source_type: SourceType
    conflicting_fact_ids: tuple[str, ...] = ()
    issue_code: CurrentStateResolutionIssueCode | None = None


@dataclass(frozen=True)
class CustomerHistoricalValue:
    fact_id: str
    field_name: str
    display_value: str | None
    state: FactState
    subject_type: EntityOwnerType
    subject_id: str
    source_type: SourceType
    superseded_by_fact_id: str | None = None


@dataclass(frozen=True)
class CustomerResolutionIssue:
    code: CurrentStateResolutionIssueCode
    field_name: str | None = None
    subject_type: EntityOwnerType | None = None
    subject_id: str | None = None
    fact_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResolvedIdentityValue:
    identity_id: str
    identity_type: IdentityType
    raw_value: str
    normalized_value: str | None
    verification_status: VerificationStatus
    fact_state: FactState
    source_fact_id: str | None
    is_current: bool = False


@dataclass(frozen=True)
class SubjectCurrentState:
    subject_type: EntityOwnerType
    subject_id: str
    is_primary: bool
    current_values: tuple[ResolvedFactValue, ...] = ()
    pending_values: tuple[ResolvedFactValue, ...] = ()
    conflicts: tuple[CustomerValueConflict, ...] = ()
    historical_values: tuple[CustomerHistoricalValue, ...] = ()
    current_identities: tuple[ResolvedIdentityValue, ...] = ()
    alternate_identities: tuple[ResolvedIdentityValue, ...] = ()


@dataclass
class CustomerCurrentStateProjection:
    current_values: list[ResolvedFactValue] = field(default_factory=list)
    pending_values: list[ResolvedFactValue] = field(default_factory=list)
    conflicts: list[CustomerValueConflict] = field(default_factory=list)
    historical_values: list[CustomerHistoricalValue] = field(default_factory=list)
    resolution_issues: list[CustomerResolutionIssue] = field(default_factory=list)
    subjects: list[SubjectCurrentState] = field(default_factory=list)


def _field_key(subject_type: EntityOwnerType, subject_id: str, field_name: str) -> tuple[str, str, str]:
    return (subject_type.value, subject_id, field_name)


def _is_allowed_fact_field(field_name: str) -> bool:
    return field_name in FACT_FIELD_ALLOWLIST


def _canonical_category(field_name: str) -> str | None:
    return CANONICAL_FIELD_CATEGORY.get(field_name)


def _fact_sort_key_desc_ts(value: datetime | None) -> float:
    if value is None:
        return float("-inf")
    return value.timestamp()


def _fact_tie_rank(fact: CustomerSourceFact) -> tuple:
    return (
        -source_precedence_rank(fact.source_type),
        _fact_sort_key_desc_ts(fact.verified_at),
        _fact_sort_key_desc_ts(fact.observed_at),
        _fact_sort_key_desc_ts(fact.recorded_at),
    )


def _fact_candidate_sort_key(fact: CustomerSourceFact) -> tuple:
    return (*_fact_tie_rank(fact), fact.fact_id)


def _is_verified_current_candidate(fact: CustomerSourceFact) -> bool:
    if fact.fact_state != FactState.VERIFIED:
        return False
    if fact.source_type == SourceType.AI_EXTRACTION:
        return False
    if not fact.verified_at:
        return False
    if not fact.verified_by:
        return False
    return True


def _identity_sort_key(identity: CustomerIdentity) -> tuple:
    return (
        VERIFICATION_STATUS_RANK.get(identity.verification_status, 99),
        FACT_STATE_RANK.get(identity.fact_state, 99),
        -_fact_sort_key_desc_ts(identity.last_seen_at),
        -_fact_sort_key_desc_ts(identity.first_seen_at),
        identity.identity_id,
    )


def _sorted_facts(facts: Iterable[CustomerSourceFact]) -> list[CustomerSourceFact]:
    return sorted(facts, key=lambda f: (f.recorded_at, f.fact_id))


def _sorted_identities(identities: Iterable[CustomerIdentity]) -> list[CustomerIdentity]:
    return sorted(identities, key=_identity_sort_key)


def _detect_supersession_cycles(
    facts: Sequence[CustomerSourceFact],
) -> set[str]:
    by_id = {f.fact_id: f for f in facts}
    in_cycle: set[str] = set()

    for fact in facts:
        if not fact.supersedes_fact_id:
            continue
        visited: set[str] = {fact.fact_id}
        current = fact.supersedes_fact_id
        while current is not None:
            if current in visited:
                in_cycle.update(visited)
                break
            if current not in by_id:
                break
            visited.add(current)
            current = by_id[current].supersedes_fact_id
    return in_cycle


def _verified_successors(
    fact: CustomerSourceFact,
    children_by_parent: Mapping[str, list[CustomerSourceFact]],
    cycle_ids: set[str],
) -> list[CustomerSourceFact]:
    children = children_by_parent.get(fact.fact_id, [])
    result: list[CustomerSourceFact] = []
    for child in children:
        if child.fact_id in cycle_ids:
            continue
        if child.supersedes_fact_id != fact.fact_id:
            continue
        if child.fact_state != FactState.VERIFIED:
            continue
        if not _is_verified_current_candidate(child):
            continue
        result.append(child)
    return sorted(result, key=_fact_candidate_sort_key)


def _is_superseded_by_verified_successor(
    fact: CustomerSourceFact,
    children_by_parent: Mapping[str, list[CustomerSourceFact]],
    cycle_ids: set[str],
) -> bool:
    return len(_verified_successors(fact, children_by_parent, cycle_ids)) > 0


def _to_resolved_fact(
    fact: CustomerSourceFact,
    *,
    is_current: bool = False,
) -> ResolvedFactValue:
    return ResolvedFactValue(
        fact_id=fact.fact_id,
        field_name=fact.field_name,
        display_value=fact.raw_value,
        normalized_value=fact.normalized_value,
        state=fact.fact_state,
        subject_type=fact.subject_type,
        subject_id=fact.subject_id,
        source_type=fact.source_type,
        observed_at=fact.observed_at,
        verified_at=fact.verified_at,
        confidence=fact.confidence,
        canonical_field_category=_canonical_category(fact.field_name),
        is_current=is_current,
    )


def resolve_fact_groups(
    facts: Sequence[CustomerSourceFact],
) -> tuple[
    list[ResolvedFactValue],
    list[ResolvedFactValue],
    list[CustomerValueConflict],
    list[CustomerHistoricalValue],
    list[CustomerResolutionIssue],
]:
    current_values: list[ResolvedFactValue] = []
    pending_values: list[ResolvedFactValue] = []
    conflicts: list[CustomerValueConflict] = []
    historical_values: list[CustomerHistoricalValue] = []
    resolution_issues: list[CustomerResolutionIssue] = []

    allowed_facts = [f for f in facts if _is_allowed_fact_field(f.field_name)]
    if not allowed_facts:
        return current_values, pending_values, conflicts, historical_values, resolution_issues

    by_id = {f.fact_id: f for f in allowed_facts}
    cycle_ids = _detect_supersession_cycles(allowed_facts)

    children_by_parent: dict[str, list[CustomerSourceFact]] = {}
    orphan_ids: set[str] = set()
    for fact in allowed_facts:
        if fact.supersedes_fact_id:
            if fact.supersedes_fact_id not in by_id:
                orphan_ids.add(fact.fact_id)
            else:
                children_by_parent.setdefault(fact.supersedes_fact_id, []).append(fact)

    if cycle_ids:
        grouped_cycles: dict[tuple[str, str, str], list[str]] = {}
        for fact_id in sorted(cycle_ids):
            fact = by_id.get(fact_id)
            if fact is None:
                continue
            key = _field_key(fact.subject_type, fact.subject_id, fact.field_name)
            grouped_cycles.setdefault(key, []).append(fact_id)
        for key, fact_ids in grouped_cycles.items():
            resolution_issues.append(
                CustomerResolutionIssue(
                    code=CurrentStateResolutionIssueCode.SUPERSESSION_CYCLE,
                    field_name=key[2],
                    subject_type=EntityOwnerType(key[0]),
                    subject_id=key[1],
                    fact_ids=tuple(sorted(fact_ids)),
                )
            )

    for fact_id in sorted(orphan_ids):
        fact = by_id[fact_id]
        resolution_issues.append(
            CustomerResolutionIssue(
                code=CurrentStateResolutionIssueCode.ORPHAN_SUPERSESSION,
                field_name=fact.field_name,
                subject_type=fact.subject_type,
                subject_id=fact.subject_id,
                fact_ids=(fact_id,),
            )
        )

    grouped: dict[tuple[str, str, str], list[CustomerSourceFact]] = {}
    for fact in allowed_facts:
        key = _field_key(fact.subject_type, fact.subject_id, fact.field_name)
        grouped.setdefault(key, []).append(fact)

    for key in sorted(grouped.keys()):
        group_facts = grouped[key]
        subject_type = EntityOwnerType(key[0])
        subject_id = key[1]
        field_name = key[2]

        group_cycle = {fid for fid in cycle_ids if fid in by_id and _field_key(
            by_id[fid].subject_type, by_id[fid].subject_id, by_id[fid].field_name
        ) == key}

        for fact in _sorted_facts(group_facts):
            if fact.fact_id in group_cycle:
                continue
            if fact.fact_state == FactState.HISTORICAL:
                historical_values.append(
                    CustomerHistoricalValue(
                        fact_id=fact.fact_id,
                        field_name=fact.field_name,
                        display_value=fact.raw_value,
                        state=fact.fact_state,
                        subject_type=fact.subject_type,
                        subject_id=fact.subject_id,
                        source_type=fact.source_type,
                    )
                )
                continue
            if fact.fact_state == FactState.REJECTED:
                historical_values.append(
                    CustomerHistoricalValue(
                        fact_id=fact.fact_id,
                        field_name=fact.field_name,
                        display_value=fact.raw_value,
                        state=fact.fact_state,
                        subject_type=fact.subject_type,
                        subject_id=fact.subject_id,
                        source_type=fact.source_type,
                    )
                )
                continue
            if _is_superseded_by_verified_successor(fact, children_by_parent, cycle_ids):
                successor = _verified_successors(fact, children_by_parent, cycle_ids)[0]
                historical_values.append(
                    CustomerHistoricalValue(
                        fact_id=fact.fact_id,
                        field_name=fact.field_name,
                        display_value=fact.raw_value,
                        state=fact.fact_state,
                        subject_type=fact.subject_type,
                        subject_id=fact.subject_id,
                        source_type=fact.source_type,
                        superseded_by_fact_id=successor.fact_id,
                    )
                )
                continue
            if fact.fact_id in orphan_ids:
                conflicts.append(
                    CustomerValueConflict(
                        fact_id=fact.fact_id,
                        field_name=fact.field_name,
                        display_value=fact.raw_value,
                        state=fact.fact_state,
                        subject_type=fact.subject_type,
                        subject_id=fact.subject_id,
                        source_type=fact.source_type,
                        issue_code=CurrentStateResolutionIssueCode.ORPHAN_SUPERSESSION,
                    )
                )
                continue
            if fact.fact_state == FactState.CONFLICTING:
                conflicts.append(
                    CustomerValueConflict(
                        fact_id=fact.fact_id,
                        field_name=fact.field_name,
                        display_value=fact.raw_value,
                        state=fact.fact_state,
                        subject_type=fact.subject_type,
                        subject_id=fact.subject_id,
                        source_type=fact.source_type,
                        conflicting_fact_ids=tuple(sorted(set(fact.conflicts_with_fact_ids))),
                    )
                )
                continue
            if fact.conflicts_with_fact_ids:
                conflicts.append(
                    CustomerValueConflict(
                        fact_id=fact.fact_id,
                        field_name=fact.field_name,
                        display_value=fact.raw_value,
                        state=fact.fact_state,
                        subject_type=fact.subject_type,
                        subject_id=fact.subject_id,
                        source_type=fact.source_type,
                        conflicting_fact_ids=tuple(sorted(set(fact.conflicts_with_fact_ids))),
                    )
                )
            if fact.fact_state in {FactState.PROPOSED, FactState.KNOWN}:
                pending_values.append(_to_resolved_fact(fact))

        verified_heads = [
            f
            for f in group_facts
            if f.fact_id not in group_cycle
            and f.fact_id not in orphan_ids
            and _is_verified_current_candidate(f)
            and not _is_superseded_by_verified_successor(f, children_by_parent, cycle_ids)
        ]

        if not verified_heads:
            continue

        sorted_heads = sorted(verified_heads, key=_fact_candidate_sort_key)
        winner: CustomerSourceFact | None = None
        if len(sorted_heads) == 1:
            winner = sorted_heads[0]
        else:
            top_rank = _fact_tie_rank(sorted_heads[0])
            tied = [f for f in sorted_heads if _fact_tie_rank(f) == top_rank]
            if len(tied) == 1:
                winner = tied[0]
            else:
                distinct_values = {
                    (f.normalized_value or f.raw_value or "") for f in tied
                }
                if len(distinct_values) > 1:
                    tied_ids = tuple(sorted(f.fact_id for f in tied))
                    resolution_issues.append(
                        CustomerResolutionIssue(
                            code=CurrentStateResolutionIssueCode.MULTIPLE_VERIFIED_HEADS,
                            field_name=field_name,
                            subject_type=subject_type,
                            subject_id=subject_id,
                            fact_ids=tied_ids,
                        )
                    )
                    for fact in tied:
                        conflicts.append(
                            CustomerValueConflict(
                                fact_id=fact.fact_id,
                                field_name=fact.field_name,
                                display_value=fact.raw_value,
                                state=fact.fact_state,
                                subject_type=fact.subject_type,
                                subject_id=fact.subject_id,
                                source_type=fact.source_type,
                                issue_code=CurrentStateResolutionIssueCode.MULTIPLE_VERIFIED_HEADS,
                            )
                        )
                else:
                    winner = sorted(tied, key=lambda f: f.fact_id)[0]

        if winner is not None:
            current_values.append(_to_resolved_fact(winner, is_current=True))

    return current_values, pending_values, conflicts, historical_values, resolution_issues


def resolve_current_identity(
    identity_type: IdentityType,
    identities: Sequence[CustomerIdentity],
) -> tuple[ResolvedIdentityValue | None, list[ResolvedIdentityValue]]:
    if identity_type not in SAFE_CONTACT_IDENTITY_TYPES:
        return None, []

    candidates = [
        i
        for i in identities
        if i.identity_type == identity_type
        and i.verification_status != VerificationStatus.REJECTED
        and i.fact_state not in {FactState.HISTORICAL, FactState.REJECTED}
    ]
    if not candidates:
        return None, []

    ordered = _sorted_identities(candidates)
    current_candidate = ordered[0]
    if current_candidate.verification_status != VerificationStatus.VERIFIED:
        return None, [
            ResolvedIdentityValue(
                identity_id=i.identity_id,
                identity_type=i.identity_type,
                raw_value=i.raw_value,
                normalized_value=i.normalized_value,
                verification_status=i.verification_status,
                fact_state=i.fact_state,
                source_fact_id=i.source_fact_id,
            )
            for i in ordered
        ]

    current = ResolvedIdentityValue(
        identity_id=current_candidate.identity_id,
        identity_type=current_candidate.identity_type,
        raw_value=current_candidate.raw_value,
        normalized_value=current_candidate.normalized_value,
        verification_status=current_candidate.verification_status,
        fact_state=current_candidate.fact_state,
        source_fact_id=current_candidate.source_fact_id,
        is_current=True,
    )
    alternates = [
        ResolvedIdentityValue(
            identity_id=i.identity_id,
            identity_type=i.identity_type,
            raw_value=i.raw_value,
            normalized_value=i.normalized_value,
            verification_status=i.verification_status,
            fact_state=i.fact_state,
            source_fact_id=i.source_fact_id,
        )
        for i in ordered[1:]
    ]
    return current, alternates


def resolve_customer_current_state(
    subjects: Sequence[SubjectRef],
    facts_by_subject: Mapping[tuple[EntityOwnerType, str], Sequence[CustomerSourceFact]],
    identities_by_owner: Mapping[tuple[EntityOwnerType, str], Sequence[CustomerIdentity]],
) -> CustomerCurrentStateProjection:
    projection = CustomerCurrentStateProjection()
    seen_subjects: set[tuple[str, str]] = set()

    for subject in subjects:
        key = (subject.subject_type.value, subject.subject_id)
        if key in seen_subjects:
            continue
        seen_subjects.add(key)

        owner_key = (subject.subject_type, subject.subject_id)
        subject_facts = list(facts_by_subject.get(owner_key, ()))
        current, pending, conflicts, historical, issues = resolve_fact_groups(subject_facts)

        subject_identities = list(identities_by_owner.get(owner_key, ()))
        current_identities: list[ResolvedIdentityValue] = []
        alternate_identities: list[ResolvedIdentityValue] = []
        for identity_type in sorted(SAFE_CONTACT_IDENTITY_TYPES, key=lambda t: t.value):
            current_identity, alternates = resolve_current_identity(identity_type, subject_identities)
            if current_identity is not None:
                current_identities.append(current_identity)
            alternate_identities.extend(alternates)

        subject_state = SubjectCurrentState(
            subject_type=subject.subject_type,
            subject_id=subject.subject_id,
            is_primary=subject.is_primary,
            current_values=tuple(current),
            pending_values=tuple(pending),
            conflicts=tuple(conflicts),
            historical_values=tuple(historical[:HISTORICAL_SUMMARY_CAP]),
            current_identities=tuple(current_identities),
            alternate_identities=tuple(alternate_identities),
        )

        projection.current_values.extend(current)
        projection.pending_values.extend(pending)
        projection.conflicts.extend(conflicts)
        projection.historical_values.extend(historical[:HISTORICAL_SUMMARY_CAP])
        projection.resolution_issues.extend(issues)
        projection.subjects.append(subject_state)

    return projection


def current_identity_raw_value(
    projection: CustomerCurrentStateProjection,
    owner_type: EntityOwnerType,
    owner_id: str,
    identity_type: IdentityType,
) -> str | None:
    for subject in projection.subjects:
        if subject.subject_type != owner_type or subject.subject_id != owner_id:
            continue
        for identity in subject.current_identities:
            if identity.identity_type == identity_type:
                return identity.raw_value
    return None
