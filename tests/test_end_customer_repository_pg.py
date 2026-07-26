"""PostgreSQL repository tests for end-customer foundation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.orm import sessionmaker

from app.domain.customer.enums import (
    CustomerStatus,
    CustomerType,
    DuplicateStatus,
    EntityOwnerType,
    FactState,
    IdentityType,
    LinkType,
    ReferenceType,
    RelationshipType,
    SourceType,
    TimelineEventType,
    VerificationStatus,
)
from app.domain.customer.provenance import build_timeline_replay_identity
from app.domain.customer.schemas import (
    CustomerIdentity,
    CustomerSourceFact,
    CustomerTimelineEvent,
    SourceReference,
)
from app.repositories.postgres.end_customer_repository import (
    EndCustomerDuplicateError,
    EndCustomerIdempotencyConflictError,
    EndCustomerNotFoundError,
    EndCustomerRepository,
    EndCustomerTenantScopeError,
    EndCustomerVersionConflictError,
)
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.migration_runner import (
    ORDERED_MIGRATION_FILES,
    apply_pre_migration_baseline,
    apply_versioned_sql_migrations,
    reset_public_schema,
)
from tests.helpers.end_customer_pg import postgres_database_url, teardown_end_customer_foundation_tables


def _postgres_url() -> str:
    return postgres_database_url()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid4())


@pytest.fixture()
def pg_engine():
    from sqlalchemy import create_engine

    engine = create_engine(_postgres_url())
    reset_public_schema(engine)
    apply_pre_migration_baseline(engine)
    apply_versioned_sql_migrations(engine, ORDERED_MIGRATION_FILES)
    yield engine
    teardown_end_customer_foundation_tables(engine)
    engine.dispose()


@pytest.fixture()
def db(pg_engine):
    session = sessionmaker(bind=pg_engine)()
    yield session
    session.close()


def _insert_job(db, tenant_id: str, job_id: str | None = None) -> str:
    job_id = job_id or _new_id()
    now = _utcnow()
    db.add(
        JobRecord(
            job_id=job_id,
            tenant_id=tenant_id,
            job_type="lead",
            status="pending",
            input_data={},
            result={},
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()
    return job_id


class TestTenantIsolation:
    def test_same_email_in_two_tenants(self, db):
        tenant_a = "TENANT_A"
        tenant_b = "TENANT_B"
        contact_a = EndCustomerRepository.create_contact(db, tenant_a, display_name="A")
        contact_b = EndCustomerRepository.create_contact(db, tenant_b, display_name="B")
        email = "shared@example.com"
        EndCustomerRepository.create_identity(
            db,
            CustomerIdentity(
                identity_id=_new_id(),
                tenant_id=tenant_a,
                owner_type=EntityOwnerType.CONTACT,
                owner_id=contact_a.contact_id,
                identity_type=IdentityType.EMAIL,
                raw_value=email,
                normalized_value=email,
                fact_state=FactState.PROPOSED,
                verification_status=VerificationStatus.PROPOSED,
            ),
        )
        EndCustomerRepository.create_identity(
            db,
            CustomerIdentity(
                identity_id=_new_id(),
                tenant_id=tenant_b,
                owner_type=EntityOwnerType.CONTACT,
                owner_id=contact_b.contact_id,
                identity_type=IdentityType.EMAIL,
                raw_value=email,
                normalized_value=email,
                fact_state=FactState.PROPOSED,
                verification_status=VerificationStatus.PROPOSED,
            ),
        )
        assert len(
            EndCustomerRepository.find_candidate_identities(db, tenant_a, IdentityType.EMAIL, email)
        ) == 1
        assert len(
            EndCustomerRepository.find_candidate_identities(db, tenant_b, IdentityType.EMAIL, email)
        ) == 1

    def test_cross_tenant_get_returns_none(self, db):
        customer = EndCustomerRepository.create_customer(
            db, "TENANT_A", CustomerType.PRIVATE, display_name="Private"
        )
        assert EndCustomerRepository.get_customer(db, "TENANT_B", customer.customer_id) is None

    def test_cross_tenant_update_raises_not_found(self, db):
        customer = EndCustomerRepository.create_customer(
            db, "TENANT_A", CustomerType.PRIVATE, display_name="Private"
        )
        with pytest.raises(EndCustomerNotFoundError):
            EndCustomerRepository.update_customer(
                db,
                "TENANT_B",
                customer.customer_id,
                expected_version=1,
                display_name="Hacked",
            )

    def test_cross_tenant_primary_company_blocked(self, db):
        company = EndCustomerRepository.create_company(db, "TENANT_A", "Legal", "Display")
        with pytest.raises(EndCustomerTenantScopeError):
            EndCustomerRepository.create_customer(
                db,
                "TENANT_B",
                CustomerType.COMPANY,
                display_name="Bad",
                primary_company_id=company.company_id,
            )

    def test_cross_tenant_job_link_blocked(self, db):
        customer = EndCustomerRepository.create_customer(
            db, "TENANT_A", CustomerType.PRIVATE, display_name="A"
        )
        job_id = _insert_job(db, "TENANT_B")
        with pytest.raises(EndCustomerTenantScopeError):
            EndCustomerRepository.create_job_link(
                db,
                "TENANT_A",
                customer.customer_id,
                job_id,
                LinkType.MANUAL,
                0.9,
                SourceType.USER_INPUT,
            )

    def test_duplicate_candidate_cross_tenant_blocked(self, db):
        a = EndCustomerRepository.create_customer(db, "TENANT_A", CustomerType.PRIVATE, "A")
        b = EndCustomerRepository.create_customer(db, "TENANT_B", CustomerType.PRIVATE, "B")
        with pytest.raises(EndCustomerTenantScopeError):
            EndCustomerRepository.create_duplicate_candidate(
                db, "TENANT_A", a.customer_id, b.customer_id, 0.8
            )


class TestConstraints:
    def test_job_link_confidence_out_of_range(self, db):
        customer = EndCustomerRepository.create_customer(
            db, "TENANT_A", CustomerType.PRIVATE, display_name="A"
        )
        job_id = _insert_job(db, "TENANT_A")
        with pytest.raises(Exception):
            EndCustomerRepository.create_job_link(
                db,
                "TENANT_A",
                customer.customer_id,
                job_id,
                LinkType.MANUAL,
                1.5,
                SourceType.USER_INPUT,
            )
            db.commit()

    def test_duplicate_self_pair_rejected(self, db):
        customer = EndCustomerRepository.create_customer(
            db, "TENANT_A", CustomerType.PRIVATE, display_name="A"
        )
        with pytest.raises(ValueError):
            EndCustomerRepository.create_duplicate_candidate(
                db, customer.tenant_id, customer.customer_id, customer.customer_id, 0.5
            )

    def test_duplicate_pair_canonicalized(self, db):
        a = EndCustomerRepository.create_customer(db, "TENANT_A", CustomerType.PRIVATE, "A")
        b = EndCustomerRepository.create_customer(db, "TENANT_A", CustomerType.PRIVATE, "B")
        left, right = sorted([a.customer_id, b.customer_id])
        cand1, created1 = EndCustomerRepository.create_duplicate_candidate(
            db, "TENANT_A", a.customer_id, b.customer_id, 0.7
        )
        cand2, created2 = EndCustomerRepository.create_duplicate_candidate(
            db, "TENANT_A", b.customer_id, a.customer_id, 0.7
        )
        assert created1 is True
        assert created2 is False
        assert cand1.candidate_id == cand2.candidate_id
        assert cand1.left_customer_id == left
        assert cand1.right_customer_id == right

    def test_source_fact_self_supersession_rejected(self, db):
        contact = EndCustomerRepository.create_contact(db, "TENANT_A", display_name="C")
        fact_id = _new_id()
        with pytest.raises(ValueError):
            EndCustomerRepository.append_fact(
                db,
                CustomerSourceFact(
                    fact_id=fact_id,
                    tenant_id="TENANT_A",
                    subject_type=EntityOwnerType.CONTACT,
                    subject_id=contact.contact_id,
                    field_name="email",
                    raw_value="a@b.com",
                    normalized_value="a@b.com",
                    fact_state=FactState.PROPOSED,
                    source_type=SourceType.USER_INPUT,
                    confidence=0.5,
                    recorded_at=_utcnow(),
                    supersedes_fact_id=fact_id,
                ),
            )

    def test_identity_duplicate_same_owner_rejected(self, db):
        contact = EndCustomerRepository.create_contact(db, "TENANT_A", display_name="C")
        identity = CustomerIdentity(
            identity_id=_new_id(),
            tenant_id="TENANT_A",
            owner_type=EntityOwnerType.CONTACT,
            owner_id=contact.contact_id,
            identity_type=IdentityType.EMAIL,
            raw_value="a@b.com",
            normalized_value="a@b.com",
            fact_state=FactState.PROPOSED,
            verification_status=VerificationStatus.PROPOSED,
        )
        EndCustomerRepository.create_identity(db, identity)
        duplicate = CustomerIdentity(
            identity_id=_new_id(),
            tenant_id="TENANT_A",
            owner_type=EntityOwnerType.CONTACT,
            owner_id=contact.contact_id,
            identity_type=IdentityType.EMAIL,
            raw_value="a@b.com",
            normalized_value="a@b.com",
            fact_state=FactState.PROPOSED,
            verification_status=VerificationStatus.PROPOSED,
        )
        with pytest.raises(EndCustomerDuplicateError):
            EndCustomerRepository.create_identity(db, duplicate)


class TestOptimisticLocking:
    def test_customer_update_increments_version(self, db):
        customer = EndCustomerRepository.create_customer(
            db, "TENANT_A", CustomerType.PRIVATE, display_name="A"
        )
        updated = EndCustomerRepository.update_customer(
            db,
            customer.tenant_id,
            customer.customer_id,
            expected_version=1,
            display_name="Updated",
        )
        assert updated.version == 2
        assert updated.display_name == "Updated"

    def test_stale_customer_version_conflict(self, db):
        customer = EndCustomerRepository.create_customer(
            db, "TENANT_A", CustomerType.PRIVATE, display_name="A"
        )
        EndCustomerRepository.update_customer(
            db, customer.tenant_id, customer.customer_id, expected_version=1, display_name="Once"
        )
        with pytest.raises(EndCustomerVersionConflictError):
            EndCustomerRepository.update_customer(
                db, customer.tenant_id, customer.customer_id, expected_version=1, display_name="Twice"
            )

    def test_missing_customer_not_found_not_version_conflict(self, db):
        with pytest.raises(EndCustomerNotFoundError):
            EndCustomerRepository.update_customer(
                db, "TENANT_A", _new_id(), expected_version=1, display_name="X"
            )

    def test_duplicate_candidate_version_conflict(self, db):
        a = EndCustomerRepository.create_customer(db, "TENANT_A", CustomerType.PRIVATE, "A")
        b = EndCustomerRepository.create_customer(db, "TENANT_A", CustomerType.PRIVATE, "B")
        cand, _ = EndCustomerRepository.create_duplicate_candidate(
            db, "TENANT_A", a.customer_id, b.customer_id, 0.6
        )
        EndCustomerRepository.update_duplicate_candidate_status(
            db, "TENANT_A", cand.candidate_id, expected_version=1, status=DuplicateStatus.REJECTED
        )
        with pytest.raises(EndCustomerVersionConflictError):
            EndCustomerRepository.update_duplicate_candidate_status(
                db, "TENANT_A", cand.candidate_id, expected_version=1, status=DuplicateStatus.REJECTED
            )


class TestAppendOnly:
    def test_repository_has_no_fact_update_delete(self):
        assert not hasattr(EndCustomerRepository, "update_fact")
        assert not hasattr(EndCustomerRepository, "delete_fact")
        assert not hasattr(EndCustomerRepository, "update_timeline_event")
        assert not hasattr(EndCustomerRepository, "delete_timeline_event")

    def test_append_fact_and_list(self, db):
        contact = EndCustomerRepository.create_contact(db, "TENANT_A", display_name="C")
        fact = CustomerSourceFact(
            fact_id=_new_id(),
            tenant_id="TENANT_A",
            subject_type=EntityOwnerType.CONTACT,
            subject_id=contact.contact_id,
            field_name="email",
            raw_value="a@b.com",
            normalized_value="a@b.com",
            fact_state=FactState.PROPOSED,
            source_type=SourceType.USER_INPUT,
            confidence=0.4,
            recorded_at=_utcnow(),
        )
        EndCustomerRepository.append_fact(db, fact)
        facts = EndCustomerRepository.list_facts_for_subject(
            db, "TENANT_A", EntityOwnerType.CONTACT, contact.contact_id
        )
        assert len(facts) == 1
        assert facts[0].fact_state == FactState.PROPOSED


class TestIdempotency:
    def test_job_link_idempotent(self, db):
        customer = EndCustomerRepository.create_customer(
            db, "TENANT_A", CustomerType.PRIVATE, display_name="A"
        )
        job_id = _insert_job(db, "TENANT_A")
        link1, created1 = EndCustomerRepository.create_job_link(
            db, "TENANT_A", customer.customer_id, job_id, LinkType.MANUAL, 0.9, SourceType.USER_INPUT
        )
        link2, created2 = EndCustomerRepository.create_job_link(
            db, "TENANT_A", customer.customer_id, job_id, LinkType.MANUAL, 0.9, SourceType.USER_INPUT
        )
        assert created1 is True
        assert created2 is False
        assert link1.link_id == link2.link_id

    def test_thread_link_idempotent(self, db):
        customer = EndCustomerRepository.create_customer(
            db, "TENANT_A", CustomerType.PRIVATE, display_name="A"
        )
        link1, created1 = EndCustomerRepository.create_thread_link(
            db,
            "TENANT_A",
            customer.customer_id,
            "google_mail",
            "acct-1",
            "thread-1",
            LinkType.MANUAL,
            0.8,
            SourceType.GMAIL_INBOUND,
        )
        link2, created2 = EndCustomerRepository.create_thread_link(
            db,
            "TENANT_A",
            customer.customer_id,
            "google_mail",
            "acct-1",
            "thread-1",
            LinkType.MANUAL,
            0.8,
            SourceType.GMAIL_INBOUND,
        )
        assert created1 is True
        assert created2 is False
        assert link1.link_id == link2.link_id

    def test_timeline_replay_idempotent(self, db):
        customer = EndCustomerRepository.create_customer(
            db, "TENANT_A", CustomerType.PRIVATE, display_name="A"
        )
        now = _utcnow()
        ref = SourceReference(
            reference_type=ReferenceType.JOB,
            reference_id="job-1",
            source_type=SourceType.GMAIL_INBOUND,
        )
        replay = build_timeline_replay_identity(
            "TENANT_A",
            customer.customer_id,
            TimelineEventType.JOB_CREATED,
            ref,
        )
        event = CustomerTimelineEvent(
            timeline_event_id=_new_id(),
            tenant_id="TENANT_A",
            customer_id=customer.customer_id,
            event_type=TimelineEventType.JOB_CREATED,
            occurred_at=now,
            recorded_at=now,
            summary="Job created",
            reference_type=ReferenceType.JOB,
            reference_id="job-1",
            source_type=SourceType.GMAIL_INBOUND,
        )
        ev1, created1 = EndCustomerRepository.append_timeline_event(
            db, event, replay.identity_key()
        )
        ev2, created2 = EndCustomerRepository.append_timeline_event(
            db, event, replay.identity_key()
        )
        assert created1 is True
        assert created2 is False
        assert ev1.timeline_event_id == ev2.timeline_event_id

    def test_timeline_replay_conflict_on_different_payload(self, db):
        customer = EndCustomerRepository.create_customer(
            db, "TENANT_A", CustomerType.PRIVATE, display_name="A"
        )
        now = _utcnow()
        ref = SourceReference(
            reference_type=ReferenceType.JOB,
            reference_id="job-1",
            source_type=SourceType.GMAIL_INBOUND,
        )
        replay = build_timeline_replay_identity(
            "TENANT_A",
            customer.customer_id,
            TimelineEventType.JOB_CREATED,
            ref,
        )
        event1 = CustomerTimelineEvent(
            timeline_event_id=_new_id(),
            tenant_id="TENANT_A",
            customer_id=customer.customer_id,
            event_type=TimelineEventType.JOB_CREATED,
            occurred_at=now,
            recorded_at=now,
            summary="First",
            reference_type=ReferenceType.JOB,
            reference_id="job-1",
        )
        EndCustomerRepository.append_timeline_event(db, event1, replay.identity_key())
        event2 = CustomerTimelineEvent(
            timeline_event_id=_new_id(),
            tenant_id="TENANT_A",
            customer_id=customer.customer_id,
            event_type=TimelineEventType.JOB_CREATED,
            occurred_at=now,
            recorded_at=now,
            summary="Different summary",
            reference_type=ReferenceType.JOB,
            reference_id="job-1",
        )
        with pytest.raises(EndCustomerIdempotencyConflictError):
            EndCustomerRepository.append_timeline_event(db, event2, replay.identity_key())


class TestMergeForbidden:
    def test_no_merge_methods_on_repository(self):
        assert not hasattr(EndCustomerRepository, "merge_customers")
        assert not hasattr(EndCustomerRepository, "execute_merge")

    def test_approve_merge_status_rejected(self, db):
        a = EndCustomerRepository.create_customer(db, "TENANT_A", CustomerType.PRIVATE, "A")
        b = EndCustomerRepository.create_customer(db, "TENANT_A", CustomerType.PRIVATE, "B")
        cand, _ = EndCustomerRepository.create_duplicate_candidate(
            db, "TENANT_A", a.customer_id, b.customer_id, 0.5
        )
        with pytest.raises(ValueError, match="merge execution is forbidden"):
            EndCustomerRepository.update_duplicate_candidate_status(
                db, "TENANT_A", cand.candidate_id, expected_version=1, status=DuplicateStatus.APPROVED
            )


class TestJobLinkRequiresTenantJob:
    def test_job_link_requires_existing_job(self, db):
        customer = EndCustomerRepository.create_customer(
            db, "TENANT_A", CustomerType.PRIVATE, display_name="A"
        )
        with pytest.raises(EndCustomerTenantScopeError):
            EndCustomerRepository.create_job_link(
                db,
                "TENANT_A",
                customer.customer_id,
                _new_id(),
                LinkType.MANUAL,
                0.5,
                SourceType.USER_INPUT,
            )

    def test_job_link_succeeds_with_tenant_job(self, db):
        customer = EndCustomerRepository.create_customer(
            db, "TENANT_A", CustomerType.PRIVATE, display_name="A"
        )
        job_id = _insert_job(db, "TENANT_A")
        link, created = EndCustomerRepository.create_job_link(
            db,
            "TENANT_A",
            customer.customer_id,
            job_id,
            LinkType.MANUAL,
            0.9,
            SourceType.USER_INPUT,
            created_by="operator-1",
        )
        assert created is True
        assert link.job_id == job_id


class TestTimelineOrdering:
    def test_timeline_deterministic_order(self, db):
        customer = EndCustomerRepository.create_customer(
            db, "TENANT_A", CustomerType.PRIVATE, display_name="A"
        )
        t1 = _utcnow()
        t2 = t1 + timedelta(seconds=1)
        for idx, occurred in enumerate([t1, t2]):
            ref = SourceReference(reference_type=ReferenceType.OTHER, reference_id=f"r{idx}")
            replay = build_timeline_replay_identity(
                "TENANT_A",
                customer.customer_id,
                TimelineEventType.NOTE_ADDED,
                ref,
            )
            EndCustomerRepository.append_timeline_event(
                db,
                CustomerTimelineEvent(
                    timeline_event_id=_new_id(),
                    tenant_id="TENANT_A",
                    customer_id=customer.customer_id,
                    event_type=TimelineEventType.NOTE_ADDED,
                    occurred_at=occurred,
                    recorded_at=occurred,
                    summary=f"Note {idx}",
                    reference_type=ReferenceType.OTHER,
                    reference_id=f"r{idx}",
                ),
                replay.identity_key(),
            )
        events = EndCustomerRepository.list_timeline_events(
            db, "TENANT_A", customer.customer_id
        )
        assert len(events) == 2
        assert events[0].occurred_at <= events[1].occurred_at
