"""Assertions for customer-domain stateful evaluation."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.domain.customer.enums import EntityOwnerType, FactState
from app.evaluation.customer_domain.guards import EVAL_TENANT_PREFIX
from app.repositories.postgres.end_customer_repository import EndCustomerRepository


def count_customers(db: Session, tenant_id: str) -> int:
    return int(
        db.execute(
            text("SELECT COUNT(*) FROM end_customers WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant_id},
        ).scalar()
        or 0
    )


def count_contacts(db: Session, tenant_id: str) -> int:
    return int(
        db.execute(
            text("SELECT COUNT(*) FROM end_customer_contacts WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant_id},
        ).scalar()
        or 0
    )


def assert_current_phone(
    card_detail: Any,
    expected: str,
) -> None:
    current_values = card_detail.current_state.current_values
    phone_values = [v for v in current_values if v.field_name == "phone"]
    if not phone_values:
        raise AssertionError("expected current phone value on card projection")
    if phone_values[0].display_value != expected:
        raise AssertionError(
            f"expected current phone {expected}, got {phone_values[0].display_value}"
        )


def assert_pending_phone(card_detail: Any, expected: str) -> None:
    pending = [
        p.display_value
        for p in card_detail.current_state.pending_values
        if p.field_name == "phone"
    ]
    if expected not in pending:
        raise AssertionError(f"expected pending phone {expected}, got {pending}")


def assert_no_automation_flags(assessment: Any) -> None:
    if assessment.automatic_link_allowed or assessment.automatic_merge_allowed:
        raise AssertionError("automatic link/merge must remain false")


def snapshot_db_counts(db: Session, tenant_id: str) -> dict[str, int]:
    tables = [
        "end_customers",
        "end_customer_contacts",
        "end_customer_source_facts",
        "end_customer_idempotency_records",
        "end_customer_timeline_events",
        "end_customer_thread_links",
        "end_customer_duplicate_candidates",
    ]
    counts: dict[str, int] = {}
    for table in tables:
        counts[table] = int(
            db.execute(
                text(f"SELECT COUNT(*) FROM {table} WHERE tenant_id = :tenant_id"),
                {"tenant_id": tenant_id},
            ).scalar()
            or 0
        )
    return counts


def snapshot_audit_counts(engine: Engine, tenant_id: str) -> int:
    with engine.connect() as conn:
        return int(
            conn.execute(
                text("SELECT COUNT(*) FROM audit_events WHERE tenant_id = :tenant_id"),
                {"tenant_id": tenant_id},
            ).scalar()
            or 0
        )


def find_fact_by_value(
    db: Session,
    tenant_id: str,
    subject_type: EntityOwnerType,
    subject_id: str,
    field_name: str,
    raw_value: str,
) -> str | None:
    facts = EndCustomerRepository.list_facts_for_subject(
        db, tenant_id, subject_type, subject_id
    )
    for fact in facts:
        if fact.field_name == field_name and fact.raw_value == raw_value:
            return fact.fact_id
    return None


def assert_historical_phone(card_detail: Any, fact_id: str) -> None:
    historical_ids = {h.fact_id for h in card_detail.current_state.historical_values}
    if fact_id not in historical_ids:
        raise AssertionError(f"expected historical fact {fact_id}")
