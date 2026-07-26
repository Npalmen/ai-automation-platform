"""Operator-controlled end-customer write orchestration."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.admin_session import OperatorIdentity
from app.core.audit_service import create_audit_event
from app.domain.customer.api_schemas import (
    OperatorAddFactRequest,
    OperatorCreateCustomerRequest,
    OperatorCreateIdentityRequest,
    OperatorCreateJobLinkRequest,
    OperatorDuplicateDecisionResponse,
    OperatorUpdateCustomerRequest,
    OperatorVerifyFactRequest,
    OperatorWriteCustomerResponse,
    OperatorWriteFactResponse,
    OperatorWriteIdentityResponse,
    OperatorWriteJobLinkResponse,
)
from app.domain.customer.enums import (
    ActorType,
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
    EndCustomerWriteOperation,
)
from app.domain.customer.normalization import (
    normalize_email,
    normalize_organization_number,
    normalize_phone,
)
from app.domain.customer.provenance import (
    build_timeline_replay_identity,
    lower_source_cannot_supersede_verified,
    validate_timeline_metadata,
)
from app.domain.customer.schemas import (
    CustomerIdentity,
    CustomerSourceFact,
    CustomerTimelineEvent,
)
from app.repositories.postgres.end_customer_idempotency_repository import (
    EndCustomerIdempotencyConflictError,
    EndCustomerIdempotencyInProgressError,
    EndCustomerIdempotencyReplay,
    EndCustomerIdempotencyRepository,
)
from app.repositories.postgres.end_customer_repository import (
    EndCustomerDuplicateError,
    EndCustomerNotFoundError,
    EndCustomerRepository,
    EndCustomerTenantScopeError,
    EndCustomerVersionConflictError,
)

_AUDIT_CATEGORY = "end_customer_write"
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")


class EndCustomerCommandError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


class EndCustomerAuditError(Exception):
    """Audit could not be recorded — fail closed."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid4())


def _mask_idempotency_reference(idempotency_key: str) -> str:
    digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
    return digest[:16]


