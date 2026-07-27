"""Family 3 — changed phone with current-state projection."""

from __future__ import annotations

from app.domain.customer.api_schemas import OperatorAddFactRequest
from app.domain.customer.enums import EntityOwnerType, FactState, SourceType
from app.evaluation.customer_domain.actions import EvalContext, new_id
from app.evaluation.customer_domain.assertions import (
    assert_current_phone,
    assert_historical_phone,
    assert_pending_phone,
    find_fact_by_value,
)
from app.evaluation.customer_domain.scenarios._common import finalize_result, ScenarioRunResult
from app.services.end_customer_command_service import EndCustomerCommandError


def run(ctx: EvalContext) -> ScenarioRunResult:
    result = ScenarioRunResult(
        scenario_id="family_03_changed_information",
        family="family_03",
        tenant_id=ctx.tenant_id,
    )
    db = ctx.session()
    try:
        create = ctx.act_create_private_customer(
            db,
            display_name="Change Phone",
            email="change.phone@example.invalid",
            idempotency_key=new_id(),
        )
        customer_id = create["body"]["customer_id"]
        contact_id = create["body"].get("primary_contact_id")

        verified_fact = OperatorAddFactRequest(
            subject_type=EntityOwnerType.CONTACT,
            subject_id=contact_id,
            field_name="phone",
            raw_value="+46701111111",
            normalized_value="+46701111111",
            fact_state=FactState.VERIFIED,
            source_type=SourceType.ADMIN_CORRECTION,
            confidence=1.0,
            reason="Initial verified phone",
        )
        ctx.act_add_fact(db, customer_id, verified_fact, new_id())

        proposed_fact = OperatorAddFactRequest(
            subject_type=EntityOwnerType.CONTACT,
            subject_id=contact_id,
            field_name="phone",
            raw_value="+46702222222",
            normalized_value="+46702222222",
            fact_state=FactState.PROPOSED,
            source_type=SourceType.AI_EXTRACTION,
            confidence=0.5,
            reason="Proposed phone change",
        )
        ctx.act_add_fact(db, customer_id, proposed_fact, new_id())

        before = ctx.read_customer_card(db, customer_id)
        if before is None:
            result.fail("card missing before verify")
        else:
            assert_current_phone(before, "+46701111111")
            assert_pending_phone(before, "+46702222222")

        original_fact_id = find_fact_by_value(
            db,
            ctx.tenant_id,
            EntityOwnerType.CONTACT,
            contact_id,
            "phone",
            "+46701111111",
        )
        if original_fact_id is None:
            result.fail("verified phone fact not found")

        ctx.act_verify_fact(
            db,
            customer_id,
            original_fact_id,
            "+46702222222",
            new_id(),
        )

        after = ctx.read_customer_card(db, customer_id)
        if after is None:
            result.fail("card missing after verify")
        else:
            assert_current_phone(after, "+46702222222")
            assert_historical_phone(after, original_fact_id)

        try:
            overwrite = OperatorAddFactRequest(
                subject_type=EntityOwnerType.CONTACT,
                subject_id=contact_id,
                field_name="phone",
                raw_value="+46709999999",
                normalized_value="+46709999999",
                fact_state=FactState.VERIFIED,
                source_type=SourceType.AI_EXTRACTION,
                confidence=0.9,
                reason="Illegal overwrite attempt",
            )
            ctx.act_add_fact(db, customer_id, overwrite, new_id())
            result.fail("AI overwrite should be blocked or not become current")
        except EndCustomerCommandError:
            pass

        result.semantic_payload = {
            "current_phone": "+46702222222",
            "historical_fact": original_fact_id,
            "projection_verified": True,
        }
        return finalize_result(ctx, db, result)
    finally:
        db.close()
