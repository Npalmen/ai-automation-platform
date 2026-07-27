"""Family 4 — company with multiple contacts."""

from __future__ import annotations

from app.domain.customer.api_schemas import OperatorCreateIdentityRequest
from app.domain.customer.enums import EntityOwnerType, IdentityType, VerificationStatus
from app.evaluation.customer_domain.actions import EvalContext, new_id
from app.evaluation.customer_domain.scenarios._common import finalize_result, ScenarioRunResult
from app.services.end_customer_command_service import EndCustomerCommandError


def run(ctx: EvalContext) -> ScenarioRunResult:
    result = ScenarioRunResult(
        scenario_id="family_04_company_contacts",
        family="family_04",
        tenant_id=ctx.tenant_id,
    )
    db = ctx.session()
    try:
        create = ctx.act_create_company_customer(
            db,
            display_name="Eval Company AB",
            legal_name="Eval Company AB",
            contact_email="primary@example.invalid",
            idempotency_key=new_id(),
        )
        customer_id = create["body"]["customer_id"]
        primary_contact_id = create["body"].get("primary_contact_id")

        second_contact_id = ctx.arrange_contact(db, "Second Contact")
        ctx.arrange_relationship(
            db,
            customer_id,
            EntityOwnerType.CONTACT,
            second_contact_id,
            "site_contact",
            is_primary=False,
        )

        ctx.act_create_identity(
            db,
            customer_id,
            OperatorCreateIdentityRequest(
                owner_type=EntityOwnerType.CONTACT,
                owner_id=second_contact_id,
                identity_type=IdentityType.EMAIL,
                raw_value="second@example.invalid",
                verification_status=VerificationStatus.VERIFIED,
                reason="Second contact email",
            ),
            new_id(),
        )

        try:
            ctx.act_create_identity(
                db,
                customer_id,
                OperatorCreateIdentityRequest(
                    owner_type=EntityOwnerType.CONTACT,
                    owner_id=second_contact_id,
                    identity_type=IdentityType.EMAIL,
                    raw_value="primary@example.invalid",
                    verification_status=VerificationStatus.VERIFIED,
                    reason="Collision attempt",
                ),
                new_id(),
            )
            result.fail("cross-owner identity collision not blocked")
        except EndCustomerCommandError as exc:
            if exc.code != "IDENTITY_COLLISION_REVIEW_REQUIRED":
                result.fail(f"expected IDENTITY_COLLISION_REVIEW_REQUIRED, got {exc.code}")

        card = ctx.read_customer_card(db, customer_id)
        if card is None:
            result.fail("card missing")
        else:
            subjects = card.current_state.subjects
            contact_subjects = [
                s for s in subjects if s.subject_type == EntityOwnerType.CONTACT
            ]
            if len(contact_subjects) < 2:
                result.fail("expected separate contact subject blocks")

        result.semantic_payload = {
            "company_customer": customer_id,
            "contact_subjects": len(
                [s for s in card.current_state.subjects if s.subject_type.value == "contact"]
            )
            if card
            else 0,
            "collision_blocked": True,
        }
        return finalize_result(ctx, db, result)
    finally:
        db.close()
