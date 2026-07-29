"""TBF2-05 — company multi-contact signals stay separate."""

from __future__ import annotations

from app.evaluation.customer_domain.actions import EvalContext
from app.evaluation.customer_domain.scenarios._common import ScenarioRunResult
from app.evaluation.customer_domain.scenarios.tbf2_common import act_shadow_intake, finalize_shadow_result
from app.evaluation.customer_domain.shadow_eval_support import shadow_eval_flags
from app.services.shadow_intake_boundary import MockIntakeMessage


def run(ctx: EvalContext) -> ScenarioRunResult:
    result = ScenarioRunResult(scenario_id="TBF2-05", family="tbf2_05", tenant_id=ctx.tenant_id)
    db = ctx.session()
    try:
        with shadow_eval_flags(ctx.tenant_id):
            for idx, (email, name) in enumerate(
                (
                    ("contact1@acme-eval.test", "Contact One"),
                    ("contact2@acme-eval.test", "Contact Two"),
                ),
                start=1,
            ):
                act_shadow_intake(
                    ctx,
                    db,
                    message=MockIntakeMessage(
                        tenant_id=ctx.tenant_id,
                        message_id=f"msg-tbf2-05-{idx}",
                        thread_id=f"thread-{idx}",
                        subject="Company inquiry",
                        message_text=f"From {name}",
                        sender_email=email,
                        sender_name=name,
                        sender_phone=None,
                    ),
                )
            db.commit()
        result.semantic_payload = {"contacts": 2, "shared_domain_no_merge": True}
        return finalize_shadow_result(ctx, db, result)
    finally:
        db.close()
