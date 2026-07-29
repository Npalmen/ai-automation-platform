"""TBF2-03 — changed phone does not mutate verified current state."""

from __future__ import annotations

from app.domain.customer.api_schemas import OperatorAddFactRequest
from app.domain.customer.enums import EntityOwnerType, FactState, SourceType
from app.evaluation.customer_domain.actions import EvalContext
from app.evaluation.customer_domain.scenarios._common import ScenarioRunResult
from app.evaluation.customer_domain.scenarios.tbf2_common import act_shadow_intake, base_message, finalize_shadow_result
from app.evaluation.customer_domain.shadow_eval_support import shadow_eval_flags
from app.services.end_customer_read_service import EndCustomerReadService


def run(ctx: EvalContext) -> ScenarioRunResult:
    result = ScenarioRunResult(scenario_id="TBF2-03", family="tbf2_03", tenant_id=ctx.tenant_id)
    db = ctx.session()
    try:
        email = "tbf2-03-phone@eval.test"
        with shadow_eval_flags(ctx.tenant_id):
            created = ctx.act_create_private_customer(
                db,
                display_name="Phone Customer",
                email=email,
                phone="+46700303001",
                idempotency_key=ctx.step_idempotency_key("seed"),
            )
            customer_id = created["body"]["customer_id"]
            contact_id = created["body"]["primary_contact_id"]
            proposed = OperatorAddFactRequest(
                subject_type=EntityOwnerType.CONTACT,
                subject_id=contact_id,
                field_name="phone",
                raw_value="+46700303001",
                normalized_value="+46700303001",
                fact_state=FactState.PROPOSED,
                source_type=SourceType.USER_INPUT,
                confidence=1.0,
                reason="seed",
            )
            fact = ctx.act_add_fact(db, customer_id, proposed, ctx.step_idempotency_key("seed_phone"))
            ctx.act_verify_fact(
                db,
                customer_id,
                fact["body"]["fact_id"],
                "+46700303001",
                ctx.step_idempotency_key("verify_phone"),
            )
            act_shadow_intake(
                ctx,
                db,
                message=base_message(
                    ctx,
                    message_id="msg-tbf2-03",
                    email=email,
                    name="Phone Customer",
                    phone="+46700999999",
                ),
            )
            db.commit()
        card = EndCustomerReadService.get_customer_card(db, ctx.tenant_id, customer_id)
        current_phone = next(
            (v.normalized_value for v in card.current_state.current_values if v.field_name == "phone"),
            None,
        )
        if current_phone != "+46700303001":
            result.fail("verified current phone must remain unchanged")
        result.semantic_payload = {"current_phone": current_phone, "shadow_conflict": True}
        return finalize_shadow_result(ctx, db, result, customer_id=customer_id)
    finally:
        db.close()
