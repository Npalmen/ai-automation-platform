"""PostgreSQL command service tests for operator-controlled writes."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.orm import sessionmaker

from app.domain.customer.api_schemas import (
    CreateCompanyEndCustomerRequest,
    CreatePrivateEndCustomerRequest,
    OperatorAddFactRequest,
    OperatorCreateCustomerRequest,
    OperatorCreateIdentityRequest,
    OperatorCreateJobLinkRequest,
    OperatorUpdateCustomerRequest,
    OperatorVerifyFactRequest,
)
from app.domain.customer.enums import (
    CustomerType,
    EntityOwnerType,
    FactState,
    IdentityType,
    LinkType,
    SourceType,
    VerificationStatus,
)
from app.repositories.postgres.end_customer_models import EndCustomerRecord
from app.repositories.postgres.end_customer_repository import (
    EndCustomerNotFoundError,
    EndCustomerRepository,
)
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.migration_runner import (
    ORDERED_MIGRATION_FILES,
    apply_pre_migration_baseline,
    apply_versioned_sql_migrations,
    reset_public_schema,
)
from app.services.end_customer_command_service import (
    EndCustomerCommandError,
    EndCustomerCommandService,
)
from tests.helpers.end_customer_pg import postgres_database_url, teardown_end_customer_foundation_tables


def _postgres_url() -> str:
    return postgres_database_url()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid4())


def _operator(role: str = "operations") -> dict[str, str]:
    return {"id": "operator-1", "display_name": "Operator", "role": role}


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


class TestAtomicCreate:
    def test_create_private_customer(self, db):
        request = OperatorCreateCustomerRequest(
            customer_type=CustomerType.PRIVATE,
            private=CreatePrivateEndCustomerRequest(
                display_name="Anna Svensson",
                email="anna@example.invalid",
            ),
            reason="Pilot onboarding",
        )
        status, body = EndCustomerCommandService.create_customer(
            db, "TENANT_A", _operator(), request, f"idem-{uuid4()}"
        )
        assert status == 201
        assert body["customer_type"] == "private"
        customer = EndCustomerRepository.get_customer(db, "TENANT_A", body["customer_id"])
        assert customer is not None

    def test_create_company_customer(self, db):
        request = OperatorCreateCustomerRequest(
            customer_type=CustomerType.COMPANY,
            company=CreateCompanyEndCustomerRequest(
                company_legal_name="Acme AB",
                primary_contact_display_name="Contact Person",
                organization_number="556677-8899",
            ),
            reason="Pilot company",
        )
        status, body = EndCustomerCommandService.create_customer(
            db, "TENANT_B", _operator(), request, f"idem-{uuid4()}"
        )
        assert status == 201
        assert body["primary_company_id"] is not None

    def test_idempotent_replay_no_second_customer(self, db):
        request = OperatorCreateCustomerRequest(
            customer_type=CustomerType.PRIVATE,
            private=CreatePrivateEndCustomerRequest(display_name="Replay Customer"),
            reason="Replay test",
        )
        key = f"idem-replay-{uuid4()}"
        count_before = db.query(EndCustomerRecord).filter_by(tenant_id="TENANT_A").count()
        status1, body1 = EndCustomerCommandService.create_customer(
            db, "TENANT_A", _operator(), request, key
        )
        count_after_first = db.query(EndCustomerRecord).filter_by(tenant_id="TENANT_A").count()
        status2, body2 = EndCustomerCommandService.create_customer(
            db, "TENANT_A", _operator(), request, key
        )
        count_after_second = db.query(EndCustomerRecord).filter_by(tenant_id="TENANT_A").count()
        assert status1 == status2 == 201
        assert body1 == body2
        assert count_after_first == count_before + 1
        assert count_after_second == count_after_first


class TestAggregateOwnership:
    def test_fact_for_other_customer_company_blocked(self, db):
        customer_a = EndCustomerRepository.create_customer(
            db, "TENANT_A", CustomerType.COMPANY, "Company A"
        )
        company = EndCustomerRepository.create_company(db, "TENANT_A", "Other Co", "Other Co")
        customer_b = EndCustomerRepository.create_customer(
            db,
            "TENANT_A",
            CustomerType.COMPANY,
            "Company B",
            primary_company_id=company.company_id,
        )
        request = OperatorAddFactRequest(
            subject_type=EntityOwnerType.COMPANY,
            subject_id=company.company_id,
            field_name="note",
            raw_value="blocked",
            confidence=1.0,
            reason="Should fail",
        )
        with pytest.raises(EndCustomerNotFoundError):
            EndCustomerCommandService.add_fact(
                db,
                "TENANT_A",
                customer_a.customer_id,
                _operator(),
                request,
                f"idem-{uuid4()}",
            )


class TestIdentityCollision:
    def test_cross_owner_same_tenant_blocked(self, db):
        contact_a = EndCustomerRepository.create_contact(db, "TENANT_A", display_name="A")
        contact_b = EndCustomerRepository.create_contact(db, "TENANT_A", display_name="B")
        customer_a = EndCustomerRepository.create_customer(
            db,
            "TENANT_A",
            CustomerType.PRIVATE,
            "Customer A",
            primary_contact_id=contact_a.contact_id,
        )
        customer_b = EndCustomerRepository.create_customer(
            db,
            "TENANT_A",
            CustomerType.PRIVATE,
            "Customer B",
            primary_contact_id=contact_b.contact_id,
        )
        email = "shared@example.invalid"
        request = OperatorCreateIdentityRequest(
            owner_type=EntityOwnerType.CONTACT,
            owner_id=contact_a.contact_id,
            identity_type=IdentityType.EMAIL,
            raw_value=email,
            reason="first",
        )
        EndCustomerCommandService.create_identity(
            db,
            "TENANT_A",
            customer_a.customer_id,
            _operator(),
            request,
            f"idem-{uuid4()}",
        )
        conflict_request = OperatorCreateIdentityRequest(
            owner_type=EntityOwnerType.CONTACT,
            owner_id=contact_b.contact_id,
            identity_type=IdentityType.EMAIL,
            raw_value=email,
            reason="second",
        )
        with pytest.raises(EndCustomerCommandError) as exc:
            EndCustomerCommandService.create_identity(
                db,
                "TENANT_A",
                customer_b.customer_id,
                _operator(),
                conflict_request,
                f"idem-{uuid4()}",
            )
        assert exc.value.code == "IDENTITY_COLLISION_REVIEW_REQUIRED"


class TestCustomerUpdate:
    def test_stale_version_conflict(self, db):
        customer = EndCustomerRepository.create_customer(
            db, "TENANT_A", CustomerType.PRIVATE, "Stale Test"
        )
        request = OperatorUpdateCustomerRequest(
            expected_version=99,
            reason="stale",
            display_name="New Name",
        )
        with pytest.raises(EndCustomerCommandError) as exc:
            EndCustomerCommandService.update_customer(
                db,
                "TENANT_A",
                customer.customer_id,
                _operator(),
                request,
                f"idem-{uuid4()}",
            )
        assert exc.value.code == "CUSTOMER_VERSION_CONFLICT"


class TestJobLink:
    def test_job_link_and_timeline(self, db):
        customer = EndCustomerRepository.create_customer(
            db, "TENANT_A", CustomerType.PRIVATE, "Job Link"
        )
        job_id = _insert_job(db, "TENANT_A")
        request = OperatorCreateJobLinkRequest(
            job_id=job_id,
            link_type=LinkType.MANUAL,
            reason="manual link",
        )
        status, body = EndCustomerCommandService.create_job_link(
            db,
            "TENANT_A",
            customer.customer_id,
            _operator(),
            request,
            f"idem-{uuid4()}",
        )
        assert status == 201
        events = EndCustomerRepository.list_timeline_events(
            db, "TENANT_A", customer.customer_id
        )
        assert any(e.event_type.value == "job_linked" for e in events)
