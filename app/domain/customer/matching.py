"""Pure customer identity match assessment — no database or I/O."""

from __future__ import annotations

from app.domain.customer.enums import (
    CustomerType,
    EntityOwnerType,
    IdentityType,
    MatchConflictCode,
    MatchDecision,
    MatchEvidenceCode,
    MatchReasonCode,
    VerificationStatus,
)
from app.domain.customer.normalization import (
    normalize_email,
    normalize_name,
    normalize_organization_number,
    normalize_phone,
    normalize_structured_address,
)
from app.domain.customer.schemas import (
    CustomerMatchAssessment,
    CustomerMatchInput,
    CustomerMatchSubject,
    IdentityMatchItem,
    MatchConflict,
    MatchEvidence,
)

_EVIDENCE_SCORES: dict[MatchEvidenceCode, float] = {
    MatchEvidenceCode.VERIFIED_ORGANIZATION_NUMBER: 0.90,
    MatchEvidenceCode.VERIFIED_CUSTOMER_NUMBER: 0.85,
    MatchEvidenceCode.NORMALIZED_EMAIL: 0.65,
    MatchEvidenceCode.NORMALIZED_PHONE: 0.55,
    MatchEvidenceCode.GMAIL_THREAD: 0.60,
    MatchEvidenceCode.COMPANY_RELATION: 0.50,
    MatchEvidenceCode.STRUCTURED_ADDRESS: 0.25,
    MatchEvidenceCode.NORMALIZED_NAME: 0.20,
}

_END_CUSTOMER_OWNER_TYPES = frozenset(
    {
        EntityOwnerType.CUSTOMER,
        EntityOwnerType.COMPANY,
        EntityOwnerType.CONTACT,
    }
)


def _is_person_subject(subject: CustomerMatchSubject) -> bool:
    if subject.owner_type == EntityOwnerType.CONTACT:
        return True
    if subject.owner_type == EntityOwnerType.CUSTOMER:
        return subject.customer_type in {CustomerType.PRIVATE, None}
    return False


def _is_company_subject(subject: CustomerMatchSubject) -> bool:
    if subject.owner_type == EntityOwnerType.COMPANY:
        return True
    if subject.owner_type == EntityOwnerType.CUSTOMER:
        return subject.customer_type in {CustomerType.COMPANY, CustomerType.ASSOCIATION}
    return False


def _identity_normalized(item: IdentityMatchItem, identity_type: IdentityType) -> str | None:
    if item.identity_type != identity_type:
        return None
    if item.normalized_value and item.normalized_value.strip():
        return item.normalized_value.strip()
    raw = item.raw_value
    if identity_type == IdentityType.EMAIL:
        result = normalize_email(raw)
        return result[0] if result else None
    if identity_type == IdentityType.PHONE:
        return normalize_phone(raw, country_code="SE")
    if identity_type == IdentityType.ORGANIZATION_NUMBER:
        return normalize_organization_number(raw, country_code="SE")
    if identity_type == IdentityType.CUSTOMER_NUMBER:
        collapsed = raw.strip()
        return collapsed if collapsed else None
    return raw.strip() or None


def _collect_identities(
    subject: CustomerMatchSubject,
    identity_type: IdentityType,
    *,
    verified_only: bool,
) -> list[tuple[str, IdentityMatchItem]]:
    collected: list[tuple[str, IdentityMatchItem]] = []
    for item in subject.identities:
        if item.identity_type != identity_type:
            continue
        if verified_only and item.verification_status != VerificationStatus.VERIFIED:
            continue
        normalized = _identity_normalized(item, identity_type)
        if normalized:
            collected.append((normalized, item))
    return collected


def _decision_from_confidence(confidence: float) -> MatchDecision:
    if confidence < 0.50:
        return MatchDecision.NO_MATCH
    if confidence < 0.75:
        return MatchDecision.POSSIBLE_DUPLICATE
    if confidence < 0.90:
        return MatchDecision.STRONG_CANDIDATE
    return MatchDecision.EXACT_CANDIDATE


