"""Tests for customer identity normalization and match assessment."""

from __future__ import annotations

import copy
from datetime import datetime, timezone

import pytest

from app.domain.customer.enums import (
    CustomerType,
    EntityOwnerType,
    IdentityType,
    MatchConflictCode,
    MatchDecision,
    MatchEvidenceCode,
    MatchReasonCode,
    SourceType,
    VerificationStatus,
)
from app.domain.customer.matching import assess_customer_match
from app.domain.customer.normalization import normalize_email, normalize_phone
from app.domain.customer.schemas import (
    CustomerMatchInput,
    CustomerMatchSubject,
    IdentityMatchItem,
    StructuredAddressInput,
)


def _email_identity(
    email: str,
    *,
    verified: bool = False,
    role_based: bool = False,
) -> IdentityMatchItem:
    normalized = normalize_email(email)
    return IdentityMatchItem(
        identity_type=IdentityType.EMAIL,
        raw_value=email,
        normalized_value=normalized[0] if normalized else None,
        verification_status=(
            VerificationStatus.VERIFIED if verified else VerificationStatus.UNVERIFIED
        ),
        is_role_based_email=role_based or (normalized[1] if normalized else False),
    )


def _phone_identity(
    phone: str,
    *,
    verified: bool = False,
) -> IdentityMatchItem:
    return IdentityMatchItem(
        identity_type=IdentityType.PHONE,
        raw_value=phone,
        normalized_value=normalize_phone(phone, country_code="SE"),
        verification_status=(
            VerificationStatus.VERIFIED if verified else VerificationStatus.UNVERIFIED
        ),
    )


def _subject(
    tenant_id: str,
    subject_id: str,
    *,
    owner_type: EntityOwnerType = EntityOwnerType.CUSTOMER,
    customer_type: CustomerType | None = CustomerType.PRIVATE,
    display_name: str | None = "Anna Svensson",
    verified_display_name: str | None = None,
    verified_company_name: str | None = None,
    identities: list[IdentityMatchItem] | None = None,
    historical_identities: list[IdentityMatchItem] | None = None,
    structured_address: StructuredAddressInput | None = None,
    gmail_thread_id: str | None = None,
    integration_type: str | None = None,
    integration_account_reference: str | None = None,
    company_relation_id: str | None = None,
) -> CustomerMatchSubject:
    return CustomerMatchSubject(
        tenant_id=tenant_id,
        subject_id=subject_id,
        owner_type=owner_type,
        customer_type=customer_type,
        display_name=display_name,
        verified_display_name=verified_display_name,
        verified_company_name=verified_company_name,
        identities=identities or [],
        historical_identities=historical_identities or [],
        structured_address=structured_address,
        gmail_thread_id=gmail_thread_id,
        integration_type=integration_type,
        integration_account_reference=integration_account_reference,
        company_relation_id=company_relation_id,
    )


def test_same_email_same_tenant_possible_duplicate() -> None:
    left = _subject("T1", "c1", display_name=None, identities=[_email_identity("Anna@Example.com")])
    right = _subject("T1", "c2", display_name=None, identities=[_email_identity("anna@example.com")])
    result = assess_customer_match(CustomerMatchInput(left=left, right=right))
    assert result.decision == MatchDecision.POSSIBLE_DUPLICATE
    assert result.confidence == 0.65
    assert result.evidence[0].code == MatchEvidenceCode.NORMALIZED_EMAIL


def test_same_email_different_tenants_blocked() -> None:
    left = _subject("T1", "c1", identities=[_email_identity("anna@example.com")])
    right = _subject("T2", "c2", identities=[_email_identity("anna@example.com")])
    result = assess_customer_match(CustomerMatchInput(left=left, right=right))
    assert result.decision == MatchDecision.BLOCKED
    assert any(item.code == MatchConflictCode.CROSS_TENANT for item in result.conflicts)


def test_same_name_without_other_evidence_not_strong() -> None:
    left = _subject("T1", "c1", display_name="Anna Svensson")
    right = _subject("T1", "c2", display_name="Anna Svensson")
    result = assess_customer_match(CustomerMatchInput(left=left, right=right))
    assert result.decision == MatchDecision.NO_MATCH
    assert result.confidence < 0.50


def test_same_phone_and_compatible_name_strong_candidate() -> None:
    left = _subject(
        "T1",
        "c1",
        identities=[_phone_identity("070-123 45 67")],
        verified_display_name="Anna Svensson",
    )
    right = _subject(
        "T1",
        "c2",
        identities=[_phone_identity("0701234567")],
        verified_display_name="Anna Svensson",
    )
    result = assess_customer_match(CustomerMatchInput(left=left, right=right))
    assert result.decision == MatchDecision.STRONG_CANDIDATE
    assert result.confidence == 0.75


