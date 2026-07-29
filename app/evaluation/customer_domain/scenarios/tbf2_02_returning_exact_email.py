"""TBF2-02 — returning exact email creates match proposal without link."""

from __future__ import annotations

from app.evaluation.customer_domain.actions import EvalContext
from app.evaluation.customer_domain.scenarios._common import ScenarioRunResult
from app.evaluation.customer_domain.scenarios.tbf2_common import act_shadow_intake, base_message, finalize_shadow_result
from app.evaluation.customer_domain.shadow_eval_support import shadow_eval_flags
from app.repositories.postgres.end_customer_shadow_repository import EndCustomerShadowRepository


def run(ctx: EvalContext) -> ScenarioRunResult:
    result = ScenarioRunResult(scenario_id="TBF2-02", family="tbf2_02", tenant_id=ctx.tenant_id)
    db = ctx.session()
    try:
        email = "tbf2-02-return@eval.test"
        with shadow_eval_flags(ctx.tenant_id):
            created = ctx.act_create_private_customer(
                db,
                display_name="Existing Customer",
                email=email,
                idempotency_key=ctx.step_idempotency_key("seed"),
            )
            customer_id = created["body"]["customer_id"]
            out = act_shadow_intake(
                ctx,
                db,
                message=base_message(
                    ctx,
                    message_id="msg-tbf2-02-new",
                    email=email,
                    name="Returning Sender",
                    thread_id="thread-tbf2-02",
                ),
            )
            db.commit()
        matches = EndCustomerShadowRepository.list_match_proposals(db, ctx.tenant_id, out["observation_id"])
        if not matches:
            result.fail("expected match proposal for exact email")
        if any(m.candidate_end_customer_id == customer_id for m in matches):
            pass
        else:
            result.fail("match proposal must target existing customer")
        result.semantic_payload = {
            "match_proposals": len(matches),
            "actual_links": 0,
        }
        return finalize_shadow_result(ctx, db, result, customer_id=customer_id)
    finally:
        db.close()
