"""TBF01 — new private customer with proposed AI facts and job link."""

from __future__ import annotations

from app.domain.customer.api_schemas import OperatorAddFactRequest
from app.domain.customer.enums import EntityOwnerType, FactState, SourceType
from app.evaluation.customer_domain.actions import EvalContext
from app.evaluation.customer_domain.assertions import count_contacts, count_customers
from app.evaluation.customer_domain.oracles import attach_oracle_to_result
from app.evaluation.customer_domain.scenarios._common import ScenarioRunResult, finalize_result
from app.services.end_customer_command_service import EndCustomerCommandError


def run(ctx: EvalContext) -> ScenarioRunResult:
    result = ScenarioRunResult(
        scenario_id="TBF01",
        family="tbf01",
        tenant_id=ctx.tenant_id,
    )
    db = ctx.session()
    try:
        idem_key = ctx.step_idempotency_key("create")
        create = ctx.act_create_private_customer(
            db,
            display_name="TBF01 Private",
            email="tbf01-private@eval.test",
            phone="+46700101001",
            idempotency_key=idem_key,
        )
        customer_id = create["body"]["customer_id"]
        contact_id = create["body"].get("primary_contact_id")

        proposed = OperatorAddFactRequest(
            subject_type=EntityOwnerType.CONTACT,
            subject_id=contact_id,
            field_name="email",
            raw_value="tbf01-private@eval.test",
            normalized_value="tbf01-private@eval.test",
            fact_state=FactState.PROPOSED,
            source_type=SourceType.AI_EXTRACTION,
            confidence=0.8,
            reason="AI observation",
        )
        ctx.act_add_fact(db, customer_id, proposed, ctx.step_idempotency_key("proposed_fact"))

        card = ctx.read_customer_card(db, customer_id)
        if card is None:
            result.fail("customer card missing")
        else:
            ai_current = [
                value
                for value in card.current_state.current_values
                if value.source_type == SourceType.AI_EXTRACTION
            ]
            if ai_current:
                result.fail("AI extraction must not become current without verify")

        job_id = ctx.arrange_job(db)
        ctx.act_create_job_link(db, customer_id, job_id, ctx.step_idempotency_key("job_link"))

        replay = ctx.act_create_private_customer(
            db,
            display_name="TBF01 Private",
            email="tbf01-private@eval.test",
            phone="+46700101001",
            idempotency_key=idem_key,
        )
        if replay["body"]["customer_id"] != customer_id:
            result.fail("idempotent create returned different customer")

        try:
            ctx.act_create_private_customer(
                db,
                display_name="Changed",
                email="other@eval.test",
                idempotency_key=idem_key,
            )
            result.fail("idempotency conflict not raised")
        except EndCustomerCommandError as exc:
            if exc.code != "IDEMPOTENCY_CONFLICT":
                result.fail(f"expected IDEMPOTENCY_CONFLICT, got {exc.code}")

        if count_customers(db, ctx.tenant_id) != 1 or count_contacts(db, ctx.tenant_id) != 1:
            result.fail("expected single customer/contact")

        result.semantic_payload = {
            "customer_id": customer_id,
            "job_linked": True,
            "ai_proposed_not_current": True,
        }
        attach_oracle_to_result(ctx, db, result, customer_id=customer_id, card_detail=card)
        return finalize_result(ctx, db, result)
    finally:
        db.close()
