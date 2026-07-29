"""Explicit operator promotion from shadow fact proposal to PROPOSED customer fact."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.domain.customer.api_schemas import OperatorAddFactRequest
from app.domain.customer.enums import EntityOwnerType, FactState, SourceType
from app.domain.customer.shadow_enums import ShadowFactProposalState, ShadowObservationState
from app.domain.customer.shadow_state import assert_shadow_observation_transition
from app.repositories.postgres.end_customer_repository import EndCustomerRepository
from app.repositories.postgres.end_customer_shadow_models import EndCustomerShadowFactProposalRecord
from app.repositories.postgres.end_customer_shadow_repository import EndCustomerShadowRepository
from app.services.end_customer_command_service import EndCustomerCommandService
from app.services.shadow_gate import assert_shadow_promotion_allowed


class ShadowPromotionService:
    @staticmethod
    def promote_fact_proposal(
        db: Session,
        tenant_id: str,
        customer_id: str,
        observation_id: str,
        proposal_id: str,
        operator: dict[str, str],
        idempotency_key: str,
    ) -> dict[str, Any]:
        assert_shadow_promotion_allowed(tenant_id)

        proposal = (
            db.query(EndCustomerShadowFactProposalRecord)
            .filter(
                EndCustomerShadowFactProposalRecord.tenant_id == tenant_id,
                EndCustomerShadowFactProposalRecord.proposal_id == proposal_id,
                EndCustomerShadowFactProposalRecord.observation_id == observation_id,
            )
            .first()
        )
        if proposal is None:
            raise ValueError("shadow fact proposal not found")

        customer = EndCustomerRepository.get_customer(db, tenant_id, customer_id)
        if customer is None:
            raise ValueError("customer not found")

        subject_id = customer.primary_contact_id
        if subject_id is None:
            raise ValueError("customer has no primary contact for promotion")

        request = OperatorAddFactRequest(
            subject_type=EntityOwnerType.CONTACT,
            subject_id=subject_id,
            field_name=proposal.field_name,
            raw_value=proposal.proposed_value,
            normalized_value=proposal.normalized_value,
            fact_state=FactState.PROPOSED,
            source_type=SourceType.AI_EXTRACTION,
            confidence=proposal.confidence,
            reason="Shadow observation operator promotion",
        )
        status, body = EndCustomerCommandService.add_fact(
            db, tenant_id, customer_id, operator, request, idempotency_key
        )

        proposal.state = ShadowFactProposalState.PROMOTED_AS_PROPOSED_FACT.value
        proposal.promotion_status = "promoted"
        proposal.target_end_customer_id = customer_id
        proposal.promoted_by = operator.get("id")
        proposal.promoted_at = datetime.now(timezone.utc)

        observation = EndCustomerShadowRepository.get_observation(db, tenant_id, observation_id)
        if observation is not None:
            assert_shadow_observation_transition(
                ShadowObservationState(observation.state),
                ShadowObservationState.PROMOTED,
                operator_action=True,
            )
            EndCustomerShadowRepository.update_observation_state(
                db, tenant_id, observation_id, ShadowObservationState.PROMOTED.value
            )

        return {"status": status, "body": body, "proposal_id": proposal_id}
