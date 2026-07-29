"""TBF2-01 — new sender creates shadow observation without verified facts."""

from __future__ import annotations

from app.evaluation.customer_domain.actions import EvalContext
from app.evaluation.customer_domain.scenarios._common import ScenarioRunResult
from app.evaluation.customer_domain.scenarios.tbf2_common import act_shadow_intake, base_message, finalize_shadow_result
from app.evaluation.customer_domain.shadow_eval_support import shadow_eval_flags
from app.repositories.postgres.end_customer_shadow_repository import EndCustomerShadowRepository


def run(ctx: EvalContext) -> ScenarioRunResult:
    result = ScenarioRunResult(scenario_id="TBF2-01", family="tbf2_01", tenant_id=ctx.tenant_id)
    db = ctx.session()
    try:
        with shadow_eval_flags(ctx.tenant_id):
            out = act_shadow_intake(
                ctx,
                db,
                message=base_message(
                    ctx,
                    message_id="msg-tbf2-01",
                    email="tbf2-01-new@eval.test",
                    name="New Sender",
                    phone="+46702001001",
                ),
            )
            db.commit()
        if EndCustomerShadowRepository.count_observations(db, ctx.tenant_id) != 1:
            result.fail("expected exactly one shadow observation")
        if not out.get("created", False) and out.get("observation_id"):
            pass
        result.semantic_payload = {"observation_id": out["observation_id"], "new_sender": True}
        return finalize_shadow_result(ctx, db, result)
    finally:
        db.close()
