"""Tests for isolated end-customer API contracts."""

from __future__ import annotations

import inspect

import pytest
from pydantic import ValidationError

from app.domain.customer.api_schemas import (
    MAX_LIST_LIMIT,
    AddContactRequest,
    CreateEndCustomerRequest,
    CreateCompanyEndCustomerRequest,
    CreatePrivateEndCustomerRequest,
    CustomerApiPagination,
    CustomerErrorResponse,
    CustomerWriteHeaders,
    DuplicateDecisionRequest,
    EndCustomerListResponse,
    EndCustomerSearchQuery,
    EndCustomerSearchResponse,
    MatchProposalResponse,
    TimelineResponse,
    UpdateVerifiedFactRequest,
)
from app.domain.customer.enums import (
    CustomerErrorCode,
    CustomerStatus,
    CustomerType,
    EntityOwnerType,
    MatchDecision,
    RelationshipType,
)
from app.domain.customer.schemas import CustomerCard, CustomerTimelineEvent


def test_list_response_shape() -> None:
    response = EndCustomerListResponse(items=[], total=0, limit=50, offset=0)
    dumped = response.model_dump()
    assert set(dumped.keys()) == {"items", "total", "limit", "offset"}


def test_limit_above_max_rejected() -> None:
    with pytest.raises(ValidationError):
        CustomerApiPagination(limit=MAX_LIST_LIMIT + 1)


def test_negative_offset_rejected() -> None:
    with pytest.raises(ValidationError):
        CustomerApiPagination(offset=-1)


def test_create_request_has_no_tenant_id_field() -> None:
    assert "tenant_id" not in CreatePrivateEndCustomerRequest.model_fields
    assert "tenant_id" not in CreateCompanyEndCustomerRequest.model_fields
    assert "tenant_id" not in CreateEndCustomerRequest.model_fields


def test_update_verified_fact_requires_expected_version() -> None:
    with pytest.raises(ValidationError):
        UpdateVerifiedFactRequest(
            subject_type=EntityOwnerType.CONTACT,
            subject_id="contact-1",
            field_name="email",
            raw_value="a@example.invalid",
            expected_version=0,
            reason="verify",
        )


def test_create_private_customer_request() -> None:
    request = CreateEndCustomerRequest(
        customer_type=CustomerType.PRIVATE,
        private=CreatePrivateEndCustomerRequest(display_name="Anna Svensson", email="a@example.invalid"),
    )
    assert request.private is not None
    assert request.company is None


def test_create_company_customer_with_contact() -> None:
    request = CreateEndCustomerRequest(
        customer_type=CustomerType.COMPANY,
        company=CreateCompanyEndCustomerRequest(
            company_legal_name="Fixture AB",
            primary_contact_display_name="Anna Svensson",
            primary_contact_email="a@example.invalid",
        ),
    )
    assert request.company is not None
    assert request.private is None


def test_company_and_private_payloads_not_mixed() -> None:
    with pytest.raises(ValidationError):
        CreateEndCustomerRequest(
            customer_type=CustomerType.PRIVATE,
            private=CreatePrivateEndCustomerRequest(display_name="Anna"),
            company=CreateCompanyEndCustomerRequest(
                company_legal_name="AB",
                primary_contact_display_name="Anna",
            ),
        )


def test_duplicate_decision_requires_reason_and_version() -> None:
    with pytest.raises(ValidationError):
        DuplicateDecisionRequest(decision="reject_merge", reason="", expected_version=1)


def test_merge_cannot_be_requested() -> None:
    with pytest.raises(ValidationError):
        DuplicateDecisionRequest(decision="approve_merge", reason="merge", expected_version=1)


def test_stable_error_codes_serialize() -> None:
    error = CustomerErrorResponse(
        code=CustomerErrorCode.AUTOMATIC_MERGE_FORBIDDEN,
        message="Automatisk merge är förbjuden",
    )
    assert error.model_dump()["code"] == "AUTOMATIC_MERGE_FORBIDDEN"


def test_customer_card_response_has_no_payload_fields() -> None:
    card = CustomerCard(
        tenant_id="T1",
        customer_id="cust-1",
        customer_type=CustomerType.PRIVATE,
        display_name="Anna",
        status=CustomerStatus.ACTIVE,
    )
    response_dump = {"card": card.model_dump()}
    forbidden = {"input_data", "result", "delivery_payload", "processor_history"}
    assert forbidden.isdisjoint(response_dump["card"].keys())


def test_timeline_response_uses_references() -> None:
    from datetime import datetime, timezone

    event = CustomerTimelineEvent(
        timeline_event_id="e1",
        tenant_id="T1",
        customer_id="cust-1",
        event_type="job_created",
        occurred_at=datetime.now(timezone.utc),
        recorded_at=datetime.now(timezone.utc),
        summary="Jobb skapades",
        reference_type="job",
        reference_id="job-1",
        metadata={"job_type": "lead"},
    )
    response = TimelineResponse(customer_id="cust-1", items=[event], total=1)
    assert response.items[0].reference_id == "job-1"
    assert "payload" not in response.items[0].metadata


def test_search_response_is_tenant_scoped_contract() -> None:
    response = EndCustomerSearchResponse(items=[], total=0, limit=50, offset=0)
    assert response.tenant_scoped is True


def test_search_query_min_length() -> None:
    with pytest.raises(ValidationError):
        EndCustomerSearchQuery(query="a")


def test_extra_fields_forbidden_on_write_requests() -> None:
    with pytest.raises(ValidationError):
        AddContactRequest(
            display_name="Anna",
            expected_version=1,
            unexpected=True,
        )


def test_match_proposal_automation_flags_false() -> None:
    response = MatchProposalResponse(
        tenant_id="T1",
        left_customer_id="c1",
        right_customer_id="c2",
        decision=MatchDecision.POSSIBLE_DUPLICATE,
        confidence=0.65,
    )
    assert response.automatic_merge_allowed is False
    assert response.automatic_link_allowed is False

    with pytest.raises(ValidationError):
        MatchProposalResponse(
            tenant_id="T1",
            left_customer_id="c1",
            right_customer_id="c2",
            decision=MatchDecision.POSSIBLE_DUPLICATE,
            confidence=0.65,
            automatic_merge_allowed=True,
        )


def test_idempotency_key_is_header_contract() -> None:
    headers = CustomerWriteHeaders(idempotency_key="idem-123")
    assert "tenant_id" not in CustomerWriteHeaders.model_fields


def test_api_schemas_do_not_import_fastapi_or_runtime() -> None:
    import app.domain.customer.api_schemas as api_mod

    forbidden_prefixes = ("fastapi", "app.main", "app.repositories", "app.api", "app.workflows")
    for name in dir(api_mod):
        if name.startswith("_"):
            continue
        obj = getattr(api_mod, name)
        if inspect.ismodule(obj):
            module_name = getattr(obj, "__name__", "")
            for prefix in forbidden_prefixes:
                assert not module_name.startswith(prefix)


def test_add_contact_uses_relationship_type() -> None:
    request = AddContactRequest(
        display_name="Erik Johansson",
        relationship_type=RelationshipType.TECHNICAL_CONTACT,
        expected_version=2,
    )
    assert request.relationship_type == RelationshipType.TECHNICAL_CONTACT
