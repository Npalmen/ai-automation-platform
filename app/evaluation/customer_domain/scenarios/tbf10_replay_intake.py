"""TBF10 — replay idempotency keys without extra rows."""

from __future__ import annotations

from app.domain.customer.api_schemas import OperatorAddFactRequest
from app.domain.customer.enums import EntityOwnerType, FactState, SourceType
from app.evaluation.customer_domain.actions import EvalContext
from app.evaluation.customer_domain.assertions import snapshot_db_counts
from app.evaluation.customer_domain.oracles import attach_oracle_to_result
from app.evaluation.customer_domain.scenarios._common import ScenarioRunResult, finalize_result


def run(ctx: EvalContext) -> ScenarioRunResult:
    result = ScenarioRunResult(
        scenario_id="TBF10",
        family="tbf10",
        tenant_id=ctx.tenant_id,
    )
    db = ctx.session()
    try:
        create_key = ctx.step_idempotency_key("create")
        create = ctx.act_create_private_customer(
            db,
            display_name="Replay Customer",
            email="tbf10-replay@eval.test",
            phone="+46701010001",
            idempotency_key=create_key,
        )
        customer_id = create["body"]["customer_id"]
        contact_id = create["body"].get("primary_contact_id")

        fact_key = ctx.step_idempotency_key("fact")
        fact_req = OperatorAddFactRequest(
            subject_type=EntityOwnerType.CONTACT,
            subject_id=contact_id,
            field_name="email",
            raw_value="tbf10-replay@eval.test",
            normalized_value="tbf10-replay@eval.test",
            fact_state=FactState.PROPOSED,
            source_type=SourceType.AI_EXTRACTION,
            confidence=0.8,
            reason="Replay intake",
        )
        ctx.act_add_fact(db, customer_id, fact_req, fact_key)

        thread_id = "thread-tbf10-replay"
        ctx.arrange_thread_link(db, customer_id, thread_id)
        job_id = ctx.arrange_job(db)
        job_key = ctx.step_idempotency_key("job_link")
        ctx.act_create_job_link(db, customer_id, job_id, job_key)

        counts_after_first = snapshot_db_counts(db, ctx.tenant_id)

        create_replay = ctx.act_create_private_customer(
            db,
            display_name="Replay Customer",
            email="tbf10-replay@eval.test",
            phone="+46701010001",
            idempotency_key=create_key,
        )
        fact_replay = ctx.act_add_fact(db, customer_id, fact_req, fact_key)
        job_replay = ctx.act_create_job_link(db, customer_id, job_id, job_key)

        counts_after_replay = snapshot_db_counts(db, ctx.tenant_id)
        if counts_after_replay != counts_after_first:
            result.fail("replay created extra rows")

        if create_replay["body"]["customer_id"] != customer_id:
            result.fail("create replay returned different customer")
        if fact_replay["status"] not in (200, 201):
            result.fail("fact replay failed")
        if job_replay["status"] not in (200, 201):
            result.fail("job link replay failed")

        card = ctx.read_customer_card(db, customer_id)
        card_replay = ctx.read_customer_card(db, customer_id)
        if card is None or card_replay is None:
            result.fail("card missing after replay")

        result.semantic_payload = {
            "customer_id": customer_id,
            "replay_stable": counts_after_replay == counts_after_first,
            "create_replay_status": create_replay["status"],
            "fact_replay_status": fact_replay["status"],
            "job_replay_status": job_replay["status"],
        }
        attach_oracle_to_result(ctx, db, result, customer_id=customer_id, card_detail=card)
        return finalize_result(ctx, db, result)
    finally:
        db.close()
