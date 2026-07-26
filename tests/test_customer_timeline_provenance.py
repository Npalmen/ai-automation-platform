"""Tests for timeline ordering, provenance rules, and fixture contracts."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domain.customer.enums import (
    EntityOwnerType,
    FactState,
    ReferenceType,
    SourceType,
    TimelineEventType,
)
from app.domain.customer.provenance import (
    ALLOWED_FACT_TRANSITIONS,
    build_source_reference_key,
    build_timeline_replay_identity,
    can_transition_fact_state,
    conflict_fact,
    evaluate_fact_transition,
    historical_fact,
    is_duplicate_replay,
    lower_source_cannot_supersede_verified,
    sort_timeline_events,
    supersession_fact,
    validate_reference_tenant_scope,
    validate_same_tenant,
    validate_timeline_metadata,
)
from app.domain.customer.schemas import CustomerSourceFact, CustomerTimelineEvent, SourceReference

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "customer_domain"
FIXTURE_FILES = sorted(FIXTURE_DIR.glob("family_*.json"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fact(
    fact_id: str,
    *,
    state: FactState = FactState.PROPOSED,
    source: SourceType = SourceType.AI_EXTRACTION,
    field_name: str = "email",
    value: str = "a@example.invalid",
) -> CustomerSourceFact:
    return CustomerSourceFact(
        fact_id=fact_id,
        tenant_id="T1",
        subject_type=EntityOwnerType.CONTACT,
        subject_id="contact-1",
        field_name=field_name,
        raw_value=value,
        normalized_value=value,
        fact_state=state,
        source_type=source,
        confidence=0.7,
        recorded_at=_now(),
    )


def _event(
    event_id: str,
    *,
    occurred_at: datetime,
    recorded_at: datetime,
    metadata: dict[str, str | int | float | bool | None] | None = None,
) -> CustomerTimelineEvent:
    return CustomerTimelineEvent(
        timeline_event_id=event_id,
        tenant_id="T1",
        customer_id="cust-1",
        event_type=TimelineEventType.JOB_CREATED,
        occurred_at=occurred_at,
        recorded_at=recorded_at,
        summary="Job skapades",
        reference_type=ReferenceType.JOB,
        reference_id="job-1",
        metadata=metadata or {"job_type": "lead"},
    )


def test_naive_timestamps_rejected_on_timeline_event() -> None:
    with pytest.raises(ValidationError):
        CustomerTimelineEvent(
            timeline_event_id="e1",
            tenant_id="T1",
            customer_id="cust-1",
            event_type=TimelineEventType.FIRST_CONTACT,
            occurred_at=datetime(2026, 1, 1),
            recorded_at=_now(),
            summary="Första kontakt",
        )


def test_occurred_and_recorded_are_separate_fields() -> None:
    occurred = _now() - timedelta(days=1)
    recorded = _now()
    event = _event("e1", occurred_at=occurred, recorded_at=recorded)
    assert event.occurred_at != event.recorded_at


def test_deterministic_timeline_ordering() -> None:
    base = _now()
    events = [
        _event("e3", occurred_at=base, recorded_at=base + timedelta(seconds=3)),
        _event("e1", occurred_at=base, recorded_at=base + timedelta(seconds=1)),
        _event("e2", occurred_at=base, recorded_at=base + timedelta(seconds=2)),
    ]
    ordered = sort_timeline_events(events)
    assert [event.timeline_event_id for event in ordered] == ["e1", "e2", "e3"]


def test_late_backfill_events_sort_by_occurred_at() -> None:
    early_occurred = _now() - timedelta(days=10)
    late_recorded = _now()
    events = [
        _event("late-backfill", occurred_at=early_occurred, recorded_at=late_recorded),
        _event("recent", occurred_at=_now(), recorded_at=_now()),
    ]
    ordered = sort_timeline_events(events)
    assert ordered[0].timeline_event_id == "late-backfill"


def test_supersession_links_prior_fact() -> None:
    prior = _fact("fact-1", state=FactState.VERIFIED, source=SourceType.USER_INPUT)
    new = _fact("fact-2", state=FactState.PROPOSED, source=SourceType.GMAIL_INBOUND)
    linked = supersession_fact(new, prior)
    assert linked.supersedes_fact_id == "fact-1"


def test_supersession_cannot_reference_self() -> None:
    fact = _fact("fact-1")
    with pytest.raises(ValueError):
        supersession_fact(fact, fact)


def test_conflict_fact_references_conflicts() -> None:
    new = _fact("fact-2")
    conflicted = conflict_fact(new, ["fact-0", "fact-1"])
    assert conflicted.fact_state == FactState.CONFLICTING
    assert conflicted.conflicts_with_fact_ids == ["fact-0", "fact-1"]


def test_verified_fact_not_superseded_by_ai_proposal() -> None:
    verified = _fact("fact-1", state=FactState.VERIFIED, source=SourceType.USER_INPUT)
    proposed = _fact("fact-2", state=FactState.PROPOSED, source=SourceType.AI_EXTRACTION)
    assert lower_source_cannot_supersede_verified(proposed, verified)


def test_historical_fact_preserves_provenance_fields() -> None:
    prior = _fact("fact-1", state=FactState.VERIFIED, source=SourceType.USER_INPUT)
    historical = historical_fact(prior)
    assert historical.fact_state == FactState.HISTORICAL
    assert historical.source_type == SourceType.USER_INPUT
    assert historical.fact_id == "fact-1"


def test_cross_tenant_reference_rejected() -> None:
    with pytest.raises(ValueError):
        validate_same_tenant("T1", "T2")
    with pytest.raises(ValueError):
        validate_reference_tenant_scope("T1", "T2")


def test_forbidden_payload_metadata_rejected() -> None:
    with pytest.raises(ValueError):
        validate_timeline_metadata({"payload": "secret"})
    with pytest.raises(ValueError):
        validate_timeline_metadata({"token": "abc"})
    with pytest.raises(ValidationError):
        _event("e1", occurred_at=_now(), recorded_at=_now(), metadata={"payload": "x"})


def test_stable_source_reference_for_replay() -> None:
    ref = SourceReference(
        reference_type=ReferenceType.JOB,
        reference_id="job-42",
        source_type=SourceType.GMAIL_INBOUND,
    )
    key = build_source_reference_key(ref)
    identity = build_timeline_replay_identity("T1", "cust-1", TimelineEventType.JOB_CREATED, ref)
    assert identity.identity_key().endswith(key)
    assert is_duplicate_replay([identity.identity_key()], identity)


def test_duplicate_source_reference_detected() -> None:
    ref = SourceReference(reference_type=ReferenceType.JOB, reference_id="job-1")
    identity = build_timeline_replay_identity("T1", "cust-1", TimelineEventType.JOB_CREATED, ref)
    assert is_duplicate_replay([], identity) is False
    assert is_duplicate_replay([identity.identity_key()], identity) is True


def test_timeline_event_reference_only_no_payload_copy() -> None:
    event = _event("e1", occurred_at=_now(), recorded_at=_now())
    assert event.reference_id == "job-1"
    assert "payload" not in event.metadata
    assert "input_data" not in event.model_dump()


def test_fact_transition_matrix_has_no_historical_exit() -> None:
    assert ALLOWED_FACT_TRANSITIONS[FactState.HISTORICAL] == frozenset()
    assert not can_transition_fact_state(FactState.HISTORICAL, FactState.VERIFIED)


def test_evaluate_fact_transition_reports_reason() -> None:
    result = evaluate_fact_transition(FactState.HISTORICAL, FactState.VERIFIED)
    assert result.allowed is False
    assert result.reason is not None


@pytest.mark.parametrize("fixture_path", FIXTURE_FILES, ids=[p.stem for p in FIXTURE_FILES])
def test_fixture_contract(fixture_path: Path) -> None:
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == "customer_domain_fixture_v1"
    assert data["tenant_id"].strip()
    assert data["automatic_merge_allowed"] is False
    assert data["automatic_link_allowed"] is False
    assert data["expected_timeline"]
    assert data["expected_facts"]
    assert "expected_duplicate" in data
    for observation in data["observations"]:
        assert observation.get("source_type")
        assert observation.get("at")


def test_all_fixture_families_present() -> None:
    assert len(FIXTURE_FILES) == 5


def test_fixtures_have_no_cross_tenant_links() -> None:
    tenants = {json.loads(path.read_text())["tenant_id"] for path in FIXTURE_FILES}
    assert len(tenants) == 1


def test_company_fixture_separates_company_and_contact() -> None:
    data = json.loads((FIXTURE_DIR / "family_04_company_multiple_contacts.json").read_text())
    assert data["company_contact_separation"] is True
    subjects = {fact.get("subject_type", "contact") for fact in data["expected_facts"]}
    assert "company" in subjects
    assert "contact" in subjects


def test_change_fixture_preserves_historical_value() -> None:
    data = json.loads((FIXTURE_DIR / "family_03_changed_contact.json").read_text())
    states = [fact["fact_state"] for fact in data["expected_facts"]]
    assert "verified" in states
    assert "proposed" in states


def test_ambiguous_fixture_requires_manual_review() -> None:
    data = json.loads((FIXTURE_DIR / "family_05_ambiguous_duplicate.json").read_text())
    assert data["expected_duplicate"]["requires_manual_review"] is True
    assert data["expected_duplicate"]["status"] == "open"
