"""Isolated customer domain enums — no runtime imports."""

from enum import Enum


class CustomerType(str, Enum):
    PRIVATE = "private"
    COMPANY = "company"
    ASSOCIATION = "association"
    UNKNOWN = "unknown"


class CustomerStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    MERGED = "merged"
    ARCHIVED = "archived"


class EntityOwnerType(str, Enum):
    CUSTOMER = "customer"
    COMPANY = "company"
    CONTACT = "contact"
    TENANT_ACCOUNT = "tenant_account"


class IdentityType(str, Enum):
    EMAIL = "email"
    PHONE = "phone"
    ORGANIZATION_NUMBER = "organization_number"
    CUSTOMER_NUMBER = "customer_number"
    EXTERNAL_ID = "external_id"
    GMAIL_THREAD = "gmail_thread"
    GMAIL_MESSAGE = "gmail_message"
    OTHER = "other"


class RelationshipType(str, Enum):
    PRIVATE_CUSTOMER = "private_customer"
    CUSTOMER_COMPANY = "customer_company"
    PRIMARY_CONTACT = "primary_contact"
    BILLING_CONTACT = "billing_contact"
    TECHNICAL_CONTACT = "technical_contact"
    SITE_CONTACT = "site_contact"
    FORMER_CONTACT = "former_contact"
    OTHER = "other"


class AddressType(str, Enum):
    VISIT = "visit"
    BILLING = "billing"
    DELIVERY = "delivery"
    REGISTERED = "registered"
    OTHER = "other"


class FactState(str, Enum):
    KNOWN = "known"
    PROPOSED = "proposed"
    VERIFIED = "verified"
    CONFLICTING = "conflicting"
    HISTORICAL = "historical"
    REJECTED = "rejected"


class SourceType(str, Enum):
    GMAIL_INBOUND = "gmail_inbound"
    USER_INPUT = "user_input"
    INTEGRATION = "integration"
    IMPORT = "import"
    AI_EXTRACTION = "ai_extraction"
    ADMIN_CORRECTION = "admin_correction"
    SYSTEM_DERIVED = "system_derived"


class VerificationStatus(str, Enum):
    UNVERIFIED = "unverified"
    PROPOSED = "proposed"
    VERIFIED = "verified"
    REJECTED = "rejected"


class MatchDecision(str, Enum):
    BLOCKED = "blocked"
    NO_MATCH = "no_match"
    POSSIBLE_DUPLICATE = "possible_duplicate"
    STRONG_CANDIDATE = "strong_candidate"
    EXACT_CANDIDATE = "exact_candidate"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"


class DuplicateStatus(str, Enum):
    OPEN = "open"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    RESOLVED_WITHOUT_MERGE = "resolved_without_merge"


class MergeDecisionType(str, Enum):
    APPROVE_MERGE = "approve_merge"
    REJECT_MERGE = "reject_merge"
    RESOLVE_WITHOUT_MERGE = "resolve_without_merge"


class TimelineEventType(str, Enum):
    FIRST_CONTACT = "first_contact"
    GMAIL_MESSAGE_RECEIVED = "gmail_message_received"
    GMAIL_THREAD_LINKED = "gmail_thread_linked"
    JOB_CREATED = "job_created"
    JOB_CLASSIFIED = "job_classified"
    JOB_STATUS_CHANGED = "job_status_changed"
    APPROVAL_CREATED = "approval_created"
    APPROVAL_DECIDED = "approval_decided"
    REPLY_PREPARED = "reply_prepared"
    REPLY_SENT = "reply_sent"
    EXTERNAL_ACTION_REQUESTED = "external_action_requested"
    EXTERNAL_ACTION_COMPLETED = "external_action_completed"
    EXTERNAL_ACTION_FAILED = "external_action_failed"
    NOTE_ADDED = "note_added"
    CONTACT_FACT_PROPOSED = "contact_fact_proposed"
    CONTACT_FACT_VERIFIED = "contact_fact_verified"
    CONTACT_FACT_CHANGED = "contact_fact_changed"
    CONTACT_FACT_CONFLICT = "contact_fact_conflict"
    DUPLICATE_CANDIDATE_CREATED = "duplicate_candidate_created"
    DUPLICATE_CANDIDATE_REJECTED = "duplicate_candidate_rejected"
    MERGE_APPROVED = "merge_approved"
    MERGE_COMPLETED = "merge_completed"
    SUPPORT_CASE_LINKED = "support_case_linked"
    INVOICE_LINKED = "invoice_linked"
    ECONOMIC_EVENT_LINKED = "economic_event_linked"


