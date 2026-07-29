"""TBF04 — operator verify creates successor current fact with idempotent replay."""

from __future__ import annotations

from app.domain.customer.api_schemas import OperatorAddFactRequest
from app.domain.customer.enums import EntityOwnerType, FactState, SourceType
from app.evaluation.customer_domain.actions import EvalContext
from app.evaluation.customer_domain.assertions import (
    assert_current_phone,
    assert_historical_phone,
    find_fact_by_value,
)
from app.evaluation.customer_domain.oracles import attach_oracle_to_result
from app.evaluation.customer_domain.scenarios._common import ScenarioRunResult, finalize_result


def run(ctx: EvalContext) -> ScenarioRunResult:
    result = ScenarioRunResult(
        scenario_id="TBF04",
        family="tbf04",
        tenant_id=ctx.tenant_id,
    )
    db = ctx.session()
    try:
        create = ctx.act_create_private_customer(
            db,
            display_name="Verify Phone",
            email="tbf04-verify@eval.test",
            idempotency_key=ctx.step_idempotency_key("create"),
        )
        customer_id = create["body"]["customer_id"]
        contact_id = create["body"].get("primary_contact_id")

        verified_fact = OperatorAddFactRequest(
            subject_type=EntityOwnerType.CONTACT,
            subject_id=contact_id,
            field_name="phone",
            raw_value="+46700404001",
            normalized_value="+46700404001",
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
            raw_value="+46700404002",
            normalized_value="+46700404002",
            fact_state=FactState.PROPOSED,
            source_type=SourceType.AI_EXTRACTION,
            confidence=0.5,
            reason="Proposed phone change",
        )
        ctx.act_add_fact(db, customer_id, proposed_fact, ctx.step_idempotency_key("proposed_phone"))

        original_fact_id = find_fact_by_value(
            db,
            ctx.tenant_id,
            EntityOwnerType.CONTACT,
            contact_id,
            "phone",
            "+46700404001",
        )
        if original_fact_id is None:
            result.fail("verified phone fact not found")

        verify_key = ctx.step_idempotency_key("verify")
        ctx.act_verify_fact(
            db,
            customer_id,
            original_fact_id,
            "+46700404002",
            verify_key,
        )

        replay = ctx.act_verify_fact(
            db,
            customer_id,
            original_fact_id,
            "+46700404002",
            verify_key,
        )
        if replay["status"] not in (200, 201):
            result.fail("verify replay failed")

        card = ctx.read_customer_card(db, customer_id)
        if card is None:
            result.fail("card missing after verify")
        else:
            assert_current_phone(card, "+46700404002")
            assert_historical_phone(card, original_fact_id)

        result.semantic_payload = {
            "current_phone": "+46700404002",
            "historical_fact": original_fact_id,
            "verify_replay_status": replay["status"],
        }
        attach_oracle_to_result(ctx, db, result, customer_id=customer_id, card_detail=card)
        return finalize_result(ctx, db, result)
    finally:
        db.close()
