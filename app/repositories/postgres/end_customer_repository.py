"""Tenant-scoped persistence for the end-customer domain — no API or workflow wiring."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

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
from app.domain.customer.provenance import timeline_sort_key
from app.domain.customer.schemas import (
    Company,
    Contact,
    Customer,
    CustomerDuplicateCandidate,
    CustomerIdentity,
    CustomerJobLink,
    CustomerRelationship,
    CustomerSourceFact,
    CustomerThreadLink,
    CustomerTimelineEvent,
    SourceReference,
)
from app.repositories.postgres.end_customer_models import (
    EndCustomerCompanyRecord,
    EndCustomerContactRecord,
    EndCustomerDuplicateCandidateRecord,
    EndCustomerIdentityRecord,
    EndCustomerJobLinkRecord,
    EndCustomerRecord,
    EndCustomerRelationshipRecord,
    EndCustomerSourceFactRecord,
    EndCustomerThreadLinkRecord,
    EndCustomerTimelineEventRecord,
)
from app.repositories.postgres.job_models import JobRecord


class EndCustomerNotFoundError(Exception):
    """Record does not exist within the tenant scope."""


class EndCustomerVersionConflictError(Exception):
    """Optimistic locking failure — expected version does not match."""


class EndCustomerTenantScopeError(Exception):
    """Tenant boundary violation or cross-tenant reference."""


class EndCustomerDuplicateError(Exception):
    """Duplicate record or canonical pair already exists."""


class EndCustomerIdempotencyConflictError(Exception):
    """Same idempotency key used with incompatible payload."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid4())


def _canonical_pair(left: str, right: str) -> tuple[str, str]:
    if left == right:
        raise ValueError("duplicate candidate pair must not reference the same customer")
    return (left, right) if left < right else (right, left)


