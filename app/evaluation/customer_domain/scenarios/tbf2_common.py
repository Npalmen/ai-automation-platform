"""Shared helpers for TBF2 shadow scenarios."""

from __future__ import annotations

from app.evaluation.customer_domain.oracles import attach_oracle_to_result
from app.evaluation.customer_domain.scenarios._common import ScenarioRunResult, finalize_result
from app.evaluation.customer_domain.shadow_eval_support import act_shadow_intake
from app.services.shadow_intake_boundary import MockIntakeMessage
from app.services.shadow_read_service import ShadowReadService


def base_message(ctx, *, message_id: str, email: str, name: str, phone: str | None = None, thread_id: str | None = None):
    return MockIntakeMessage(
        tenant_id=ctx.tenant_id,
        message_id=message_id,
        thread_id=thread_id,
        subject=f"Eval {ctx.scenario_id}",
        message_text=f"Message from {name}",
        sender_email=email,
        sender_name=name,
        sender_phone=phone,
    )


def finalize_shadow_result(ctx, db, result: ScenarioRunResult, *, customer_id: str | None = None) -> ScenarioRunResult:
    oracle = ShadowReadService.build_oracle(db, ctx.tenant_id)
    result.oracle = oracle
    if customer_id:
        attach_oracle_to_result(ctx, db, result, customer_id=customer_id)
    if oracle.get("verified_facts_created", 0) != 0:
        result.fail("verified_facts_created must be 0 in shadow scenarios")
    if oracle.get("automatic_merges", 0) != 0:
        result.fail("automatic_merges must be 0")
    return finalize_result(ctx, db, result)
