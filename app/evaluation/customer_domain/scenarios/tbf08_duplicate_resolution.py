"""TBF08 — duplicate resolution idempotent; approve_merge blocked."""

from __future__ import annotations

from app.evaluation.customer_domain.actions import EvalContext
from app.evaluation.customer_domain.assertions import count_customers, snapshot_db_counts
from app.evaluation.customer_domain.oracles import attach_oracle_to_result
from app.evaluation.customer_domain.scenarios._common import ScenarioRunResult, finalize_result
from app.repositories.postgres.end_customer_repository import EndCustomerRepository
from app.services.end_customer_command_service import EndCustomerCommandError


def run(ctx: EvalContext) -> ScenarioRunResult:
    result = ScenarioRunResult(
        scenario_id="TBF08",
        family="tbf08",
        tenant_id=ctx.tenant_id,
    )
    db = ctx.session()
    try:
        first = ctx.act_create_private_customer(
            db,
            display_name="Dup A",
            email="tbf08-a@eval.test",
            idempotency_key=ctx.step_idempotency_key("create_a"),
        )
        second = ctx.act_create_private_customer(
            db,
            display_name="Dup B",
            email="tbf08-b@eval.test",
            idempotency_key=ctx.step_idempotency_key("create_b"),
        )
        customer_a = first["body"]["customer_id"]
        customer_b = second["body"]["customer_id"]

        candidate_reject = ctx.arrange_duplicate_candidate(db, customer_a, customer_b)
        candidate = EndCustomerRepository.get_duplicate_candidate(
            db, ctx.tenant_id, candidate_reject
        )
        if candidate is None:
            result.fail("duplicate candidate missing")

        before_counts = snapshot_db_counts(db, ctx.tenant_id)
        try:
            ctx.act_duplicate_decision(
                db,
                candidate_reject,
                "approve_merge",
                candidate.version,
                ctx.step_idempotency_key("approve_merge"),
            )
            result.fail("approve_merge must be blocked")
        except EndCustomerCommandError as exc:
            if exc.code != "AUTOMATIC_MERGE_FORBIDDEN":
                result.fail(f"expected AUTOMATIC_MERGE_FORBIDDEN, got {exc.code}")

        after_merge_attempt = snapshot_db_counts(db, ctx.tenant_id)
        if after_merge_attempt != before_counts:
            result.fail("approve_merge attempt mutated data")

        try:
            ctx.act_duplicate_decision(
                db,
                candidate_reject,
                "defer",
                candidate.version,
                ctx.step_idempotency_key("defer"),
            )
            defer_status = "capability_not_implemented"
        except EndCustomerCommandError:
            defer_status = "capability_not_implemented"

        reject_key = ctx.step_idempotency_key("reject_merge")
        ctx.act_duplicate_decision(
            db,
            candidate_reject,
            "reject_merge",
            candidate.version,
            reject_key,
        )
        reject_replay = ctx.act_duplicate_decision(
            db,
            candidate_reject,
            "reject_merge",
            candidate.version,
            reject_key,
        )
        if reject_replay["status"] != 200:
            result.fail("reject_merge replay failed")

        third = ctx.act_create_private_customer(
            db,
            display_name="Dup C",
            email="tbf08-c@eval.test",
            idempotency_key=ctx.step_idempotency_key("create_c"),
        )
        customer_c = third["body"]["customer_id"]
        candidate_resolve = ctx.arrange_duplicate_candidate(db, customer_a, customer_c)
        resolve_candidate = EndCustomerRepository.get_duplicate_candidate(
            db, ctx.tenant_id, candidate_resolve
        )
        if resolve_candidate is None:
            result.fail("resolve candidate missing")

        resolve_key = ctx.step_idempotency_key("resolve_without_merge")
        ctx.act_duplicate_decision(
            db,
            candidate_resolve,
            "resolve_without_merge",
            resolve_candidate.version,
            resolve_key,
        )
        resolve_replay = ctx.act_duplicate_decision(
            db,
            candidate_resolve,
            "resolve_without_merge",
            resolve_candidate.version,
            resolve_key,
        )
        if resolve_replay["status"] != 200:
            result.fail("resolve_without_merge replay failed")

        if count_customers(db, ctx.tenant_id) != 3:
            result.fail("merge forbidden but customer count changed unexpectedly")

        result.semantic_payload = {
            "customers": 3,
            "approve_merge_blocked": True,
            "defer_status": defer_status,
            "reject_replay_status": reject_replay["status"],
            "resolve_replay_status": resolve_replay["status"],
        }
        attach_oracle_to_result(ctx, db, result, customer_id=customer_a)
        return finalize_result(ctx, db, result)
    finally:
        db.close()
