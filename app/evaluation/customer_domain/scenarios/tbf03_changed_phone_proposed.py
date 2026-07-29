"""TBF03 — verified phone unchanged while proposed phone stays pending."""

from __future__ import annotations

from app.domain.customer.api_schemas import OperatorAddFactRequest
from app.domain.customer.enums import EntityOwnerType, FactState, SourceType
from app.evaluation.customer_domain.actions import EvalContext
from app.evaluation.customer_domain.assertions import assert_current_phone, assert_pending_phone
from app.evaluation.customer_domain.oracles import attach_oracle_to_result
from app.evaluation.customer_domain.scenarios._common import ScenarioRunResult, finalize_result


def run(ctx: EvalContext) -> ScenarioRunResult:
    result = ScenarioRunResult(
        scenario_id="TBF03",
        family="tbf03",
        tenant_id=ctx.tenant_id,
    )
    db = ctx.session()
    try:
        create = ctx.act_create_private_customer(
            db,
            display_name="Change Phone",
            email="tbf03-phone@eval.test",
            idempotency_key=ctx.step_idempotency_key("create"),
        )
        customer_id = create["body"]["customer_id"]
        contact_id = create["body"].get("primary_contact_id")

        verified_fact = OperatorAddFactRequest(
            subject_type=EntityOwnerType.CONTACT,
            subject_id=contact_id,
            field_name="phone",
            raw_value="+46700303001",
            normalized_value="+46700303001",
            fact_state=FactState.VERIFIED,
            source_type=SourceType.ADMIN_CORRECTION,
            confidence=1.0,
            reason="Initial verified phone",
        )
        ctx.act_add_fact(db, customer_id, verified_fact, ctx.step_idempotency_key("verified_phone"))

        proposed_fact = OperatorAddFactRequest(
            subject_type=EntityOwnerType.CONTACT,
            subject_id=contact_id,
            field_name="phone",
            raw_value="+46700303002",
            normalized_value="+46700303002",
            fact_state=FactState.PROPOSED,
            source_type=SourceType.AI_EXTRACTION,
            confidence=0.5,
            reason="Proposed phone change",
        )
        ctx.act_add_fact(db, customer_id, proposed_fact, ctx.step_idempotency_key("proposed_phone"))

        card = ctx.read_customer_card(db, customer_id)
        if card is None:
            result.fail("card missing")
        else:
            assert_current_phone(card, "+46700303001")
            assert_pending_phone(card, "+46700303002")

        result.semantic_payload = {
            "current_phone": "+46700303001",
            "pending_phone": "+46700303002",
        }
        attach_oracle_to_result(ctx, db, result, customer_id=customer_id, card_detail=card)
        return finalize_result(ctx, db, result)
    finally:
        db.close()
