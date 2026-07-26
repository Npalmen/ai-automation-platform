"""Read-only projection service for end-customer API — no writes or commits."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.domain.customer.api_schemas import (
    ALLOWED_LIST_SORT_FIELDS,
    DEFAULT_LIST_LIMIT,
    DuplicateCandidateListViewResponse,
    DuplicateCandidateView,
    EndCustomerCardCompanyView,
    EndCustomerCardContactView,
    EndCustomerCardDetailResponse,
    EndCustomerCardView,
    EndCustomerJobLinkView,
    EndCustomerJobSummaryView,
    EndCustomerListItemView,
    EndCustomerListViewResponse,
    EndCustomerSearchResponse,
    EndCustomerSearchResultItem,
    EndCustomerThreadLinkView,
    EndCustomerTimelineEventView,
    LinkedJobsViewResponse,
    LinkedThreadsViewResponse,
    MAX_LIST_LIMIT,
    MIN_SEARCH_QUERY_LENGTH,
    SafeCustomerIdentityView,
    TimelineViewResponse,
)
from app.domain.customer.enums import (
    CustomerStatus,
    CustomerType,
    DuplicateStatus,
    EntityOwnerType,
    IdentityType,
    MatchConflictCode,
    MatchEvidenceCode,
)
from app.domain.customer.normalization import (
    normalize_email,
    normalize_organization_number,
    normalize_phone,
)
from app.domain.customer.provenance import validate_timeline_metadata
from app.domain.customer.schemas import CustomerDuplicateCandidate, MatchConflict, MatchEvidence
from app.repositories.postgres.end_customer_repository import (
    EndCustomerNotFoundError,
    EndCustomerRepository,
)

_SAFE_IDENTITY_TYPES = frozenset(
    {
        IdentityType.EMAIL,
        IdentityType.PHONE,
        IdentityType.ORGANIZATION_NUMBER,
        IdentityType.CUSTOMER_NUMBER,
    }
)

_DIGITS_ONLY_RE = re.compile(r"^\d+$")


class EndCustomerReadValidationError(Exception):
    """Client input rejected before repository access."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        self.code = code
        self.message = message
        self.details = details or {}


