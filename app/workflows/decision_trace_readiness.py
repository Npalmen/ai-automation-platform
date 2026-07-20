"""Startup/readiness checks for decision trace."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.core.settings import Settings, resolve_decision_record_enforce_writes


def _table_exists(engine: Engine, table_name: str) -> bool:
    if engine.dialect.name == "postgresql":
        with engine.connect() as conn:
            exists = conn.execute(
                text("SELECT to_regclass(:name)"),
                {"name": f"public.{table_name}"},
            ).scalar()
            return bool(exists)
    return inspect(engine).has_table(table_name)


def verify_decision_trace_readiness(engine: Engine, settings: Settings) -> None:
    if not resolve_decision_record_enforce_writes(settings):
        return

    if not _table_exists(engine, "decision_records"):
        raise RuntimeError(
            "DECISION_RECORD_ENFORCE_WRITES is active but decision_records table is missing. "
            "Apply migration 015_decision_records.sql before starting the application."
        )

    with engine.connect() as conn:
        conn.execute(text("SELECT 1 FROM decision_records LIMIT 0"))

