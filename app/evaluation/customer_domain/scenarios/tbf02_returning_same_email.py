"""TBF02 — returning customer matched by email without duplicate creation."""

from __future__ import annotations

from app.domain.customer.enums import EntityOwnerType, MatchDecision
from app.evaluation.customer_domain.actions import EvalContext
from app.evaluation.customer_domain.assertions import assert_no_automation_flags, count_customers
from app.evaluation.customer_domain.oracles import attach_oracle_to_result
from app.evaluation.customer_domain.scenarios._common import ScenarioRunResult, finalize_result
from app.repositories.postgres.end_customer_repository import EndCustomerRepository


def run(ctx: EvalContext) -> ScenarioRunResult:
    result = ScenarioRunResult(
        scenario_id="TBF02",
        family="tbf02",
        tenant_id=ctx.tenant_id,
    )
    db = ctx.session()
    try:
        email = "tbf02-return@eval.test"
        create = ctx.act_create_private_customer(
            db,
            display_name="Returning Customer",
            email=email,
            idempotency_key=ctx.step_idempotency_key("create"),
        )
        customer_id = create["body"]["customer_id"]
        contact_id = create["body"].get("primary_contact_id")

        left = ctx.build_match_subject(contact_id, EntityOwnerType.CONTACT, email=email)
        right = ctx.build_match_subject(
            "new-thread-subject",
            EntityOwnerType.CONTACT,
            email=email,
            thread_id="thread-tbf02-001",
        )
        assessment = ctx.assess_match(left, right)
        assert_no_automation_flags(assessment)
        if assessment.decision == MatchDecision.NO_MATCH:
            result.fail("expected match candidate for returning email")

        if count_customers(db, ctx.tenant_id) != 1:
            result.fail("match assessment must not create customer")

        job_id = ctx.arrange_job(db)
        ctx.act_create_job_link(db, customer_id, job_id, ctx.step_idempotency_key("job_link"))
        open_duplicates = EndCustomerRepository.list_open_duplicate_candidates(db, ctx.tenant_id)
        if open_duplicates:
            result.fail("returning customer must not create duplicate candidates")

        card = ctx.read_customer_card(db, customer_id)
        result.semantic_payload = {
            "customer_count": count_customers(db, ctx.tenant_id),
            "match_decision": assessment.decision.value,
            "duplicate_candidates": len(open_duplicates),
        }
        attach_oracle_to_result(ctx, db, result, customer_id=customer_id, card_detail=card)
        return finalize_result(ctx, db, result)
    finally:
        db.close()
