"""Structured oracle builders for TBF customer-card stateful evaluation."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domain.customer.enums import EntityOwnerType, FactState
from app.evaluation.customer_domain.assertions import (
    count_contacts,
    count_customers,
    snapshot_audit_counts,
    snapshot_db_counts,
)
from app.repositories.postgres.end_customer_repository import EndCustomerRepository
from app.services.end_customer_read_service import EndCustomerReadService


def _count_identities(db: Session, tenant_id: str) -> int:
    return int(
        db.execute(
            text("SELECT COUNT(*) FROM end_customer_identities WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant_id},
        ).scalar()
        or 0
    )


def _count_facts_by_state(db: Session, tenant_id: str) -> dict[str, int]:
    rows = db.execute(
        text(
            "SELECT fact_state, COUNT(*) FROM end_customer_source_facts "
            "WHERE tenant_id = :tenant_id GROUP BY fact_state"
        ),
        {"tenant_id": tenant_id},
    ).fetchall()
    return {str(state): int(count) for state, count in rows}


def _count_job_links(db: Session, tenant_id: str) -> int:
    return int(
        db.execute(
            text("SELECT COUNT(*) FROM end_customer_job_links WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant_id},
        ).scalar()
        or 0
    )


def _count_thread_links(db: Session, tenant_id: str) -> int:
    return int(
        db.execute(
            text("SELECT COUNT(*) FROM end_customer_thread_links WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant_id},
        ).scalar()
        or 0
    )


def _count_duplicate_candidates(db: Session, tenant_id: str) -> int:
    return int(
        db.execute(
            text(
                "SELECT COUNT(*) FROM end_customer_duplicate_candidates "
                "WHERE tenant_id = :tenant_id"
            ),
            {"tenant_id": tenant_id},
        ).scalar()
        or 0
    )


def _count_idempotency_records(db: Session, tenant_id: str) -> int:
    return int(
        db.execute(
            text(
                "SELECT COUNT(*) FROM end_customer_idempotency_records "
                "WHERE tenant_id = :tenant_id"
            ),
            {"tenant_id": tenant_id},
        ).scalar()
        or 0
    )


def build_scenario_oracle(
    db: Session,
    tenant_id: str,
    *,
    card_detail: Any | None = None,
    customer_id: str | None = None,
) -> dict[str, Any]:
    if card_detail is None and customer_id:
        card_detail = EndCustomerReadService.get_customer_card(db, tenant_id, customer_id)

    current_state: dict[str, Any] = {}
    pending_facts: list[str] = []
    conflicts: list[str] = []
    resolution_issues: list[str] = []
    historical_facts: list[str] = []

    if card_detail is not None:
        state = card_detail.current_state
        current_state = {
            item.field_name: item.display_value for item in state.current_values
        }
        pending_facts = [item.display_value for item in state.pending_values]
        conflicts = [item.fact_id for item in state.conflicts]
        resolution_issues = [item.code.value for item in state.resolution_issues]
        historical_facts = [item.fact_id for item in state.historical_values]

    return {
        "tenant_id": tenant_id,
        "end_customer_count": count_customers(db, tenant_id),
        "contact_count": count_contacts(db, tenant_id),
        "identity_count": _count_identities(db, tenant_id),
        "source_fact_count_by_state": _count_facts_by_state(db, tenant_id),
        "current_state": current_state,
        "pending_facts": pending_facts,
        "conflicts": conflicts,
        "resolution_issues": resolution_issues,
        "historical_facts": historical_facts,
        "job_links": _count_job_links(db, tenant_id),
        "thread_links": _count_thread_links(db, tenant_id),
        "duplicate_candidates": _count_duplicate_candidates(db, tenant_id),
        "idempotency_records": _count_idempotency_records(db, tenant_id),
        "database_counts": snapshot_db_counts(db, tenant_id),
    }


def attach_oracle_to_result(
    ctx,
    db: Session,
    result,
    *,
    customer_id: str | None = None,
    card_detail: Any | None = None,
) -> None:
    oracle = build_scenario_oracle(
        db,
        ctx.tenant_id,
        card_detail=card_detail,
        customer_id=customer_id,
    )
    oracle["audit_events"] = snapshot_audit_counts(ctx.engine, ctx.tenant_id)
    result.oracle = oracle
    result.semantic_payload = {**result.semantic_payload, **oracle}
