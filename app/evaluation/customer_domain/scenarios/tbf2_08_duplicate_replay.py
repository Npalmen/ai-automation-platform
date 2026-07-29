"""TBF2-08 — duplicate intake replay is exact-once."""

from __future__ import annotations

from app.evaluation.customer_domain.actions import EvalContext
from app.evaluation.customer_domain.scenarios._common import ScenarioRunResult
from app.evaluation.customer_domain.scenarios.tbf2_common import act_shadow_intake, base_message, finalize_shadow_result
from app.evaluation.customer_domain.shadow_eval_support import shadow_eval_flags
from app.repositories.postgres.end_customer_shadow_repository import EndCustomerShadowRepository


def run(ctx: EvalContext) -> ScenarioRunResult:
    result = ScenarioRunResult(scenario_id="TBF2-08", family="tbf2_08", tenant_id=ctx.tenant_id)
    db = ctx.session()
    try:
        message = base_message(
            ctx,
            message_id="msg-tbf2-08",
            email="replay@eval.test",
            name="Replay User",
        )
        with shadow_eval_flags(ctx.tenant_id):
            first = act_shadow_intake(ctx, db, message=message)
            second = act_shadow_intake(ctx, db, message=message)
            db.commit()
        if first["observation_id"] != second["observation_id"]:
            result.fail("replay must return same observation")
        if EndCustomerShadowRepository.count_observations(db, ctx.tenant_id) != 1:
            result.fail("expected single observation after replay")
        result.semantic_payload = {"observation_id": first["observation_id"], "replay_ok": True}
        return finalize_shadow_result(ctx, db, result)
    finally:
        db.close()