class EndCustomerRepository:
    # --- mapping helpers ---

    @staticmethod
    def _to_company(record: EndCustomerCompanyRecord) -> Company:
        return Company(
            company_id=record.company_id,
            tenant_id=record.tenant_id,
            legal_name=record.legal_name,
            display_name=record.display_name,
            status=CustomerStatus(record.status),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _to_contact(record: EndCustomerContactRecord) -> Contact:
        return Contact(
            contact_id=record.contact_id,
            tenant_id=record.tenant_id,
            given_name=record.given_name,
            family_name=record.family_name,
            display_name=record.display_name,
            title=record.title,
            status=CustomerStatus(record.status),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _to_customer(record: EndCustomerRecord) -> Customer:
        return Customer(
            customer_id=record.customer_id,
            tenant_id=record.tenant_id,
            customer_type=CustomerType(record.customer_type),
            status=CustomerStatus(record.status),
            display_name=record.display_name,
            primary_company_id=record.primary_company_id,
            primary_contact_id=record.primary_contact_id,
            version=record.version,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _source_ref_from_json(data: dict | None) -> SourceReference | None:
        if not data:
            return None
        return SourceReference(
            reference_type=ReferenceType(data["reference_type"]),
            reference_id=data["reference_id"],
            source_type=SourceType(data["source_type"]) if data.get("source_type") else None,
            label=data.get("label"),
        )

    @staticmethod
    def _source_ref_to_json(ref: SourceReference | None) -> dict | None:
        if ref is None:
            return None
        payload: dict[str, Any] = {
            "reference_type": ref.reference_type.value,
            "reference_id": ref.reference_id,
        }
        if ref.source_type is not None:
            payload["source_type"] = ref.source_type.value
        if ref.label is not None:
            payload["label"] = ref.label
        return payload

    @staticmethod
    def _to_source_fact(record: EndCustomerSourceFactRecord) -> CustomerSourceFact:
        return CustomerSourceFact(
            fact_id=record.fact_id,
            tenant_id=record.tenant_id,
            subject_type=EntityOwnerType(record.subject_type),
            subject_id=record.subject_id,
            field_name=record.field_name,
            raw_value=record.raw_value,
            normalized_value=record.normalized_value,
            fact_state=FactState(record.fact_state),
            source_type=SourceType(record.source_type),
            source_reference=EndCustomerRepository._source_ref_from_json(record.source_reference),
            source_actor=record.source_actor,
            confidence=record.confidence,
            observed_at=record.observed_at,
            recorded_at=record.recorded_at,
            verified_at=record.verified_at,
            verified_by=record.verified_by,
            supersedes_fact_id=record.supersedes_fact_id,
            conflicts_with_fact_ids=list(record.conflicts_with_fact_ids or []),
        )

    @staticmethod
    def _to_identity(record: EndCustomerIdentityRecord) -> CustomerIdentity:
        return CustomerIdentity(
            identity_id=record.identity_id,
            tenant_id=record.tenant_id,
            owner_type=EntityOwnerType(record.owner_type),
            owner_id=record.owner_id,
            identity_type=IdentityType(record.identity_type),
            raw_value=record.raw_value,
            normalized_value=record.normalized_value,
            fact_state=FactState(record.fact_state),
            verification_status=VerificationStatus(record.verification_status),
            source_fact_id=record.source_fact_id,
            first_seen_at=record.first_seen_at,
            last_seen_at=record.last_seen_at,
        )

    @staticmethod
    def _to_relationship(record: EndCustomerRelationshipRecord) -> CustomerRelationship:
        return CustomerRelationship(
            relationship_id=record.relationship_id,
            tenant_id=record.tenant_id,
            customer_id=record.customer_id,
            subject_type=EntityOwnerType(record.subject_type),
            subject_id=record.subject_id,
            relationship_type=RelationshipType(record.relationship_type),
            is_primary=record.is_primary,
            valid_from=record.valid_from,
            valid_to=record.valid_to,
        )

    @staticmethod
    def _to_job_link(record: EndCustomerJobLinkRecord) -> CustomerJobLink:
        return CustomerJobLink(
            link_id=record.link_id,
            tenant_id=record.tenant_id,
            customer_id=record.customer_id,
            job_id=record.job_id,
            link_type=LinkType(record.link_type),
            confidence=record.confidence,
            source_type=SourceType(record.source_type),
            created_at=record.created_at,
            created_by=record.created_by,
        )

    @staticmethod
    def _to_thread_link(record: EndCustomerThreadLinkRecord) -> CustomerThreadLink:
        return CustomerThreadLink(
            link_id=record.link_id,
            tenant_id=record.tenant_id,
            customer_id=record.customer_id,
            integration_type=record.integration_type,
            integration_account_reference=record.integration_account_reference,
            thread_id=record.thread_id,
            link_type=LinkType(record.link_type),
            confidence=record.confidence,
            source_type=SourceType(record.source_type),
            created_at=record.created_at,
        )

    @staticmethod
    def _to_timeline_event(record: EndCustomerTimelineEventRecord) -> CustomerTimelineEvent:
        return CustomerTimelineEvent(
            timeline_event_id=record.timeline_event_id,
            tenant_id=record.tenant_id,
            customer_id=record.customer_id,
            event_type=TimelineEventType(record.event_type),
            occurred_at=record.occurred_at,
            recorded_at=record.recorded_at,
            actor_type=record.actor_type,
            actor_id=record.actor_id,
            source_type=SourceType(record.source_type) if record.source_type else None,
            reference_type=ReferenceType(record.reference_type) if record.reference_type else None,
            reference_id=record.reference_id,
            summary=record.summary,
            metadata=dict(record.metadata_json or {}),
        )

    @staticmethod
    def _to_duplicate_candidate(record: EndCustomerDuplicateCandidateRecord) -> CustomerDuplicateCandidate:
        return CustomerDuplicateCandidate(
            candidate_id=record.candidate_id,
            tenant_id=record.tenant_id,
            left_customer_id=record.left_customer_id,
            right_customer_id=record.right_customer_id,
            status=DuplicateStatus(record.status),
            confidence=record.confidence,
            evidence=list(record.evidence or []),
            conflicts=list(record.conflicts or []),
            created_at=record.created_at,
            updated_at=record.updated_at,
            version=record.version,
        )

    # --- tenant validation ---

    @staticmethod
    def _get_customer_record(db: Session, tenant_id: str, customer_id: str) -> EndCustomerRecord | None:
        return (
            db.query(EndCustomerRecord)
            .filter_by(tenant_id=tenant_id, customer_id=customer_id)
            .first()
        )

    @staticmethod
    def _validate_subject_exists(
        db: Session,
        tenant_id: str,
        subject_type: EntityOwnerType,
        subject_id: str,
    ) -> None:
        if subject_type == EntityOwnerType.CUSTOMER:
            if EndCustomerRepository._get_customer_record(db, tenant_id, subject_id) is None:
                raise EndCustomerTenantScopeError("customer subject not found in tenant")
            return
        if subject_type == EntityOwnerType.COMPANY:
            if (
                db.query(EndCustomerCompanyRecord)
                .filter_by(tenant_id=tenant_id, company_id=subject_id)
                .first()
                is None
            ):
                raise EndCustomerTenantScopeError("company subject not found in tenant")
            return
        if subject_type == EntityOwnerType.CONTACT:
            if (
                db.query(EndCustomerContactRecord)
                .filter_by(tenant_id=tenant_id, contact_id=subject_id)
                .first()
                is None
            ):
                raise EndCustomerTenantScopeError("contact subject not found in tenant")
            return
        raise EndCustomerTenantScopeError(f"unsupported subject_type: {subject_type.value}")

    @staticmethod
    def _validate_primary_refs(
        db: Session,
        tenant_id: str,
        primary_company_id: str | None,
        primary_contact_id: str | None,
    ) -> None:
        if primary_company_id is not None:
            if (
                db.query(EndCustomerCompanyRecord)
                .filter_by(tenant_id=tenant_id, company_id=primary_company_id)
                .first()
                is None
            ):
                raise EndCustomerTenantScopeError("primary_company_id not found in tenant")
        if primary_contact_id is not None:
            if (
                db.query(EndCustomerContactRecord)
                .filter_by(tenant_id=tenant_id, contact_id=primary_contact_id)
                .first()
                is None
            ):
                raise EndCustomerTenantScopeError("primary_contact_id not found in tenant")

    @staticmethod
    def _job_exists_in_tenant(db: Session, tenant_id: str, job_id: str) -> bool:
        return (
            db.query(JobRecord)
            .filter_by(tenant_id=tenant_id, job_id=job_id)
            .first()
            is not None
        )

    # --- company / contact ---

    @staticmethod
    def create_company(
        db: Session,
        tenant_id: str,
        legal_name: str,
        display_name: str,
        status: CustomerStatus = CustomerStatus.ACTIVE,
        *,
        commit: bool = True,
    ) -> Company:
        now = _utcnow()
        record = EndCustomerCompanyRecord(
            company_id=_new_id(),
            tenant_id=tenant_id,
            legal_name=legal_name,
            display_name=display_name,
            status=status.value,
            created_at=now,
            updated_at=now,
        )
        db.add(record)
        if commit:
            db.commit()
        else:
            db.flush()
        db.refresh(record)
        return EndCustomerRepository._to_company(record)

    @staticmethod
    def get_company(db: Session, tenant_id: str, company_id: str) -> Company | None:
        record = (
            db.query(EndCustomerCompanyRecord)
            .filter_by(tenant_id=tenant_id, company_id=company_id)
            .first()
        )
        if record is None:
            return None
        return EndCustomerRepository._to_company(record)

    @staticmethod
    def create_contact(
        db: Session,
        tenant_id: str,
        display_name: str,
        given_name: str | None = None,
        family_name: str | None = None,
        title: str | None = None,
        status: CustomerStatus = CustomerStatus.ACTIVE,
        *,
        commit: bool = True,
    ) -> Contact:
        now = _utcnow()
        record = EndCustomerContactRecord(
            contact_id=_new_id(),
            tenant_id=tenant_id,
            given_name=given_name,
            family_name=family_name,
            display_name=display_name,
            title=title,
            status=status.value,
            created_at=now,
            updated_at=now,
        )
        db.add(record)
        if commit:
            db.commit()
        else:
            db.flush()
        db.refresh(record)
        return EndCustomerRepository._to_contact(record)

    @staticmethod
    def get_contact(db: Session, tenant_id: str, contact_id: str) -> Contact | None:
        record = (
            db.query(EndCustomerContactRecord)
            .filter_by(tenant_id=tenant_id, contact_id=contact_id)
            .first()
        )
        if record is None:
            return None
        return EndCustomerRepository._to_contact(record)

    # --- customer ---

    @staticmethod
    def create_customer(
        db: Session,
        tenant_id: str,
        customer_type: CustomerType,
        display_name: str,
        status: CustomerStatus = CustomerStatus.ACTIVE,
        primary_company_id: str | None = None,
        primary_contact_id: str | None = None,
        *,
        commit: bool = True,
    ) -> Customer:
        EndCustomerRepository._validate_primary_refs(
            db, tenant_id, primary_company_id, primary_contact_id
        )
        now = _utcnow()
        record = EndCustomerRecord(
            customer_id=_new_id(),
            tenant_id=tenant_id,
            customer_type=customer_type.value,
            status=status.value,
            display_name=display_name,
            primary_company_id=primary_company_id,
            primary_contact_id=primary_contact_id,
            version=1,
            created_at=now,
            updated_at=now,
        )
        db.add(record)
        if commit:
            db.commit()
        else:
            db.flush()
        db.refresh(record)
        return EndCustomerRepository._to_customer(record)

    @staticmethod
    def get_customer(db: Session, tenant_id: str, customer_id: str) -> Customer | None:
        record = EndCustomerRepository._get_customer_record(db, tenant_id, customer_id)
        if record is None:
            return None
        return EndCustomerRepository._to_customer(record)

    @staticmethod
    def update_customer(
        db: Session,
        tenant_id: str,
        customer_id: str,
        expected_version: int,
        *,
        display_name: str | None = None,
        status: CustomerStatus | None = None,
        primary_company_id: str | None = None,
        primary_contact_id: str | None = None,
        clear_primary_company: bool = False,
        clear_primary_contact: bool = False,
        commit: bool = True,
    ) -> Customer:
        if expected_version < 1:
            raise ValueError("expected_version must be >= 1")

        new_company_id = None if clear_primary_company else primary_company_id
        new_contact_id = None if clear_primary_contact else primary_contact_id
        if not clear_primary_company and primary_company_id is not None:
            new_company_id = primary_company_id
        if not clear_primary_contact and primary_contact_id is not None:
            new_contact_id = primary_contact_id

        existing = EndCustomerRepository._get_customer_record(db, tenant_id, customer_id)
        if existing is None:
            raise EndCustomerNotFoundError("customer not found")

        final_company = new_company_id if new_company_id is not None else existing.primary_company_id
        final_contact = new_contact_id if new_contact_id is not None else existing.primary_contact_id
        EndCustomerRepository._validate_primary_refs(db, tenant_id, final_company, final_contact)

        values: dict[str, Any] = {"version": expected_version + 1, "updated_at": _utcnow()}
        if display_name is not None:
            values["display_name"] = display_name
        if status is not None:
            values["status"] = status.value
        if clear_primary_company or primary_company_id is not None:
            values["primary_company_id"] = new_company_id
        if clear_primary_contact or primary_contact_id is not None:
            values["primary_contact_id"] = new_contact_id

        result = db.execute(
            update(EndCustomerRecord)
            .where(
                EndCustomerRecord.tenant_id == tenant_id,
                EndCustomerRecord.customer_id == customer_id,
                EndCustomerRecord.version == expected_version,
            )
            .values(**values)
        )
        if result.rowcount == 0:
            if EndCustomerRepository._get_customer_record(db, tenant_id, customer_id) is None:
                raise EndCustomerNotFoundError("customer not found")
            raise EndCustomerVersionConflictError("stale customer version")

        if commit:
            db.commit()
        else:
            db.flush()

        record = EndCustomerRepository._get_customer_record(db, tenant_id, customer_id)
        assert record is not None
        return EndCustomerRepository._to_customer(record)

    # --- relationships ---

    @staticmethod
    def create_relationship(
        db: Session,
        tenant_id: str,
        customer_id: str,
        subject_type: EntityOwnerType,
        subject_id: str,
        relationship_type: RelationshipType,
        is_primary: bool = False,
        valid_from: datetime | None = None,
        valid_to: datetime | None = None,
        *,
        commit: bool = True,
    ) -> CustomerRelationship:
        if EndCustomerRepository._get_customer_record(db, tenant_id, customer_id) is None:
            raise EndCustomerNotFoundError("customer not found")
        EndCustomerRepository._validate_subject_exists(db, tenant_id, subject_type, subject_id)

        record = EndCustomerRelationshipRecord(
            relationship_id=_new_id(),
            tenant_id=tenant_id,
            customer_id=customer_id,
            subject_type=subject_type.value,
            subject_id=subject_id,
            relationship_type=relationship_type.value,
            is_primary=is_primary,
            valid_from=valid_from,
            valid_to=valid_to,
        )
        db.add(record)
        if commit:
            db.commit()
        else:
            db.flush()
        db.refresh(record)
        return EndCustomerRepository._to_relationship(record)

    # --- source facts (append-only) ---

    @staticmethod
    def append_fact(
        db: Session,
        fact: CustomerSourceFact,
        *,
        commit: bool = True,
    ) -> CustomerSourceFact:
        if fact.supersedes_fact_id and fact.supersedes_fact_id == fact.fact_id:
            raise ValueError("supersedes_fact_id cannot reference self")

        EndCustomerRepository._validate_subject_exists(
            db, fact.tenant_id, fact.subject_type, fact.subject_id
        )
        if fact.supersedes_fact_id:
            prior = (
                db.query(EndCustomerSourceFactRecord)
                .filter_by(tenant_id=fact.tenant_id, fact_id=fact.supersedes_fact_id)
                .first()
            )
            if prior is None:
                raise EndCustomerTenantScopeError("supersedes_fact_id not found in tenant")

        record = EndCustomerSourceFactRecord(
            fact_id=fact.fact_id,
            tenant_id=fact.tenant_id,
            subject_type=fact.subject_type.value,
            subject_id=fact.subject_id,
            field_name=fact.field_name,
            raw_value=fact.raw_value,
            normalized_value=fact.normalized_value,
            fact_state=fact.fact_state.value,
            source_type=fact.source_type.value,
            source_reference=EndCustomerRepository._source_ref_to_json(fact.source_reference),
            source_actor=fact.source_actor,
            confidence=fact.confidence,
            observed_at=fact.observed_at,
            recorded_at=fact.recorded_at,
            verified_at=fact.verified_at,
            verified_by=fact.verified_by,
            supersedes_fact_id=fact.supersedes_fact_id,
            conflicts_with_fact_ids=list(fact.conflicts_with_fact_ids),
        )
        db.add(record)
        try:
            if commit:
                db.commit()
            else:
                db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise ValueError(f"invalid source fact: {exc}") from exc
        db.refresh(record)
        return EndCustomerRepository._to_source_fact(record)

    @staticmethod
    def get_fact(db: Session, tenant_id: str, fact_id: str) -> CustomerSourceFact | None:
        record = (
            db.query(EndCustomerSourceFactRecord)
            .filter_by(tenant_id=tenant_id, fact_id=fact_id)
            .first()
        )
        if record is None:
            return None
        return EndCustomerRepository._to_source_fact(record)

    @staticmethod
    def list_facts_for_subject(
        db: Session,
        tenant_id: str,
        subject_type: EntityOwnerType,
        subject_id: str,
    ) -> list[CustomerSourceFact]:
        records = (
            db.query(EndCustomerSourceFactRecord)
            .filter_by(
                tenant_id=tenant_id,
                subject_type=subject_type.value,
                subject_id=subject_id,
            )
            .order_by(EndCustomerSourceFactRecord.recorded_at.asc())
            .all()
        )
        return [EndCustomerRepository._to_source_fact(r) for r in records]

    # --- identities ---

    @staticmethod
    def create_identity(
        db: Session,
        identity: CustomerIdentity,
        *,
        commit: bool = True,
    ) -> CustomerIdentity:
        EndCustomerRepository._validate_subject_exists(
            db, identity.tenant_id, identity.owner_type, identity.owner_id
        )
        if identity.source_fact_id:
            fact = (
                db.query(EndCustomerSourceFactRecord)
                .filter_by(tenant_id=identity.tenant_id, fact_id=identity.source_fact_id)
                .first()
            )
            if fact is None:
                raise EndCustomerTenantScopeError("source_fact_id not found in tenant")

        record = EndCustomerIdentityRecord(
            identity_id=identity.identity_id,
            tenant_id=identity.tenant_id,
            owner_type=identity.owner_type.value,
            owner_id=identity.owner_id,
            identity_type=identity.identity_type.value,
            raw_value=identity.raw_value,
            normalized_value=identity.normalized_value,
            fact_state=identity.fact_state.value,
            verification_status=identity.verification_status.value,
            source_fact_id=identity.source_fact_id,
            first_seen_at=identity.first_seen_at,
            last_seen_at=identity.last_seen_at,
        )
        db.add(record)
        try:
            if commit:
                db.commit()
            else:
                db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise EndCustomerDuplicateError(f"duplicate identity: {exc}") from exc
        db.refresh(record)
        return EndCustomerRepository._to_identity(record)

    @staticmethod
    def list_identities_for_owner(
        db: Session,
        tenant_id: str,
        owner_type: EntityOwnerType,
        owner_id: str,
    ) -> list[CustomerIdentity]:
        records = (
            db.query(EndCustomerIdentityRecord)
            .filter_by(tenant_id=tenant_id, owner_type=owner_type.value, owner_id=owner_id)
            .all()
        )
        return [EndCustomerRepository._to_identity(r) for r in records]

    @staticmethod
    def find_candidate_identities(
        db: Session,
        tenant_id: str,
        identity_type: IdentityType,
        normalized_value: str,
    ) -> list[CustomerIdentity]:
        records = (
            db.query(EndCustomerIdentityRecord)
            .filter_by(
                tenant_id=tenant_id,
                identity_type=identity_type.value,
                normalized_value=normalized_value,
            )
            .all()
        )
        return [EndCustomerRepository._to_identity(r) for r in records]

    # --- job links ---

    @staticmethod
    def create_job_link(
        db: Session,
        tenant_id: str,
        customer_id: str,
        job_id: str,
        link_type: LinkType,
        confidence: float,
        source_type: SourceType,
        created_by: str | None = None,
        *,
        commit: bool = True,
    ) -> tuple[CustomerJobLink, bool]:
        if EndCustomerRepository._get_customer_record(db, tenant_id, customer_id) is None:
            raise EndCustomerNotFoundError("customer not found")
        if not EndCustomerRepository._job_exists_in_tenant(db, tenant_id, job_id):
            raise EndCustomerTenantScopeError("job not found in tenant")

        existing = (
            db.query(EndCustomerJobLinkRecord)
            .filter_by(
                tenant_id=tenant_id,
                customer_id=customer_id,
                job_id=job_id,
                link_type=link_type.value,
            )
            .first()
        )
        if existing is not None:
            return EndCustomerRepository._to_job_link(existing), False

        now = _utcnow()
        record = EndCustomerJobLinkRecord(
            link_id=_new_id(),
            tenant_id=tenant_id,
            customer_id=customer_id,
            job_id=job_id,
            link_type=link_type.value,
            confidence=confidence,
            source_type=source_type.value,
            created_at=now,
            created_by=created_by,
        )
        db.add(record)
        try:
            if commit:
                db.commit()
            else:
                db.flush()
        except IntegrityError as exc:
            db.rollback()
            dup = (
                db.query(EndCustomerJobLinkRecord)
                .filter_by(
                    tenant_id=tenant_id,
                    customer_id=customer_id,
                    job_id=job_id,
                    link_type=link_type.value,
                )
                .first()
            )
            if dup is not None:
                return EndCustomerRepository._to_job_link(dup), False
            raise EndCustomerIdempotencyConflictError(str(exc)) from exc
        db.refresh(record)
        return EndCustomerRepository._to_job_link(record), True

    # --- thread links ---

    @staticmethod
    def create_thread_link(
        db: Session,
        tenant_id: str,
        customer_id: str,
        integration_type: str,
        integration_account_reference: str,
        thread_id: str,
        link_type: LinkType,
        confidence: float,
        source_type: SourceType,
        *,
        commit: bool = True,
    ) -> tuple[CustomerThreadLink, bool]:
        if EndCustomerRepository._get_customer_record(db, tenant_id, customer_id) is None:
            raise EndCustomerNotFoundError("customer not found")

        existing = (
            db.query(EndCustomerThreadLinkRecord)
            .filter_by(
                tenant_id=tenant_id,
                customer_id=customer_id,
                integration_type=integration_type,
                integration_account_reference=integration_account_reference,
                thread_id=thread_id,
                link_type=link_type.value,
            )
            .first()
        )
        if existing is not None:
            return EndCustomerRepository._to_thread_link(existing), False

        now = _utcnow()
        record = EndCustomerThreadLinkRecord(
            link_id=_new_id(),
            tenant_id=tenant_id,
            customer_id=customer_id,
            integration_type=integration_type,
            integration_account_reference=integration_account_reference,
            thread_id=thread_id,
            link_type=link_type.value,
            confidence=confidence,
            source_type=source_type.value,
            created_at=now,
        )
        db.add(record)
        try:
            if commit:
                db.commit()
            else:
                db.flush()
        except IntegrityError as exc:
            db.rollback()
            dup = (
                db.query(EndCustomerThreadLinkRecord)
                .filter_by(
                    tenant_id=tenant_id,
                    customer_id=customer_id,
                    integration_type=integration_type,
                    integration_account_reference=integration_account_reference,
                    thread_id=thread_id,
                    link_type=link_type.value,
                )
                .first()
            )
            if dup is not None:
                return EndCustomerRepository._to_thread_link(dup), False
            raise EndCustomerIdempotencyConflictError(str(exc)) from exc
        db.refresh(record)
        return EndCustomerRepository._to_thread_link(record), True

    # --- timeline (append-only) ---

    @staticmethod
    def _timeline_payload_matches(
        record: EndCustomerTimelineEventRecord,
        event: CustomerTimelineEvent,
        replay_key: str,
    ) -> bool:
        return (
            record.replay_identity_key == replay_key
            and record.event_type == event.event_type.value
            and record.summary == event.summary
            and record.occurred_at == event.occurred_at
            and record.reference_type == (event.reference_type.value if event.reference_type else None)
            and record.reference_id == event.reference_id
        )

    @staticmethod
    def append_timeline_event(
        db: Session,
        event: CustomerTimelineEvent,
        replay_identity_key: str,
        *,
        commit: bool = True,
    ) -> tuple[CustomerTimelineEvent, bool]:
        if EndCustomerRepository._get_customer_record(db, event.tenant_id, event.customer_id) is None:
            raise EndCustomerNotFoundError("customer not found")

        existing = (
            db.query(EndCustomerTimelineEventRecord)
            .filter_by(tenant_id=event.tenant_id, replay_identity_key=replay_identity_key)
            .first()
        )
        if existing is not None:
            if EndCustomerRepository._timeline_payload_matches(existing, event, replay_identity_key):
                return EndCustomerRepository._to_timeline_event(existing), False
            raise EndCustomerIdempotencyConflictError(
                "replay identity key already used for a different timeline event"
            )

        record = EndCustomerTimelineEventRecord(
            timeline_event_id=event.timeline_event_id,
            tenant_id=event.tenant_id,
            customer_id=event.customer_id,
            event_type=event.event_type.value,
            occurred_at=event.occurred_at,
            recorded_at=event.recorded_at,
            actor_type=event.actor_type,
            actor_id=event.actor_id,
            source_type=event.source_type.value if event.source_type else None,
            reference_type=event.reference_type.value if event.reference_type else None,
            reference_id=event.reference_id,
            summary=event.summary,
            metadata_json=dict(event.metadata),
            replay_identity_key=replay_identity_key,
        )
        db.add(record)
        try:
            if commit:
                db.commit()
            else:
                db.flush()
        except IntegrityError as exc:
            db.rollback()
            dup = (
                db.query(EndCustomerTimelineEventRecord)
                .filter_by(tenant_id=event.tenant_id, replay_identity_key=replay_identity_key)
                .first()
            )
            if dup is not None:
                if EndCustomerRepository._timeline_payload_matches(dup, event, replay_identity_key):
                    return EndCustomerRepository._to_timeline_event(dup), False
                raise EndCustomerIdempotencyConflictError(
                    "replay identity key already used for a different timeline event"
                ) from exc
            raise EndCustomerIdempotencyConflictError(str(exc)) from exc
        db.refresh(record)
        return EndCustomerRepository._to_timeline_event(record), True

    @staticmethod
    def list_timeline_events(
        db: Session,
        tenant_id: str,
        customer_id: str,
    ) -> list[CustomerTimelineEvent]:
        records = (
            db.query(EndCustomerTimelineEventRecord)
            .filter_by(tenant_id=tenant_id, customer_id=customer_id)
            .all()
        )
        events = [EndCustomerRepository._to_timeline_event(r) for r in records]
        return sorted(events, key=timeline_sort_key)

    # --- duplicate candidates ---

    @staticmethod
    def create_duplicate_candidate(
        db: Session,
        tenant_id: str,
        customer_a_id: str,
        customer_b_id: str,
        confidence: float,
        evidence: list[dict] | None = None,
        conflicts: list[dict] | None = None,
        *,
        commit: bool = True,
    ) -> tuple[CustomerDuplicateCandidate, bool]:
        left_id, right_id = _canonical_pair(customer_a_id, customer_b_id)
        left = EndCustomerRepository._get_customer_record(db, tenant_id, left_id)
        right = EndCustomerRepository._get_customer_record(db, tenant_id, right_id)
        if left is None or right is None:
            raise EndCustomerTenantScopeError("both customers must exist in tenant")

        existing = (
            db.query(EndCustomerDuplicateCandidateRecord)
            .filter_by(
                tenant_id=tenant_id,
                left_customer_id=left_id,
                right_customer_id=right_id,
            )
            .first()
        )
        if existing is not None:
            return EndCustomerRepository._to_duplicate_candidate(existing), False

        now = _utcnow()
        record = EndCustomerDuplicateCandidateRecord(
            candidate_id=_new_id(),
            tenant_id=tenant_id,
            left_customer_id=left_id,
            right_customer_id=right_id,
            status=DuplicateStatus.OPEN.value,
            confidence=confidence,
            evidence=list(evidence or []),
            conflicts=list(conflicts or []),
            version=1,
            created_at=now,
            updated_at=now,
        )
        db.add(record)
        try:
            if commit:
                db.commit()
            else:
                db.flush()
        except IntegrityError as exc:
            db.rollback()
            dup = (
                db.query(EndCustomerDuplicateCandidateRecord)
                .filter_by(
                    tenant_id=tenant_id,
                    left_customer_id=left_id,
                    right_customer_id=right_id,
                )
                .first()
            )
            if dup is not None:
                return EndCustomerRepository._to_duplicate_candidate(dup), False
            raise EndCustomerDuplicateError(str(exc)) from exc
        db.refresh(record)
        return EndCustomerRepository._to_duplicate_candidate(record), True

    @staticmethod
    def get_duplicate_candidate(
        db: Session,
        tenant_id: str,
        candidate_id: str,
    ) -> CustomerDuplicateCandidate | None:
        record = (
            db.query(EndCustomerDuplicateCandidateRecord)
            .filter_by(tenant_id=tenant_id, candidate_id=candidate_id)
            .first()
        )
        if record is None:
            return None
        return EndCustomerRepository._to_duplicate_candidate(record)

    @staticmethod
    def list_open_duplicate_candidates(
        db: Session,
        tenant_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CustomerDuplicateCandidate]:
        records = (
            db.query(EndCustomerDuplicateCandidateRecord)
            .filter_by(tenant_id=tenant_id, status=DuplicateStatus.OPEN.value)
            .order_by(EndCustomerDuplicateCandidateRecord.created_at.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [EndCustomerRepository._to_duplicate_candidate(r) for r in records]

    # --- read-only queries (API chapter) ---

    _LIST_SORT_FIELDS = frozenset({"created_at", "display_name"})

    @staticmethod
    def count_customers(
        db: Session,
        tenant_id: str,
        status: CustomerStatus | None = None,
        customer_type: CustomerType | None = None,
    ) -> int:
        query = db.query(EndCustomerRecord).filter_by(tenant_id=tenant_id)
        if status is not None:
            query = query.filter(EndCustomerRecord.status == status.value)
        if customer_type is not None:
            query = query.filter(EndCustomerRecord.customer_type == customer_type.value)
        return int(query.count())

    @staticmethod
    def list_customers(
        db: Session,
        tenant_id: str,
        status: CustomerStatus | None = None,
        customer_type: CustomerType | None = None,
        sort: str = "created_at",
        order: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> list[Customer]:
        sort_field = sort if sort in EndCustomerRepository._LIST_SORT_FIELDS else "created_at"
        order_norm = order.strip().lower()
        primary_col = (
            EndCustomerRecord.display_name
            if sort_field == "display_name"
            else EndCustomerRecord.created_at
        )
        query = db.query(EndCustomerRecord).filter_by(tenant_id=tenant_id)
        if status is not None:
            query = query.filter(EndCustomerRecord.status == status.value)
        if customer_type is not None:
            query = query.filter(EndCustomerRecord.customer_type == customer_type.value)
        if order_norm == "asc":
            query = query.order_by(primary_col.asc(), EndCustomerRecord.customer_id.asc())
        else:
            query = query.order_by(primary_col.desc(), EndCustomerRecord.customer_id.asc())
        records = query.offset(offset).limit(limit).all()
        return [EndCustomerRepository._to_customer(r) for r in records]

    @staticmethod
    def search_customers_by_display_name_prefix(
        db: Session,
        tenant_id: str,
        prefix: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Customer]:
        escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"{escaped}%"
        records = (
            db.query(EndCustomerRecord)
            .filter(
                EndCustomerRecord.tenant_id == tenant_id,
                EndCustomerRecord.display_name.ilike(pattern, escape="\\"),
            )
            .order_by(EndCustomerRecord.display_name.asc(), EndCustomerRecord.customer_id.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [EndCustomerRepository._to_customer(r) for r in records]

    @staticmethod
    def _customer_subject_refs(
        db: Session,
        tenant_id: str,
        customer_id: str,
    ) -> list[tuple[EntityOwnerType, str]]:
        record = EndCustomerRepository._get_customer_record(db, tenant_id, customer_id)
        if record is None:
            return []
        refs: list[tuple[EntityOwnerType, str]] = [
            (EntityOwnerType.CUSTOMER, customer_id),
        ]
        if record.primary_company_id:
            refs.append((EntityOwnerType.COMPANY, record.primary_company_id))
        if record.primary_contact_id:
            refs.append((EntityOwnerType.CONTACT, record.primary_contact_id))
        rels = (
            db.query(EndCustomerRelationshipRecord)
            .filter_by(tenant_id=tenant_id, customer_id=customer_id)
            .all()
        )
        for rel in rels:
            refs.append((EntityOwnerType(rel.subject_type), rel.subject_id))
        return refs

    @staticmethod
    def count_open_conflicts_for_customer(
        db: Session,
        tenant_id: str,
        customer_id: str,
    ) -> int:
        refs = EndCustomerRepository._customer_subject_refs(db, tenant_id, customer_id)
        if not refs:
            return 0
        count = 0
        for subject_type, subject_id in refs:
            facts = (
                db.query(EndCustomerSourceFactRecord)
                .filter_by(
                    tenant_id=tenant_id,
                    subject_type=subject_type.value,
                    subject_id=subject_id,
                )
                .all()
            )
            for fact in facts:
                conflicts = fact.conflicts_with_fact_ids or []
                if conflicts and fact.fact_state in {
                    FactState.PROPOSED.value,
                    FactState.VERIFIED.value,
                }:
                    count += 1
        return count

    @staticmethod
    def get_duplicate_status_for_customer(
        db: Session,
        tenant_id: str,
        customer_id: str,
    ) -> DuplicateStatus | None:
        record = (
            db.query(EndCustomerDuplicateCandidateRecord)
            .filter(
                EndCustomerDuplicateCandidateRecord.tenant_id == tenant_id,
                EndCustomerDuplicateCandidateRecord.status == DuplicateStatus.OPEN.value,
                (
                    (EndCustomerDuplicateCandidateRecord.left_customer_id == customer_id)
                    | (EndCustomerDuplicateCandidateRecord.right_customer_id == customer_id)
                ),
            )
            .first()
        )
        if record is None:
            return None
        return DuplicateStatus(record.status)

    @staticmethod
    def count_job_links(db: Session, tenant_id: str, customer_id: str) -> int:
        return int(
            db.query(EndCustomerJobLinkRecord)
            .filter_by(tenant_id=tenant_id, customer_id=customer_id)
            .count()
        )

    @staticmethod
    def list_job_links(
        db: Session,
        tenant_id: str,
        customer_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CustomerJobLink]:
        records = (
            db.query(EndCustomerJobLinkRecord)
            .filter_by(tenant_id=tenant_id, customer_id=customer_id)
            .order_by(
                EndCustomerJobLinkRecord.created_at.desc(),
                EndCustomerJobLinkRecord.link_id.asc(),
            )
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [EndCustomerRepository._to_job_link(r) for r in records]

    @staticmethod
    def count_thread_links(db: Session, tenant_id: str, customer_id: str) -> int:
        return int(
            db.query(EndCustomerThreadLinkRecord)
            .filter_by(tenant_id=tenant_id, customer_id=customer_id)
            .count()
        )

    @staticmethod
    def list_thread_links(
        db: Session,
        tenant_id: str,
        customer_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CustomerThreadLink]:
        records = (
            db.query(EndCustomerThreadLinkRecord)
            .filter_by(tenant_id=tenant_id, customer_id=customer_id)
            .order_by(
                EndCustomerThreadLinkRecord.created_at.desc(),
                EndCustomerThreadLinkRecord.link_id.asc(),
            )
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [EndCustomerRepository._to_thread_link(r) for r in records]

    @staticmethod
    def count_timeline_events(db: Session, tenant_id: str, customer_id: str) -> int:
        return int(
            db.query(EndCustomerTimelineEventRecord)
            .filter_by(tenant_id=tenant_id, customer_id=customer_id)
            .count()
        )

    @staticmethod
    def list_timeline_events_paginated(
        db: Session,
        tenant_id: str,
        customer_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CustomerTimelineEvent]:
        records = (
            db.query(EndCustomerTimelineEventRecord)
            .filter_by(tenant_id=tenant_id, customer_id=customer_id)
            .order_by(
                EndCustomerTimelineEventRecord.occurred_at.desc(),
                EndCustomerTimelineEventRecord.recorded_at.desc(),
                EndCustomerTimelineEventRecord.timeline_event_id.desc(),
            )
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [EndCustomerRepository._to_timeline_event(r) for r in records]

    @staticmethod
    def get_latest_timeline_event(
        db: Session,
        tenant_id: str,
        customer_id: str,
    ) -> CustomerTimelineEvent | None:
        record = (
            db.query(EndCustomerTimelineEventRecord)
            .filter_by(tenant_id=tenant_id, customer_id=customer_id)
            .order_by(
                EndCustomerTimelineEventRecord.occurred_at.desc(),
                EndCustomerTimelineEventRecord.recorded_at.desc(),
                EndCustomerTimelineEventRecord.timeline_event_id.desc(),
            )
            .first()
        )
        if record is None:
            return None
        return EndCustomerRepository._to_timeline_event(record)

    @staticmethod
    def count_open_duplicate_candidates(db: Session, tenant_id: str) -> int:
        return int(
            db.query(EndCustomerDuplicateCandidateRecord)
            .filter_by(tenant_id=tenant_id, status=DuplicateStatus.OPEN.value)
            .count()
        )

    @staticmethod
    def get_job_records_for_tenant(
        db: Session,
        tenant_id: str,
        job_ids: list[str],
    ) -> dict[str, JobRecord]:
        if not job_ids:
            return {}
        unique_ids = list(dict.fromkeys(job_ids))
        records = (
            db.query(JobRecord)
            .filter(
                JobRecord.tenant_id == tenant_id,
                JobRecord.job_id.in_(unique_ids),
            )
            .all()
        )
        return {record.job_id: record for record in records}

    @staticmethod
    def resolve_customer_ids_for_owner(
        db: Session,
        tenant_id: str,
        owner_type: EntityOwnerType,
        owner_id: str,
    ) -> set[str]:
        ids: set[str] = set()
        if owner_type == EntityOwnerType.CUSTOMER:
            if EndCustomerRepository._get_customer_record(db, tenant_id, owner_id) is not None:
                ids.add(owner_id)
            return ids
        if owner_type == EntityOwnerType.CONTACT:
            for row in (
                db.query(EndCustomerRecord)
                .filter_by(tenant_id=tenant_id, primary_contact_id=owner_id)
                .all()
            ):
                ids.add(row.customer_id)
        elif owner_type == EntityOwnerType.COMPANY:
            for row in (
                db.query(EndCustomerRecord)
                .filter_by(tenant_id=tenant_id, primary_company_id=owner_id)
                .all()
            ):
                ids.add(row.customer_id)
        for rel in (
            db.query(EndCustomerRelationshipRecord)
            .filter_by(
                tenant_id=tenant_id,
                subject_type=owner_type.value,
                subject_id=owner_id,
            )
            .all()
        ):
            ids.add(rel.customer_id)
        return ids

    @staticmethod
    def update_duplicate_candidate_status(
        db: Session,
        tenant_id: str,
        candidate_id: str,
        expected_version: int,
        status: DuplicateStatus,
        *,
        commit: bool = True,
    ) -> CustomerDuplicateCandidate:
        if expected_version < 1:
            raise ValueError("expected_version must be >= 1")
        if status == DuplicateStatus.APPROVED:
            raise ValueError("merge execution is forbidden in foundation chapter")

        existing = (
            db.query(EndCustomerDuplicateCandidateRecord)
            .filter_by(tenant_id=tenant_id, candidate_id=candidate_id)
            .first()
        )
        if existing is None:
            raise EndCustomerNotFoundError("duplicate candidate not found")

        result = db.execute(
            update(EndCustomerDuplicateCandidateRecord)
            .where(
                EndCustomerDuplicateCandidateRecord.tenant_id == tenant_id,
                EndCustomerDuplicateCandidateRecord.candidate_id == candidate_id,
                EndCustomerDuplicateCandidateRecord.version == expected_version,
            )
            .values(
                status=status.value,
                version=expected_version + 1,
                updated_at=_utcnow(),
            )
        )
        if result.rowcount == 0:
            if (
                db.query(EndCustomerDuplicateCandidateRecord)
                .filter_by(tenant_id=tenant_id, candidate_id=candidate_id)
                .first()
                is None
            ):
                raise EndCustomerNotFoundError("duplicate candidate not found")
            raise EndCustomerVersionConflictError("stale duplicate candidate version")

        if commit:
            db.commit()
        else:
            db.flush()

        record = (
            db.query(EndCustomerDuplicateCandidateRecord)
            .filter_by(tenant_id=tenant_id, candidate_id=candidate_id)
            .first()
        )
        assert record is not None
        return EndCustomerRepository._to_duplicate_candidate(record)
