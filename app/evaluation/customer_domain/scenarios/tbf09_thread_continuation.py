"""TBF09 — thread continuation links job without identity proof."""

from __future__ import annotations

from app.domain.customer.enums import EntityOwnerType, LinkType, MatchDecision, SourceType
from app.evaluation.customer_domain.actions import EvalContext
from app.evaluation.customer_domain.assertions import assert_no_automation_flags
from app.evaluation.customer_domain.oracles import attach_oracle_to_result
from app.evaluation.customer_domain.scenarios._common import ScenarioRunResult, finalize_result
from app.repositories.postgres.end_customer_repository import EndCustomerRepository
from app.services.end_customer_read_service import EndCustomerReadService


def run(ctx: EvalContext) -> ScenarioRunResult:
    result = ScenarioRunResult(
        scenario_id="TBF09",
        family="tbf09",
        tenant_id=ctx.tenant_id,
    )
    db = ctx.session()
    try:
        email = "tbf09-thread@eval.test"
        thread_id = "thread-tbf09-continuation"
        create = ctx.act_create_private_customer(
            db,
            display_name="Thread Customer",
            email=email,
            idempotency_key=ctx.step_idempotency_key("create"),
        )
        customer_id = create["body"]["customer_id"]
        contact_id = create["body"].get("primary_contact_id")

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

        job_id = ctx.arrange_job(db)
        ctx.act_create_job_link(db, customer_id, job_id, ctx.step_idempotency_key("job_link"))

        no_email_subject = ctx.build_match_subject(
            "thread-only-subject",
            EntityOwnerType.CONTACT,
            email=None,
            thread_id=thread_id,
        )
        email_subject = ctx.build_match_subject(contact_id, EntityOwnerType.CONTACT, email=email)
        thread_only_assessment = ctx.assess_match(email_subject, no_email_subject)
        assert_no_automation_flags(thread_only_assessment)
        if thread_only_assessment.decision != MatchDecision.NO_MATCH:
            result.fail("thread_id alone must not prove identity match")

        threads = EndCustomerReadService.list_threads(db, ctx.tenant_id, customer_id)
        jobs = EndCustomerReadService.list_jobs(db, ctx.tenant_id, customer_id)
        if threads is None or threads.total < 1:
            result.fail("expected thread references")
        if jobs is None or jobs.total < 1:
            result.fail("expected job links")

        result.semantic_payload = {
            "customer_id": customer_id,
            "thread_link_count": threads.total,
            "job_link_count": jobs.total,
            "thread_not_identity_proof": True,
        }
        attach_oracle_to_result(ctx, db, result, customer_id=customer_id)
        return finalize_result(ctx, db, result)
    finally:
        db.close()
