"""Tests for EndCustomerReadService projections and search."""

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
    MatchConflictCode,
    MatchEvidenceCode,
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
from app.repositories.postgres.end_customer_models import EndCustomerJobLinkRecord
from app.repositories.postgres.end_customer_repository import EndCustomerRepository
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.migration_runner import (
    ORDERED_MIGRATION_FILES,
    apply_pre_migration_baseline,
    apply_versioned_sql_migrations,
    reset_public_schema,
)
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
from app.services.end_customer_read_service import (
    EndCustomerReadService,
    EndCustomerReadValidationError,
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
    TenantConfigRepository.upsert(session, tenant_id="TENANT_A", name="Tenant A", slug="tenant-a")
    TenantConfigRepository.upsert(session, tenant_id="TENANT_B", name="Tenant B", slug="tenant-b")
    session.commit()
    yield session
    session.close()


def _insert_job(db, tenant_id: str, job_id: str | None = None, status: str = "pending") -> str:
    job_id = job_id or _new_id()
    now = _utcnow()
    db.add(
        JobRecord(
            job_id=job_id,
            tenant_id=tenant_id,
            job_type="lead",
            status=status,
            input_data={"body": "secret"},
            result={"payload": "secret"},
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()
    return job_id


class TestReadServiceProjection:
    def test_list_customers_tenant_scoped(self, db):
        EndCustomerRepository.create_customer(
            db, "TENANT_A", CustomerType.PRIVATE, display_name="Alpha"
        )
        EndCustomerRepository.create_customer(
            db, "TENANT_B", CustomerType.PRIVATE, display_name="Beta"
        )
        result = EndCustomerReadService.list_customers(db, "TENANT_A")
        assert result.total == 1
        assert result.items[0].display_name == "Alpha"

    def test_customer_card_detail_projection(self, db):
        company = EndCustomerRepository.create_company(
            db, "TENANT_A", legal_name="Acme AB", display_name="Acme"
        )
        contact = EndCustomerRepository.create_contact(db, "TENANT_A", display_name="Jane")
        customer = EndCustomerRepository.create_customer(
            db,
            "TENANT_A",
            CustomerType.COMPANY,
            display_name="Acme",
            primary_company_id=company.company_id,
            primary_contact_id=contact.contact_id,
        )
        EndCustomerRepository.create_identity(
            db,
            CustomerIdentity(
                identity_id=_new_id(),
                tenant_id="TENANT_A",
                owner_type=EntityOwnerType.CONTACT,
                owner_id=contact.contact_id,
                identity_type=IdentityType.EMAIL,
                raw_value="jane@example.com",
                normalized_value="jane@example.com",
                fact_state=FactState.VERIFIED,
                verification_status=VerificationStatus.VERIFIED,
            ),
        )
        card = EndCustomerReadService.get_customer_card(
            db, "TENANT_A", customer.customer_id
        )
        assert card is not None
        assert card.card.display_name == "Acme"
        assert card.card.primary_contact is not None
        assert card.card.primary_contact.email == "jane@example.com"
        assert any(i.identity_type == IdentityType.EMAIL for i in card.identities)
        assert all(
            i.identity_type not in {IdentityType.GMAIL_THREAD, IdentityType.EXTERNAL_ID}
            for i in card.identities
        )

    def test_duplicate_sanitization(self, db):
        a = EndCustomerRepository.create_customer(db, "TENANT_A", CustomerType.PRIVATE, "A")
        b = EndCustomerRepository.create_customer(db, "TENANT_A", CustomerType.PRIVATE, "B")
        EndCustomerRepository.create_duplicate_candidate(
            db,
            "TENANT_A",
            a.customer_id,
            b.customer_id,
            0.8,
            evidence=[
                {
                    "code": MatchEvidenceCode.NORMALIZED_EMAIL.value,
                    "score": 0.9,
                    "left_value": "a@example.com",
                    "right_value": "a@example.com",
                    "extra": "forbidden",
                }
            ],
            conflicts=[
                {
                    "code": MatchConflictCode.PERSON_VS_COMPANY.value,
                    "detail": "types differ",
                    "raw_payload": "secret",
                }
            ],
        )
        result = EndCustomerReadService.list_duplicates(db, "TENANT_A")
        assert result.total == 1
        item = result.items[0]
        assert item.evidence[0].code == MatchEvidenceCode.NORMALIZED_EMAIL
        assert item.conflicts[0].code == MatchConflictCode.PERSON_VS_COMPANY
        assert "raw_payload" not in item.conflicts[0].model_dump()

    def test_timeline_metadata_sanitized(self, db):
        customer = EndCustomerRepository.create_customer(
            db, "TENANT_A", CustomerType.PRIVATE, display_name="T"
        )
        now = _utcnow()
        source_ref = SourceReference(
            reference_type=ReferenceType.JOB,
            reference_id=_new_id(),
            source_type=SourceType.MANUAL,
        )
        replay = build_timeline_replay_identity(
            "TENANT_A",
            customer.customer_id,
            TimelineEventType.NOTE_ADDED,
            source_ref,
        )
        event = CustomerTimelineEvent(
            timeline_event_id=_new_id(),
            tenant_id="TENANT_A",
            customer_id=customer.customer_id,
            event_type=TimelineEventType.NOTE_ADDED,
            occurred_at=now,
            recorded_at=now,
            summary="created",
            metadata={"reason_code": "manual_create"},
        )
        EndCustomerRepository.append_timeline_event(
            db, event, replay_identity_key=replay.identity_key()
        )
        later = now + timedelta(minutes=1)
        replay2 = build_timeline_replay_identity(
            "TENANT_A",
            customer.customer_id,
            TimelineEventType.JOB_CREATED,
            source_ref,
        )
        event2 = CustomerTimelineEvent(
            timeline_event_id=_new_id(),
            tenant_id="TENANT_A",
            customer_id=customer.customer_id,
            event_type=TimelineEventType.JOB_CREATED,
            occurred_at=later,
            recorded_at=later,
            summary="linked",
            metadata={"link_type": "primary"},
        )
        EndCustomerRepository.append_timeline_event(
            db, event2, replay_identity_key=replay2.identity_key()
        )
        timeline = EndCustomerReadService.list_timeline(
            db, "TENANT_A", customer.customer_id, limit=10, offset=0
        )
        assert timeline is not None
        assert timeline.total == 2
        assert timeline.items[0].event_type == TimelineEventType.JOB_CREATED

    def test_job_hydration_stale_link(self, db):
        customer = EndCustomerRepository.create_customer(
            db, "TENANT_A", CustomerType.PRIVATE, display_name="T"
        )
        existing_job = _insert_job(db, "TENANT_A")
        EndCustomerRepository.create_job_link(
            db,
            "TENANT_A",
            customer.customer_id,
            existing_job,
            LinkType.PRIMARY,
            1.0,
            SourceType.MANUAL,
        )
        missing_job = _new_id()
        db.add(
            EndCustomerJobLinkRecord(
                link_id=_new_id(),
                tenant_id="TENANT_A",
                customer_id=customer.customer_id,
                job_id=missing_job,
                link_type=LinkType.RELATED.value,
                confidence=0.5,
                source_type=SourceType.MANUAL.value,
                created_at=_utcnow(),
                created_by=None,
            )
        )
        db.commit()
        jobs = EndCustomerReadService.list_jobs(db, "TENANT_A", customer.customer_id)
        assert jobs is not None
        assert jobs.total == 2
        by_job = {item.job_id: item for item in jobs.items}
        assert by_job[existing_job].job_exists is True
        assert by_job[existing_job].job_summary is not None
        assert by_job[existing_job].job_summary.job_type == "lead"
        assert by_job[missing_job].job_exists is False
        assert by_job[missing_job].job_summary is None

    def test_search_exact_identity_and_prefix_deduped(self, db):
        customer = EndCustomerRepository.create_customer(
            db, "TENANT_A", CustomerType.PRIVATE, display_name="anna@example.com"
        )
        contact = EndCustomerRepository.create_contact(db, "TENANT_A", display_name="Anna")
        EndCustomerRepository.update_customer(
            db,
            "TENANT_A",
            customer.customer_id,
            expected_version=1,
            primary_contact_id=contact.contact_id,
        )
        EndCustomerRepository.create_identity(
            db,
            CustomerIdentity(
                identity_id=_new_id(),
                tenant_id="TENANT_A",
                owner_type=EntityOwnerType.CONTACT,
                owner_id=contact.contact_id,
                identity_type=IdentityType.EMAIL,
                raw_value="anna@example.com",
                normalized_value="anna@example.com",
                fact_state=FactState.VERIFIED,
                verification_status=VerificationStatus.VERIFIED,
            ),
        )
        result = EndCustomerReadService.search(db, "TENANT_A", "anna@example.com")
        assert result.total == 1
        assert result.items[0].customer_id == customer.customer_id

    def test_search_wildcard_escaped(self, db):
        EndCustomerRepository.create_customer(
            db, "TENANT_A", CustomerType.PRIVATE, display_name="100% off"
        )
        EndCustomerRepository.create_customer(
            db, "TENANT_A", CustomerType.PRIVATE, display_name="100X off"
        )
        result = EndCustomerReadService.search(db, "TENANT_A", "100%")
        assert result.total == 1
        assert result.items[0].display_name == "100% off"

    def test_search_tenant_isolation(self, db):
        contact_a = EndCustomerRepository.create_contact(db, "TENANT_A", display_name="A")
        contact_b = EndCustomerRepository.create_contact(db, "TENANT_B", display_name="B")
        email = "shared@example.com"
        EndCustomerRepository.create_identity(
            db,
            CustomerIdentity(
                identity_id=_new_id(),
                tenant_id="TENANT_A",
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
                tenant_id="TENANT_B",
                owner_type=EntityOwnerType.CONTACT,
                owner_id=contact_b.contact_id,
                identity_type=IdentityType.EMAIL,
                raw_value=email,
                normalized_value=email,
                fact_state=FactState.PROPOSED,
                verification_status=VerificationStatus.PROPOSED,
            ),
        )
        result_a = EndCustomerReadService.search(db, "TENANT_A", email)
        result_b = EndCustomerReadService.search(db, "TENANT_B", email)
        assert result_a.total == 1
        assert result_b.total == 1
        assert result_a.items[0].customer_id != result_b.items[0].customer_id

    def test_invalid_sort_raises(self, db):
        with pytest.raises(EndCustomerReadValidationError) as exc:
            EndCustomerReadService.list_customers(db, "TENANT_A", sort="invalid")
        assert exc.value.code == "INVALID_SORT"

    def test_short_search_query_raises(self, db):
        with pytest.raises(EndCustomerReadValidationError) as exc:
            EndCustomerReadService.search(db, "TENANT_A", "a")
        assert exc.value.code == "INVALID_SEARCH_QUERY"
