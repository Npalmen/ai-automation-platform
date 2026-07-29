"""TBF06 — company with multiple contacts and separate facts."""

from __future__ import annotations

from app.domain.customer.api_schemas import OperatorAddFactRequest, OperatorCreateIdentityRequest
from app.domain.customer.enums import EntityOwnerType, FactState, IdentityType, SourceType, VerificationStatus
from app.evaluation.customer_domain.actions import EvalContext
from app.evaluation.customer_domain.oracles import attach_oracle_to_result
from app.evaluation.customer_domain.scenarios._common import ScenarioRunResult, finalize_result
from app.services.end_customer_command_service import EndCustomerCommandError


def run(ctx: EvalContext) -> ScenarioRunResult:
    result = ScenarioRunResult(
        scenario_id="TBF06",
        family="tbf06",
        tenant_id=ctx.tenant_id,
    )
    db = ctx.session()
    try:
        create = ctx.act_create_company_customer(
            db,
            display_name="TBF06 Company AB",
            legal_name="TBF06 Company AB",
            contact_email="primary@eval.test",
            idempotency_key=ctx.step_idempotency_key("create"),
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
                raw_value="second@eval.test",
                verification_status=VerificationStatus.VERIFIED,
                reason="Second contact email",
            ),
            ctx.step_idempotency_key("second_identity"),
        )

        ctx.act_add_fact(
            db,
            customer_id,
            OperatorAddFactRequest(
                subject_type=EntityOwnerType.CONTACT,
                subject_id=primary_contact_id,
                field_name="phone",
                raw_value="+46700606001",
                normalized_value="+46700606001",
                fact_state=FactState.VERIFIED,
                source_type=SourceType.ADMIN_CORRECTION,
                confidence=1.0,
                reason="Primary phone",
            ),
            ctx.step_idempotency_key("primary_phone"),
        )
        ctx.act_add_fact(
            db,
            customer_id,
            OperatorAddFactRequest(
                subject_type=EntityOwnerType.CONTACT,
                subject_id=second_contact_id,
                field_name="phone",
                raw_value="+46700606002",
                normalized_value="+46700606002",
                fact_state=FactState.VERIFIED,
                source_type=SourceType.ADMIN_CORRECTION,
                confidence=1.0,
                reason="Second phone",
            ),
            ctx.step_idempotency_key("second_phone"),
        )

        job_primary = ctx.arrange_job(db)
        job_second = ctx.arrange_job(db)
        ctx.act_create_job_link(
            db, customer_id, job_primary, ctx.step_idempotency_key("job_primary")
        )
        ctx.act_create_job_link(
            db, customer_id, job_second, ctx.step_idempotency_key("job_second")
        )

        try:
            ctx.act_create_identity(
                db,
                customer_id,
                OperatorCreateIdentityRequest(
                    owner_type=EntityOwnerType.CONTACT,
                    owner_id=second_contact_id,
                    identity_type=IdentityType.EMAIL,
                    raw_value="primary@eval.test",
                    verification_status=VerificationStatus.VERIFIED,
                    reason="Collision attempt",
                ),
                ctx.step_idempotency_key("collision"),
            )
            result.fail("cross-owner identity collision not blocked")
        except EndCustomerCommandError as exc:
            if exc.code != "IDENTITY_COLLISION_REVIEW_REQUIRED":
                result.fail(f"expected IDENTITY_COLLISION_REVIEW_REQUIRED, got {exc.code}")

        card = ctx.read_customer_card(db, customer_id)
        if card is None:
            result.fail("card missing")
        else:
            contact_subjects = [
                subject
                for subject in card.current_state.subjects
                if subject.subject_type == EntityOwnerType.CONTACT
            ]
            if len(contact_subjects) < 2:
                result.fail("expected separate contact subject blocks")

        result.semantic_payload = {
            "company_customer": customer_id,
            "contact_subjects": len(contact_subjects) if card else 0,
            "collision_blocked": True,
        }
        attach_oracle_to_result(ctx, db, result, customer_id=customer_id, card_detail=card)
        return finalize_result(ctx, db, result)
    finally:
        db.close()
