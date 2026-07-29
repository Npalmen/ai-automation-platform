"""TBF07 — ambiguous identity creates duplicate candidate without auto-link."""

from __future__ import annotations

from app.domain.customer.api_schemas import OperatorCreateIdentityRequest
from app.domain.customer.enums import EntityOwnerType, IdentityType, VerificationStatus
from app.evaluation.customer_domain.actions import EvalContext
from app.evaluation.customer_domain.assertions import assert_no_automation_flags
from app.evaluation.customer_domain.oracles import attach_oracle_to_result
from app.evaluation.customer_domain.scenarios._common import ScenarioRunResult, finalize_result
from app.repositories.postgres.end_customer_repository import EndCustomerRepository
from app.services.end_customer_command_service import EndCustomerCommandError


def run(ctx: EvalContext) -> ScenarioRunResult:
    result = ScenarioRunResult(
        scenario_id="TBF07",
        family="tbf07",
        tenant_id=ctx.tenant_id,
    )
    db = ctx.session()
    try:
        email = "tbf07-ambiguous@eval.test"
        first = ctx.act_create_private_customer(
            db,
            display_name="Customer A",
            email=email,
            idempotency_key=ctx.step_idempotency_key("create_a"),
        )
        second = ctx.act_create_private_customer(
            db,
            display_name="Customer B",
            email="other@eval.test",
            idempotency_key=ctx.step_idempotency_key("create_b"),
        )
        customer_a = first["body"]["customer_id"]
        customer_b = second["body"]["customer_id"]
        contact_b = second["body"].get("primary_contact_id")

        try:
            ctx.act_create_identity(
                db,
                customer_b,
                OperatorCreateIdentityRequest(
                    owner_type=EntityOwnerType.CONTACT,
                    owner_id=contact_b,
                    identity_type=IdentityType.EMAIL,
                    raw_value=email,
                    verification_status=VerificationStatus.VERIFIED,
                    reason="Collision",
                ),
                ctx.step_idempotency_key("collision_identity"),
            )
            result.fail("duplicate identity write should fail closed")
        except EndCustomerCommandError as exc:
            if exc.code != "IDENTITY_COLLISION_REVIEW_REQUIRED":
                result.fail(f"expected identity collision, got {exc.code}")

        candidate_id = ctx.arrange_duplicate_candidate(db, customer_a, customer_b)
        candidates = EndCustomerRepository.list_open_duplicate_candidates(db, ctx.tenant_id)
        if not candidates:
            result.fail("duplicate queue empty")

        left = ctx.build_match_subject(contact_b, EntityOwnerType.CONTACT, email=email)
        right = ctx.build_match_subject(
            "weak-match",
            EntityOwnerType.CONTACT,
            email=email,
            thread_id="thread-tbf07",
        )
        assessment = ctx.assess_match(left, right)
        assert_no_automation_flags(assessment)

        result.semantic_payload = {
            "customers": 2,
            "duplicate_candidate_id": candidate_id,
            "identity_collision_blocked": True,
            "automatic_link_allowed": assessment.automatic_link_allowed,
            "match_decision": assessment.decision.value,
        }
        attach_oracle_to_result(ctx, db, result, customer_id=customer_a)
        return finalize_result(ctx, db, result)
    finally:
        db.close()