def test_same_phone_different_verified_names_manual_review() -> None:
    left = _subject(
        "T1",
        "c1",
        identities=[_phone_identity("0701234567")],
        verified_display_name="Anna Svensson",
    )
    right = _subject(
        "T1",
        "c2",
        identities=[_phone_identity("0701234567")],
        verified_display_name="Erik Johansson",
    )
    result = assess_customer_match(CustomerMatchInput(left=left, right=right))
    assert result.decision == MatchDecision.MANUAL_REVIEW_REQUIRED
    assert MatchReasonCode.PHONE_NAME_MISMATCH_REVIEW in result.reason_codes


def test_same_verified_organization_number_exact_candidate() -> None:
    org = IdentityMatchItem(
        identity_type=IdentityType.ORGANIZATION_NUMBER,
        raw_value="556016-0680",
        normalized_value="5560160680",
        verification_status=VerificationStatus.VERIFIED,
    )
    left = _subject(
        "T1",
        "c1",
        owner_type=EntityOwnerType.COMPANY,
        customer_type=CustomerType.COMPANY,
        display_name=None,
        identities=[org],
    )
    right = _subject(
        "T1",
        "c2",
        owner_type=EntityOwnerType.COMPANY,
        customer_type=CustomerType.COMPANY,
        display_name=None,
        identities=[org],
    )
    result = assess_customer_match(CustomerMatchInput(left=left, right=right))
    assert result.decision == MatchDecision.EXACT_CANDIDATE
    assert result.confidence == 0.90


def test_different_verified_organization_numbers_blocked() -> None:
    left = _subject(
        "T1",
        "c1",
        owner_type=EntityOwnerType.COMPANY,
        customer_type=CustomerType.COMPANY,
        identities=[
            IdentityMatchItem(
                identity_type=IdentityType.ORGANIZATION_NUMBER,
                raw_value="556016-0680",
                normalized_value="5560160680",
                verification_status=VerificationStatus.VERIFIED,
            )
        ],
    )
    right = _subject(
        "T1",
        "c2",
        owner_type=EntityOwnerType.COMPANY,
        customer_type=CustomerType.COMPANY,
        identities=[
            IdentityMatchItem(
                identity_type=IdentityType.ORGANIZATION_NUMBER,
                raw_value="556000-0000",
                normalized_value="5560000000",
                verification_status=VerificationStatus.VERIFIED,
            )
        ],
    )
    result = assess_customer_match(CustomerMatchInput(left=left, right=right))
    assert result.decision == MatchDecision.BLOCKED
    assert any(
        item.code == MatchConflictCode.DIFFERENT_VERIFIED_ORGANIZATION_NUMBER
        for item in result.conflicts
    )


def test_person_vs_company_blocked() -> None:
    left = _subject("T1", "c1", owner_type=EntityOwnerType.CONTACT)
    right = _subject(
        "T1",
        "co1",
        owner_type=EntityOwnerType.COMPANY,
        customer_type=CustomerType.COMPANY,
        display_name="AB Sol",
    )
    result = assess_customer_match(CustomerMatchInput(left=left, right=right))
    assert result.decision == MatchDecision.BLOCKED
    assert any(item.code == MatchConflictCode.PERSON_VS_COMPANY for item in result.conflicts)


def test_role_based_email_without_company_signal_manual_review() -> None:
    left = _subject("T1", "c1", identities=[_email_identity("info@example.com")])
    right = _subject("T1", "c2", identities=[_email_identity("info@example.com")])
    result = assess_customer_match(CustomerMatchInput(left=left, right=right))
    assert result.decision == MatchDecision.MANUAL_REVIEW_REQUIRED
    assert MatchReasonCode.ROLE_BASED_EMAIL_REVIEW in result.reason_codes


def test_same_gmail_thread_same_integration_context() -> None:
    left = _subject(
        "T1",
        "c1",
        display_name=None,
        gmail_thread_id="thread-abc",
        integration_type="google_mail",
        integration_account_reference="acct-1",
    )
    right = _subject(
        "T1",
        "c2",
        display_name=None,
        gmail_thread_id="thread-abc",
        integration_type="google_mail",
        integration_account_reference="acct-1",
    )
    result = assess_customer_match(CustomerMatchInput(left=left, right=right))
    assert result.evidence[0].code == MatchEvidenceCode.GMAIL_THREAD
    assert result.confidence == 0.60


def test_same_thread_id_different_tenants_blocked() -> None:
    left = _subject(
        "T1",
        "c1",
        gmail_thread_id="thread-abc",
        integration_type="google_mail",
        integration_account_reference="acct-1",
    )
    right = _subject(
        "T2",
        "c2",
        gmail_thread_id="thread-abc",
        integration_type="google_mail",
        integration_account_reference="acct-1",
    )
    result = assess_customer_match(CustomerMatchInput(left=left, right=right))
    assert result.decision == MatchDecision.BLOCKED