class ReferenceType(str, Enum):
    JOB = "job"
    GMAIL_THREAD = "gmail_thread"
    GMAIL_MESSAGE = "gmail_message"
    APPROVAL = "approval"
    ACTION_EXECUTION = "action_execution"
    INTEGRATION_EVENT = "integration_event"
    INVOICE_REFERENCE = "invoice_reference"
    SOURCE_FACT = "source_fact"
    CUSTOMER = "customer"
    COMPANY = "company"
    CONTACT = "contact"
    OTHER = "other"


class LinkType(str, Enum):
    PRIMARY = "primary"
    RELATED = "related"
    DERIVED = "derived"
    MANUAL = "manual"


class MatchEvidenceCode(str, Enum):
    VERIFIED_ORGANIZATION_NUMBER = "verified_organization_number"
    VERIFIED_CUSTOMER_NUMBER = "verified_customer_number"
    NORMALIZED_EMAIL = "normalized_email"
    NORMALIZED_PHONE = "normalized_phone"
    GMAIL_THREAD = "gmail_thread"
    COMPANY_RELATION = "company_relation"
    STRUCTURED_ADDRESS = "structured_address"
    NORMALIZED_NAME = "normalized_name"


class MatchConflictCode(str, Enum):
    CROSS_TENANT = "cross_tenant"
    TENANT_ACCOUNT_VS_END_CUSTOMER = "tenant_account_vs_end_customer"
    PERSON_VS_COMPANY = "person_vs_company"
    DIFFERENT_VERIFIED_ORGANIZATION_NUMBER = "different_verified_organization_number"
    DIFFERENT_VERIFIED_CUSTOMER_NUMBER = "different_verified_customer_number"
    MISSING_TENANT = "missing_tenant"
    INVALID_MATCH_INPUT = "invalid_match_input"


class MatchReasonCode(str, Enum):
    CROSS_TENANT_BLOCKED = "cross_tenant_blocked"
    TENANT_ACCOUNT_BLOCKED = "tenant_account_blocked"
    PERSON_COMPANY_BLOCKED = "person_company_blocked"
    ORG_NUMBER_CONFLICT = "org_number_conflict"
    CUSTOMER_NUMBER_CONFLICT = "customer_number_conflict"
    MISSING_TENANT = "missing_tenant"
    ROLE_BASED_EMAIL_REVIEW = "role_based_email_review"
    PHONE_NAME_MISMATCH_REVIEW = "phone_name_mismatch_review"
    EMAIL_COMPANY_MISMATCH_REVIEW = "email_company_mismatch_review"
    NAME_ONLY_WEAK_SIGNAL = "name_only_weak_signal"
    ADDRESS_ONLY_WEAK_SIGNAL = "address_only_weak_signal"
    HISTORICAL_CONTACT_CONFLICT = "historical_contact_conflict"
    CONFIDENCE_BELOW_THRESHOLD = "confidence_below_threshold"
    STRONG_MATCH_REVIEW_REQUIRED = "strong_match_review_required"
    EXACT_MATCH_REVIEW_REQUIRED = "exact_match_review_required"


class CustomerErrorCode(str, Enum):
    CUSTOMER_NOT_FOUND = "CUSTOMER_NOT_FOUND"
    CUSTOMER_VERSION_CONFLICT = "CUSTOMER_VERSION_CONFLICT"
    TENANT_SCOPE_VIOLATION = "TENANT_SCOPE_VIOLATION"
    INVALID_CUSTOMER_IDENTITY = "INVALID_CUSTOMER_IDENTITY"
    INVALID_SOURCE_PROVENANCE = "INVALID_SOURCE_PROVENANCE"
    CUSTOMER_RELATIONSHIP_CONFLICT = "CUSTOMER_RELATIONSHIP_CONFLICT"
    DUPLICATE_REVIEW_REQUIRED = "DUPLICATE_REVIEW_REQUIRED"
    DUPLICATE_CANDIDATE_NOT_FOUND = "DUPLICATE_CANDIDATE_NOT_FOUND"
    DUPLICATE_DECISION_CONFLICT = "DUPLICATE_DECISION_CONFLICT"
    AUTOMATIC_MERGE_FORBIDDEN = "AUTOMATIC_MERGE_FORBIDDEN"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    UNSUPPORTED_CUSTOMER_TRANSITION = "UNSUPPORTED_CUSTOMER_TRANSITION"
    DUPLICATE_TIMELINE_EVENT = "DUPLICATE_TIMELINE_EVENT"
    INVALID_TIMELINE_METADATA = "INVALID_TIMELINE_METADATA"


class ActorType(str, Enum):
    SYSTEM = "system"
    OPERATOR = "operator"
    TENANT_USER = "tenant_user"
    INTEGRATION = "integration"
    AI = "ai"