def assess_customer_match(match_input: CustomerMatchInput) -> CustomerMatchAssessment:
    left = match_input.left
    right = match_input.right
    tenant_id = left.tenant_id if left.tenant_id == right.tenant_id else left.tenant_id

    conflicts: list[MatchConflict] = []
    evidence: list[MatchEvidence] = []
    reason_codes: list[MatchReasonCode] = []

    if not left.tenant_id or not right.tenant_id:
        conflicts.append(
            MatchConflict(code=MatchConflictCode.MISSING_TENANT, detail="tenant_id required")
        )
        reason_codes.append(MatchReasonCode.MISSING_TENANT)
        return _blocked_assessment(tenant_id or "", conflicts, reason_codes)

    if left.tenant_id != right.tenant_id:
        conflicts.append(
            MatchConflict(
                code=MatchConflictCode.CROSS_TENANT,
                left_value=left.tenant_id,
                right_value=right.tenant_id,
            )
        )
        reason_codes.append(MatchReasonCode.CROSS_TENANT_BLOCKED)
        return _blocked_assessment(left.tenant_id, conflicts, reason_codes)

    tenant_id = left.tenant_id

    left_is_account = left.owner_type == EntityOwnerType.TENANT_ACCOUNT
    right_is_account = right.owner_type == EntityOwnerType.TENANT_ACCOUNT
    if left_is_account or right_is_account:
        other_is_end = (
            (left_is_account and right.owner_type in _END_CUSTOMER_OWNER_TYPES)
            or (right_is_account and left.owner_type in _END_CUSTOMER_OWNER_TYPES)
        )
        if other_is_end:
            conflicts.append(
                MatchConflict(code=MatchConflictCode.TENANT_ACCOUNT_VS_END_CUSTOMER)
            )
            reason_codes.append(MatchReasonCode.TENANT_ACCOUNT_BLOCKED)
            return _blocked_assessment(tenant_id, conflicts, reason_codes)

    if _is_person_subject(left) and _is_company_subject(right):
        conflicts.append(MatchConflict(code=MatchConflictCode.PERSON_VS_COMPANY))
        reason_codes.append(MatchReasonCode.PERSON_COMPANY_BLOCKED)
        return _blocked_assessment(tenant_id, conflicts, reason_codes)
    if _is_person_subject(right) and _is_company_subject(left):
        conflicts.append(MatchConflict(code=MatchConflictCode.PERSON_VS_COMPANY))
        reason_codes.append(MatchReasonCode.PERSON_COMPANY_BLOCKED)
        return _blocked_assessment(tenant_id, conflicts, reason_codes)

    # Verified organization numbers
    left_verified_orgs = _collect_identities(left, IdentityType.ORGANIZATION_NUMBER, verified_only=True)
    right_verified_orgs = _collect_identities(right, IdentityType.ORGANIZATION_NUMBER, verified_only=True)
    if left_verified_orgs and right_verified_orgs:
        left_set = {value for value, _ in left_verified_orgs}
        right_set = {value for value, _ in right_verified_orgs}
        if left_set == right_set:
            evidence.append(
                MatchEvidence(
                    code=MatchEvidenceCode.VERIFIED_ORGANIZATION_NUMBER,
                    score=_EVIDENCE_SCORES[MatchEvidenceCode.VERIFIED_ORGANIZATION_NUMBER],
                    left_value=next(iter(left_set)),
                    right_value=next(iter(right_set)),
                )
            )
        else:
            conflicts.append(
                MatchConflict(
                    code=MatchConflictCode.DIFFERENT_VERIFIED_ORGANIZATION_NUMBER,
                    left_value=",".join(sorted(left_set)),
                    right_value=",".join(sorted(right_set)),
                )
            )
            reason_codes.append(MatchReasonCode.ORG_NUMBER_CONFLICT)
            return _blocked_assessment(tenant_id, conflicts, reason_codes)

    # Verified customer numbers within same source
    left_verified_customers = _collect_identities(left, IdentityType.CUSTOMER_NUMBER, verified_only=True)
    right_verified_customers = _collect_identities(right, IdentityType.CUSTOMER_NUMBER, verified_only=True)
    if left_verified_customers and right_verified_customers:
        left_by_source = {
            (item.source_type, item.source_key or ""): value
            for value, item in left_verified_customers
        }
        right_by_source = {
            (item.source_type, item.source_key or ""): value
            for value, item in right_verified_customers
        }
        shared_sources = set(left_by_source.keys()) & set(right_by_source.keys())
        conflict_found = False
        for source in shared_sources:
            if left_by_source[source] == right_by_source[source]:
                evidence.append(
                    MatchEvidence(
                        code=MatchEvidenceCode.VERIFIED_CUSTOMER_NUMBER,
                        score=_EVIDENCE_SCORES[MatchEvidenceCode.VERIFIED_CUSTOMER_NUMBER],
                        left_value=left_by_source[source],
                        right_value=right_by_source[source],
                        detail=str(source),
                    )
                )
            else:
                conflict_found = True
                conflicts.append(
                    MatchConflict(
                        code=MatchConflictCode.DIFFERENT_VERIFIED_CUSTOMER_NUMBER,
                        left_value=left_by_source[source],
                        right_value=right_by_source[source],
                        detail=str(source),
                    )
                )
        if conflict_found:
            reason_codes.append(MatchReasonCode.CUSTOMER_NUMBER_CONFLICT)
            return _blocked_assessment(tenant_id, conflicts, reason_codes)

    # Email
    left_emails = _collect_identities(left, IdentityType.EMAIL, verified_only=False)
    right_emails = _collect_identities(right, IdentityType.EMAIL, verified_only=False)
    shared_emails = {value for value, _ in left_emails} & {value for value, _ in right_emails}
    role_based_without_company = False
    if shared_emails:
        evidence.append(
            MatchEvidence(
                code=MatchEvidenceCode.NORMALIZED_EMAIL,
                score=_EVIDENCE_SCORES[MatchEvidenceCode.NORMALIZED_EMAIL],
                left_value=next(iter(shared_emails)),
                right_value=next(iter(shared_emails)),
            )
        )
        for value, item in left_emails + right_emails:
            if value in shared_emails and item.is_role_based_email:
                if not left.company_relation_id and not right.company_relation_id:
                    if not left.verified_company_name and not right.verified_company_name:
                        role_based_without_company = True

    # Phone
    left_phones = _collect_identities(left, IdentityType.PHONE, verified_only=False)
    right_phones = _collect_identities(right, IdentityType.PHONE, verified_only=False)
    shared_phones = {value for value, _ in left_phones} & {value for value, _ in right_phones}
    phone_name_mismatch = False
    if shared_phones:
        evidence.append(
            MatchEvidence(
                code=MatchEvidenceCode.NORMALIZED_PHONE,
                score=_EVIDENCE_SCORES[MatchEvidenceCode.NORMALIZED_PHONE],
                left_value=next(iter(shared_phones)),
                right_value=next(iter(shared_phones)),
            )
        )
        left_name = normalize_name(left.verified_display_name or left.display_name)
        right_name = normalize_name(right.verified_display_name or right.display_name)
        if left_name and right_name and left_name != right_name:
            phone_name_mismatch = True

    # Gmail thread within integration context
    if (
        left.gmail_thread_id
        and right.gmail_thread_id
        and left.gmail_thread_id == right.gmail_thread_id
        and left.integration_type
        and right.integration_type
        and left.integration_account_reference
        and right.integration_account_reference
        and left.integration_type == right.integration_type
        and left.integration_account_reference == right.integration_account_reference
    ):
        evidence.append(
            MatchEvidence(
                code=MatchEvidenceCode.GMAIL_THREAD,
                score=_EVIDENCE_SCORES[MatchEvidenceCode.GMAIL_THREAD],
                left_value=left.gmail_thread_id,
                right_value=right.gmail_thread_id,
            )
        )

    # Company relation
    if (
        left.company_relation_id
        and right.company_relation_id
        and left.company_relation_id == right.company_relation_id
    ):
        evidence.append(
            MatchEvidence(
                code=MatchEvidenceCode.COMPANY_RELATION,
                score=_EVIDENCE_SCORES[MatchEvidenceCode.COMPANY_RELATION],
                left_value=left.company_relation_id,
                right_value=right.company_relation_id,
            )
        )

    # Address
    left_address = normalize_structured_address(left.structured_address)
    right_address = normalize_structured_address(right.structured_address)
    if left_address and right_address and left_address == right_address:
        evidence.append(
            MatchEvidence(
                code=MatchEvidenceCode.STRUCTURED_ADDRESS,
                score=_EVIDENCE_SCORES[MatchEvidenceCode.STRUCTURED_ADDRESS],
                left_value=left_address,
                right_value=right_address,
            )
        )

    # Name (weak)
    left_name = normalize_name(left.verified_display_name or left.display_name)
    right_name = normalize_name(right.verified_display_name or right.display_name)
    if left_name and right_name and left_name == right_name:
        evidence.append(
            MatchEvidence(
                code=MatchEvidenceCode.NORMALIZED_NAME,
                score=_EVIDENCE_SCORES[MatchEvidenceCode.NORMALIZED_NAME],
                left_value=left_name,
                right_value=right_name,
            )
        )

    # Historical verified contact conflict (e.g. changed phone)
    historical_conflict = False
    for current_side, other_side in ((left, right), (right, left)):
        current_phones = {
            value for value, _ in _collect_identities(current_side, IdentityType.PHONE, verified_only=False)
        }
        historical_items = list(other_side.identities) + list(other_side.historical_identities)
        for item in historical_items:
            if item.identity_type != IdentityType.PHONE:
                continue
            if item.verification_status != VerificationStatus.VERIFIED:
                continue
            hist_value = _identity_normalized(item, IdentityType.PHONE)
            if hist_value and current_phones and hist_value not in current_phones:
                historical_conflict = True

    evidence = _sort_evidence(evidence)
    confidence = min(1.0, sum(item.score for item in evidence))

    email_company_mismatch = False
    if shared_emails:
        left_company = normalize_name(left.verified_company_name)
        right_company = normalize_name(right.verified_company_name)
        if left_company and right_company and left_company != right_company:
            email_company_mismatch = True

    strong_codes = frozenset(
        {
            MatchEvidenceCode.VERIFIED_ORGANIZATION_NUMBER,
            MatchEvidenceCode.VERIFIED_CUSTOMER_NUMBER,
            MatchEvidenceCode.NORMALIZED_EMAIL,
            MatchEvidenceCode.NORMALIZED_PHONE,
            MatchEvidenceCode.GMAIL_THREAD,
            MatchEvidenceCode.COMPANY_RELATION,
        }
    )
    has_strong_identity = any(item.code in strong_codes for item in evidence)
    name_only = (
        len(evidence) == 1 and evidence[0].code == MatchEvidenceCode.NORMALIZED_NAME
    )
    address_only = (
        len(evidence) == 1
        and evidence[0].code == MatchEvidenceCode.STRUCTURED_ADDRESS
        and not has_strong_identity
    )

    manual_review_flags = False
    if phone_name_mismatch:
        reason_codes.append(MatchReasonCode.PHONE_NAME_MISMATCH_REVIEW)
        manual_review_flags = True
        confidence = min(confidence, 0.74)
    if email_company_mismatch:
        reason_codes.append(MatchReasonCode.EMAIL_COMPANY_MISMATCH_REVIEW)
        manual_review_flags = True
        confidence = min(confidence, 0.74)
    if role_based_without_company:
        reason_codes.append(MatchReasonCode.ROLE_BASED_EMAIL_REVIEW)
        manual_review_flags = True
        confidence = min(confidence, 0.74)
    if historical_conflict:
        reason_codes.append(MatchReasonCode.HISTORICAL_CONTACT_CONFLICT)
        manual_review_flags = True
        confidence = min(confidence, 0.74)
    if name_only:
        reason_codes.append(MatchReasonCode.NAME_ONLY_WEAK_SIGNAL)
        confidence = min(confidence, 0.49)
    if address_only:
        reason_codes.append(MatchReasonCode.ADDRESS_ONLY_WEAK_SIGNAL)
        confidence = min(confidence, 0.49)

    if name_only or address_only:
        decision = MatchDecision.NO_MATCH
    elif manual_review_flags:
        decision = MatchDecision.MANUAL_REVIEW_REQUIRED
    else:
        decision = _decision_from_confidence(confidence)

    requires_manual_review = decision not in {
        MatchDecision.BLOCKED,
        MatchDecision.NO_MATCH,
    }

    if decision == MatchDecision.EXACT_CANDIDATE:
        reason_codes.append(MatchReasonCode.EXACT_MATCH_REVIEW_REQUIRED)
    elif decision == MatchDecision.STRONG_CANDIDATE:
        reason_codes.append(MatchReasonCode.STRONG_MATCH_REVIEW_REQUIRED)
    elif decision in {
        MatchDecision.POSSIBLE_DUPLICATE,
        MatchDecision.MANUAL_REVIEW_REQUIRED,
    }:
        reason_codes.append(MatchReasonCode.STRONG_MATCH_REVIEW_REQUIRED)
    elif decision == MatchDecision.NO_MATCH:
        reason_codes.append(MatchReasonCode.CONFIDENCE_BELOW_THRESHOLD)

    reason_codes = sorted(set(reason_codes), key=lambda code: code.value)

    return CustomerMatchAssessment(
        tenant_id=tenant_id,
        decision=decision,
        confidence=confidence,
        evidence=evidence,
        conflicts=conflicts,
        reason_codes=reason_codes,
        requires_manual_review=requires_manual_review,
        automatic_link_allowed=False,
        automatic_merge_allowed=False,
    )


def _blocked_assessment(
    tenant_id: str,
    conflicts: list[MatchConflict],
    reason_codes: list[MatchReasonCode],
) -> CustomerMatchAssessment:
    sorted_conflicts = sorted(conflicts, key=lambda item: item.code.value)
    sorted_reasons = sorted(set(reason_codes), key=lambda code: code.value)
    return CustomerMatchAssessment(
        tenant_id=tenant_id,
        decision=MatchDecision.BLOCKED,
        confidence=0.0,
        evidence=[],
        conflicts=sorted_conflicts,
        reason_codes=sorted_reasons,
        requires_manual_review=False,
        automatic_link_allowed=False,
        automatic_merge_allowed=False,
    )


def _sort_evidence(evidence: list[MatchEvidence]) -> list[MatchEvidence]:
    return sorted(evidence, key=lambda item: (-item.score, item.code.value))
