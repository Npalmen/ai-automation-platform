"""Migration 017/018 parity with runtime schema."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest


def test_migration_files_exist_and_are_split():
    root = Path(__file__).resolve().parents[3]
    runs = root / "migrations" / "017_live_eval_runs.sql"
    events = root / "migrations" / "018_live_eval_external_events.sql"
    assert runs.exists()
    assert events.exists()
    runs_sql = runs.read_text(encoding="utf-8")
    events_sql = events.read_text(encoding="utf-8")
    assert "live_eval_runs" in runs_sql
    assert "live_eval_external_events" not in runs_sql
    assert "operation_key" in events_sql
    assert "uq_live_eval_external_events_operation_succeeded" in events_sql


def test_runtime_schema_includes_both_migration_groups():
    from app.repositories.postgres.schema_migrations import (
        _LIVE_EVAL_EVENTS_MIGRATION_STATEMENTS,
        _LIVE_EVAL_RUNS_MIGRATION_STATEMENTS,
        ensure_runtime_schema,
    )

    engine = MagicMock()
    conn = MagicMock()
    engine.begin.return_value.__enter__ = MagicMock(return_value=conn)
    engine.begin.return_value.__exit__ = MagicMock(return_value=False)
    ensure_runtime_schema(engine)
    assert conn.execute.call_count >= (
        len(_LIVE_EVAL_RUNS_MIGRATION_STATEMENTS)
        + len(_LIVE_EVAL_EVENTS_MIGRATION_STATEMENTS)
    )
