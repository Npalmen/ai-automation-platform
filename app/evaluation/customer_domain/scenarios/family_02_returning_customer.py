"""Family 2 — returning customer in new thread."""

from __future__ import annotations

from app.domain.customer.enums import EntityOwnerType, LinkType, MatchDecision, SourceType
from app.evaluation.customer_domain.actions import EvalContext, new_id
from app.evaluation.customer_domain.assertions import assert_no_automation_flags, count_customers
from app.evaluation.customer_domain.scenarios._common import finalize_result, ScenarioRunResult
from app.repositories.postgres.end_customer_repository import EndCustomerRepository
from app.services.end_customer_read_service import EndCustomerReadService


def run(ctx: EvalContext) -> ScenarioRunResult:
    result = ScenarioRunResult(
        scenario_id="family_02_returning_customer_new_thread",
        family="family_02",
        tenant_id=ctx.tenant_id,
    )
    db = ctx.session()
    try:
        email = "fam02.return@example.invalid"
        create = ctx.act_create_private_customer(
            db,
            display_name="Returning",
            email=email,
            idempotency_key=new_id(),
        )
        customer_id = create["body"]["customer_id"]
        contact_id = create["body"].get("primary_contact_id")

        left = ctx.build_match_subject(contact_id, EntityOwnerType.CONTACT, email=email)
        right = ctx.build_match_subject(
            "new-thread-subject",
            EntityOwnerType.CONTACT,
            email=email,
            thread_id="thread-fam02-001",
        )
        assessment = ctx.assess_match(left, right)
        assert_no_automation_flags(assessment)
        if assessment.decision == MatchDecision.NO_MATCH:
            result.fail("expected match candidate for returning email")

        if count_customers(db, ctx.tenant_id) != 1:
            result.fail("match assessment must not create customer")

        thread_id = "thread-fam02-001"
        ctx.arrange_thread_link(db, customer_id, thread_id)
        _, created = EndCustomerRepository.create_thread_link(
            db,
            ctx.tenant_id,
            customer_id,
            "gmail",
            "eval-account",
            thread_id,
            LinkType.MANUAL,
            1.0,
            SourceType.SYSTEM_DERIVED,
        )
        db.commit()
        if created:
            result.fail("duplicate thread link created on replay")

        threads = EndCustomerReadService.list_threads(db, ctx.tenant_id, customer_id)
        if threads is None or threads.total < 1:
            result.fail("expected thread references on card")

        result.semantic_payload = {
            "customer_count": count_customers(db, ctx.tenant_id),
            "automatic_link_allowed": assessment.automatic_link_allowed,
            "automatic_merge_allowed": assessment.automatic_merge_allowed,
            "match_decision": assessment.decision.value,
            "thread_link_count": threads.total,
            "thread_replay_created": created,
        }
        return finalize_result(ctx, db, result)
    finally:
        db.close()
