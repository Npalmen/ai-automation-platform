"""TBF2-07 — thread continuation is provenance only."""

from __future__ import annotations

from app.evaluation.customer_domain.actions import EvalContext
from app.evaluation.customer_domain.scenarios._common import ScenarioRunResult
from app.evaluation.customer_domain.scenarios.tbf2_common import act_shadow_intake, base_message, finalize_shadow_result
from app.evaluation.customer_domain.shadow_eval_support import shadow_eval_flags
from app.repositories.postgres.end_customer_shadow_repository import EndCustomerShadowRepository


def run(ctx: EvalContext) -> ScenarioRunResult:
    result = ScenarioRunResult(scenario_id="TBF2-07", family="tbf2_07", tenant_id=ctx.tenant_id)
    db = ctx.session()
    try:
        thread = "thread-tbf2-07"
        email = "thread-user@eval.test"
        with shadow_eval_flags(ctx.tenant_id):
            ctx.act_create_private_customer(
                db,
                display_name="Thread User",
                email=email,
                idempotency_key=ctx.step_idempotency_key("seed"),
            )
            first = act_shadow_intake(
                ctx,
                db,
                message=base_message(
                    ctx,
                    message_id="msg-tbf2-07-a",
                    email=email,
                    name="Thread User",
                    thread_id=thread,
                ),
            )
            second = act_shadow_intake(
                ctx,
                db,
                message=base_message(
                    ctx,
                    message_id="msg-tbf2-07-b",
                    email=email,
                    name="Thread User",
                    thread_id=thread,
                ),
            )
            db.commit()
        if first["observation_id"] == second["observation_id"]:
            result.fail("new message must create new observation")
        if EndCustomerShadowRepository.count_observations(db, ctx.tenant_id) != 2:
            result.fail("expected two observations")
        result.semantic_payload = {"observations": 2, "thread_provenance_only": True}
        return finalize_shadow_result(ctx, db, result)
    finally:
        db.close()
