"""Isolated API request/response contracts — no FastAPI or auth imports."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.customer.enums import (
    CustomerErrorCode,
    CustomerStatus,
    CustomerType,
    DuplicateStatus,
    EntityOwnerType,
    FactState,
    IdentityType,
    LinkType,
    MatchDecision,
    MergeDecisionType,
    ReferenceType,
    RelationshipType,
    SourceType,
    TimelineEventType,
    VerificationStatus,
)
from app.domain.customer.schemas import (
    CustomerCard,
    CustomerJobLink,
    CustomerThreadLink,
    CustomerTimelineEvent,
    CustomerDuplicateCandidate,
    MatchEvidence,
    MatchConflict,
)

DEFAULT_LIST_LIMIT = 50
MAX_LIST_LIMIT = 100
MIN_SEARCH_QUERY_LENGTH = 2
ALLOWED_LIST_SORT_FIELDS = frozenset({"created_at", "display_name"})


class CustomerApiPagination(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT)
    offset: int = Field(default=0, ge=0)


class CustomerErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: CustomerErrorCode
    message: str
    details: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class EndCustomerListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: str
    customer_type: CustomerType
    display_name: str
    status: CustomerStatus
    open_conflict_count: int = Field(ge=0, default=0)
    duplicate_status: DuplicateStatus | None = None
    last_activity_at: datetime | None = None
    version: int = Field(ge=1, default=1)


class EndCustomerListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[EndCustomerListItem] = Field(default_factory=list)
    total: int = Field(ge=0, default=0)
    limit: int = Field(ge=1, le=MAX_LIST_LIMIT)
    offset: int = Field(ge=0, default=0)


class EndCustomerCardResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    card: CustomerCard


class EndCustomerListItemView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: str
    customer_type: CustomerType
    display_name: str
    status: CustomerStatus
    version: int = Field(ge=1, default=1)
    created_at: datetime
    updated_at: datetime
    last_activity_at: datetime | None = None


class EndCustomerListViewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[EndCustomerListItemView] = Field(default_factory=list)
    total: int = Field(ge=0, default=0)
    limit: int = Field(ge=1, le=MAX_LIST_LIMIT)
    offset: int = Field(ge=0, default=0)


class EndCustomerCardCompanyView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_id: str | None = None
    display_name: str | None = None
    organization_number: str | None = None


class EndCustomerCardContactView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contact_id: str | None = None
    display_name: str | None = None
    email: str | None = None
    phone: str | None = None


class EndCustomerCardView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: str = Field(min_length=1)
    customer_type: CustomerType
    display_name: str = Field(min_length=1)
    status: CustomerStatus
    primary_company: EndCustomerCardCompanyView | None = None
    primary_contact: EndCustomerCardContactView | None = None
    open_conflict_count: int = Field(ge=0, default=0)
    linked_job_count: int = Field(ge=0, default=0)
    linked_thread_count: int = Field(ge=0, default=0)
    duplicate_status: DuplicateStatus | None = None
    data_quality_score: float | None = Field(default=None, ge=0.0, le=1.0)
    last_activity_at: datetime | None = None
    version: int = Field(ge=1, default=1)
    created_at: datetime
    updated_at: datetime


class SafeCustomerIdentityView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity_id: str
    owner_type: EntityOwnerType
    owner_id: str
    identity_type: IdentityType
    raw_value: str
    verification_status: VerificationStatus
    fact_state: FactState


class EndCustomerCardDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    card: EndCustomerCardView
    identities: list[SafeCustomerIdentityView] = Field(default_factory=list)


class EndCustomerTimelineEventView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeline_event_id: str
    customer_id: str
    event_type: TimelineEventType
    occurred_at: datetime
    recorded_at: datetime
    actor_type: str | None = None
    actor_id: str | None = None
    source_type: SourceType | None = None
    reference_type: ReferenceType | None = None
    reference_id: str | None = None
    summary: str
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class TimelineViewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: str
    items: list[EndCustomerTimelineEventView] = Field(default_factory=list)
    total: int = Field(ge=0, default=0)
    limit: int = Field(ge=1, le=MAX_LIST_LIMIT)
    offset: int = Field(ge=0, default=0)


class EndCustomerJobSummaryView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    job_type: str
    status: str
    created_at: datetime
    updated_at: datetime


class EndCustomerJobLinkView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    link_id: str
    customer_id: str
    job_id: str
    link_type: LinkType
    confidence: float = Field(ge=0.0, le=1.0)
    source_type: SourceType
    created_at: datetime
    created_by: str | None = None
    job_exists: bool = False
    job_summary: EndCustomerJobSummaryView | None = None


class LinkedJobsViewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: str
    items: list[EndCustomerJobLinkView] = Field(default_factory=list)
    total: int = Field(ge=0, default=0)
    limit: int = Field(ge=1, le=MAX_LIST_LIMIT)
    offset: int = Field(ge=0, default=0)


class EndCustomerThreadLinkView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    link_id: str
    customer_id: str
    integration_type: str
    integration_account_reference: str
    thread_id: str
    link_type: LinkType
    confidence: float = Field(ge=0.0, le=1.0)
    source_type: SourceType
    created_at: datetime


class LinkedThreadsViewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: str
    items: list[EndCustomerThreadLinkView] = Field(default_factory=list)
    total: int = Field(ge=0, default=0)
    limit: int = Field(ge=1, le=MAX_LIST_LIMIT)
    offset: int = Field(ge=0, default=0)


class DuplicateCandidateView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    left_customer_id: str
    right_customer_id: str
    status: DuplicateStatus
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[MatchEvidence] = Field(default_factory=list)
    conflicts: list[MatchConflict] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    version: int = Field(ge=1, default=1)


class DuplicateCandidateListViewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[DuplicateCandidateView] = Field(default_factory=list)
    total: int = Field(ge=0, default=0)
    limit: int = Field(ge=1, le=MAX_LIST_LIMIT)
    offset: int = Field(ge=0, default=0)


class CreatePrivateEndCustomerRequest(BaseModel):
    """Tenant write — tenant_id resolved server-side from auth."""

    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1)
    given_name: str | None = None
    family_name: str | None = None
    email: str | None = None
    phone: str | None = None
    reason: str | None = None


class CreateCompanyEndCustomerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_legal_name: str = Field(min_length=1)
    company_display_name: str | None = None
    organization_number: str | None = None
    primary_contact_display_name: str = Field(min_length=1)
    primary_contact_email: str | None = None
    primary_contact_phone: str | None = None
    reason: str | None = None


class CreateEndCustomerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_type: CustomerType
    private: CreatePrivateEndCustomerRequest | None = None
    company: CreateCompanyEndCustomerRequest | None = None
    expected_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_shape(self) -> CreateEndCustomerRequest:
        if self.customer_type == CustomerType.PRIVATE:
            if self.private is None:
                raise ValueError("private payload required for private customer")
            if self.company is not None:
                raise ValueError("company payload not allowed for private customer")
        elif self.customer_type in {CustomerType.COMPANY, CustomerType.ASSOCIATION}:
            if self.company is None:
                raise ValueError("company payload required for company customer")
            if self.private is not None:
                raise ValueError("private payload not allowed for company customer")
        return self


class UpdateVerifiedFactRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_type: EntityOwnerType
    subject_id: str = Field(min_length=1)
    field_name: str = Field(min_length=1)
    raw_value: str = Field(min_length=1)
    normalized_value: str | None = None
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1)
    supersedes_fact_id: str | None = None

    @model_validator(mode="after")
    def subject_must_be_end_customer_entity(self) -> UpdateVerifiedFactRequest:
        if self.subject_type not in {
            EntityOwnerType.CUSTOMER,
            EntityOwnerType.COMPANY,
            EntityOwnerType.CONTACT,
        }:
            raise ValueError("subject_type must be customer, company, or contact")
        return self


class AddContactRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1)
    given_name: str | None = None
    family_name: str | None = None
    title: str | None = None
    email: str | None = None
    phone: str | None = None
    relationship_type: RelationshipType = RelationshipType.PRIMARY_CONTACT
    is_primary: bool = False
    expected_version: int = Field(ge=1)
    reason: str | None = None


class TimelineResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: str
    items: list[CustomerTimelineEvent] = Field(default_factory=list)
    total: int = Field(ge=0, default=0)


class LinkedJobsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: str
    items: list[CustomerJobLink] = Field(default_factory=list)
    total: int = Field(ge=0, default=0)


class LinkedThreadsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: str
    items: list[CustomerThreadLink] = Field(default_factory=list)
    total: int = Field(ge=0, default=0)


class DuplicateCandidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate: CustomerDuplicateCandidate


class DuplicateCandidateListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CustomerDuplicateCandidate] = Field(default_factory=list)
    total: int = Field(ge=0, default=0)
    limit: int = Field(ge=1, le=MAX_LIST_LIMIT)
    offset: int = Field(ge=0, default=0)


class DuplicateDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["reject_merge", "resolve_without_merge"]
    reason: str = Field(min_length=1)
    expected_version: int = Field(ge=1)

    @field_validator("decision")
    @classmethod
    def merge_not_allowed(cls, value: str) -> str:
        if value == MergeDecisionType.APPROVE_MERGE.value:
            raise ValueError("approve_merge is forbidden")
        return value


class EndCustomerSearchQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=MIN_SEARCH_QUERY_LENGTH)
    limit: int = Field(default=DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT)
    offset: int = Field(default=0, ge=0)
    exact_match: bool = False


class EndCustomerSearchResultItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: str
    display_name: str
    customer_type: CustomerType
    matched_field: str
    matched_value: str


class EndCustomerSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_scoped: bool = True
    items: list[EndCustomerSearchResultItem] = Field(default_factory=list)
    total: int = Field(ge=0, default=0)
    limit: int = Field(ge=1, le=MAX_LIST_LIMIT)
    offset: int = Field(ge=0, default=0)


class MatchProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    left_customer_id: str = Field(min_length=1)
    right_customer_id: str = Field(min_length=1)


class MatchProposalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    left_customer_id: str
    right_customer_id: str
    decision: MatchDecision
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[MatchEvidence] = Field(default_factory=list)
    conflicts: list[MatchConflict] = Field(default_factory=list)
    requires_manual_review: bool = True
    automatic_link_allowed: bool = False
    automatic_merge_allowed: bool = False

    @model_validator(mode="after")
    def automation_forbidden(self) -> MatchProposalResponse:
        if self.automatic_link_allowed or self.automatic_merge_allowed:
            raise ValueError("automatic link/merge must remain false")
        return self


class CustomerWriteHeaders(BaseModel):
    """Documented header contract for future mutations — not a runtime HTTP model."""

    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(min_length=1, max_length=128)
