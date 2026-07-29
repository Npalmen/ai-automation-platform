"""Shadow match proposal service — proposals only, no automatic links."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.domain.customer.enums import CustomerType, EntityOwnerType, IdentityType, MatchDecision, VerificationStatus
from app.domain.customer.matching import assess_customer_match
from app.domain.customer.schemas import CustomerMatchInput, CustomerMatchSubject, IdentityMatchItem
from app.domain.customer.shadow_enums import ShadowMatchProposalState, ShadowObservationState
from app.domain.customer.shadow_state import assert_shadow_observation_transition
from app.repositories.postgres.end_customer_repository import EndCustomerRepository
from app.repositories.postgres.end_customer_shadow_repository import EndCustomerShadowRepository
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
from app.services.shadow_gate import assert_shadow_matching_allowed


class ShadowMatchProposalService:
    MATCHER_VERSION = "v1"

    @staticmethod
    def _customer_subject(db: Session, tenant_id: str, customer_id: str) -> CustomerMatchSubject | None:
        customer = EndCustomerRepository.get_customer(db, tenant_id, customer_id)
        if customer is None:
            return None
        refs = EndCustomerRepository._customer_subject_refs(db, tenant_id, customer_id)
        identities = EndCustomerRepository.list_identities_for_owners(db, tenant_id, refs)
        identity_items = [
            IdentityMatchItem(
                identity_type=IdentityType(item.identity_type),
                raw_value=item.raw_value,
                normalized_value=item.normalized_value,
                verification_status=VerificationStatus(item.verification_status),
            )
            for item in identities
        ]
        return CustomerMatchSubject(
            tenant_id=tenant_id,
            subject_id=customer_id,
            owner_type=EntityOwnerType.CUSTOMER,
            customer_type=CustomerType(customer.customer_type),
            display_name=customer.display_name,
            identities=identity_items,
        )

    @staticmethod
    def _observation_subject(
        tenant_id: str,
        observation_id: str,
        *,
        email: str | None,
        phone: str | None,
        customer_name: str | None,
        thread_id: str | None,
    ) -> CustomerMatchSubject:
        identities: list[IdentityMatchItem] = []
        if email:
            identities.append(
                IdentityMatchItem(
                    identity_type=IdentityType.EMAIL,
                    raw_value=email,
                    normalized_value=email.lower(),
                    verification_status=VerificationStatus.UNVERIFIED,
                )
            )
        if phone:
            identities.append(
                IdentityMatchItem(
                    identity_type=IdentityType.PHONE,
                    raw_value=phone,
                    normalized_value=phone,
                    verification_status=VerificationStatus.UNVERIFIED,
                )
            )
        return CustomerMatchSubject(
            tenant_id=tenant_id,
            subject_id=f"shadow:{observation_id}",
            owner_type=EntityOwnerType.CONTACT,
            customer_type=CustomerType.PRIVATE,
            display_name=customer_name,
            identities=identities,
            gmail_thread_id=thread_id,
        )

    @staticmethod
    def assess_and_propose(
        db: Session,
        tenant_id: str,
        observation_id: str,
        *,
        email: str | None = None,
        phone: str | None = None,
        customer_name: str | None = None,
        thread_id: str | None = None,
    ) -> list[dict[str, Any]]:
        assert_shadow_matching_allowed(
            tenant_id,
            TenantConfigRepository.get_settings(db, tenant_id),
        )
        observation = EndCustomerShadowRepository.get_observation(db, tenant_id, observation_id)
        if observation is None:
            return []

        left = ShadowMatchProposalService._observation_subject(
            tenant_id,
            observation_id,
            email=email,
            phone=phone,
            customer_name=customer_name,
            thread_id=thread_id or observation.source_thread_id,
        )
        proposals: list[dict[str, Any]] = []

        for customer in EndCustomerRepository.list_customers(db, tenant_id, limit=200):
            right = ShadowMatchProposalService._customer_subject(db, tenant_id, customer.customer_id)
            if right is None:
                continue
            assessment = assess_customer_match(CustomerMatchInput(left=left, right=right))
            if assessment.decision in {MatchDecision.NO_MATCH, MatchDecision.BLOCKED}:
                continue
            if assessment.automatic_link_allowed:
                raise RuntimeError("automatic_link_allowed must remain false in shadow matching")

            state = ShadowMatchProposalState.PROPOSED.value
            if assessment.decision in {
                MatchDecision.MANUAL_REVIEW_REQUIRED,
                MatchDecision.POSSIBLE_DUPLICATE,
            }:
                state = ShadowMatchProposalState.AWAITING_OPERATOR.value

            row = EndCustomerShadowRepository.create_match_proposal(
                db,
                tenant_id=tenant_id,
                observation_id=observation_id,
                candidate_end_customer_id=customer.customer_id,
                match_score=float(assessment.confidence),
                match_reasons=[code.value for code in assessment.reason_codes],
                deterministic_signals=[item.code.value for item in assessment.evidence],
                ambiguous_signals=[code.value for code in assessment.reason_codes],
                matcher_version=ShadowMatchProposalService.MATCHER_VERSION,
                state=state,
            )
            if row is not None:
                proposals.append(
                    {
                        "match_proposal_id": row.match_proposal_id,
                        "candidate_end_customer_id": row.candidate_end_customer_id,
                        "match_score": row.match_score,
                        "state": row.state,
                        "decision": assessment.decision.value,
                    }
                )

        current = ShadowObservationState(observation.state)
        if current == ShadowObservationState.EXTRACTED:
            assert_shadow_observation_transition(current, ShadowObservationState.MATCH_ASSESSED)
            EndCustomerShadowRepository.update_observation_state(
                db, tenant_id, observation_id, ShadowObservationState.MATCH_ASSESSED.value
            )
            current = ShadowObservationState.MATCH_ASSESSED

        if current == ShadowObservationState.MATCH_ASSESSED:
            assert_shadow_observation_transition(current, ShadowObservationState.AWAITING_OPERATOR)
            EndCustomerShadowRepository.update_observation_state(
                db, tenant_id, observation_id, ShadowObservationState.AWAITING_OPERATOR.value
            )

        return proposals

