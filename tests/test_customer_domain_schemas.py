"""Contract tests for isolated customer domain schemas."""

from __future__ import annotations

import inspect
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.domain.customer.enums import (
    CustomerStatus,
    CustomerType,
    DuplicateStatus,
    EntityOwnerType,
    FactState,
    IdentityType,
    MatchDecision,
    ReferenceType,
    SourceType,
    TimelineEventType,
    VerificationStatus,
)
from app.domain.customer.schemas import (
    Company,
    Contact,
    Customer,
    CustomerCard,
    CustomerIdentity,
    CustomerMatchAssessment,
    CustomerSourceFact,
    SourceReference,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _customer() -> Customer:
    return Customer(
        customer_id="cust-1",
        tenant_id="T1",
        customer_type=CustomerType.PRIVATE,
        status=CustomerStatus.ACTIVE,
        display_name="Anna Svensson",
        primary_contact_id="contact-1",
        created_at=_now(),
        updated_at=_now(),
    )


def test_tenant_id_required_on_customer() -> None:
    with pytest.raises(ValidationError):
        Customer(
            customer_id="cust-1",
            tenant_id="",
            customer_type=CustomerType.PRIVATE,
            display_name="Anna",
            created_at=_now(),
            updated_at=_now(),
        )


def test_confidence_outside_range_rejected() -> None:
    with pytest.raises(ValidationError):
        CustomerMatchAssessment(
            tenant_id="T1",
            decision=MatchDecision.NO_MATCH,
            confidence=1.1,
        )


def test_naive_timestamp_rejected() -> None:
    with pytest.raises(ValidationError):
        Customer(
            customer_id="cust-1",
            tenant_id="T1",
            customer_type=CustomerType.PRIVATE,
            display_name="Anna",
            created_at=datetime(2026, 1, 1),
            updated_at=_now(),
        )


def test_enum_values_round_trip() -> None:
    customer = _customer()
    payload = customer.model_dump(mode="json")
    restored = Customer.model_validate(payload)
    assert restored.customer_type == CustomerType.PRIVATE


def test_extra_fields_forbidden_on_customer() -> None:
    with pytest.raises(ValidationError):
        Customer(
            customer_id="cust-1",
            tenant_id="T1",
            customer_type=CustomerType.PRIVATE,
            display_name="Anna",
            created_at=_now(),
            updated_at=_now(),
            unexpected=True,
        )


def test_company_and_contact_are_separate_models() -> None:
    company = Company(
        company_id="co-1",
        tenant_id="T1",
        legal_name="AB Sol",
        display_name="AB Sol",
        created_at=_now(),
        updated_at=_now(),
    )
    contact = Contact(
        contact_id="contact-1",
        tenant_id="T1",
        display_name="Anna Svensson",
        created_at=_now(),
        updated_at=_now(),
    )
    assert company.company_id != contact.contact_id
    assert Company.model_fields.keys() != Contact.model_fields.keys()


def test_source_fact_provenance_and_self_reference_guard() -> None:
    fact = CustomerSourceFact(
        fact_id="fact-1",
        tenant_id="T1",
        subject_type=EntityOwnerType.CONTACT,
        subject_id="contact-1",
        field_name="email",
        raw_value="anna@example.com",
        normalized_value="anna@example.com",
        fact_state=FactState.PROPOSED,
        source_type=SourceType.AI_EXTRACTION,
        source_reference=SourceReference(
            reference_type=ReferenceType.JOB,
            reference_id="job-1",
        ),
        confidence=0.8,
        recorded_at=_now(),
        conflicts_with_fact_ids=["fact-0"],
    )
    assert fact.source_reference.reference_id == "job-1"

    with pytest.raises(ValidationError):
        CustomerSourceFact(
            fact_id="fact-1",
            tenant_id="T1",
            subject_type=EntityOwnerType.CONTACT,
            subject_id="contact-1",
            field_name="email",
            fact_state=FactState.PROPOSED,
            source_type=SourceType.AI_EXTRACTION,
            confidence=0.5,
            recorded_at=_now(),
            supersedes_fact_id="fact-1",
        )


def test_verified_identity_requires_normalized_value() -> None:
    with pytest.raises(ValidationError):
        CustomerIdentity(
            identity_id="id-1",
            tenant_id="T1",
            owner_type=EntityOwnerType.CONTACT,
            owner_id="contact-1",
            identity_type=IdentityType.EMAIL,
            raw_value="anna@example.com",
            normalized_value="",
            fact_state=FactState.VERIFIED,
            verification_status=VerificationStatus.VERIFIED,
        )


def test_customer_card_has_no_internal_payload_fields() -> None:
    card = CustomerCard(
        tenant_id="T1",
        customer_id="cust-1",
        customer_type=CustomerType.PRIVATE,
        display_name="Anna",
        status=CustomerStatus.ACTIVE,
        duplicate_status=DuplicateStatus.OPEN,
    )
    dumped = card.model_dump()
    forbidden_keys = {"input_data", "result", "request_payload", "delivery_payload", "processor_history"}
    assert forbidden_keys.isdisjoint(dumped.keys())


def test_automatic_merge_and_link_default_false() -> None:
    assessment = CustomerMatchAssessment(
        tenant_id="T1",
        decision=MatchDecision.STRONG_CANDIDATE,
        confidence=0.8,
        requires_manual_review=True,
    )
    assert assessment.automatic_merge_allowed is False
    assert assessment.automatic_link_allowed is False

    with pytest.raises(ValidationError):
        CustomerMatchAssessment(
            tenant_id="T1",
            decision=MatchDecision.STRONG_CANDIDATE,
            confidence=0.8,
            automatic_merge_allowed=True,
        )


def test_fact_states_and_timeline_event_types() -> None:
    event_type = TimelineEventType.JOB_CREATED
    assert FactState.VERIFIED.value == "verified"
    assert event_type.value == "job_created"


def test_no_sqlalchemy_or_runtime_imports_in_customer_package() -> None:
    import app.domain.customer.enums as enums_mod
    import app.domain.customer.matching as matching_mod
    import app.domain.customer.normalization as normalization_mod
    import app.domain.customer.schemas as schemas_mod

    modules = [enums_mod, schemas_mod, normalization_mod, matching_mod]
    forbidden_prefixes = (
        "sqlalchemy",
        "app.main",
        "app.repositories",
        "app.workflows",
        "app.integrations",
    )
    for module in modules:
        for name in dir(module):
            if name.startswith("_"):
                continue
            obj = getattr(module, name)
            if inspect.ismodule(obj):
                module_name = getattr(obj, "__name__", "")
                for prefix in forbidden_prefixes:
                    assert not module_name.startswith(prefix)


def test_customer_serialization_round_trip() -> None:
    original = _customer()
    restored = Customer.model_validate(original.model_dump())
    assert restored == original
