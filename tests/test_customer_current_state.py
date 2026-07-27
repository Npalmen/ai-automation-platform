"""Pure tests for deterministic customer current-state projection."""

from __future__ import annotations

import itertools
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.domain.customer.current_state import (
    CurrentStateResolutionIssueCode,
    resolve_current_identity,
    resolve_customer_current_state,
    resolve_fact_groups,
    SubjectRef,
)
from app.domain.customer.enums import (
    EntityOwnerType,
    FactState,
    IdentityType,
    SourceType,
    VerificationStatus,
)
from app.domain.customer.schemas import CustomerIdentity, CustomerSourceFact

UTC = timezone.utc


def _now(offset: int = 0) -> datetime:
    return datetime(2026, 1, 10, 9, 0, offset, tzinfo=UTC)


def _fact_id() -> str:
    return str(uuid4())


def _fact(
    *,
    fact_id: str | None = None,
    subject_type: EntityOwnerType = EntityOwnerType.CONTACT,
    subject_id: str = "contact-1",
    field_name: str = "phone",
    raw_value: str = "0701234567",
    state: FactState = FactState.PROPOSED,
    source: SourceType = SourceType.AI_EXTRACTION,
    recorded_at: datetime | None = None,
    verified_at: datetime | None = None,
    verified_by: str | None = None,
    supersedes: str | None = None,
    conflicts: list[str] | None = None,
) -> CustomerSourceFact:
    return CustomerSourceFact(
        fact_id=fact_id or _fact_id(),
        tenant_id="T1",
        subject_type=subject_type,
        subject_id=subject_id,
        field_name=field_name,
        raw_value=raw_value,
        normalized_value=raw_value,
        fact_state=state,
        source_type=source,
        confidence=0.8,
        observed_at=recorded_at or _now(),
        recorded_at=recorded_at or _now(),
        verified_at=verified_at,
        verified_by=verified_by,
        supersedes_fact_id=supersedes,
        conflicts_with_fact_ids=conflicts or [],
    )


def _identity(
    *,
    identity_id: str | None = None,
    owner_type: EntityOwnerType = EntityOwnerType.CONTACT,
    owner_id: str = "contact-1",
    identity_type: IdentityType = IdentityType.EMAIL,
    raw_value: str = "a@example.invalid",
    verification: VerificationStatus = VerificationStatus.VERIFIED,
    fact_state: FactState = FactState.VERIFIED,
    last_seen_at: datetime | None = None,
) -> CustomerIdentity:
    return CustomerIdentity(
        identity_id=identity_id or _fact_id(),
        tenant_id="T1",
        owner_type=owner_type,
        owner_id=owner_id,
        identity_type=identity_type,
        raw_value=raw_value,
        normalized_value=raw_value.lower(),
        fact_state=fact_state,
        verification_status=verification,
        first_seen_at=_now(),
        last_seen_at=last_seen_at or _now(),
    )


