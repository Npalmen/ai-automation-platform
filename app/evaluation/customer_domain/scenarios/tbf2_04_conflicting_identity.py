"""TBF2-04 — conflicting identity requires manual review."""

from __future__ import annotations

from app.evaluation.customer_domain.actions import EvalContext
from app.evaluation.customer_domain.scenarios._common import ScenarioRunResult
from app.evaluation.customer_domain.scenarios.tbf2_common import act_shadow_intake, base_message, finalize_shadow_result
from app.evaluation.customer_domain.shadow_eval_support import shadow_eval_flags
from app.repositories.postgres.end_customer_shadow_repository import EndCustomerShadowRepository


def run(ctx: EvalContext) -> ScenarioRunResult:
    result = ScenarioRunResult(scenario_id="TBF2-04", family="tbf2_04", tenant_id=ctx.tenant_id)
    db = ctx.session()
    try:
        with shadow_eval_flags(ctx.tenant_id):
            ctx.act_create_private_customer(
                db,
                display_name="Person A",
                email="person-a@eval.test",
                idempotency_key=ctx.step_idempotency_key("a"),
            )
            ctx.act_create_private_customer(
                db,
                display_name="Person B",
                email="person-b@eval.test",
                idempotency_key=ctx.step_idempotency_key("b"),
            )
            out = act_shadow_intake(
                ctx,
                db,
                message=base_message(
                    ctx,
                    message_id="msg-tbf2-04",
                    email="person-a@eval.test",
                    name="Different Name",
                    phone="+46700404001",
                ),
            )
            db.commit()
        obs = EndCustomerShadowRepository.get_observation(db, ctx.tenant_id, out["observation_id"])
        if obs is None:
            result.fail("observation missing")
        elif obs.state not in {"match_assessed", "awaiting_operator"}:
            result.fail(f"expected manual review state, got {obs.state}")
        result.semantic_payload = {"state": obs.state if obs else None}
        return finalize_shadow_result(ctx, db, result)
    finally:
        db.close()
