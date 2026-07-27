"""Family 1 — new private customer."""

from __future__ import annotations

from app.domain.customer.api_schemas import OperatorAddFactRequest
from app.domain.customer.enums import EntityOwnerType, FactState, SourceType
from app.evaluation.customer_domain.actions import EvalContext, new_id
from app.evaluation.customer_domain.assertions import count_contacts, count_customers
from app.evaluation.customer_domain.scenarios._common import finalize_result, ScenarioRunResult
from app.services.end_customer_command_service import EndCustomerCommandError


def run(ctx: EvalContext) -> ScenarioRunResult:
    result = ScenarioRunResult(
        scenario_id="family_01_new_private_customer",
        family="family_01",
        tenant_id=ctx.tenant_id,
    )
    db = ctx.session()
    try:
        idem_key = f"fam01-create-{ctx.tenant_id}"
        create = ctx.act_create_private_customer(
            db,
            display_name="Eval Private A",
            email="fam01.private@example.invalid",
            phone="+46701111111",
            idempotency_key=idem_key,
        )
        customer_id = create["body"]["customer_id"]
        contact_id = create["body"].get("primary_contact_id")
        result.steps.append({"step_id": "create", "phase": "act", "result": "ok"})

        fact_req = OperatorAddFactRequest(
            subject_type=EntityOwnerType.CONTACT,
            subject_id=contact_id,
            field_name="email",
            raw_value="fam01.private@example.invalid",
            normalized_value="fam01.private@example.invalid",
            fact_state=FactState.PROPOSED,
            source_type=SourceType.GMAIL_INBOUND,
            confidence=0.8,
            reason="Stateful evaluation",
        )
        ctx.act_add_fact(db, customer_id, fact_req, new_id())
        card = ctx.read_customer_card(db, customer_id)
        if card is None:
            result.fail("customer card missing")

        replay = ctx.act_create_private_customer(
            db,
            display_name="Eval Private A",
            email="fam01.private@example.invalid",
            phone="+46701111111",
            idempotency_key=idem_key,
        )
        if replay["body"]["customer_id"] != customer_id:
            result.fail("idempotency replay created new customer")

        try:
            ctx.act_create_private_customer(
                db,
                display_name="Changed",
                email="other@example.invalid",
                idempotency_key=idem_key,
            )
            result.fail("idempotency conflict not raised")
        except EndCustomerCommandError as exc:
            if exc.code != "IDEMPOTENCY_CONFLICT":
                result.fail(f"expected IDEMPOTENCY_CONFLICT, got {exc.code}")

        if count_customers(db, ctx.tenant_id) != 1:
            result.fail("expected exactly one customer")
        if count_contacts(db, ctx.tenant_id) != 1:
            result.fail("expected exactly one contact")

        result.semantic_payload = {
            "customer_count": count_customers(db, ctx.tenant_id),
            "contact_count": count_contacts(db, ctx.tenant_id),
            "current_state_present": card is not None and card.current_state is not None,
            "idempotency_replay": replay["body"]["customer_id"] == customer_id,
        }
        return finalize_result(ctx, db, result)
    finally:
        db.close()