class TestFactResolverOrdering:
    def test_same_facts_different_input_order_same_projection(self):
        verified = _fact(
            fact_id="verified-1",
            state=FactState.VERIFIED,
            source=SourceType.ADMIN_CORRECTION,
            verified_at=_now(1),
            verified_by="op-1",
            raw_value="0701111111",
        )
        proposed = _fact(
            fact_id="proposed-1",
            state=FactState.PROPOSED,
            source=SourceType.AI_EXTRACTION,
            raw_value="0702222222",
            recorded_at=_now(2),
        )
        for ordering in itertools.permutations([verified, proposed]):
            current, pending, conflicts, historical, issues = resolve_fact_groups(list(ordering))
            assert len(current) == 1
            assert current[0].fact_id == "verified-1"
            assert current[0].display_value == "0701111111"
            assert len(pending) == 1
            assert pending[0].fact_id == "proposed-1"
            assert not conflicts
            assert not issues

    def test_verified_wins_over_proposed(self):
        verified = _fact(
            state=FactState.VERIFIED,
            source=SourceType.ADMIN_CORRECTION,
            verified_at=_now(),
            verified_by="op",
        )
        proposed = _fact(state=FactState.PROPOSED, source=SourceType.AI_EXTRACTION)
        current, pending, _, _, _ = resolve_fact_groups([proposed, verified])
        assert current[0].state == FactState.VERIFIED
        assert pending[0].state == FactState.PROPOSED

    def test_proposed_successor_does_not_replace_verified_current(self):
        original = _fact(
            fact_id="orig",
            state=FactState.VERIFIED,
            source=SourceType.ADMIN_CORRECTION,
            verified_at=_now(),
            verified_by="op",
            raw_value="0701111111",
        )
        proposed_child = _fact(
            fact_id="child",
            state=FactState.PROPOSED,
            source=SourceType.AI_EXTRACTION,
            supersedes="orig",
            raw_value="0702222222",
        )
        current, pending, conflicts, historical, _ = resolve_fact_groups(
            [original, proposed_child]
        )
        assert len(current) == 1
        assert current[0].fact_id == "orig"
        assert any(p.fact_id == "child" for p in pending)
        assert not historical

    def test_verified_successor_moves_parent_to_historical(self):
        original = _fact(
            fact_id="orig",
            state=FactState.PROPOSED,
            source=SourceType.GMAIL_INBOUND,
            raw_value="0701111111",
        )
        verified_child = _fact(
            fact_id="child",
            state=FactState.VERIFIED,
            source=SourceType.ADMIN_CORRECTION,
            verified_at=_now(5),
            verified_by="op",
            supersedes="orig",
            raw_value="0702222222",
        )
        current, pending, _, historical, _ = resolve_fact_groups([original, verified_child])
        assert len(current) == 1
        assert current[0].fact_id == "child"
        assert any(h.fact_id == "orig" for h in historical)

    def test_conflicting_not_current_when_verified_exists(self):
        verified = _fact(
            fact_id="v1",
            state=FactState.VERIFIED,
            source=SourceType.ADMIN_CORRECTION,
            verified_at=_now(),
            verified_by="op",
        )
        conflicting = _fact(
            fact_id="c1",
            state=FactState.CONFLICTING,
            source=SourceType.AI_EXTRACTION,
            conflicts=["v1"],
        )
        current, _, conflicts, _, _ = resolve_fact_groups([verified, conflicting])
        assert current[0].fact_id == "v1"
        assert any(c.fact_id == "c1" for c in conflicts)

    def test_rejected_never_current(self):
        rejected = _fact(state=FactState.REJECTED, source=SourceType.AI_EXTRACTION)
        current, _, _, historical, _ = resolve_fact_groups([rejected])
        assert not current
        assert any(h.fact_id == rejected.fact_id for h in historical)

    def test_ai_verified_fact_not_current(self):
        ai_verified = _fact(
            state=FactState.VERIFIED,
            source=SourceType.AI_EXTRACTION,
            verified_at=_now(),
            verified_by="op",
        )
        current, _, _, _, _ = resolve_fact_groups([ai_verified])
        assert not current

    def test_orphan_supersession_fail_closed(self):
        orphan = _fact(
            fact_id="orphan",
            state=FactState.VERIFIED,
            source=SourceType.ADMIN_CORRECTION,
            verified_at=_now(),
            verified_by="op",
            supersedes="missing",
        )
        current, _, conflicts, _, issues = resolve_fact_groups([orphan])
        assert not current
        assert issues[0].code == CurrentStateResolutionIssueCode.ORPHAN_SUPERSESSION
        assert conflicts

    def test_two_node_cycle_fail_closed(self):
        a = _fact(
            fact_id="a",
            state=FactState.VERIFIED,
            source=SourceType.ADMIN_CORRECTION,
            verified_at=_now(),
            verified_by="op",
            supersedes="b",
        )
        b = _fact(
            fact_id="b",
            state=FactState.VERIFIED,
            source=SourceType.ADMIN_CORRECTION,
            verified_at=_now(1),
            verified_by="op",
            supersedes="a",
        )
        current, _, _, _, issues = resolve_fact_groups([a, b])
        assert not current
        assert issues[0].code == CurrentStateResolutionIssueCode.SUPERSESSION_CYCLE

    def test_multiple_verified_heads_same_precedence_conflict(self):
        first = _fact(
            fact_id="f1",
            state=FactState.VERIFIED,
            source=SourceType.GMAIL_INBOUND,
            verified_at=_now(),
            verified_by="op",
            raw_value="0701111111",
            recorded_at=_now(),
        )
        second = _fact(
            fact_id="f2",
            state=FactState.VERIFIED,
            source=SourceType.GMAIL_INBOUND,
            verified_at=_now(),
            verified_by="op",
            raw_value="0702222222",
            recorded_at=_now(),
        )
        current, _, conflicts, _, issues = resolve_fact_groups([first, second])
        assert not current
        assert issues[0].code == CurrentStateResolutionIssueCode.MULTIPLE_VERIFIED_HEADS
        assert len(conflicts) == 2

    def test_source_precedence_tie_break_allows_current(self):
        weak = _fact(
            fact_id="weak",
            state=FactState.VERIFIED,
            source=SourceType.GMAIL_INBOUND,
            verified_at=_now(),
            verified_by="op",
            raw_value="0701111111",
        )
        strong = _fact(
            fact_id="strong",
            state=FactState.VERIFIED,
            source=SourceType.ADMIN_CORRECTION,
            verified_at=_now(),
            verified_by="op",
            raw_value="0702222222",
        )
        current, _, _, _, _ = resolve_fact_groups([weak, strong])
        assert current[0].fact_id == "strong"