class EndCustomerReadService:
    @staticmethod
    def _clamp_limit(limit: int) -> int:
        return min(max(limit, 1), MAX_LIST_LIMIT)

    @staticmethod
    def _clamp_offset(offset: int) -> int:
        return max(offset, 0)

    @staticmethod
    def _parse_status(value: str | None) -> CustomerStatus | None:
        if value is None:
            return None
        try:
            return CustomerStatus(value.strip().lower())
        except ValueError:
            raise EndCustomerReadValidationError(
                "INVALID_SEARCH_QUERY",
                "Invalid status filter.",
            ) from None

    @staticmethod
    def _parse_customer_type(value: str | None) -> CustomerType | None:
        if value is None:
            return None
        try:
            return CustomerType(value.strip().lower())
        except ValueError:
            raise EndCustomerReadValidationError(
                "INVALID_SEARCH_QUERY",
                "Invalid customer_type filter.",
            ) from None

    @staticmethod
    def _validate_sort(sort: str | None, order: str | None) -> tuple[str, str]:
        sort_field = (sort or "created_at").strip().lower()
        order_norm = (order or "desc").strip().lower()
        if sort_field not in ALLOWED_LIST_SORT_FIELDS:
            raise EndCustomerReadValidationError(
                "INVALID_SORT",
                "Invalid sort field.",
                {"allowed": ",".join(sorted(ALLOWED_LIST_SORT_FIELDS))},
            )
        if order_norm not in {"asc", "desc"}:
            raise EndCustomerReadValidationError(
                "INVALID_SORT",
                "Invalid sort order.",
                {"allowed": "asc,desc"},
            )
        return sort_field, order_norm

    @staticmethod
    def list_customers(
        db: Session,
        tenant_id: str,
        *,
        status: str | None = None,
        customer_type: str | None = None,
        sort: str | None = None,
        order: str | None = None,
        limit: int = DEFAULT_LIST_LIMIT,
        offset: int = 0,
    ) -> EndCustomerListViewResponse:
        status_enum = EndCustomerReadService._parse_status(status)
        type_enum = EndCustomerReadService._parse_customer_type(customer_type)
        sort_field, order_norm = EndCustomerReadService._validate_sort(sort, order)
        limit_val = EndCustomerReadService._clamp_limit(limit)
        offset_val = EndCustomerReadService._clamp_offset(offset)
        total = EndCustomerRepository.count_customers(
            db, tenant_id, status=status_enum, customer_type=type_enum
        )
        customers = EndCustomerRepository.list_customers(
            db,
            tenant_id,
            status=status_enum,
            customer_type=type_enum,
            sort=sort_field,
            order=order_norm,
            limit=limit_val,
            offset=offset_val,
        )
        items = [
            EndCustomerListItemView(
                customer_id=c.customer_id,
                customer_type=c.customer_type,
                display_name=c.display_name,
                status=c.status,
                version=c.version,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in customers
        ]
        return EndCustomerListViewResponse(
            items=items,
            total=total,
            limit=limit_val,
            offset=offset_val,
        )

    @staticmethod
    def _identity_value_for_owner(
        db: Session,
        tenant_id: str,
        owner_type: EntityOwnerType,
        owner_id: str,
        identity_type: IdentityType,
    ) -> str | None:
        identities = EndCustomerRepository.list_identities_for_owner(
            db, tenant_id, owner_type, owner_id
        )
        for identity in identities:
            if identity.identity_type == identity_type:
                return identity.raw_value
        return None

    @staticmethod
    def _build_company_view(
        db: Session,
        tenant_id: str,
        company_id: str | None,
    ) -> EndCustomerCardCompanyView | None:
        if not company_id:
            return None
        company = EndCustomerRepository.get_company(db, tenant_id, company_id)
        if company is None:
            return None
        org_number = EndCustomerReadService._identity_value_for_owner(
            db,
            tenant_id,
            EntityOwnerType.COMPANY,
            company_id,
            IdentityType.ORGANIZATION_NUMBER,
        )
        return EndCustomerCardCompanyView(
            company_id=company.company_id,
            display_name=company.display_name,
            organization_number=org_number,
        )

    @staticmethod
    def _build_contact_view(
        db: Session,
        tenant_id: str,
        contact_id: str | None,
    ) -> EndCustomerCardContactView | None:
        if not contact_id:
            return None
        contact = EndCustomerRepository.get_contact(db, tenant_id, contact_id)
        if contact is None:
            return None
        email = EndCustomerReadService._identity_value_for_owner(
            db,
            tenant_id,
            EntityOwnerType.CONTACT,
            contact_id,
            IdentityType.EMAIL,
        )
        phone = EndCustomerReadService._identity_value_for_owner(
            db,
            tenant_id,
            EntityOwnerType.CONTACT,
            contact_id,
            IdentityType.PHONE,
        )
        return EndCustomerCardContactView(
            contact_id=contact.contact_id,
            display_name=contact.display_name,
            email=email,
            phone=phone,
        )

    @staticmethod
    def _safe_identities(
        db: Session,
        tenant_id: str,
        customer_id: str,
        primary_company_id: str | None,
        primary_contact_id: str | None,
    ) -> list[SafeCustomerIdentityView]:
        owners: list[tuple[EntityOwnerType, str]] = [
            (EntityOwnerType.CUSTOMER, customer_id),
        ]
        if primary_company_id:
            owners.append((EntityOwnerType.COMPANY, primary_company_id))
        if primary_contact_id:
            owners.append((EntityOwnerType.CONTACT, primary_contact_id))
        seen: set[str] = set()
        result: list[SafeCustomerIdentityView] = []
        for owner_type, owner_id in owners:
            identities = EndCustomerRepository.list_identities_for_owner(
                db, tenant_id, owner_type, owner_id
            )
            for identity in identities:
                if identity.identity_type not in _SAFE_IDENTITY_TYPES:
                    continue
                if identity.identity_id in seen:
                    continue
                seen.add(identity.identity_id)
                result.append(
                    SafeCustomerIdentityView(
                        identity_id=identity.identity_id,
                        owner_type=identity.owner_type,
                        owner_id=identity.owner_id,
                        identity_type=identity.identity_type,
                        raw_value=identity.raw_value,
                        verification_status=identity.verification_status,
                        fact_state=identity.fact_state,
                    )
                )
        return result

    @staticmethod
    def get_customer_card(
        db: Session,
        tenant_id: str,
        customer_id: str,
    ) -> EndCustomerCardDetailResponse | None:
        customer = EndCustomerRepository.get_customer(db, tenant_id, customer_id)
        if customer is None:
            return None
        last_event = EndCustomerRepository.get_latest_timeline_event(
            db, tenant_id, customer_id
        )
        last_activity = last_event.occurred_at if last_event is not None else None
        card = EndCustomerCardView(
            customer_id=customer.customer_id,
            customer_type=customer.customer_type,
            display_name=customer.display_name,
            status=customer.status,
            primary_company=EndCustomerReadService._build_company_view(
                db, tenant_id, customer.primary_company_id
            ),
            primary_contact=EndCustomerReadService._build_contact_view(
                db, tenant_id, customer.primary_contact_id
            ),
            open_conflict_count=EndCustomerRepository.count_open_conflicts_for_customer(
                db, tenant_id, customer_id
            ),
            linked_job_count=EndCustomerRepository.count_job_links(
                db, tenant_id, customer_id
            ),
            linked_thread_count=EndCustomerRepository.count_thread_links(
                db, tenant_id, customer_id
            ),
            duplicate_status=EndCustomerRepository.get_duplicate_status_for_customer(
                db, tenant_id, customer_id
            ),
            data_quality_score=None,
            last_activity_at=last_activity,
            version=customer.version,
            created_at=customer.created_at,
            updated_at=customer.updated_at,
        )
        identities = EndCustomerReadService._safe_identities(
            db,
            tenant_id,
            customer_id,
            customer.primary_company_id,
            customer.primary_contact_id,
        )
        return EndCustomerCardDetailResponse(card=card, identities=identities)

    @staticmethod
    def _timeline_view(event: Any) -> EndCustomerTimelineEventView:
        metadata = validate_timeline_metadata(dict(event.metadata or {}))
        return EndCustomerTimelineEventView(
            timeline_event_id=event.timeline_event_id,
            customer_id=event.customer_id,
            event_type=event.event_type,
            occurred_at=event.occurred_at,
            recorded_at=event.recorded_at,
            actor_type=event.actor_type,
            actor_id=event.actor_id,
            source_type=event.source_type,
            reference_type=event.reference_type,
            reference_id=event.reference_id,
            summary=event.summary,
            metadata=metadata,
        )

    @staticmethod
    def list_timeline(
        db: Session,
        tenant_id: str,
        customer_id: str,
        limit: int = DEFAULT_LIST_LIMIT,
        offset: int = 0,
    ) -> TimelineViewResponse | None:
        if EndCustomerRepository.get_customer(db, tenant_id, customer_id) is None:
            return None
        limit_val = EndCustomerReadService._clamp_limit(limit)
        offset_val = EndCustomerReadService._clamp_offset(offset)
        total = EndCustomerRepository.count_timeline_events(db, tenant_id, customer_id)
        events = EndCustomerRepository.list_timeline_events_paginated(
            db, tenant_id, customer_id, limit=limit_val, offset=offset_val
        )
        return TimelineViewResponse(
            customer_id=customer_id,
            items=[EndCustomerReadService._timeline_view(e) for e in events],
            total=total,
            limit=limit_val,
            offset=offset_val,
        )

    @staticmethod
    def list_jobs(
        db: Session,
        tenant_id: str,
        customer_id: str,
        limit: int = DEFAULT_LIST_LIMIT,
        offset: int = 0,
    ) -> LinkedJobsViewResponse | None:
        if EndCustomerRepository.get_customer(db, tenant_id, customer_id) is None:
            return None
        limit_val = EndCustomerReadService._clamp_limit(limit)
        offset_val = EndCustomerReadService._clamp_offset(offset)
        total = EndCustomerRepository.count_job_links(db, tenant_id, customer_id)
        links = EndCustomerRepository.list_job_links(
            db, tenant_id, customer_id, limit=limit_val, offset=offset_val
        )
        job_ids = [link.job_id for link in links]
        job_map = EndCustomerRepository.get_job_records_for_tenant(
            db, tenant_id, job_ids
        )
        items: list[EndCustomerJobLinkView] = []
        for link in links:
            record = job_map.get(link.job_id)
            summary = None
            job_exists = record is not None
            if record is not None:
                summary = EndCustomerJobSummaryView(
                    job_id=record.job_id,
                    job_type=record.job_type,
                    status=record.status,
                    created_at=record.created_at,
                    updated_at=record.updated_at,
                )
            items.append(
                EndCustomerJobLinkView(
                    link_id=link.link_id,
                    customer_id=link.customer_id,
                    job_id=link.job_id,
                    link_type=link.link_type,
                    confidence=link.confidence,
                    source_type=link.source_type,
                    created_at=link.created_at,
                    created_by=link.created_by,
                    job_exists=job_exists,
                    job_summary=summary,
                )
            )
        return LinkedJobsViewResponse(
            customer_id=customer_id,
            items=items,
            total=total,
            limit=limit_val,
            offset=offset_val,
        )

    @staticmethod
    def list_threads(
        db: Session,
        tenant_id: str,
        customer_id: str,
        limit: int = DEFAULT_LIST_LIMIT,
        offset: int = 0,
    ) -> LinkedThreadsViewResponse | None:
        if EndCustomerRepository.get_customer(db, tenant_id, customer_id) is None:
            return None
        limit_val = EndCustomerReadService._clamp_limit(limit)
        offset_val = EndCustomerReadService._clamp_offset(offset)
        total = EndCustomerRepository.count_thread_links(db, tenant_id, customer_id)
        links = EndCustomerRepository.list_thread_links(
            db, tenant_id, customer_id, limit=limit_val, offset=offset_val
        )
        items = [
            EndCustomerThreadLinkView(
                link_id=link.link_id,
                customer_id=link.customer_id,
                integration_type=link.integration_type,
                integration_account_reference=link.integration_account_reference,
                thread_id=link.thread_id,
                link_type=link.link_type,
                confidence=link.confidence,
                source_type=link.source_type,
                created_at=link.created_at,
            )
            for link in links
        ]
        return LinkedThreadsViewResponse(
            customer_id=customer_id,
            items=items,
            total=total,
            limit=limit_val,
            offset=offset_val,
        )

    @staticmethod
    def _sanitize_evidence(raw_items: list[Any]) -> list[MatchEvidence]:
        cleaned: list[MatchEvidence] = []
        for item in raw_items:
            if isinstance(item, MatchEvidence):
                cleaned.append(item)
                continue
            if not isinstance(item, dict):
                continue
            code_raw = str(item.get("code", "")).strip()
            try:
                code = MatchEvidenceCode(code_raw)
            except ValueError:
                continue
            score = item.get("score", 0.0)
            try:
                score_val = float(score)
            except (TypeError, ValueError):
                score_val = 0.0
            cleaned.append(
                MatchEvidence(
                    code=code,
                    score=max(0.0, min(1.0, score_val)),
                    left_value=item.get("left_value") if isinstance(item.get("left_value"), str) else None,
                    right_value=item.get("right_value") if isinstance(item.get("right_value"), str) else None,
                    detail=item.get("detail") if isinstance(item.get("detail"), str) else None,
                )
            )
        return cleaned

    @staticmethod
    def _sanitize_conflicts(raw_items: list[Any]) -> list[MatchConflict]:
        cleaned: list[MatchConflict] = []
        for item in raw_items:
            if isinstance(item, MatchConflict):
                cleaned.append(item)
                continue
            if not isinstance(item, dict):
                continue
            code_raw = str(item.get("code", "")).strip()
            try:
                code = MatchConflictCode(code_raw)
            except ValueError:
                continue
            cleaned.append(
                MatchConflict(
                    code=code,
                    detail=item.get("detail") if isinstance(item.get("detail"), str) else None,
                    left_value=item.get("left_value") if isinstance(item.get("left_value"), str) else None,
                    right_value=item.get("right_value") if isinstance(item.get("right_value"), str) else None,
                )
            )
        return cleaned

    @staticmethod
    def _duplicate_view(candidate: CustomerDuplicateCandidate) -> DuplicateCandidateView:
        evidence = EndCustomerReadService._sanitize_evidence(list(candidate.evidence or []))
        conflicts = EndCustomerReadService._sanitize_conflicts(list(candidate.conflicts or []))
        return DuplicateCandidateView(
            candidate_id=candidate.candidate_id,
            left_customer_id=candidate.left_customer_id,
            right_customer_id=candidate.right_customer_id,
            status=candidate.status,
            confidence=candidate.confidence,
            evidence=evidence,
            conflicts=conflicts,
            created_at=candidate.created_at,
            updated_at=candidate.updated_at,
            version=candidate.version,
        )

    @staticmethod
    def list_duplicates(
        db: Session,
        tenant_id: str,
        limit: int = DEFAULT_LIST_LIMIT,
        offset: int = 0,
    ) -> DuplicateCandidateListViewResponse:
        limit_val = EndCustomerReadService._clamp_limit(limit)
        offset_val = EndCustomerReadService._clamp_offset(offset)
        total = EndCustomerRepository.count_open_duplicate_candidates(db, tenant_id)
        candidates = EndCustomerRepository.list_open_duplicate_candidates(
            db, tenant_id, limit=limit_val, offset=offset_val
        )
        items = [EndCustomerReadService._duplicate_view(c) for c in candidates]
        return DuplicateCandidateListViewResponse(
            items=items,
            total=total,
            limit=limit_val,
            offset=offset_val,
        )

    @staticmethod
    def _identity_search_candidates(query: str) -> list[tuple[IdentityType, str]]:
        candidates: list[tuple[IdentityType, str]] = []
        email = normalize_email(query)
        if email is not None:
            candidates.append((IdentityType.EMAIL, email[0]))
        phone = normalize_phone(query, "SE")
        if phone is not None:
            candidates.append((IdentityType.PHONE, phone))
        org = normalize_organization_number(query)
        if org is not None:
            candidates.append((IdentityType.ORGANIZATION_NUMBER, org))
        stripped = query.strip()
        if stripped and _DIGITS_ONLY_RE.match(stripped) and len(stripped) >= 4:
            candidates.append((IdentityType.CUSTOMER_NUMBER, stripped))
        return candidates

    @staticmethod
    def search(
        db: Session,
        tenant_id: str,
        query: str,
        limit: int = DEFAULT_LIST_LIMIT,
        offset: int = 0,
    ) -> EndCustomerSearchResponse:
        text = query.strip()
        if len(text) < MIN_SEARCH_QUERY_LENGTH:
            raise EndCustomerReadValidationError(
                "INVALID_SEARCH_QUERY",
                "Search query too short.",
                {"min_length": MIN_SEARCH_QUERY_LENGTH},
            )
        limit_val = EndCustomerReadService._clamp_limit(limit)
        offset_val = EndCustomerReadService._clamp_offset(offset)

        matched: dict[str, tuple[str, str]] = {}
        for identity_type, normalized in EndCustomerReadService._identity_search_candidates(text):
            identities = EndCustomerRepository.find_candidate_identities(
                db, tenant_id, identity_type, normalized
            )
            for identity in identities:
                customer_ids = EndCustomerRepository.resolve_customer_ids_for_owner(
                    db,
                    tenant_id,
                    identity.owner_type,
                    identity.owner_id,
                )
                for customer_id in customer_ids:
                    if customer_id not in matched:
                        matched[customer_id] = (identity_type.value, identity.raw_value)

        prefix_customers = EndCustomerRepository.search_customers_by_display_name_prefix(
            db, tenant_id, text, limit=MAX_LIST_LIMIT, offset=0
        )
        for customer in prefix_customers:
            if customer.customer_id not in matched:
                matched[customer.customer_id] = ("display_name", customer.display_name)

        ordered_ids = sorted(matched.keys())
        total = len(ordered_ids)
        page_ids = ordered_ids[offset_val: offset_val + limit_val]
        items: list[EndCustomerSearchResultItem] = []
        for customer_id in page_ids:
            customer = EndCustomerRepository.get_customer(db, tenant_id, customer_id)
            if customer is None:
                continue
            field, value = matched[customer_id]
            items.append(
                EndCustomerSearchResultItem(
                    customer_id=customer.customer_id,
                    display_name=customer.display_name,
                    customer_type=customer.customer_type,
                    matched_field=field,
                    matched_value=value,
                )
            )
        return EndCustomerSearchResponse(
            tenant_scoped=True,
            items=items,
            total=total,
            limit=limit_val,
            offset=offset_val,
        )

    @staticmethod
    def require_customer(
        db: Session,
        tenant_id: str,
        customer_id: str,
    ) -> None:
        if EndCustomerRepository.get_customer(db, tenant_id, customer_id) is None:
            raise EndCustomerNotFoundError("customer not found")
