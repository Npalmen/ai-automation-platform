"""Apply versioned SQL migrations from migrations/ using deployment semantics."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

_MIGRATIONS_ROOT = Path(__file__).resolve().parents[3] / "migrations"


def migration_sql_path(filename: str) -> Path:
    path = _MIGRATIONS_ROOT / filename
    if not path.exists():
        raise FileNotFoundError(f"Migration file not found: {path}")
    return path


def apply_sql_migration_file(engine: Engine, filename: str) -> None:
    """Execute a migrations/*.sql file in a single transaction."""
    sql = migration_sql_path(filename).read_text(encoding="utf-8")
    with engine.begin() as conn:
        conn.execute(text(sql))


def table_exists(engine: Engine, table_name: str) -> bool:
    from sqlalchemy import inspect

    return table_name in inspect(engine).get_table_names()