class TestIdentityResolver:
    def test_identity_order_independent(self):
        older = _identity(
            identity_id="old",
            raw_value="old@example.invalid",
            last_seen_at=_now(),
        )
        newer = _identity(
            identity_id="new",
            raw_value="new@example.invalid",
            last_seen_at=_now(10),
        )
        for ordering in itertools.permutations([older, newer]):
            current, alternates = resolve_current_identity(IdentityType.EMAIL, list(ordering))
            assert current is not None
            assert current.identity_id == "new"
            assert len(alternates) == 1

    def test_multiple_identities_same_type_current_and_alternates(self):
        primary = _identity(identity_id="p", raw_value="a@example.invalid")
        alt = _identity(
            identity_id="a",
            raw_value="b@example.invalid",
            verification=VerificationStatus.PROPOSED,
            fact_state=FactState.PROPOSED,
        )
        current, alternates = resolve_current_identity(
            IdentityType.EMAIL, [primary, alt]
        )
        assert current is not None
        assert current.identity_id == "p"
        assert any(a.identity_id == "a" for a in alternates)

    def test_rejected_identity_not_current(self):
        rejected = _identity(
            verification=VerificationStatus.REJECTED,
            fact_state=FactState.REJECTED,
        )
        current, alternates = resolve_current_identity(IdentityType.EMAIL, [rejected])
        assert current is None
        assert not alternates

    def test_gmail_identity_type_filtered(self):
        gmail = _identity(
            identity_type=IdentityType.GMAIL_THREAD,
            raw_value="thread-1",
        )
        current, alternates = resolve_current_identity(IdentityType.GMAIL_THREAD, [gmail])
        assert current is None
        assert not alternates


class TestAggregateProjection:
    def test_separate_contact_subjects(self):
        facts = [
            _fact(
                subject_id="contact-1",
                field_name="email",
                state=FactState.VERIFIED,
                source=SourceType.ADMIN_CORRECTION,
                verified_at=_now(),
                verified_by="op",
                raw_value="c1@example.invalid",
            ),
            _fact(
                subject_id="contact-2",
                field_name="email",
                state=FactState.VERIFIED,
                source=SourceType.ADMIN_CORRECTION,
                verified_at=_now(),
                verified_by="op",
                raw_value="c2@example.invalid",
            ),
        ]
        identities = [
            _identity(owner_id="contact-1", raw_value="c1@example.invalid"),
            _identity(owner_id="contact-2", raw_value="c2@example.invalid"),
        ]
        subjects = [
            SubjectRef(EntityOwnerType.CONTACT, "contact-1", True),
            SubjectRef(EntityOwnerType.CONTACT, "contact-2", False),
        ]
        facts_map = {
            (EntityOwnerType.CONTACT, "contact-1"): [facts[0]],
            (EntityOwnerType.CONTACT, "contact-2"): [facts[1]],
        }
        identity_map = {
            (EntityOwnerType.CONTACT, "contact-1"): [identities[0]],
            (EntityOwnerType.CONTACT, "contact-2"): [identities[1]],
        }
        projection = resolve_customer_current_state(subjects, facts_map, identity_map)
        assert len(projection.subjects) == 2
        values = {s.subject_id: s.current_values[0].display_value for s in projection.subjects}
        assert values["contact-1"] == "c1@example.invalid"
        assert values["contact-2"] == "c2@example.invalid"

    def test_address_field_preserved(self):
        address_fact = _fact(
            field_name="address",
            state=FactState.VERIFIED,
            source=SourceType.ADMIN_CORRECTION,
            verified_at=_now(),
            verified_by="op",
            raw_value="Storgatan 1",
        )
        current, _, _, _, _ = resolve_fact_groups([address_fact])
        assert current[0].field_name == "address"
        assert current[0].canonical_field_category == "street"
