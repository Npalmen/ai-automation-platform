"""TBF2-09 — low-confidence extraction does not create fact proposals."""

from __future__ import annotations

from app.evaluation.customer_domain.actions import EvalContext
from app.evaluation.customer_domain.scenarios._common import ScenarioRunResult
from app.evaluation.customer_domain.scenarios.tbf2_common import act_shadow_intake, base_message, finalize_shadow_result
from app.evaluation.customer_domain.shadow_eval_support import shadow_eval_flags
from app.repositories.postgres.end_customer_shadow_repository import EndCustomerShadowRepository


def run(ctx: EvalContext) -> ScenarioRunResult:
    result = ScenarioRunResult(scenario_id="TBF2-09", family="tbf2_09", tenant_id=ctx.tenant_id)
    db = ctx.session()
    try:
        with shadow_eval_flags(ctx.tenant_id):
            out = act_shadow_intake(
                ctx,
                db,
                message=base_message(
                    ctx,
                    message_id="msg-tbf2-09",
                    email="lowconf@eval.test",
                    name="Low Confidence",
                ),
                confidence=0.1,
                run_matching=False,
            )
            db.commit()
        facts = EndCustomerShadowRepository.list_fact_proposals(db, ctx.tenant_id, out["observation_id"])
        if facts:
            result.fail("low-confidence observation must not create fact proposals")
        obs = EndCustomerShadowRepository.get_observation(db, ctx.tenant_id, out["observation_id"])
        if obs and obs.state != "awaiting_operator":
            result.fail(f"expected awaiting_operator, got {obs.state}")
        result.semantic_payload = {"low_confidence": True, "fact_proposals": 0}
        return finalize_shadow_result(ctx, db, result)
    finally:
        db.close()
