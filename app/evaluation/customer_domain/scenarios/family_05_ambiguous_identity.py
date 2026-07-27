"""Family 5 — ambiguous / duplicate identity."""

from __future__ import annotations

from app.domain.customer.api_schemas import OperatorCreateIdentityRequest
from app.domain.customer.enums import EntityOwnerType, IdentityType, VerificationStatus
from app.evaluation.customer_domain.actions import EvalContext, new_id
from app.evaluation.customer_domain.scenarios._common import finalize_result, ScenarioRunResult
from app.repositories.postgres.end_customer_repository import EndCustomerRepository
from app.services.end_customer_command_service import EndCustomerCommandError


def run(ctx: EvalContext) -> ScenarioRunResult:
    result = ScenarioRunResult(
        scenario_id="family_05_ambiguous_identity",
        family="family_05",
        tenant_id=ctx.tenant_id,
    )
    db = ctx.session()
    try:
        email = "ambiguous@example.invalid"
        first = ctx.act_create_private_customer(
            db,
            display_name="Customer A",
            email=email,
            idempotency_key=new_id(),
        )
        second = ctx.act_create_private_customer(
            db,
            display_name="Customer B",
            email="other@example.invalid",
            idempotency_key=new_id(),
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
                new_id(),
            )
            result.fail("duplicate identity write should fail closed")
        except EndCustomerCommandError as exc:
            if exc.code != "IDENTITY_COLLISION_REVIEW_REQUIRED":
                result.fail(f"expected identity collision, got {exc.code}")

        candidate_id = ctx.arrange_duplicate_candidate(db, customer_a, customer_b)
        candidates = EndCustomerRepository.list_open_duplicate_candidates(db, ctx.tenant_id)
        if not candidates:
            result.fail("duplicate queue empty")

        candidate = EndCustomerRepository.get_duplicate_candidate(
            db, ctx.tenant_id, candidate_id
        )
        if candidate is None:
            result.fail("duplicate candidate missing")

        decision_key = f"dup-decision-{ctx.tenant_id}"
        try:
            ctx.act_duplicate_decision(
                db,
                candidate_id,
                "resolve_without_merge",
                candidate.version + 99,
                new_id(),
            )
            result.fail("stale duplicate decision should conflict")
        except EndCustomerCommandError as exc:
            if exc.code != "DUPLICATE_DECISION_CONFLICT":
                result.fail(f"unexpected stale decision error: {exc.code}")

        ctx.act_duplicate_decision(
            db,
            candidate_id,
            "resolve_without_merge",
            candidate.version,
            decision_key,
        )

        replay = ctx.act_duplicate_decision(
            db,
            candidate_id,
            "resolve_without_merge",
            candidate.version,
            decision_key,
        )
        if replay["status"] != 200:
            result.fail("idempotent duplicate decision replay failed")

        result.semantic_payload = {
            "customers": 2,
            "duplicate_resolved": True,
            "identity_collision_blocked": True,
            "decision_replay_status": replay["status"],
        }
        return finalize_result(ctx, db, result)
    finally:
        db.close()
