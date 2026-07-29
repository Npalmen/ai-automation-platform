"""TBF2-06 — ambiguous match creates no customer link."""

from __future__ import annotations

from app.evaluation.customer_domain.actions import EvalContext
from app.evaluation.customer_domain.scenarios._common import ScenarioRunResult
from app.evaluation.customer_domain.scenarios.tbf2_common import act_shadow_intake, base_message, finalize_shadow_result
from app.evaluation.customer_domain.shadow_eval_support import shadow_eval_flags


def run(ctx: EvalContext) -> ScenarioRunResult:
    result = ScenarioRunResult(scenario_id="TBF2-06", family="tbf2_06", tenant_id=ctx.tenant_id)
    db = ctx.session()
    try:
        with shadow_eval_flags(ctx.tenant_id):
            ctx.act_create_private_customer(
                db,
                display_name="Alpha",
                email="alpha@eval.test",
                idempotency_key=ctx.step_idempotency_key("a"),
            )
            ctx.act_create_private_customer(
                db,
                display_name="Beta",
                email="beta@eval.test",
                idempotency_key=ctx.step_idempotency_key("b"),
            )
            act_shadow_intake(
                ctx,
                db,
                message=base_message(
                    ctx,
                    message_id="msg-tbf2-06",
                    email="unknown-shared@eval.test",
                    name="Smith",
                ),
            )
            db.commit()
        result.semantic_payload = {"ambiguous": True, "links": 0}
        return finalize_shadow_result(ctx, db, result)
    finally:
        db.close()
