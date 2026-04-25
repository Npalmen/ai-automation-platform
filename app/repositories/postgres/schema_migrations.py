"""Runtime schema safeguard for columns that create_all cannot add to existing tables."""
import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)

# Each entry: (table, column, DDL_type)
# ADD COLUMN IF NOT EXISTS is idempotent — safe to run on every startup.
_REQUIRED_COLUMNS: list[tuple[str, str, str]] = [
    ("tenant_configs", "settings", "JSON"),
]


def ensure_runtime_schema(engine: Engine) -> None:
    """Add any columns that exist in ORM models but may be missing from older DB instances."""
    try:
        with engine.begin() as conn:
            for table, column, col_type in _REQUIRED_COLUMNS:
                conn.execute(
                    text(
                        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}"
                    )
                )
                log.debug("Schema check OK: %s.%s (%s)", table, column, col_type)
        log.info("Runtime schema safeguard complete (%d column(s) checked)", len(_REQUIRED_COLUMNS))
    except Exception as exc:
        log.error(
            "Runtime schema migration failed — server cannot start safely: %s", exc,
            exc_info=True,
        )
        raise RuntimeError(
            f"Runtime schema migration failed: {exc}. "
            "Fix the database schema before restarting."
        ) from exc
