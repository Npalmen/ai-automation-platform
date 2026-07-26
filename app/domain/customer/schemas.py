"""Isolated Pydantic contracts for the end-customer domain."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.customer.enums import (
    AddressType,
    CustomerStatus,
    CustomerType,
    DuplicateStatus,
    EntityOwnerType,
    FactState,
    IdentityType,
    LinkType,
    MatchConflictCode,
    MatchDecision,
    MatchEvidenceCode,
    MatchReasonCode,
    MergeDecisionType,
    ReferenceType,
    RelationshipType,
    SourceType,
    TimelineEventType,
    VerificationStatus,
)


def _require_tz_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError("timestamp must be timezone-aware")
    return value


class SourceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_type: ReferenceType
    reference_id: str = Field(min_length=1)
    source_type: SourceType | None = None
    label: str | None = None


class Customer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    customer_type: CustomerType
    status: CustomerStatus = CustomerStatus.ACTIVE
    display_name: str = Field(min_length=1)
    primary_company_id: str | None = None
    primary_contact_id: str | None = None
    version: int = Field(ge=1, default=1)
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_timestamps(cls, value: datetime) -> datetime:
        return _require_tz_aware(value)


class Company(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    legal_name: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    organization_number_fact_id: str | None = None
    status: CustomerStatus = CustomerStatus.ACTIVE
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_timestamps(cls, value: datetime) -> datetime:
        return _require_tz_aware(value)


class Contact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contact_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    given_name: str | None = None
    family_name: str | None = None
    display_name: str = Field(min_length=1)
    title: str | None = None
    status: CustomerStatus = CustomerStatus.ACTIVE
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_timestamps(cls, value: datetime) -> datetime:
        return _require_tz_aware(value)


class CustomerAddress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    address_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    owner_type: EntityOwnerType
    owner_id: str = Field(min_length=1)
    address_type: AddressType
    street: str | None = None
    postal_code: str | None = None
    city: str | None = None
    region: str | None = None
    country_code: str | None = None
    fact_state: FactState
    source_fact_id: str | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None

    @field_validator("valid_from", "valid_to")
    @classmethod
    def validate_optional_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        return _require_tz_aware(value)

    @model_validator(mode="after")
    def owner_must_be_addressable(self) -> CustomerAddress:
        if self.owner_type not in {
            EntityOwnerType.CUSTOMER,
            EntityOwnerType.COMPANY,
            EntityOwnerType.CONTACT,
        }:
            raise ValueError("owner_type must be customer, company, or contact for addresses")
        return self


class CustomerIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    owner_type: EntityOwnerType
    owner_id: str = Field(min_length=1)
    identity_type: IdentityType
    raw_value: str = Field(min_length=1)
    normalized_value: str | None = None
    fact_state: FactState
    verification_status: VerificationStatus
    source_fact_id: str | None = None
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None

    @field_validator("first_seen_at", "last_seen_at")
    @classmethod
    def validate_optional_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        return _require_tz_aware(value)

    @model_validator(mode="after")
    def verified_requires_normalized_value(self) -> CustomerIdentity:
        if self.verification_status == VerificationStatus.VERIFIED:
            if not self.normalized_value or not self.normalized_value.strip():
                raise ValueError("verified identity requires non-empty normalized_value")
        return self


class CustomerRelationship(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relationship_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    subject_type: EntityOwnerType
    subject_id: str = Field(min_length=1)
    relationship_type: RelationshipType
    is_primary: bool = False
    valid_from: datetime | None = None
    valid_to: datetime | None = None

    @field_validator("valid_from", "valid_to")
    @classmethod
    def validate_optional_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        return _require_tz_aware(value)


class CustomerSourceFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fact_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    subject_type: EntityOwnerType
    subject_id: str = Field(min_length=1)
    field_name: str = Field(min_length=1)
    raw_value: str | None = None
    normalized_value: str | None = None
    fact_state: FactState
    source_type: SourceType
    source_reference: SourceReference | None = None
    source_actor: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    observed_at: datetime | None = None
    recorded_at: datetime
    verified_at: datetime | None = None
    verified_by: str | None = None
    supersedes_fact_id: str | None = None
    conflicts_with_fact_ids: list[str] = Field(default_factory=list)

    @field_validator("observed_at", "recorded_at", "verified_at")
    @classmethod
    def validate_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        return _require_tz_aware(value)

    @model_validator(mode="after")
    def no_self_supersedes(self) -> CustomerSourceFact:
        if self.supersedes_fact_id and self.supersedes_fact_id == self.fact_id:
            raise ValueError("supersedes_fact_id cannot reference self")
        return self


class CustomerTimelineEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeline_event_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    event_type: TimelineEventType
    occurred_at: datetime
    recorded_at: datetime
    actor_type: str | None = None
    actor_id: str | None = None
    source_type: SourceType | None = None
    reference_type: ReferenceType | None = None
    reference_id: str | None = None
    summary: str = Field(min_length=1)
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    @field_validator("occurred_at", "recorded_at")
    @classmethod
    def validate_timestamps(cls, value: datetime) -> datetime:
        return _require_tz_aware(value)


class CustomerJobLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    link_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    link_type: LinkType
    confidence: float = Field(ge=0.0, le=1.0)
    source_type: SourceType
    created_at: datetime
    created_by: str | None = None

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return _require_tz_aware(value)


class CustomerThreadLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    link_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    integration_type: str = Field(min_length=1)
    integration_account_reference: str = Field(min_length=1)
    thread_id: str = Field(min_length=1)
    link_type: LinkType
    confidence: float = Field(ge=0.0, le=1.0)
    source_type: SourceType
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return _require_tz_aware(value)


class MatchEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: MatchEvidenceCode
    score: float = Field(ge=0.0, le=1.0)
    left_value: str | None = None
    right_value: str | None = None
    detail: str | None = None


class MatchConflict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: MatchConflictCode
    detail: str | None = None
    left_value: str | None = None
    right_value: str | None = None


class CustomerDuplicateCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    left_customer_id: str = Field(min_length=1)
    right_customer_id: str = Field(min_length=1)
    status: DuplicateStatus = DuplicateStatus.OPEN
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[MatchEvidence] = Field(default_factory=list)
    conflicts: list[MatchConflict] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    version: int = Field(ge=1, default=1)

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_timestamps(cls, value: datetime) -> datetime:
        return _require_tz_aware(value)


class CustomerMergeDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    decision: MergeDecisionType
    survivor_customer_id: str = Field(min_length=1)
    merged_customer_id: str = Field(min_length=1)
    reason: str | None = None
    actor_type: str | None = None
    actor_id: str | None = None
    expected_version: int = Field(ge=1)
    decided_at: datetime

    @field_validator("decided_at")
    @classmethod
    def validate_decided_at(cls, value: datetime) -> datetime:
        return _require_tz_aware(value)


class CustomerCardContactSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contact_id: str | None = None
    display_name: str | None = None
    email: str | None = None
    phone: str | None = None


class CustomerCardCompanySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_id: str | None = None
    display_name: str | None = None
    organization_number: str | None = None


class CustomerCard(BaseModel):
    """Read projection — no raw job, Gmail, or action payloads."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    customer_type: CustomerType
    display_name: str = Field(min_length=1)
    status: CustomerStatus
    primary_company: CustomerCardCompanySummary | None = None
    primary_contact: CustomerCardContactSummary | None = None
    open_conflict_count: int = Field(ge=0, default=0)
    linked_job_count: int = Field(ge=0, default=0)
    linked_thread_count: int = Field(ge=0, default=0)
    duplicate_status: DuplicateStatus | None = None
    data_quality_score: float | None = Field(default=None, ge=0.0, le=1.0)
    last_activity_at: datetime | None = None
    version: int = Field(ge=1, default=1)

    @field_validator("last_activity_at")
    @classmethod
    def validate_last_activity(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        return _require_tz_aware(value)


class IdentityMatchItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity_type: IdentityType
    raw_value: str = Field(min_length=1)
    normalized_value: str | None = None
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    source_type: SourceType | None = None
    source_key: str | None = None
    is_role_based_email: bool = False


class StructuredAddressInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    street: str | None = None
    postal_code: str | None = None
    city: str | None = None
    region: str | None = None
    country_code: str | None = None


class CustomerMatchSubject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    owner_type: EntityOwnerType
    customer_type: CustomerType | None = None
    display_name: str | None = None
    verified_display_name: str | None = None
    verified_company_name: str | None = None
    identities: list[IdentityMatchItem] = Field(default_factory=list)
    historical_identities: list[IdentityMatchItem] = Field(default_factory=list)
    structured_address: StructuredAddressInput | None = None
    gmail_thread_id: str | None = None
    integration_type: str | None = None
    integration_account_reference: str | None = None
    company_relation_id: str | None = None


class CustomerMatchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    left: CustomerMatchSubject
    right: CustomerMatchSubject


class CustomerMatchAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1)
    decision: MatchDecision
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[MatchEvidence] = Field(default_factory=list)
    conflicts: list[MatchConflict] = Field(default_factory=list)
    reason_codes: list[MatchReasonCode] = Field(default_factory=list)
    requires_manual_review: bool = False
    automatic_link_allowed: bool = False
    automatic_merge_allowed: bool = False

    @model_validator(mode="after")
    def automation_flags_must_be_false(self) -> CustomerMatchAssessment:
        if self.automatic_link_allowed or self.automatic_merge_allowed:
            raise ValueError("automatic_link_allowed and automatic_merge_allowed must be false")
        return self