def test_address_and_name_without_strong_identity_no_match() -> None:
    address = StructuredAddressInput(
        street="Storgatan 1",
        postal_code="12345",
        city="Stockholm",
        country_code="SE",
    )
    left = _subject("T1", "c1", display_name="Anna Svensson", structured_address=address)
    right = _subject("T1", "c2", display_name="Anna Svensson", structured_address=address)
    result = assess_customer_match(CustomerMatchInput(left=left, right=right))
    assert result.decision == MatchDecision.NO_MATCH
    assert result.confidence < 0.50


def test_changed_phone_with_old_verified_value_manual_review() -> None:
    left = _subject(
        "T1",
        "c1",
        identities=[_phone_identity("0701234567")],
    )
    right = _subject(
        "T1",
        "c2",
        identities=[_phone_identity("0701234567")],
        historical_identities=[_phone_identity("0709876543", verified=True)],
    )
    result = assess_customer_match(CustomerMatchInput(left=left, right=right))
    assert result.decision == MatchDecision.MANUAL_REVIEW_REQUIRED
    assert MatchReasonCode.HISTORICAL_CONTACT_CONFLICT in result.reason_codes


def test_deterministic_evidence_order() -> None:
    left = _subject(
        "T1",
        "c1",
        identities=[_email_identity("anna@example.com"), _phone_identity("0701234567")],
        display_name="Anna Svensson",
    )
    right = _subject(
        "T1",
        "c2",
        identities=[_phone_identity("0701234567"), _email_identity("anna@example.com")],
        display_name="Anna Svensson",
    )
    first = assess_customer_match(CustomerMatchInput(left=left, right=right))
    second = assess_customer_match(CustomerMatchInput(left=right, right=left))
    assert [item.code for item in first.evidence] == [item.code for item in second.evidence]


def test_deterministic_reason_codes() -> None:
    left = _subject(
        "T1",
        "c1",
        identities=[_phone_identity("0701234567")],
        verified_display_name="Anna Svensson",
    )
    right = _subject(
        "T1",
        "c2",
        identities=[_phone_identity("0701234567")],
        verified_display_name="Erik Johansson",
    )
    first = assess_customer_match(CustomerMatchInput(left=left, right=right))
    second = assess_customer_match(CustomerMatchInput(left=right, right=left))
    assert first.reason_codes == second.reason_codes


def test_confidence_never_above_one() -> None:
    left = _subject(
        "T1",
        "c1",
        identities=[
            IdentityMatchItem(
                identity_type=IdentityType.ORGANIZATION_NUMBER,
                raw_value="556016-0680",
                normalized_value="5560160680",
                verification_status=VerificationStatus.VERIFIED,
            ),
            _email_identity("anna@example.com"),
            _phone_identity("0701234567"),
        ],
        gmail_thread_id="thread-abc",
        integration_type="google_mail",
        integration_account_reference="acct-1",
        company_relation_id="co-1",
        structured_address=StructuredAddressInput(street="Storgatan 1", city="Stockholm"),
        display_name="Anna Svensson",
    )
    right = copy.deepcopy(left)
    right.subject_id = "c2"
    result = assess_customer_match(CustomerMatchInput(left=left, right=right))
    assert result.confidence <= 1.0


def test_input_not_mutated() -> None:
    left = _subject("T1", "c1", identities=[_email_identity("anna@example.com")])
    right = _subject("T1", "c2", identities=[_email_identity("anna@example.com")])
    left_snapshot = left.model_dump()
    right_snapshot = right.model_dump()
    assess_customer_match(CustomerMatchInput(left=left, right=right))
    assert left.model_dump() == left_snapshot
    assert right.model_dump() == right_snapshot


def test_automatic_merge_and_link_always_false() -> None:
    cases = [
        _subject("T1", "c1", identities=[_email_identity("anna@example.com")]),
        _subject(
            "T1",
            "c2",
            owner_type=EntityOwnerType.COMPANY,
            customer_type=CustomerType.COMPANY,
            identities=[
                IdentityMatchItem(
                    identity_type=IdentityType.ORGANIZATION_NUMBER,
                    raw_value="556016-0680",
                    normalized_value="5560160680",
                    verification_status=VerificationStatus.VERIFIED,
                )
            ],
        ),
    ]
    result = assess_customer_match(CustomerMatchInput(left=cases[0], right=cases[1]))
    assert result.automatic_merge_allowed is False
    assert result.automatic_link_allowed is False

    same_email = assess_customer_match(
        CustomerMatchInput(
            left=_subject("T1", "c1", identities=[_email_identity("anna@example.com")]),
            right=_subject("T1", "c2", identities=[_email_identity("anna@example.com")]),
        )
    )
    assert same_email.automatic_merge_allowed is False
    assert same_email.automatic_link_allowed is False


def test_email_plus_tag_preserved_in_normalization() -> None:
    result = normalize_email("Anna+tag@Example.com")
    assert result is not None
    assert result[0] == "anna+tag@example.com"
