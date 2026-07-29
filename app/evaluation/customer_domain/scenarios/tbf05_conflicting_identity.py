"""TBF05 — conflicting verified facts expose resolution issues."""

from __future__ import annotations

from app.domain.customer.enums import EntityOwnerType, FactState, SourceType
from app.domain.customer.schemas import CustomerSourceFact
from app.evaluation.customer_domain.actions import EvalContext, new_id, utcnow
from app.evaluation.customer_domain.oracles import attach_oracle_to_result
from app.evaluation.customer_domain.scenarios._common import ScenarioRunResult, finalize_result


def run(ctx: EvalContext) -> ScenarioRunResult:
    result = ScenarioRunResult(
        scenario_id="TBF05",
        family="tbf05",
        tenant_id=ctx.tenant_id,
    )
    db = ctx.session()
    try:
        create = ctx.act_create_private_customer(
            db,
            display_name="Official Name",
            email="tbf05-conflict@eval.test",
            phone="+46700505001",
            idempotency_key=ctx.step_idempotency_key("create"),
        )
        customer_id = create["body"]["customer_id"]
        now = utcnow()

        fact_a_id = new_id()
        fact_b_id = new_id()
        ctx.arrange_fact(
            db,
            CustomerSourceFact(
                fact_id=fact_a_id,
                tenant_id=ctx.tenant_id,
                subject_type=EntityOwnerType.CUSTOMER,
                subject_id=customer_id,
                field_name="display_name",
                raw_value="Official Name",
                normalized_value="official name",
                fact_state=FactState.VERIFIED,
                source_type=SourceType.ADMIN_CORRECTION,
                confidence=1.0,
                recorded_at=now,
                verified_at=now,
                verified_by="eval-operator",
            ),
        )
        ctx.arrange_fact(
            db,
            CustomerSourceFact(
                fact_id=fact_b_id,
                tenant_id=ctx.tenant_id,
                subject_type=EntityOwnerType.CUSTOMER,
                subject_id=customer_id,
                field_name="display_name",
                raw_value="Conflicting Name",
                normalized_value="conflicting name",
                fact_state=FactState.VERIFIED,
                source_type=SourceType.ADMIN_CORRECTION,
                confidence=1.0,
                recorded_at=now,
                verified_at=now,
                verified_by="eval-operator",
            ),
        )

        card = ctx.read_customer_card(db, customer_id)
        issues: list[str] = []
        if card is None:
            result.fail("card missing")
        else:
            issues = [issue.code.value for issue in card.current_state.resolution_issues]
            if "multiple_verified_heads" not in issues:
                result.fail(f"expected multiple_verified_heads resolution issue, got {issues}")
            current_names = {
                value.display_value
                for value in card.current_state.current_values
                if value.field_name == "display_name"
            }
            if len(current_names) > 1:
                result.fail("current_state must not expose multiple current display names")

        result.semantic_payload = {
            "customer_id": customer_id,
            "resolution_issues": issues,
            "conflict_exposed": bool(issues),
        }
        attach_oracle_to_result(ctx, db, result, customer_id=customer_id, card_detail=card)
        return finalize_result(ctx, db, result)
    finally:
        db.close()