def _canonical_request_hash(
    operation_type: str,
    path_targets: dict[str, str],
    body: dict[str, Any],
) -> str:
    envelope = {
        "operation_type": operation_type,
        "path_targets": dict(sorted(path_targets.items())),
        "body": body,
    }
    payload = json.dumps(envelope, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _assert_subject_in_aggregate(
    db: Session,
    tenant_id: str,
    customer_id: str,
    subject_type: EntityOwnerType,
    subject_id: str,
) -> None:
    if not EndCustomerRepository.subject_belongs_to_customer_aggregate(
        db, tenant_id, customer_id, subject_type, subject_id
    ):
        raise EndCustomerNotFoundError("subject not found in customer aggregate")


def _write_audit(
    db: Session,
    *,
    tenant_id: str,
    action: str,
    status: str,
    operator: OperatorIdentity,
    reason: str,
    idempotency_key: str,
    target_type: str,
    target_id: str,
    details: dict[str, Any],
) -> None:
    audit_details: dict[str, Any] = {
        "actor_type": ActorType.OPERATOR.value,
        "actor_id": operator["id"],
        "operator_display_name": operator["display_name"],
        "operator_role": operator["role"],
        "reason": reason,
        "target_type": target_type,
        "target_id": target_id,
        "idempotency_reference": _mask_idempotency_reference(idempotency_key),
        **details,
    }
    try:
        create_audit_event(
            db=db,
            tenant_id=tenant_id,
            category=_AUDIT_CATEGORY,
            action=action,
            status=status,
            details=audit_details,
            commit=False,
        )
    except Exception as exc:
        raise EndCustomerAuditError("Audit could not be recorded.") from exc


def _append_timeline(
    db: Session,
    *,
    tenant_id: str,
    customer_id: str,
    event_type: TimelineEventType,
    summary: str,
    operator: OperatorIdentity,
    replay_key: str,
    reference_type: ReferenceType | None = None,
    reference_id: str | None = None,
    metadata: dict[str, object] | None = None,
) -> None:
    now = _utcnow()
    replay_identity = build_timeline_replay_identity(
        tenant_id=tenant_id,
        customer_id=customer_id,
        event_type=event_type,
        source_reference_key=replay_key,
    )
    event = CustomerTimelineEvent(
        timeline_event_id=_new_id(),
        tenant_id=tenant_id,
        customer_id=customer_id,
        event_type=event_type,
        occurred_at=now,
        recorded_at=now,
        actor_type=ActorType.OPERATOR.value,
        actor_id=operator["id"],
        source_type=SourceType.ADMIN_CORRECTION,
        reference_type=reference_type,
        reference_id=reference_id,
        summary=summary,
        metadata=validate_timeline_metadata(metadata or {}),
    )
    EndCustomerRepository.append_timeline_event(
        db,
        event,
        replay_identity.identity_key(),
        commit=False,
    )


def _normalize_identity_value(identity_type: IdentityType, raw_value: str) -> str | None:
    if identity_type == IdentityType.EMAIL:
        result = normalize_email(raw_value)
        return result[0] if result else None
    if identity_type == IdentityType.PHONE:
        return normalize_phone(raw_value)
    if identity_type == IdentityType.ORGANIZATION_NUMBER:
        return normalize_organization_number(raw_value)
    if identity_type in {IdentityType.CUSTOMER_NUMBER, IdentityType.EXTERNAL_ID, IdentityType.OTHER}:
        text = raw_value.strip()
        return text if text else None
    return None


class EndCustomerCommandService:
    @staticmethod
    def validate_idempotency_key(raw_key: str) -> str:
        key = raw_key.strip()
        if not key or len(key) > 128:
            raise EndCustomerCommandError(
                "INVALID_PAGINATION",
                "Idempotency-Key must be between 1 and 128 characters.",
            )
        if _CONTROL_CHAR_RE.search(key):
            raise EndCustomerCommandError(
                "INVALID_PAGINATION",
                "Idempotency-Key contains invalid control characters.",
            )
        return key

    @staticmethod
    def _execute_idempotent(
        db: Session,
        tenant_id: str,
        operation: EndCustomerWriteOperation,
        idempotency_key: str,
        path_targets: dict[str, str],
        body: dict[str, Any],
        handler: Callable[[], tuple[int, dict[str, Any], dict[str, Any]]],
    ) -> tuple[int, dict[str, Any]]:
        request_hash = _canonical_request_hash(operation.value, path_targets, body)
        try:
            acquired = EndCustomerIdempotencyRepository.acquire(
                db,
                tenant_id,
                operation.value,
                idempotency_key,
                request_hash,
            )
        except EndCustomerIdempotencyConflictError as exc:
            raise EndCustomerCommandError("IDEMPOTENCY_CONFLICT", str(exc)) from exc
        except EndCustomerIdempotencyInProgressError as exc:
            raise EndCustomerCommandError("IDEMPOTENCY_CONFLICT", str(exc)) from exc

        if isinstance(acquired, EndCustomerIdempotencyReplay):
            return acquired.response_status_code, dict(acquired.response_body)

        record_id = acquired
        try:
            status_code, response_body, resource_reference = handler()
            EndCustomerIdempotencyRepository.complete(
                db,
                record_id,
                status_code,
                response_body,
                resource_reference,
            )
            db.commit()
            return status_code, response_body
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def create_customer(
        db: Session,
        tenant_id: str,
        operator: OperatorIdentity,
        request: OperatorCreateCustomerRequest,
        idempotency_key: str,
    ) -> tuple[int, dict[str, Any]]:
        body = request.model_dump(mode="json")
        return EndCustomerCommandService._execute_idempotent(
            db,
            tenant_id,
            EndCustomerWriteOperation.CREATE_CUSTOMER,
            idempotency_key,
            {},
            body,
            lambda: EndCustomerCommandService._create_customer_body(
                db, tenant_id, operator, request, idempotency_key
            ),
        )

    @staticmethod
    def _create_customer_body(
        db: Session,
        tenant_id: str,
        operator: OperatorIdentity,
        request: OperatorCreateCustomerRequest,
        idempotency_key: str,
    ) -> tuple[int, dict[str, Any], dict[str, Any]]:
        company_id: str | None = None
        contact_id: str | None = None
        customer_display_name: str

        if request.customer_type == CustomerType.PRIVATE:
            private = request.private
            assert private is not None
            customer_display_name = private.display_name
            contact_display = private.display_name
            if private.given_name or private.family_name:
                parts = [p for p in [private.given_name, private.family_name] if p]
                contact_display = " ".join(parts)
            contact = EndCustomerRepository.create_contact(
                db,
                tenant_id,
                display_name=contact_display,
                given_name=private.given_name,
                family_name=private.family_name,
                commit=False,
            )
            contact_id = contact.contact_id
            customer = EndCustomerRepository.create_customer(
                db,
                tenant_id,
                CustomerType.PRIVATE,
                display_name=customer_display_name,
                primary_contact_id=contact_id,
                commit=False,
            )
            EndCustomerRepository.create_relationship(
                db,
                tenant_id,
                customer.customer_id,
                EntityOwnerType.CONTACT,
                contact_id,
                RelationshipType.PRIVATE_CUSTOMER,
                is_primary=True,
                commit=False,
            )
            if private.email:
                EndCustomerCommandService._create_identity_record(
                    db,
                    tenant_id,
                    customer.customer_id,
                    EntityOwnerType.CONTACT,
                    contact_id,
                    IdentityType.EMAIL,
                    private.email,
                    VerificationStatus.VERIFIED,
                    None,
                )
            if private.phone:
                EndCustomerCommandService._create_identity_record(
                    db,
                    tenant_id,
                    customer.customer_id,
                    EntityOwnerType.CONTACT,
                    contact_id,
                    IdentityType.PHONE,
                    private.phone,
                    VerificationStatus.VERIFIED,
                    None,
                )
        else:
            company_payload = request.company
            assert company_payload is not None
            company_display = company_payload.company_display_name or company_payload.company_legal_name
            customer_display_name = company_display
            company = EndCustomerRepository.create_company(
                db,
                tenant_id,
                legal_name=company_payload.company_legal_name,
                display_name=company_display,
                commit=False,
            )
            company_id = company.company_id
            contact = EndCustomerRepository.create_contact(
                db,
                tenant_id,
                display_name=company_payload.primary_contact_display_name,
                commit=False,
            )
            contact_id = contact.contact_id
            customer = EndCustomerRepository.create_customer(
                db,
                tenant_id,
                request.customer_type,
                display_name=customer_display_name,
                primary_company_id=company_id,
                primary_contact_id=contact_id,
                commit=False,
            )
            EndCustomerRepository.create_relationship(
                db,
                tenant_id,
                customer.customer_id,
                EntityOwnerType.COMPANY,
                company_id,
                RelationshipType.CUSTOMER_COMPANY,
                is_primary=True,
                commit=False,
            )
            EndCustomerRepository.create_relationship(
                db,
                tenant_id,
                customer.customer_id,
                EntityOwnerType.CONTACT,
                contact_id,
                RelationshipType.PRIMARY_CONTACT,
                is_primary=True,
                commit=False,
            )
            if company_payload.organization_number:
                EndCustomerCommandService._create_identity_record(
                    db,
                    tenant_id,
                    customer.customer_id,
                    EntityOwnerType.COMPANY,
                    company_id,
                    IdentityType.ORGANIZATION_NUMBER,
                    company_payload.organization_number,
                    VerificationStatus.VERIFIED,
                    None,
                )
            if company_payload.primary_contact_email:
                EndCustomerCommandService._create_identity_record(
                    db,
                    tenant_id,
                    customer.customer_id,
                    EntityOwnerType.CONTACT,
                    contact_id,
                    IdentityType.EMAIL,
                    company_payload.primary_contact_email,
                    VerificationStatus.VERIFIED,
                    None,
                )
            if company_payload.primary_contact_phone:
                EndCustomerCommandService._create_identity_record(
                    db,
                    tenant_id,
                    customer.customer_id,
                    EntityOwnerType.CONTACT,
                    contact_id,
                    IdentityType.PHONE,
                    company_payload.primary_contact_phone,
                    VerificationStatus.VERIFIED,
                    None,
                )

        for fact_req in request.initial_facts:
            if fact_req.subject_type == EntityOwnerType.CUSTOMER:
                subject_id = customer.customer_id
            elif fact_req.subject_type == EntityOwnerType.COMPANY:
                if company_id is None:
                    raise EndCustomerCommandError(
                        "INVALID_SOURCE_PROVENANCE",
                        "Company facts require a company customer payload.",
                    )
                subject_id = company_id
            else:
                if contact_id is None:
                    raise EndCustomerCommandError(
                        "INVALID_SOURCE_PROVENANCE",
                        "Contact facts require a contact on the customer.",
                    )
                subject_id = contact_id
            _assert_subject_in_aggregate(
                db,
                tenant_id,
                customer.customer_id,
                fact_req.subject_type,
                subject_id,
            )
            EndCustomerCommandService._append_fact_record(
                db,
                tenant_id,
                customer.customer_id,
                operator,
                fact_req.subject_type,
                subject_id,
                fact_req.field_name,
                fact_req.raw_value,
                fact_req.normalized_value,
                fact_req.fact_state,
                fact_req.source_type,
                fact_req.confidence,
            )

        for identity_req in request.initial_identities:
            if identity_req.owner_type == EntityOwnerType.CUSTOMER:
                owner_id = customer.customer_id
            elif identity_req.owner_type == EntityOwnerType.COMPANY:
                if company_id is None:
                    raise EndCustomerCommandError(
                        "INVALID_CUSTOMER_IDENTITY",
                        "Company identities require a company customer payload.",
                    )
                owner_id = company_id
            else:
                if contact_id is None:
                    raise EndCustomerCommandError(
                        "INVALID_CUSTOMER_IDENTITY",
                        "Contact identities require a contact on the customer.",
                    )
                owner_id = contact_id
            _assert_subject_in_aggregate(
                db,
                tenant_id,
                customer.customer_id,
                identity_req.owner_type,
                owner_id,
            )
            EndCustomerCommandService._create_identity_record(
                db,
                tenant_id,
                customer.customer_id,
                identity_req.owner_type,
                owner_id,
                identity_req.identity_type,
                identity_req.raw_value,
                identity_req.verification_status,
                identity_req.source_fact_id,
            )

        _append_timeline(
            db,
            tenant_id=tenant_id,
            customer_id=customer.customer_id,
            event_type=TimelineEventType.NOTE_ADDED,
            summary="Customer created by operator.",
            operator=operator,
            replay_key=f"create:{idempotency_key}",
            metadata={"source_label": "operator_create"},
        )

        response = OperatorWriteCustomerResponse(
            customer_id=customer.customer_id,
            customer_type=customer.customer_type,
            display_name=customer.display_name,
            status=customer.status,
            version=customer.version,
            primary_company_id=customer.primary_company_id,
            primary_contact_id=customer.primary_contact_id,
            created=True,
        )
        _write_audit(
            db,
            tenant_id=tenant_id,
            action="customer.created",
            status="completed",
            operator=operator,
            reason=request.reason,
            idempotency_key=idempotency_key,
            target_type="customer",
            target_id=customer.customer_id,
            details={
                "operation": EndCustomerWriteOperation.CREATE_CUSTOMER.value,
                "new_version": customer.version,
                "customer_type": customer.customer_type.value,
            },
        )
        body = response.model_dump(mode="json")
        resource = {"customer_id": customer.customer_id}
        return 201, body, resource

    @staticmethod
    def update_customer(
        db: Session,
        tenant_id: str,
        customer_id: str,
        operator: OperatorIdentity,
        request: OperatorUpdateCustomerRequest,
        idempotency_key: str,
    ) -> tuple[int, dict[str, Any]]:
        body = request.model_dump(mode="json")
        return EndCustomerCommandService._execute_idempotent(
            db,
            tenant_id,
            EndCustomerWriteOperation.UPDATE_CUSTOMER,
            idempotency_key,
            {"customer_id": customer_id},
            body,
            lambda: EndCustomerCommandService._update_customer_body(
                db, tenant_id, customer_id, operator, request, idempotency_key
            ),
        )

    @staticmethod
    def _update_customer_body(
        db: Session,
        tenant_id: str,
        customer_id: str,
        operator: OperatorIdentity,
        request: OperatorUpdateCustomerRequest,
        idempotency_key: str,
    ) -> tuple[int, dict[str, Any], dict[str, Any]]:
        existing = EndCustomerRepository.get_customer(db, tenant_id, customer_id)
        if existing is None:
            raise EndCustomerNotFoundError("customer not found")
        previous_version = existing.version
        if request.primary_company_id is not None:
            _assert_subject_in_aggregate(
                db,
                tenant_id,
                customer_id,
                EntityOwnerType.COMPANY,
                request.primary_company_id,
            )
        if request.primary_contact_id is not None:
            _assert_subject_in_aggregate(
                db,
                tenant_id,
                customer_id,
                EntityOwnerType.CONTACT,
                request.primary_contact_id,
            )
        try:
            updated = EndCustomerRepository.update_customer(
                db,
                tenant_id,
                customer_id,
                request.expected_version,
                display_name=request.display_name,
                status=request.status,
                primary_company_id=request.primary_company_id,
                primary_contact_id=request.primary_contact_id,
                clear_primary_company=request.clear_primary_company,
                clear_primary_contact=request.clear_primary_contact,
                commit=False,
            )
        except EndCustomerVersionConflictError as exc:
            raise EndCustomerCommandError("CUSTOMER_VERSION_CONFLICT", str(exc)) from exc

        _append_timeline(
            db,
            tenant_id=tenant_id,
            customer_id=customer_id,
            event_type=TimelineEventType.NOTE_ADDED,
            summary="Customer updated by operator.",
            operator=operator,
            replay_key=f"update:{idempotency_key}",
            metadata={"source_label": "operator_update"},
        )
        response = OperatorWriteCustomerResponse(
            customer_id=updated.customer_id,
            customer_type=updated.customer_type,
            display_name=updated.display_name,
            status=updated.status,
            version=updated.version,
            primary_company_id=updated.primary_company_id,
            primary_contact_id=updated.primary_contact_id,
            created=False,
        )
        _write_audit(
            db,
            tenant_id=tenant_id,
            action="customer.updated",
            status="completed",
            operator=operator,
            reason=request.reason,
            idempotency_key=idempotency_key,
            target_type="customer",
            target_id=customer_id,
            details={
                "operation": EndCustomerWriteOperation.UPDATE_CUSTOMER.value,
                "expected_version": request.expected_version,
                "previous_version": previous_version,
                "new_version": updated.version,
            },
        )
        body = response.model_dump(mode="json")
        return 200, body, {"customer_id": customer_id}

    @staticmethod
    def add_fact(
        db: Session,
        tenant_id: str,
        customer_id: str,
        operator: OperatorIdentity,
        request: OperatorAddFactRequest,
        idempotency_key: str,
    ) -> tuple[int, dict[str, Any]]:
        body = request.model_dump(mode="json")
        return EndCustomerCommandService._execute_idempotent(
            db,
            tenant_id,
            EndCustomerWriteOperation.APPEND_FACT,
            idempotency_key,
            {"customer_id": customer_id},
            body,
            lambda: EndCustomerCommandService._add_fact_body(
                db, tenant_id, customer_id, operator, request, idempotency_key
            ),
        )

    @staticmethod
    def _add_fact_body(
        db: Session,
        tenant_id: str,
        customer_id: str,
        operator: OperatorIdentity,
        request: OperatorAddFactRequest,
        idempotency_key: str,
    ) -> tuple[int, dict[str, Any], dict[str, Any]]:
        _assert_subject_in_aggregate(
            db, tenant_id, customer_id, request.subject_type, request.subject_id
        )
        fact = EndCustomerCommandService._append_fact_record(
            db,
            tenant_id,
            customer_id,
            operator,
            request.subject_type,
            request.subject_id,
            request.field_name,
            request.raw_value,
            request.normalized_value,
            request.fact_state,
            request.source_type,
            request.confidence,
            verified_by=operator["id"] if request.fact_state == FactState.VERIFIED else None,
        )
        action = "fact.verified" if fact.fact_state == FactState.VERIFIED else "fact.proposed"
        _write_audit(
            db,
            tenant_id=tenant_id,
            action=action,
            status="completed",
            operator=operator,
            reason=request.reason,
            idempotency_key=idempotency_key,
            target_type="source_fact",
            target_id=fact.fact_id,
            details={
                "operation": EndCustomerWriteOperation.APPEND_FACT.value,
                "fact_state": fact.fact_state.value,
                "source_type": fact.source_type.value,
                "field_name": fact.field_name,
            },
        )
        response = OperatorWriteFactResponse(
            fact_id=fact.fact_id,
            fact_state=fact.fact_state,
            subject_type=fact.subject_type,
            subject_id=fact.subject_id,
            field_name=fact.field_name,
            supersedes_fact_id=fact.supersedes_fact_id,
        )
        body = response.model_dump(mode="json")
        return 201, body, {"fact_id": fact.fact_id, "customer_id": customer_id}

    @staticmethod
    def verify_fact(
        db: Session,
        tenant_id: str,
        customer_id: str,
        fact_id: str,
        operator: OperatorIdentity,
        request: OperatorVerifyFactRequest,
        idempotency_key: str,
    ) -> tuple[int, dict[str, Any]]:
        body = request.model_dump(mode="json")
        return EndCustomerCommandService._execute_idempotent(
            db,
            tenant_id,
            EndCustomerWriteOperation.VERIFY_FACT,
            idempotency_key,
            {"customer_id": customer_id, "fact_id": fact_id},
            body,
            lambda: EndCustomerCommandService._verify_fact_body(
                db, tenant_id, customer_id, fact_id, operator, request, idempotency_key
            ),
        )

    @staticmethod
    def _verify_fact_body(
        db: Session,
        tenant_id: str,
        customer_id: str,
        fact_id: str,
        operator: OperatorIdentity,
        request: OperatorVerifyFactRequest,
        idempotency_key: str,
    ) -> tuple[int, dict[str, Any], dict[str, Any]]:
        original = EndCustomerRepository.get_fact(db, tenant_id, fact_id)
        if original is None:
            raise EndCustomerNotFoundError("fact not found")
        _assert_subject_in_aggregate(
            db, tenant_id, customer_id, original.subject_type, original.subject_id
        )
        now = _utcnow()
        verified_fact = CustomerSourceFact(
            fact_id=_new_id(),
            tenant_id=tenant_id,
            subject_type=original.subject_type,
            subject_id=original.subject_id,
            field_name=original.field_name,
            raw_value=request.verified_raw_value,
            normalized_value=request.normalized_value,
            fact_state=FactState.VERIFIED,
            source_type=SourceType.ADMIN_CORRECTION,
            source_actor=operator["id"],
            confidence=1.0,
            observed_at=now,
            recorded_at=now,
            verified_at=now,
            verified_by=operator["id"],
            supersedes_fact_id=original.fact_id,
        )
        if lower_source_cannot_supersede_verified(verified_fact, original):
            raise EndCustomerCommandError(
                "INVALID_SOURCE_PROVENANCE",
                "Lower-precedence source cannot supersede verified fact.",
            )
        EndCustomerRepository.append_fact(db, verified_fact, commit=False)
        _append_timeline(
            db,
            tenant_id=tenant_id,
            customer_id=customer_id,
            event_type=TimelineEventType.CONTACT_FACT_VERIFIED,
            summary=f"Fact verified for {original.field_name}.",
            operator=operator,
            replay_key=f"verify-fact:{idempotency_key}",
            reference_type=ReferenceType.SOURCE_FACT,
            reference_id=verified_fact.fact_id,
            metadata={"field_name": original.field_name, "fact_state": FactState.VERIFIED.value},
        )
        _write_audit(
            db,
            tenant_id=tenant_id,
            action="fact.verified",
            status="completed",
            operator=operator,
            reason=request.reason,
            idempotency_key=idempotency_key,
            target_type="source_fact",
            target_id=verified_fact.fact_id,
            details={
                "operation": EndCustomerWriteOperation.VERIFY_FACT.value,
                "supersedes_fact_id": original.fact_id,
                "field_name": original.field_name,
            },
        )
        response = OperatorWriteFactResponse(
            fact_id=verified_fact.fact_id,
            fact_state=verified_fact.fact_state,
            subject_type=verified_fact.subject_type,
            subject_id=verified_fact.subject_id,
            field_name=verified_fact.field_name,
            supersedes_fact_id=verified_fact.supersedes_fact_id,
        )
        body = response.model_dump(mode="json")
        return 201, body, {"fact_id": verified_fact.fact_id, "customer_id": customer_id}

    @staticmethod
    def create_identity(
        db: Session,
        tenant_id: str,
        customer_id: str,
        operator: OperatorIdentity,
        request: OperatorCreateIdentityRequest,
        idempotency_key: str,
    ) -> tuple[int, dict[str, Any]]:
        body = request.model_dump(mode="json")
        return EndCustomerCommandService._execute_idempotent(
            db,
            tenant_id,
            EndCustomerWriteOperation.CREATE_IDENTITY,
            idempotency_key,
            {"customer_id": customer_id},
            body,
            lambda: EndCustomerCommandService._create_identity_body(
                db, tenant_id, customer_id, operator, request, idempotency_key
            ),
        )

    @staticmethod
    def _create_identity_body(
        db: Session,
        tenant_id: str,
        customer_id: str,
        operator: OperatorIdentity,
        request: OperatorCreateIdentityRequest,
        idempotency_key: str,
    ) -> tuple[int, dict[str, Any], dict[str, Any]]:
        _assert_subject_in_aggregate(
            db, tenant_id, customer_id, request.owner_type, request.owner_id
        )
        identity = EndCustomerCommandService._create_identity_record(
            db,
            tenant_id,
            customer_id,
            request.owner_type,
            request.owner_id,
            request.identity_type,
            request.raw_value,
            request.verification_status,
            request.source_fact_id,
        )
        _write_audit(
            db,
            tenant_id=tenant_id,
            action="identity.created",
            status="completed",
            operator=operator,
            reason=request.reason,
            idempotency_key=idempotency_key,
            target_type="identity",
            target_id=identity.identity_id,
            details={
                "operation": EndCustomerWriteOperation.CREATE_IDENTITY.value,
                "identity_type": identity.identity_type.value,
                "owner_type": identity.owner_type.value,
                "owner_id": identity.owner_id,
            },
        )
        response = OperatorWriteIdentityResponse(
            identity_id=identity.identity_id,
            owner_type=identity.owner_type,
            owner_id=identity.owner_id,
            identity_type=identity.identity_type,
            verification_status=identity.verification_status,
            normalized_value=identity.normalized_value,
        )
        body = response.model_dump(mode="json")
        return 201, body, {"identity_id": identity.identity_id, "customer_id": customer_id}

    @staticmethod
    def create_job_link(
        db: Session,
        tenant_id: str,
        customer_id: str,
        operator: OperatorIdentity,
        request: OperatorCreateJobLinkRequest,
        idempotency_key: str,
    ) -> tuple[int, dict[str, Any]]:
        body = request.model_dump(mode="json")
        return EndCustomerCommandService._execute_idempotent(
            db,
            tenant_id,
            EndCustomerWriteOperation.JOB_LINK,
            idempotency_key,
            {"customer_id": customer_id},
            body,
            lambda: EndCustomerCommandService._create_job_link_body(
                db, tenant_id, customer_id, operator, request, idempotency_key
            ),
        )

    @staticmethod
    def _create_job_link_body(
        db: Session,
        tenant_id: str,
        customer_id: str,
        operator: OperatorIdentity,
        request: OperatorCreateJobLinkRequest,
        idempotency_key: str,
    ) -> tuple[int, dict[str, Any], dict[str, Any]]:
        if EndCustomerRepository.get_customer(db, tenant_id, customer_id) is None:
            raise EndCustomerNotFoundError("customer not found")
        try:
            link, created = EndCustomerRepository.create_job_link(
                db,
                tenant_id,
                customer_id,
                request.job_id,
                request.link_type,
                request.confidence,
                request.source_type,
                created_by=operator["id"],
                commit=False,
            )
        except EndCustomerTenantScopeError as exc:
            raise EndCustomerNotFoundError(str(exc)) from exc

        _append_timeline(
            db,
            tenant_id=tenant_id,
            customer_id=customer_id,
            event_type=TimelineEventType.JOB_LINKED,
            summary="Job linked to customer by operator.",
            operator=operator,
            replay_key=f"job-link:{idempotency_key}",
            reference_type=ReferenceType.JOB,
            reference_id=request.job_id,
            metadata={"link_type": request.link_type.value},
        )
        _write_audit(
            db,
            tenant_id=tenant_id,
            action="job.linked",
            status="completed",
            operator=operator,
            reason=request.reason,
            idempotency_key=idempotency_key,
            target_type="job_link",
            target_id=link.link_id,
            details={
                "operation": EndCustomerWriteOperation.JOB_LINK.value,
                "job_id": request.job_id,
                "created": created,
            },
        )
        response = OperatorWriteJobLinkResponse(
            link_id=link.link_id,
            customer_id=link.customer_id,
            job_id=link.job_id,
            link_type=link.link_type,
            created=created,
        )
        body = response.model_dump(mode="json")
        return 201, body, {"link_id": link.link_id, "customer_id": customer_id}

    @staticmethod
    def duplicate_decision(
        db: Session,
        tenant_id: str,
        candidate_id: str,
        operator: OperatorIdentity,
        decision: str,
        expected_version: int,
        reason: str,
        idempotency_key: str,
    ) -> tuple[int, dict[str, Any]]:
        body = {
            "decision": decision,
            "expected_version": expected_version,
            "reason": reason,
        }
        return EndCustomerCommandService._execute_idempotent(
            db,
            tenant_id,
            EndCustomerWriteOperation.DUPLICATE_DECISION,
            idempotency_key,
            {"candidate_id": candidate_id},
            body,
            lambda: EndCustomerCommandService._duplicate_decision_body(
                db,
                tenant_id,
                candidate_id,
                operator,
                decision,
                expected_version,
                reason,
                idempotency_key,
            ),
        )

    @staticmethod
    def _duplicate_decision_body(
        db: Session,
        tenant_id: str,
        candidate_id: str,
        operator: OperatorIdentity,
        decision: str,
        expected_version: int,
        reason: str,
        idempotency_key: str,
    ) -> tuple[int, dict[str, Any], dict[str, Any]]:
        if decision == "approve_merge":
            raise EndCustomerCommandError(
                "AUTOMATIC_MERGE_FORBIDDEN",
                "Merge decisions are forbidden.",
            )
        if decision == "reject_merge":
            target_status = DuplicateStatus.REJECTED
            audit_action = "duplicate.rejected"
            timeline_type = TimelineEventType.DUPLICATE_CANDIDATE_REJECTED
        elif decision == "resolve_without_merge":
            target_status = DuplicateStatus.RESOLVED_WITHOUT_MERGE
            audit_action = "duplicate.resolved_without_merge"
            timeline_type = TimelineEventType.DUPLICATE_CANDIDATE_REJECTED
        else:
            raise EndCustomerCommandError(
                "UNSUPPORTED_CUSTOMER_TRANSITION",
                f"Unsupported duplicate decision: {decision}",
            )

        existing = EndCustomerRepository.get_duplicate_candidate(db, tenant_id, candidate_id)
        if existing is None:
            raise EndCustomerNotFoundError("duplicate candidate not found")
        if existing.status != DuplicateStatus.OPEN:
            raise EndCustomerCommandError(
                "UNSUPPORTED_CUSTOMER_TRANSITION",
                "Duplicate candidate is not open.",
            )
        previous_version = existing.version
        try:
            updated = EndCustomerRepository.update_duplicate_candidate_status(
                db,
                tenant_id,
                candidate_id,
                expected_version,
                target_status,
                commit=False,
            )
        except EndCustomerVersionConflictError as exc:
            raise EndCustomerCommandError("DUPLICATE_DECISION_CONFLICT", str(exc)) from exc

        customer_id = updated.left_customer_id
        _append_timeline(
            db,
            tenant_id=tenant_id,
            customer_id=customer_id,
            event_type=timeline_type,
            summary=f"Duplicate candidate {target_status.value}.",
            operator=operator,
            replay_key=f"duplicate-decision:{idempotency_key}",
            metadata={"duplicate_status": target_status.value},
        )
        _write_audit(
            db,
            tenant_id=tenant_id,
            action=audit_action,
            status="completed",
            operator=operator,
            reason=reason,
            idempotency_key=idempotency_key,
            target_type="duplicate_candidate",
            target_id=candidate_id,
            details={
                "operation": EndCustomerWriteOperation.DUPLICATE_DECISION.value,
                "expected_version": expected_version,
                "previous_version": previous_version,
                "new_version": updated.version,
                "decision": decision,
            },
        )
        response = OperatorDuplicateDecisionResponse(
            candidate_id=updated.candidate_id,
            status=updated.status,
            version=updated.version,
            left_customer_id=updated.left_customer_id,
            right_customer_id=updated.right_customer_id,
        )
        body = response.model_dump(mode="json")
        return 200, body, {"candidate_id": candidate_id}

    @staticmethod
    def _append_fact_record(
        db: Session,
        tenant_id: str,
        customer_id: str,
        operator: OperatorIdentity,
        subject_type: EntityOwnerType,
        subject_id: str,
        field_name: str,
        raw_value: str,
        normalized_value: str | None,
        fact_state: FactState,
        source_type: SourceType,
        confidence: float,
        verified_by: str | None = None,
    ) -> CustomerSourceFact:
        now = _utcnow()
        fact = CustomerSourceFact(
            fact_id=_new_id(),
            tenant_id=tenant_id,
            subject_type=subject_type,
            subject_id=subject_id,
            field_name=field_name,
            raw_value=raw_value,
            normalized_value=normalized_value,
            fact_state=fact_state,
            source_type=source_type,
            source_actor=operator["id"],
            confidence=confidence,
            observed_at=now,
            recorded_at=now,
            verified_at=now if fact_state == FactState.VERIFIED else None,
            verified_by=verified_by,
        )
        EndCustomerRepository.append_fact(db, fact, commit=False)
        event_type = (
            TimelineEventType.CONTACT_FACT_VERIFIED
            if fact_state == FactState.VERIFIED
            else TimelineEventType.CONTACT_FACT_PROPOSED
        )
        _append_timeline(
            db,
            tenant_id=tenant_id,
            customer_id=customer_id,
            event_type=event_type,
            summary=f"Fact {fact_state.value} for {field_name}.",
            operator=operator,
            replay_key=f"fact:{fact.fact_id}",
            reference_type=ReferenceType.SOURCE_FACT,
            reference_id=fact.fact_id,
            metadata={"field_name": field_name, "fact_state": fact_state.value},
        )
        return fact

    @staticmethod
    def _create_identity_record(
        db: Session,
        tenant_id: str,
        customer_id: str,
        owner_type: EntityOwnerType,
        owner_id: str,
        identity_type: IdentityType,
        raw_value: str,
        verification_status: VerificationStatus,
        source_fact_id: str | None,
    ) -> CustomerIdentity:
        normalized = _normalize_identity_value(identity_type, raw_value)
        if verification_status == VerificationStatus.VERIFIED and not normalized:
            raise EndCustomerCommandError(
                "INVALID_CUSTOMER_IDENTITY",
                "Verified identity requires a normalizable value.",
            )
        if normalized:
            matches = EndCustomerRepository.find_candidate_identities(
                db, tenant_id, identity_type, normalized
            )
            for match in matches:
                if match.owner_id != owner_id or match.owner_type != owner_type:
                    raise EndCustomerCommandError(
                        "IDENTITY_COLLISION_REVIEW_REQUIRED",
                        "Identity already exists for another owner in tenant.",
                    )
        now = _utcnow()
        identity = CustomerIdentity(
            identity_id=_new_id(),
            tenant_id=tenant_id,
            owner_type=owner_type,
            owner_id=owner_id,
            identity_type=identity_type,
            raw_value=raw_value,
            normalized_value=normalized,
            fact_state=FactState.VERIFIED if verification_status == VerificationStatus.VERIFIED else FactState.PROPOSED,
            verification_status=verification_status,
            source_fact_id=source_fact_id,
            first_seen_at=now,
            last_seen_at=now,
        )
        try:
            EndCustomerRepository.create_identity(db, identity, commit=False)
        except EndCustomerDuplicateError as exc:
            raise EndCustomerCommandError("INVALID_CUSTOMER_IDENTITY", str(exc)) from exc
        return identity

    @staticmethod
    def map_repository_error(exc: Exception) -> EndCustomerCommandError:
        if isinstance(exc, EndCustomerNotFoundError):
            if "duplicate" in str(exc).lower():
                return EndCustomerCommandError("DUPLICATE_CANDIDATE_NOT_FOUND", "Resource not found.")
            if "fact" in str(exc).lower():
                return EndCustomerCommandError("CUSTOMER_NOT_FOUND", "Resource not found.")
            return EndCustomerCommandError("CUSTOMER_NOT_FOUND", "Resource not found.")
        if isinstance(exc, EndCustomerCommandError):
            return exc
        if isinstance(exc, EndCustomerAuditError):
            return EndCustomerCommandError("INTERNAL_ERROR", "Audit could not be recorded.")
        return EndCustomerCommandError("INTERNAL_ERROR", "Unexpected command failure.")
